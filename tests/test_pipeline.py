"""Offline end-to-end test of the pipeline using a fake Sarvam client.

No API key, no network. Verifies that research -> outline -> script -> TTS ->
assembly is wired correctly.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from podcastgen import audio  # noqa: E402
from podcastgen.config import Config  # noqa: E402
from podcastgen.pipeline import PodcastGenerator  # noqa: E402


class FakeClient:
    """Mimics SarvamClient.chat / .tts for offline testing."""

    def __init__(self, cfg):
        self.cfg = cfg

    def chat(self, messages, **kwargs):
        user = messages[-1]["content"]
        if "Write the full dialogue" in user:
            return json.dumps({
                "title": "UPI at Scale",
                "logline": "How UPI rewired Indian payments.",
                "chapters": [
                    {"title": "Cold open", "segments": [
                        {"speaker": "Host", "text": "So UPI just crossed another billion.",
                         "pace": 1.0, "pause_after": 0.4},
                        {"speaker": "Co-host", "text": "A billion a day. Wild.",
                         "pace": 1.0, "pause_after": 0.5},
                    ]},
                    {"title": "The takeaway", "segments": [
                        {"speaker": "Host", "text": "The real story is interoperability.",
                         "pace": 0.95, "pause_after": 0.6},
                    ]},
                ],
                "show_notes": "A short episode about UPI.",
                "sources": ["NPCI public stats"],
            })
        if "Create an outline" in user:
            return json.dumps({
                "title": "UPI at Scale",
                "logline": "How UPI rewired Indian payments.",
                "chapters": [
                    {"title": "Cold open", "goal": "hook", "beats": ["scale", "surprise"]},
                    {"title": "The takeaway", "goal": "wrap", "beats": ["so what"]},
                ],
            })
        if "Research brief for a podcast" in user:
            return "## Hook\nUPI is huge.\n\n## Key facts\n- 100 crore+ daily txns (medium)"
        raise AssertionError("unexpected prompt: " + user[:60])

    def tts(self, text, **kwargs):
        sr = kwargs.get("sample_rate", 24000)
        seconds = max(0.4, len(text.split()) * 0.3)
        t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
        sig = (0.4 * np.sin(2 * np.pi * 200 * t)).astype(np.float32)
        return audio.to_wav_bytes(sig, sr)


def test_full_pipeline_offline():
    with tempfile.TemporaryDirectory() as d:
        cfg = Config(api_key="fake", language="en-IN", target_minutes=3, num_speakers=2)
        gen = PodcastGenerator(cfg, client=FakeClient(cfg))
        out = os.path.join(d, "episode.wav")
        result = gen.generate("UPI at scale", out_path=out, keep_assets=True)

        assert os.path.isfile(out)
        assert result.duration > 1.0
        assert len(result.segments) == 3
        assert result.title == "UPI at Scale"
        assert os.path.isfile(result.metadata_path)

        meta = json.load(open(result.metadata_path))
        assert meta["chapters"] == ["Cold open", "The takeaway"]
        assert meta["duration_seconds"] > 0

        samples, sr = audio.read_wav(out)
        assert samples.size > 0
        assert np.max(np.abs(samples)) <= 1.0


def test_script_only_offline():
    with tempfile.TemporaryDirectory() as d:
        cfg = Config(api_key="fake", language="hi-IN", target_minutes=3)
        gen = PodcastGenerator(cfg, client=FakeClient(cfg))
        result = gen.generate("UPI", out_path=os.path.join(d, "x.wav"), script_only=True)
        assert result.out_path == ""
        assert os.path.isfile(os.path.join(result.assets_dir, "script.json"))


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all pipeline tests passed")
