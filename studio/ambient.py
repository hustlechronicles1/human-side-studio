"""A soft generated ambient pad, used only when the music/ folder is empty."""
import numpy as np
import soundfile as sf

SR = 44100
# A minor -> F major 7 -> C major -> G major (6) : calm, reflective
CHORDS = [
    [110.00, 130.81, 164.81, 220.00],
    [87.31, 110.00, 130.81, 164.81],
    [130.81, 164.81, 196.00, 261.63],
    [98.00, 123.47, 146.83, 164.81],
]


def make(seconds, path, chord_len=8.0):
    n = int(seconds * SR)
    t = np.arange(n) / SR
    left = np.zeros(n)
    right = np.zeros(n)
    fade = 2.5
    k = 0
    start = -fade
    while start < seconds:
        chord = CHORDS[k % len(CHORDS)]
        a, b = max(0, int(start * SR)), min(n, int((start + chord_len + fade) * SR))
        seg = t[a:b] - start
        env = np.minimum(1, np.minimum(seg / fade, (chord_len + fade - seg) / fade)).clip(0, 1)
        env = 0.5 - 0.5 * np.cos(np.pi * env)
        for i, f in enumerate(chord):
            amp = 0.22 / (1 + 0.35 * i)
            left[a:b] += env * amp * (np.sin(2 * np.pi * f * 0.9985 * t[a:b]) + 0.12 * np.sin(4 * np.pi * f * t[a:b]))
            right[a:b] += env * amp * (np.sin(2 * np.pi * f * 1.0015 * t[a:b]) + 0.12 * np.sin(4 * np.pi * f * t[a:b]))
        start += chord_len
        k += 1
    breathe = 0.85 + 0.15 * np.sin(2 * np.pi * 0.07 * t)
    stereo = np.stack([left * breathe, right * breathe], axis=1)
    stereo *= 0.5 / max(1e-9, np.abs(stereo).max())
    edge = int(1.5 * SR)
    ramp = np.linspace(0, 1, edge)[:, None]
    stereo[:edge] *= ramp
    stereo[-edge:] *= ramp[::-1]
    sf.write(path, stereo.astype(np.float32), SR)
    return path
