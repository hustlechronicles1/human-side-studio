"""Word-by-word captions (ASS subtitles) with the active word highlighted in brand gold."""
import math
import re

from . import config

BREAK_AFTER = re.compile(r"[.,!?;:—-]$")
CAPTION_SIZE = 84
MAX_LINE_PX = 880          # frame is 1080 wide; keep each caption on a single line


def _ass_time(t):
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _clean(text):
    return text.replace("{", "(").replace("}", ")").replace("\\", "/").replace("\n", " ")


def _weight(word):
    core = re.sub(r"[^a-zA-Z0-9']", "", word)
    if core.isdigit():
        syl = len(core) + 1
    else:
        syl = max(1, len(re.findall(r"[aeiouy]+", core.lower())))
    if word.endswith((".", "!", "?")):
        syl += 1.6
    elif word.endswith((",", ";", ":", "—")):
        syl += 1.0
    return syl


_font = None


def _width(text):
    global _font
    if _font is None:
        from PIL import ImageFont
        _font = ImageFont.truetype(str(config.FONTS_DIR / "Montserrat-ExtraBold.ttf"), CAPTION_SIZE)
    return _font.getlength(text)


def _chunks(words, max_words=4):
    """Split at punctuation, then pick the most natural on-screen groups (fits one line, no orphans)."""
    phrases, cur = [], []
    for w in words:
        cur.append(w)
        if BREAK_AFTER.search(w):
            phrases.append(cur)
            cur = []
    if cur:
        phrases.append(cur)
    out = []
    for p in phrases:
        n = len(p)
        best = [0.0] + [math.inf] * n          # best[i]: cheapest way to show the first i words
        back = [0] * (n + 1)
        for i in range(1, n + 1):
            for j in range(max(0, i - max_words), i):
                group = " ".join(p[j:i])
                width = _width(group)
                if width > MAX_LINE_PX and i - j > 1:
                    continue
                cost = ((width - 0.62 * MAX_LINE_PX) / 100) ** 2   # aim for ~half-width lines
                if i - j == 1 and n > 1:
                    cost += 9                                       # avoid a word alone on screen
                if best[j] + cost < best[i]:
                    best[i], back[i] = best[j] + cost, j
        groups, i = [], n
        while i > 0:
            groups.append(p[back[i]:i])
            i = back[i]
        out.extend(reversed(groups))
    return out


_black = {}


def _hook_size(text, max_size, max_px=940):
    """Largest ASS font size whose rendered width fits. ASS size ~ 1.2x the font's em size."""
    from PIL import ImageFont
    size = max_size
    while size > 60:
        em = round(size / 1.2)
        if em not in _black:
            _black[em] = ImageFont.truetype(str(config.FONTS_DIR / "Montserrat-Black.ttf"), em)
        if _black[em].getlength(text) <= max_px:
            return size
        size -= 6
    return size


def _hook_events(hook, until, gold_ass):
    """Huge two/three-line hook in the upper third for the first seconds (*word* = gold)."""
    out, y = [], int(hook.get("y", 300))
    rows = []
    for raw in hook["lines"]:
        gold = raw.startswith("*") and raw.endswith("*")
        text = _clean(raw.strip("*"))
        rows.append((text, gold, _hook_size(text, 190 if gold else 135)))
    height = sum(int(sz * 0.98) for _, _, sz in rows)
    # soft dark wash behind the words so they read on any background
    top, bottom = max(0, y - 70), y + height + 70
    out.append(f"Dialogue: 2,{_ass_time(0)},{_ass_time(until)},Cap,,0,0,0,,"
               f"{{\\an7\\pos(0,0)\\p1\\bord0\\shad0\\c&H000000&\\1a&H78&\\blur40\\fad(0,250)}}"
               f"m 0 {top} l {config.WIDTH} {top} {config.WIDTH} {bottom} 0 {bottom}{{\\p0}}")
    for text, gold, size in rows:
        colour = gold_ass if gold else "&H00FFFFFF&"
        out.append(f"Dialogue: 3,{_ass_time(0)},{_ass_time(until)},Cap,,0,0,0,,"
                   f"{{\\an8\\pos({config.WIDTH // 2},{y})\\fnMontserrat Black\\fs{size}\\c{colour}"
                   f"\\bord9\\shad4\\fad(0,250)\\fscx108\\fscy108\\t(0,160,\\fscx100\\fscy100)}}{text}")
        y += int(size * 0.98)
    return out


def build(scenes, starts, speech, header, path, hook=None):
    gold = config.BRAND_GOLD
    gold_ass = f"&H00{gold[4:6]}{gold[2:4]}{gold[0:2]}&"      # ASS colours are BGR
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {config.WIDTH}", f"PlayResY: {config.HEIGHT}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
        "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Cap,Montserrat ExtraBold,{CAPTION_SIZE},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,"
        "100,100,1,0,1,6,3,5,80,80,0,1",
        "Style: Head,Montserrat Black,60,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,"
        "100,100,1,0,1,5,2,8,90,90,250,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    total_end = starts[-1] + speech[-1] + config.END_TAIL
    header_from = 0.15
    if hook and hook.get("lines"):
        until = float(hook.get("until") or (starts[0] + speech[0] + 0.2))
        lines.extend(_hook_events(hook, until, gold_ass))
        header_from = until
    if header:
        lines.append(f"Dialogue: 1,{_ass_time(header_from)},{_ass_time(total_end)},Head,,0,0,0,,"
                     f"{{\\fad(300,400)}}{_clean(header)}")

    for k, scene in enumerate(scenes):
        words = _clean(scene["text"]).split()
        if not words:
            continue
        weights = [_weight(w) for w in words]
        total_w = sum(weights)
        t0, dur = starts[k], speech[k]
        word_start, acc = [], 0.0
        for w in weights:
            word_start.append(t0 + dur * acc / total_w)
            acc += w
        scene_end = t0 + dur + 0.15
        idx = 0
        for chunk in _chunks(words):
            first = idx
            for j in range(len(chunk)):
                wi = first + j
                start = word_start[wi]
                end = word_start[wi + 1] if wi + 1 < len(words) else scene_end
                pieces = []
                for m, word in enumerate(chunk):
                    pieces.append(f"{{\\c{gold_ass}}}{word}{{\\c&H00FFFFFF&}}" if m == j else word)
                pop = "{\\fscx84\\fscy84\\t(0,90,\\fscx100\\fscy100)}" if j == 0 else ""
                lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Cap,,0,0,0,,"
                             f"{{\\pos({config.WIDTH // 2},1180)}}{pop}{' '.join(pieces)}")
            idx += len(chunk)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
