"""Find and download free stock visuals (Pixabay; Pexels too if a key is ever added)."""
import hashlib
import json
import os
import random
import re
import time
import urllib.parse

import requests

from . import config

UA = {"User-Agent": "human-side-studio/1.0"}
SEARCH_TTL = 24 * 3600   # Pixabay asks that API responses be cached for 24 hours


def _cached_get(url, headers=None):
    key = hashlib.sha1(url.encode()).hexdigest()
    path = config.CACHE_DIR / "search" / f"{key}.json"
    if path.exists():
        saved = json.loads(path.read_text())
        if time.time() - saved["time"] < SEARCH_TTL:
            return saved["data"]
    for attempt in range(4):
        r = requests.get(url, headers={**UA, **(headers or {})}, timeout=30)
        if r.status_code == 429:
            time.sleep(15 * (attempt + 1))
            continue
        r.raise_for_status()
        break
    data = r.json()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"time": time.time(), "data": data}))
    return data


def _download(url, name):
    path = config.CACHE_DIR / "media" / name
    if path.exists() and path.stat().st_size > 10_000:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, headers=UA, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for block in r.iter_content(1 << 20):
                f.write(block)
    return path


def _quality(w, h):
    """How many source pixels we get per output pixel after cropping to 9:16 (1.0 = sharp)."""
    crop_w = min(w, h * config.WIDTH / config.HEIGHT)
    return crop_w / config.WIDTH


# ---------------------------------------------------------------- Pixabay
def _words(text):
    """Lower-case content words with a crude plural strip, for matching queries against tags."""
    stop = {"a", "an", "the", "in", "at", "on", "of", "to", "and", "with", "over", "for", "by", "from", "up"}
    return {re.sub(r"(?<=[a-z]{3})s$", "", w) for w in re.findall(r"[a-z]+", text.lower()) if w not in stop}


def _pixabay_photo_hits(params, key):
    q = urllib.parse.urlencode({"key": key, "image_type": "photo", "safesearch": "true", **params})
    out = []
    for rank, hit in enumerate(_cached_get(f"https://pixabay.com/api/?{q}").get("hits", [])):
        iw, ih = hit["imageWidth"], hit["imageHeight"]
        s = 1280 / max(iw, ih)          # largeImageURL is capped at 1280px
        w, h = round(iw * min(1, s)), round(ih * min(1, s))
        out.append({"ref": f"photo:{hit['id']}", "id": f"pixabay-photo-{hit['id']}", "kind": "photo",
                    "url": hit["largeImageURL"], "quality": _quality(w, h), "vertical": ih > iw,
                    "tags": _words(hit.get("tags", "")), "rank": rank,
                    "page": hit["pageURL"], "author": hit.get("user", "")})
    return out


def _pixabay_video_hits(params, key):
    q = urllib.parse.urlencode({"key": key, "video_type": "film", "safesearch": "true", **params})
    out = []
    for rank, hit in enumerate(_cached_get(f"https://pixabay.com/api/videos/?{q}").get("hits", [])):
        best = None
        for size in ("large", "medium"):
            v = hit["videos"].get(size) or {}
            if v.get("url") and v.get("width"):
                cand = {"ref": f"video:{hit['id']}", "id": f"pixabay-video-{hit['id']}-{size}", "kind": "video",
                        "url": v["url"], "quality": _quality(v["width"], v["height"]),
                        "vertical": v["height"] > v["width"], "duration": hit.get("duration", 0),
                        "tags": _words(hit.get("tags", "")), "rank": rank,
                        "page": hit["pageURL"], "author": hit.get("user", "")}
                if best is None or cand["quality"] > best["quality"]:
                    best = cand
        if best:
            out.append(best)
    return out


def _pixabay_photos(query, key):
    out = _pixabay_photo_hits({"q": query[:100], "orientation": "vertical", "per_page": 50}, key)
    if len(out) < 12:
        out += _pixabay_photo_hits({"q": query[:100], "per_page": 50}, key)
    return out


def _pixabay_videos(query, key):
    return _pixabay_video_hits({"q": query[:100], "per_page": 50}, key)


# ---------------------------------------------------------------- Pexels (optional)
def _slug_words(url):
    return _words(url.rstrip("/").rsplit("/", 1)[-1].replace("-", " "))


def _pexels_photos(query, key):
    q = urllib.parse.urlencode({"query": query, "orientation": "portrait", "per_page": 40})
    data = _cached_get(f"https://api.pexels.com/v1/search?{q}", {"Authorization": key})
    return [{"ref": f"pexels-photo:{p['id']}", "id": f"pexels-photo-{p['id']}", "kind": "photo",
             "url": p["src"]["large2x"], "quality": 1.2, "vertical": True, "rank": rank,
             "tags": _words(p.get("alt") or "") | _slug_words(p["url"]),
             "page": p["url"], "author": p.get("photographer", "")}
            for rank, p in enumerate(data.get("photos", []))]


def _pexels_videos(query, key):
    q = urllib.parse.urlencode({"query": query, "orientation": "portrait", "per_page": 30})
    data = _cached_get(f"https://api.pexels.com/videos/search?{q}", {"Authorization": key})
    out = []
    for rank, v in enumerate(data.get("videos", [])):
        files = [f for f in v.get("video_files", []) if f.get("width") and f.get("link")]
        if not files:
            continue
        f = min(files, key=lambda f: abs(f["height"] - config.HEIGHT))
        out.append({"ref": f"pexels-video:{v['id']}", "id": f"pexels-video-{v['id']}-{f['height']}",
                    "kind": "video", "url": f["link"], "quality": _quality(f["width"], f["height"]),
                    "vertical": f["height"] > f["width"], "duration": v.get("duration", 0), "rank": rank,
                    "tags": _slug_words(v["url"]), "page": v["url"],
                    "author": v.get("user", {}).get("name", "")})
    return out


# ---------------------------------------------------------------- selection
# Visuals that clash with the channel's reflective mood, unless the scene's query asks for them
MOOD_AVOID = {"happy", "smile", "smiling", "laugh", "laughing", "fun", "funny", "joy", "joyful", "party",
              "celebration", "christmas", "cheerful", "excited", "kid", "child", "childhood", "toy",
              "playing", "play", "snow", "winter", "beach", "bikini", "food", "cartoon", "illustration",
              "children", "baby", "toddler", "infant", "schoolgirl", "schoolboy",           # no children on this channel
              "animal", "bird", "dog", "cat", "pet", "wildlife", "zoo", "insect",
              "beggar", "begging", "homeles", "poverty", "charity",           # never exploit real hardship
              "chroma", "greenbox", "greenscreen", "studio", "equipment", "render", "3d"}


def _keys():
    pixabay = os.environ.get("PIXABAY_API_KEY", "").strip()
    pexels = os.environ.get("PEXELS_API_KEY", "").strip()
    if not pixabay and not pexels:
        raise SystemExit("No stock-media key found. Add PIXABAY_API_KEY as a GitHub Actions secret "
                         "(repo Settings > Secrets and variables > Actions).")
    return pixabay, pexels


def _guard(fn, *args):
    try:
        return fn(*args)
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code in (400, 401, 403):
            raise SystemExit(f"The stock-media API rejected the request ({e.response.status_code}). "
                             "Check the PIXABAY_API_KEY secret.")
        raise


def _candidates(query, kind):
    pixabay, pexels = _keys()
    found = []
    if pexels:
        found += _guard(_pexels_photos if kind == "photo" else _pexels_videos, query, pexels)
    if pixabay:
        found += _guard(_pixabay_photos if kind == "photo" else _pixabay_videos, query, pixabay)
    return found


def _pinned(ref):
    """A scene can force one exact Pixabay item, e.g. "pin": "photo:2072907" or "video:22761"."""
    pixabay, _ = _keys()
    kind, _, pid = ref.partition(":")
    hits = _guard(_pixabay_photo_hits if kind == "photo" else _pixabay_video_hits, {"id": pid}, pixabay)
    if not hits:
        raise SystemExit(f"Pinned item {ref} was not found on Pixabay.")
    return hits[0]


def _score(c, want_words, avoid, want_kind):
    match = len(want_words & c["tags"]) / max(1, len(want_words))
    s = 3.0 * match - 0.02 * c["rank"] + 0.8 * min(c["quality"], 1.2)
    if c["tags"] & avoid:
        s -= 5
    if c["kind"] == "video" and not c["vertical"]:
        s -= 0.6                     # landscape clips get centre-cropped, which can lose the subject
    if c["kind"] == want_kind:
        s += 0.7
    return s


def pick(scene, index, seed, used, need_seconds):
    """Return {'path', 'kind', 'credit'} for a scene: the most on-topic, on-mood visual not used yet."""
    if scene.get("pin"):
        choice = _pinned(scene["pin"])
    else:
        want_kind = scene.get("visual", "photo")
        queries = [scene["query"]] + scene.get("fallback_queries", [])
        want_words = set().union(*(_words(q) for q in queries[:1]))
        allow = _words(" ".join(scene.get("allow", [])))
        avoid = (MOOD_AVOID - want_words - allow) | _words(" ".join(scene.get("avoid", [])))
        excluded = set(scene.get("exclude", []))
        pool, seen = [], set()
        for kind in (want_kind, "photo" if want_kind == "video" else "video"):
            for query in queries:
                for c in _candidates(query, kind):
                    if c["id"] in used or c["ref"] in excluded or c["ref"] in seen:
                        continue
                    if kind == "video" and c.get("duration", 0) < min(need_seconds, 6):
                        continue
                    if c["quality"] < (0.9 if kind == "video" else 0.6):
                        continue
                    seen.add(c["ref"])
                    c["score"] = _score(c, want_words | _words(query), avoid, want_kind)
                    pool.append(c)
            if pool and max(c["score"] for c in pool) >= 3.0:
                break                # good on-topic match in the preferred kind; no need to look further
        if not pool:
            raise SystemExit(f"No usable visual found for scene {index + 1}: '{scene['query']}'. "
                             "Try a simpler search phrase or add fallback_queries.")
        pool.sort(key=lambda c: c["score"], reverse=True)
        top = [c for c in pool[:3] if c["score"] >= pool[0]["score"] - 0.5]
        choice = random.Random(f"{seed}-{index}").choice(top)
    used.add(choice["id"])
    ext = ".mp4" if choice["kind"] == "video" else ".jpg"
    path = _download(choice["url"], choice["id"] + ext)
    print(f"    picked {choice['ref']} tags={sorted(choice['tags'])[:8]} score={choice.get('score', 'pin')}",
          flush=True)
    return {"path": path, "kind": choice["kind"], "credit": choice}


# ---------------------------------------------------------------- offline preview
def placeholder(scene, index, workdir):
    """Moody gradient stand-in used when rendering without internet access."""
    import numpy as np
    import cv2

    w, h = 1440, 2560
    rng = np.random.default_rng(index + 7)
    y = np.linspace(0, 1, h)[:, None]
    top = np.array([40, 28, 18]) * (0.8 + 0.4 * rng.random())       # BGR deep navy
    bottom = np.array([20, 90, 200]) * (0.7 + 0.3 * rng.random())   # BGR warm orange
    img = (top * (1 - y) + bottom * y)[:, None, :].repeat(w, axis=1)
    img = img.reshape(h, w, 3).astype(np.float32)
    glow = np.zeros((h, w), np.float32)
    for _ in range(26):
        cx, cy, r = rng.integers(0, w), rng.integers(int(h * 0.3), h), rng.integers(30, 140)
        cv2.circle(glow, (int(cx), int(cy)), int(r), float(rng.uniform(0.15, 0.6)), -1)
    glow = cv2.GaussianBlur(glow, (0, 0), 25)
    img += glow[..., None] * np.array([120, 200, 255], np.float32)
    img = np.clip(img, 0, 255).astype(np.uint8)
    cv2.putText(img, f"[{scene.get('visual', 'photo')}] {scene['query']}", (60, 140),
                cv2.FONT_HERSHEY_SIMPLEX, 1.4, (230, 230, 230), 3, cv2.LINE_AA)
    path = workdir / f"placeholder-{index:02d}.jpg"
    cv2.imwrite(str(path), img)
    return {"path": path, "kind": "photo", "credit": None}
