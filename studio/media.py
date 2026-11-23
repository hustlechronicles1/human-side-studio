"""Find and download free stock visuals (Pixabay; Pexels too if a key is ever added)."""
import hashlib
import json
import os
import random
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
def _pixabay_photos(query, key):
    out = []
    for orientation in ("vertical", "all"):
        q = urllib.parse.urlencode({"key": key, "q": query[:100], "image_type": "photo",
                                    "orientation": orientation, "safesearch": "true", "per_page": 40})
        for hit in _cached_get(f"https://pixabay.com/api/?{q}").get("hits", []):
            iw, ih = hit["imageWidth"], hit["imageHeight"]
            s = 1280 / max(iw, ih)          # largeImageURL is capped at 1280px
            w, h = round(iw * min(1, s)), round(ih * min(1, s))
            out.append({"id": f"pixabay-photo-{hit['id']}", "kind": "photo", "url": hit["largeImageURL"],
                        "quality": _quality(w, h), "page": hit["pageURL"], "author": hit.get("user", "")})
        if len([c for c in out if c["quality"] >= 0.6]) >= 6:
            break
    return out


def _pixabay_videos(query, key):
    q = urllib.parse.urlencode({"key": key, "q": query[:100], "video_type": "film",
                                "safesearch": "true", "per_page": 40})
    out = []
    for hit in _cached_get(f"https://pixabay.com/api/videos/?{q}").get("hits", []):
        best = None
        for size in ("large", "medium"):
            v = hit["videos"].get(size) or {}
            if v.get("url") and v.get("width"):
                cand = {"id": f"pixabay-video-{hit['id']}-{size}", "kind": "video", "url": v["url"],
                        "quality": _quality(v["width"], v["height"]), "duration": hit.get("duration", 0),
                        "page": hit["pageURL"], "author": hit.get("user", "")}
                if best is None or cand["quality"] > best["quality"]:
                    best = cand
        if best:
            out.append(best)
    return out


# ---------------------------------------------------------------- Pexels (optional)
def _pexels_photos(query, key):
    q = urllib.parse.urlencode({"query": query, "orientation": "portrait", "per_page": 40})
    data = _cached_get(f"https://api.pexels.com/v1/search?{q}", {"Authorization": key})
    return [{"id": f"pexels-photo-{p['id']}", "kind": "photo", "url": p["src"]["large2x"],
             "quality": 1.2, "page": p["url"], "author": p.get("photographer", "")}
            for p in data.get("photos", [])]


def _pexels_videos(query, key):
    q = urllib.parse.urlencode({"query": query, "orientation": "portrait", "per_page": 30})
    data = _cached_get(f"https://api.pexels.com/videos/search?{q}", {"Authorization": key})
    out = []
    for v in data.get("videos", []):
        files = [f for f in v.get("video_files", []) if f.get("width") and f.get("link")]
        if not files:
            continue
        f = min(files, key=lambda f: abs(f["height"] - config.HEIGHT))
        out.append({"id": f"pexels-video-{v['id']}-{f['height']}", "kind": "video", "url": f["link"],
                    "quality": _quality(f["width"], f["height"]), "duration": v.get("duration", 0),
                    "page": v["url"], "author": v.get("user", {}).get("name", "")})
    return out


# ---------------------------------------------------------------- selection
def _candidates(query, kind):
    pixabay = os.environ.get("PIXABAY_API_KEY", "").strip()
    pexels = os.environ.get("PEXELS_API_KEY", "").strip()
    if not pixabay and not pexels:
        raise SystemExit("No stock-media key found. Add PIXABAY_API_KEY as a GitHub Actions secret "
                         "(repo Settings > Secrets and variables > Actions).")
    found = []
    try:
        if pexels:
            found += _pexels_photos(query, pexels) if kind == "photo" else _pexels_videos(query, pexels)
        if pixabay:
            found += _pixabay_photos(query, pixabay) if kind == "photo" else _pixabay_videos(query, pixabay)
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code in (400, 401, 403):
            raise SystemExit(f"The stock-media API rejected the key ({e.response.status_code}). "
                             "Check the PIXABAY_API_KEY secret.")
        raise
    return found


def pick(scene, index, seed, used, need_seconds):
    """Return {'path', 'kind', 'credit'} for a scene, avoiding visuals already used in this video."""
    want = scene.get("visual", "photo")
    order = ["video", "photo"] if want == "video" else ["photo", "video"]
    queries = [scene["query"]] + scene.get("fallback_queries", [])
    words = scene["query"].split()
    if len(words) > 2:
        queries.append(" ".join(words[:2]))
    rng = random.Random(f"{seed}-{index}")
    for kind in order:
        for query in queries:
            pool = [c for c in _candidates(query, kind) if c["id"] not in used]
            if kind == "video":
                pool = [c for c in pool if c.get("duration", 0) >= min(need_seconds, 6)]
            good = [c for c in pool if c["quality"] >= (0.9 if kind == "video" else 0.6)]
            pool = good or [c for c in pool if c["quality"] >= 0.45]
            if not pool:
                continue
            choice = rng.choice(pool[:8])
            used.add(choice["id"])
            ext = ".mp4" if kind == "video" else ".jpg"
            path = _download(choice["url"], choice["id"] + ext)
            return {"path": path, "kind": kind, "credit": choice}
    raise SystemExit(f"No usable visual found for scene {index + 1}: '{scene['query']}'. "
                     "Try a simpler search phrase.")


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
