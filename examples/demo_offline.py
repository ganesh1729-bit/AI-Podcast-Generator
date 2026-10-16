"""Offline demo: run the whole pipeline with a fake client (no API key, no network).

    python examples/demo_offline.py

Produces ./demo_episode.wav plus its asset folder, so you can see the exact
files a real run creates before spending any API credits.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from podcastgen import audio
from podcastgen.config import Config
from podcastgen.pipeline import PodcastGenerator


class FakeClient:
    def __init__(self, cfg):
        self.cfg = cfg

    def chat(self, messages, **kwargs):
        import json

        user = messages[-1]["content"]
        if "Write the full dialogue" in user:
            return json.dumps({
                "title": "Demo: Why Podcasts Are Hard",
                "logline": "Two hosts riff on what makes a good episode.",
                "chapters": [
                    {"title": "Cold open", "segments": [
                        {"speaker": "Host", "text": "Everyone thinks podcasts are easy.",
                         "pace": 1.0, "pause_after": 0.4},
                        {"speaker": "Co-host", "text": "Then they try to edit one.",
                         "pace": 1.0, "pause_after": 0.5},
                    ]},
                    {"title": "The point", "segments": [
                        {"speaker": "Host", "text": "The magic is in the pacing, not the audio.",
                         "pace": 0.95, "pause_after": 0.6},
                    ]},
                ],
                "show_notes": "A tiny offline demo episode.",
                "sources": [],
            })
        if "Create an outline" in user:
            return json.dumps({"title": "Demo", "logline": "", "chapters": []})
        if "Research brief for a podcast" in user:
            return "## Hook\nPodcasts are hard.\n\n## Key facts\n- editing matters (high)"
        raise AssertionError(user[:60])

    def tts(self, text, **kwargs):
        sr = kwargs.get("sample_rate", 24000)
        seconds = max(0.5, len(text.split()) * 0.35)
        t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
        return audio.to_wav_bytes((0.4 * np.sin(2 * np.pi * 190 * t)).astype(np.float32), sr)


def main():
    cfg = Config(api_key="offline-demo", language="en-IN", target_minutes=3, num_speakers=2)
    gen = PodcastGenerator(cfg, client=FakeClient(cfg))
    out = os.path.join(os.getcwd(), "demo_episode.wav")
    result = gen.generate("Why podcasts are hard", out_path=out)
    print("\nFiles written:")
    print(" ", result.out_path)
    print(" ", result.assets_dir, "(script.json, outline.json, research.md, transcript.txt, episode.json)")


if __name__ == "__main__":
    main()
