# The Human Side: video studio

Turns a short script into a finished YouTube Short, for free:

1. **Script**: one JSON file per video in `episodes/` (written by Claude).
2. **Voice**: [Kokoro](https://github.com/thewh1teagle/kokoro-onnx), an open-weight voice model that runs on the free GitHub runner.
3. **Visuals**: free stock photos and clips from Pixabay (Pexels too, if a key is ever added).
4. **Editing**: slow zoom / pan on photos, cropped stock clips, calm transitions, a consistent moody colour grade,
   word-by-word captions with the active word in gold, background music.
5. **Delivery**: each finished video appears under **Releases** (right side of the repo page) with an upload sheet:
   title, description and tags ready to copy into YouTube.

## Everyday use

- Add a new episode file to `episodes/` and commit it. The **Render videos** workflow starts on its own
  (Actions tab) and takes a few minutes.
- Open **Releases**, download the `.mp4`, upload it in YouTube Studio or the YouTube app, and paste the title,
  description and tags from the release notes.
- To re-render one video: Actions > Render videos > Run workflow, and enter the episode path.

## One-time setup

- Secret `PIXABAY_API_KEY` (Settings > Secrets and variables > Actions). Never put the key in a file here: this repo is public.
- Optional: calm music tracks in `music/` (see the note there).

## Episode format

```json
{
  "id": "002-short-name",
  "title": "Title shown on YouTube",
  "header": "Line shown at the top of the video",
  "description": "YouTube description",
  "tags": ["tag one", "tag two"],
  "hashtags": ["shorts", "psychology"],
  "voice": "af_heart",
  "speed": 0.88,
  "scenes": [
    {"text": "One or two spoken sentences.", "query": "stock search words", "visual": "photo", "motion": "zoom_in"},
    {"text": "Next line.", "query": "rain on window night", "visual": "video"}
  ]
}
```

- `visual`: `photo` (animated with `motion`) or `video` (stock clip).
- `motion`: `zoom_in`, `zoom_out`, `pan_left`, `pan_right`, `pan_up`, `pan_down`.
- `transition` (optional): any FFmpeg xfade name, e.g. `fade`, `fadeblack`, `smoothleft`, `slideup`.
- `voice`: e.g. `af_heart`, `af_bella`, `bf_emma` (female), `am_michael`, `am_fenrir`, `bm_george` (male).
- `music` (optional): a file name from `music/`, or `"none"`.
- `thumbnail` (optional): `{"scene": 2, "at": 0.5, "tag": "2:00 AM", "lines": ["STILL", "*REPLAYING*", "IT?"]}`
  builds a 1080x1920 JPG from that scene's clean visual (`*word*` = gold). It's attached to the release.
- `hook` (optional): `{"lines": ["STILL", "*CHECKING?*"]}` shows huge text for the opening seconds (until the first line ends).
- `pace` (optional): `{"pause": 0.15, "transition": 0.35, "tail": 0.3}` for a faster cut (defaults are slower).
- `loop` (optional): `true` keeps the end short and the music fades quick, so the Short replays smoothly.
- `pinned_comment`, `source` (optional): added to the upload sheet / description.
- `allow` (optional, per scene): words like `"happy"` that the mood filter would otherwise skip.
- `pin` / `exclude` (optional, per scene): lock or ban a specific stock item, e.g. `"pin": "photo:7346682"`.
  The upload sheet lists the ref of every visual used.

## Run locally (optional)

```bash
pip install -r requirements.txt   # needs ffmpeg installed
python -m studio.make_video episodes/001-replaying-conversations.json --offline   # placeholder visuals
```
