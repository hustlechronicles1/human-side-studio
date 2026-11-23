"""Narration with Kokoro (open-weight, Apache-2.0, runs on CPU)."""
import urllib.request

import numpy as np
import soundfile as sf

from . import config

_kokoro = None


def ensure_models():
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for path in (config.KOKORO_MODEL, config.KOKORO_VOICES):
        if not path.exists() or path.stat().st_size < 1_000_000:
            print(f"Downloading {path.name} ...", flush=True)
            urllib.request.urlretrieve(config.KOKORO_URL + path.name, path)


def _engine():
    global _kokoro
    if _kokoro is None:
        from kokoro_onnx import Kokoro
        ensure_models()
        _kokoro = Kokoro(str(config.KOKORO_MODEL), str(config.KOKORO_VOICES))
    return _kokoro


def _trim(samples, sr, threshold=0.004):
    """Cut leading/trailing near-silence so scene timing is tight."""
    idx = np.where(np.abs(samples) > threshold)[0]
    if len(idx) == 0:
        return samples
    start = max(0, idx[0] - int(0.03 * sr))
    end = min(len(samples), idx[-1] + int(0.08 * sr))
    return samples[start:end]


def narrate(scenes, voice, speed, workdir):
    """Synthesize each scene. Returns (narration_wav_path, [scene_durations], [speech_durations])."""
    engine = _engine()
    chunks, durations, speech = [], [], []
    sr = 24000
    for i, scene in enumerate(scenes):
        samples, sr = engine.create(scene["text"], voice=voice, speed=speed, lang="en-us")
        samples = _trim(np.asarray(samples, dtype=np.float32), sr)
        pause = scene.get("pause", config.SCENE_PAUSE)
        padded = np.concatenate([samples, np.zeros(int(pause * sr), dtype=np.float32)])
        chunks.append(padded)
        speech.append(len(samples) / sr)
        durations.append(len(padded) / sr)
        print(f"  voice {i + 1}/{len(scenes)}: {speech[-1]:.2f}s", flush=True)
    tail = np.zeros(int(config.END_TAIL * sr), dtype=np.float32)
    audio = np.concatenate(chunks + [tail])
    path = workdir / "narration.wav"
    sf.write(path, audio, sr)
    return path, durations, speech
