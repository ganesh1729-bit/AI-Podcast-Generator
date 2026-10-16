"""Audio-engine tests — no API key or network required."""

import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from podcastgen import audio  # noqa: E402


def _tone(freq: float, seconds: float, sr: int, amp: float = 0.5) -> np.ndarray:
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_roundtrip_wav():
    sr = 24000
    sig = _tone(440, 0.5, sr)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "a.wav")
        audio.write_wav(path, sig, sr)
        back, back_sr = audio.read_wav(path)
    assert back_sr == sr
    assert abs(back.size - sig.size) <= 1
    assert np.max(np.abs(back - sig)) < 1e-3


def test_concat_and_silence():
    sr = 24000
    a = _tone(300, 0.3, sr)
    b = _tone(600, 0.2, sr)
    out = audio.concat([a, audio.silence(0.1, sr), b])
    assert out.size == a.size + int(0.1 * sr) + b.size


def test_build_episode_with_music_and_ducking():
    sr = 24000
    with tempfile.TemporaryDirectory() as d:
        s1 = os.path.join(d, "s1.wav")
        s2 = os.path.join(d, "s2.wav")
        music = os.path.join(d, "bed.wav")
        audio.write_wav(s1, _tone(220, 1.0, sr, 0.6), sr)
        audio.write_wav(s2, _tone(330, 1.0, sr, 0.6), sr)
        audio.write_wav(music, _tone(80, 0.5, sr, 0.5), sr)

        episode = audio.build_episode(
            [
                {"path": s1, "pause_after": 0.2, "chapter_index": 0},
                {"path": s2, "pause_after": 0.2, "chapter_index": 1},
            ],
            sr=sr, turn_gap=0.3, chapter_gap=0.8, music_path=music,
            music_gain=0.1, duck=True,
        )
    assert episode.size > 2 * sr  # longer than the two 1s clips
    assert np.max(np.abs(episode)) <= 1.0 + 1e-6  # no clipping past full scale
    assert np.max(np.abs(episode)) > 0.5  # normalised up


def test_resample():
    sr = 24000
    sig = _tone(440, 0.5, sr)
    out = audio.resample_linear(sig, sr, 16000)
    assert abs(out.size - int(0.5 * 16000)) <= 2


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all audio tests passed")
