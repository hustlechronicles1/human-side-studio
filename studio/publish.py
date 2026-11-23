"""Render every episode that doesn't have a GitHub Release yet, and publish each as a Release.

Each Release holds the finished .mp4 and an upload sheet (title, description, tags) to copy into YouTube.
Usage:  python -m studio.publish                 # all new episodes
        python -m studio.publish episodes/x.json # (re)render one episode
"""
import json
import subprocess
import sys

from . import config, make_video


def release_exists(tag):
    return subprocess.run(["gh", "release", "view", tag], capture_output=True).returncode == 0


def publish(path, force=False):
    ep = json.loads(open(path, encoding="utf-8").read())
    tag = ep["id"]
    if release_exists(tag):
        if not force:
            print(f"skip {tag}: already rendered")
            return False
        subprocess.run(["gh", "release", "delete", tag, "--yes", "--cleanup-tag"], check=True)
    video = make_video.make(path)
    sheet = config.OUT_DIR / f"{tag}-upload.md"
    subprocess.run(["gh", "release", "create", tag, str(video), "--title", ep["title"],
                    "--notes-file", str(sheet)], check=True)
    return True


def main(args):
    if args and args[0].strip():
        publish(args[0].strip(), force=True)
        return
    done = 0
    for path in sorted(config.EPISODES_DIR.glob("*.json")):
        done += publish(path)
    print(f"Rendered {done} new episode(s).")


if __name__ == "__main__":
    main(sys.argv[1:])
