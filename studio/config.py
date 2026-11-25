from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EPISODES_DIR = ROOT / "episodes"
MUSIC_DIR = ROOT / "music"
FONTS_DIR = ROOT / "assets" / "fonts"
MODELS_DIR = ROOT / "models"
CACHE_DIR = ROOT / ".cache"
OUT_DIR = ROOT / "out"

# Output format (YouTube Shorts)
WIDTH, HEIGHT, FPS = 1080, 1920, 30

# Voice (Kokoro, free and open-weight)
KOKORO_MODEL = MODELS_DIR / "kokoro-v1.0.onnx"
KOKORO_VOICES = MODELS_DIR / "voices-v1.0.bin"
KOKORO_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
DEFAULT_VOICE = "af_heart"
DEFAULT_SPEED = 0.88

# Timing
SCENE_PAUSE = 0.40       # breath added after each scene's narration (seconds)
TRANSITION = 0.60        # length of each visual transition (seconds)
END_TAIL = 1.20          # silence/visual hold at the very end (seconds)

# Per-episode "pace" overrides these: {"pause": .., "transition": .., "tail": ..}
PACE_DEFAULTS = {"pause": SCENE_PAUSE, "transition": TRANSITION, "tail": END_TAIL}

# Calm transition rotation used when a scene doesn't name one
TRANSITIONS = ["fade", "smoothleft", "fade", "smoothup", "fadeblack", "slideleft"]
# Motion rotation for photos when a scene doesn't name one
MOTIONS = ["zoom_in", "pan_right", "zoom_out", "pan_left", "zoom_in", "pan_up"]

# Look
BRAND_GOLD = "F5B700"    # RGB hex, matches the channel banner
MUSIC_VOLUME = 0.11
