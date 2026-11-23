"""Turn one episode script (JSON) into a finished Short plus an upload sheet.

Usage:  python -m studio.make_video episodes/001-example.json [--offline]
"""
import argparse
import json
import random
import shutil

from . import ambient, captions, config, edit, media, thumbnail, voice

REQUIRED = ("id", "title", "description", "scenes")


def load(path):
    ep = json.loads(open(path, encoding="utf-8").read())
    missing = [k for k in REQUIRED if k not in ep]
    if missing:
        raise SystemExit(f"{path}: missing {', '.join(missing)}")
    for i, s in enumerate(ep["scenes"]):
        if not s.get("text") or not s.get("query"):
            raise SystemExit(f"{path}: scene {i + 1} needs both 'text' and 'query'")
    return ep


def pick_music(ep, seconds, workdir):
    if ep.get("music") == "none":
        return None
    tracks = sorted(p for p in config.MUSIC_DIR.glob("*") if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg"))
    if ep.get("music") and (config.MUSIC_DIR / ep["music"]).exists():
        return config.MUSIC_DIR / ep["music"]
    if tracks:
        return random.Random(ep["id"]).choice(tracks)
    return ambient.make(seconds + 1, workdir / "ambient.wav")


def upload_sheet(ep, credits, path, seconds):
    tags = ep.get("tags", [])
    hashtags = " ".join("#" + t.replace(" ", "") for t in ep.get("hashtags", ["shorts", "psychology"]))
    people = sorted({c["author"] for c in credits if c and c.get("author")})
    credit_line = "Visuals: Pixabay / Pexels" + (f" ({', '.join(people[:6])})" if people else "")
    text = (
        f"# {ep['title']}\n\n"
        f"Length: {seconds:.0f}s\n\n"
        "## Title\n```\n" + ep["title"] + "\n```\n\n"
        "## Description\n```\n" + ep["description"].strip() + f"\n\n{hashtags}\n\n{credit_line}\n```\n\n"
        "## Tags\n```\n" + ", ".join(tags) + "\n```\n\n"
        "## Visuals used (scene: ref, link)\n"
        + "\n".join(f"- scene {i + 1}: `{c.get('ref', '')}` {c['page']}" for i, c in enumerate(credits) if c) + "\n"
    )
    path.write_text(text, encoding="utf-8")


def make(path, offline=False):
    ep = load(path)
    vid = ep["id"]
    workdir = config.OUT_DIR / "work" / vid
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)
    scenes = ep["scenes"]
    print(f"== {vid}: {ep['title']} ({len(scenes)} scenes)", flush=True)

    narration, durations, speech = voice.narrate(
        scenes, ep.get("voice", config.DEFAULT_VOICE), ep.get("speed", config.DEFAULT_SPEED), workdir)
    starts, offsets, lengths, total = edit.timeline(durations)

    used, credits, clips, transitions, visuals = set(), [], [], [], []
    for i, scene in enumerate(scenes):
        need = lengths[i]
        vis = media.placeholder(scene, i, workdir) if offline else media.pick(scene, i, vid, used, need)
        credits.append(vis["credit"])
        visuals.append(vis)
        clip = workdir / f"clip-{i:02d}.mp4"
        if vis["kind"] == "video":
            edit.video_clip(vis["path"], need, clip, speed=scene.get("speed", 0.9))
        else:
            motion = scene.get("motion") or config.MOTIONS[i % len(config.MOTIONS)]
            edit.photo_clip(vis["path"], need, motion, clip)
        clips.append(clip)
        transitions.append(scene.get("transition") or config.TRANSITIONS[i % len(config.TRANSITIONS)])
        print(f"  scene {i + 1}/{len(scenes)}: {vis['kind']} {need:.2f}s", flush=True)

    ass = captions.build(scenes, starts, speech, ep.get("header", ""), workdir / "captions.ass")
    music = pick_music(ep, total, workdir)
    config.OUT_DIR.mkdir(exist_ok=True)
    out = config.OUT_DIR / f"{vid}.mp4"
    edit.assemble(clips, transitions, offsets, total, narration, music, ass, out, workdir)
    upload_sheet(ep, credits, config.OUT_DIR / f"{vid}-upload.md", total)
    if not offline:
        thumbnail.for_episode(ep, workdir, visuals)
    print(f"Done: {out} ({total:.1f}s)", flush=True)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("--offline", action="store_true", help="placeholder visuals, no stock-media API")
    args = ap.parse_args()
    make(args.episode, offline=args.offline)
