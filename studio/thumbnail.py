"""Eye-catching vertical thumbnail (1080x1920) built from a clean, caption-free scene visual.

Episode JSON:
  "thumbnail": {"scene": 2, "at": 0.5, "tag": "2:00 AM", "lines": ["STILL", "*REPLAYING*", "IT?"]}
  scene = 1-based scene number, at = position inside a video clip (0-1), *word* = brand gold.
"""
import json
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from . import config, media

W, H = config.WIDTH, config.HEIGHT
GOLD = tuple(int(config.BRAND_GOLD[i:i + 2], 16) for i in (0, 2, 4))
WHITE = (255, 255, 255)


def _font(name, size):
    return ImageFont.truetype(str(config.FONTS_DIR / f"Montserrat-{name}.ttf"), size)


def _cover(img, zoom=1.08, focus_y=0.42):
    """Crop/scale to fill 9:16, zoomed slightly toward the upper-middle where faces usually are."""
    iw, ih = img.size
    s = max(W / iw, H / ih) * zoom
    img = img.resize((round(iw * s), round(ih * s)), Image.LANCZOS)
    iw, ih = img.size
    left = (iw - W) // 2
    top = int(min(max(0, ih * focus_y - H * focus_y), ih - H))
    return img.crop((left, top, left + W, top + H))


def _frame_from_video(path, at, workdir):
    dur = float(json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True).stdout)["format"]["duration"])
    out = workdir / "thumb-src.png"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{dur * at:.2f}", "-i", str(path),
                    "-frames:v", "1", str(out)], check=True)
    return Image.open(out).convert("RGB")


def _fit(text, name, max_size, max_width):
    size = max_size
    while size > 40:
        f = _font(name, size)
        if f.getlength(text) <= max_width:
            return f
        size -= 4
    return _font(name, size)


def compose(source, kind, spec, out_path, workdir):
    img = _frame_from_video(source, spec.get("at", 0.5), workdir) if kind == "video" else Image.open(source).convert("RGB")
    img = _cover(img)
    img = ImageEnhance.Contrast(img).enhance(1.12)
    img = ImageEnhance.Color(img).enhance(0.85)

    # Vignette + bottom shade so the words pop on any background
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.sqrt(((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H * 0.4) / (H * 0.75)) ** 2)
    vignette = np.clip(1.0 - 0.55 * r ** 2, 0.35, 1.0)
    shade = np.clip((yy - H * 0.42) / (H * 0.40), 0, 1) ** 1.3 * 0.88
    top = np.clip(1 - yy / (H * 0.12), 0, 1) * 0.35
    factor = vignette * (1 - shade) * (1 - top)
    arr = (np.asarray(img, np.float32) * factor[..., None]).clip(0, 255).astype(np.uint8)
    img = Image.fromarray(arr)

    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    lines = spec.get("lines", ["WATCH", "*THIS*"])
    max_w = W - 110
    fonts = []
    for i, line in enumerate(lines):
        gold = line.startswith("*") and line.endswith("*")
        text = line.strip("*")
        big = 250 if gold else 150
        fonts.append((text, _fit(text, "Black", big, max_w), gold))
    heights = [f.getbbox(t)[3] - f.getbbox(t)[1] for t, f, _ in fonts]
    gap = 26
    total = sum(heights) + gap * (len(fonts) - 1)
    y = int(H * 0.73 - total / 2)

    tag = spec.get("tag")
    if tag:
        tf = _font("ExtraBold", 54)
        tw = tf.getlength(tag)
        bx0, by1 = (W - tw) / 2 - 38, y - 48
        by0 = by1 - 96
        d.rounded_rectangle([bx0, by0, W - bx0, by1], radius=48, fill=(0, 0, 0, 150), outline=GOLD + (255,), width=5)
        d.text((W / 2, (by0 + by1) / 2), tag, font=tf, fill=GOLD + (255,), anchor="mm")

    for (text, f, gold), h in zip(fonts, heights):
        top_off = f.getbbox(text)[1]
        # soft drop shadow
        shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).text((W / 2 + 8, y - top_off + 12), text, font=f, fill=(0, 0, 0, 200), anchor="ma")
        layer = Image.alpha_composite(layer, shadow.filter(ImageFilter.GaussianBlur(10)))
        d = ImageDraw.Draw(layer)
        d.text((W / 2, y - top_off), text, font=f, fill=(GOLD if gold else WHITE) + (255,), anchor="ma",
               stroke_width=10 if gold else 8, stroke_fill=(0, 0, 0, 255))
        y += h + gap

    brand_font = _font("ExtraBold", 38)
    brand = "T H E   H U M A N   S I D E"
    d.text((W / 2, H - 150), brand, font=brand_font, fill=GOLD + (230,), anchor="mm")
    d.line([(W / 2 - 60, H - 112), (W / 2 + 60, H - 112)], fill=GOLD + (200,), width=4)

    out = Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")
    out.save(out_path, "JPEG", quality=90, optimize=True, progressive=True)
    return out_path


def for_episode(ep, workdir, visuals=None):
    """Build the thumbnail; reuses visuals already picked during a render, else picks the scene again."""
    spec = ep.get("thumbnail")
    if not spec:
        return None
    idx = max(0, int(spec.get("scene", 1)) - 1)
    if visuals:
        vis = visuals[idx]
    else:
        vis = media.pick(ep["scenes"][idx], idx, ep["id"], set(), 30)
    out = config.OUT_DIR / f"{ep['id']}-thumbnail.jpg"
    config.OUT_DIR.mkdir(exist_ok=True)
    workdir.mkdir(parents=True, exist_ok=True)
    return compose(vis["path"], vis["kind"], spec, out, workdir)
