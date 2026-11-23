"""The editing: Ken Burns motion on photos, cropped stock clips, transitions, grade, captions, audio mix."""
import json
import math
import subprocess

import cv2
import numpy as np

from . import config

W, H, FPS = config.WIDTH, config.HEIGHT, config.FPS


def run(cmd, **kw):
    result = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(map(str, cmd))[:300]}\n{result.stderr[-2500:]}")
    return result


def probe_duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)])
    return float(json.loads(out.stdout)["format"]["duration"])


def _ease(t):
    return 0.5 - 0.5 * math.cos(math.pi * max(0.0, min(1.0, t)))


def _encoder(out_path):
    return subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "15",
         "-pix_fmt", "yuv420p", str(out_path)],
        stdin=subprocess.PIPE)


def photo_clip(src, seconds, motion, out_path):
    """Smooth sub-pixel zoom / pan over a still photo (no jitter, unlike ffmpeg zoompan)."""
    img = cv2.imread(str(src), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"Could not read image {src}")
    ih, iw = img.shape[:2]
    s0 = max(W / iw, H / ih)                       # scale that just covers the frame
    if s0 < 0.6:                                   # very large source: shrink first to avoid aliasing
        f = s0 / 0.6
        img = cv2.resize(img, (round(iw * f), round(ih * f)), interpolation=cv2.INTER_AREA)
        ih, iw = img.shape[:2]
        s0 = max(W / iw, H / ih)

    n = max(2, round(seconds * FPS))
    enc = _encoder(out_path)
    for i in range(n):
        t = _ease(i / (n - 1))
        if motion == "zoom_out":
            z = 1.16 - 0.16 * t
        elif motion in ("pan_left", "pan_right", "pan_up", "pan_down"):
            z = 1.12 + 0.03 * t
        else:                                      # zoom_in (default)
            z = 1.0 + 0.16 * t
        scale = s0 * z
        hw, hh = W / (2 * scale), H / (2 * scale)  # half the visible window, in image pixels
        cx, cy = iw / 2, ih / 2
        span_x, span_y = iw / 2 - hw, ih / 2 - hh  # room to move each way
        if motion == "pan_right":
            cx = iw / 2 + span_x * 0.85 * (2 * t - 1)
        elif motion == "pan_left":
            cx = iw / 2 - span_x * 0.85 * (2 * t - 1)
        elif motion == "pan_up":
            cy = ih / 2 - span_y * 0.85 * (2 * t - 1)
        elif motion == "pan_down":
            cy = ih / 2 + span_y * 0.85 * (2 * t - 1)
        a = 1 / scale
        m = np.array([[a, 0, cx - a * W / 2], [0, a, cy - a * H / 2]], dtype=np.float64)
        frame = cv2.warpAffine(img, m, (W, H),
                               flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REFLECT)
        enc.stdin.write(frame.tobytes())
    enc.stdin.close()
    if enc.wait() != 0:
        raise RuntimeError("Encoding photo clip failed")


def video_clip(src, seconds, out_path, speed=1.0):
    """Crop a stock clip to 9:16, loop it if it's too short, optionally slow it down a little."""
    dur = probe_duration(src)
    start = 0.4 if dur > seconds * speed + 1.0 else 0.0
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},"
          f"setpts={1 / speed:.4f}*PTS,fps={FPS},setsar=1")
    run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start}", "-stream_loop", "-1", "-i", str(src),
         "-t", f"{seconds:.3f}", "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "15",
         "-pix_fmt", "yuv420p", str(out_path)])


def timeline(durations):
    """Start time and length of every clip so each transition lands just before the next sentence."""
    T = config.TRANSITION
    starts, s = [], 0.0
    for d in durations:
        starts.append(s)
        s += d
    total = s + config.END_TAIL
    shift = min(T / 2, config.SCENE_PAUSE)
    v = [0.0] + [st - shift for st in starts[1:]]
    lengths = []
    for k in range(len(durations)):
        end = v[k + 1] + T if k + 1 < len(durations) else total
        lengths.append(end - v[k])
    return starts, v, lengths, total


def assemble(clips, transitions, offsets, total, narration, music, ass_path, out_path, workdir):
    T = config.TRANSITION
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for c in clips:
        cmd += ["-i", str(c)]
    cmd += ["-i", str(narration)]
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(music)]

    parts = [f"[{i}:v]settb=AVTB,fps={FPS},format=yuv420p[c{i}]" for i in range(len(clips))]
    last = "c0"
    for k in range(1, len(clips)):
        parts.append(f"[{last}][c{k}]xfade=transition={transitions[k]}:duration={T}:offset={offsets[k]:.3f}[x{k}]")
        last = f"x{k}"
    # Consistent moody grade: gentle contrast, slightly muted colour, warm highlights / cool shadows
    parts.append(
        f"[{last}]eq=contrast=1.06:saturation=0.86:brightness=-0.01,"
        "colorbalance=rs=-0.02:bs=0.04:rh=0.04:bh=-0.04,vignette=angle=PI/5,unsharp=5:5:0.35,"
        f"subtitles={ass_path.name}:fontsdir={config.FONTS_DIR},format=yuv420p[v]")

    n = len(clips)
    parts.append(f"[{n}:a]loudnorm=I=-15:TP=-1.5:LRA=11,aresample=48000[nar]")
    if music:
        fade_at = max(0.0, total - 2.5)
        parts.append(f"[{n + 1}:a]aresample=48000,volume={config.MUSIC_VOLUME},afade=t=in:d=1.5,"
                     f"afade=t=out:st={fade_at:.2f}:d=2.5[mus]")
        parts.append("[nar][mus]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]")
    else:
        parts.append("[nar]anull[a]")

    cmd += ["-filter_complex", ";".join(parts), "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-profile:v", "high", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out_path)]
    run(cmd, cwd=workdir)
