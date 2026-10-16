"""Script-parsing tests — no API key or network required."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from podcastgen import scriptwriter as sw  # noqa: E402
from podcastgen import tts  # noqa: E402
from podcastgen import voices  # noqa: E402


def test_parse_json_plain():
    assert sw.parse_json('{"a": 1}') == {"a": 1}


def test_parse_json_fenced():
    raw = "Here you go:\n```json\n{\"a\": 2, \"b\": [1,2]}\n```\nDone."
    assert sw.parse_json(raw)["a"] == 2


def test_parse_json_embedded():
    raw = "blah {\"title\": \"X\", \"chapters\": []} trailing"
    assert sw.parse_json(raw)["title"] == "X"


def test_normalise_script():
    script = {
        "title": "T",
        "chapters": [
            {"title": "Intro", "segments": [
                {"speaker": "Host", "text": "Hi", "pace": 9.0, "pause_after": -1},
                {"role": "Co-host", "line": "Hey there"},
                {"speaker": "Host", "text": "   "},  # dropped
            ]}
        ],
    }
    out = sw.normalise_script(script, ["Host", "Co-host"])
    segs = out["chapters"][0]["segments"]
    assert len(segs) == 2
    assert segs[0]["pace"] == 2.0        # clamped to max
    assert segs[0]["pause_after"] == 0.0  # clamped to min
    assert segs[1]["speaker"] == "Co-host"  # 'role'/'line' handled
    assert segs[1]["text"] == "Hey there"


def test_word_count_and_transcript():
    script = {"chapters": [{"title": "C", "segments": [
        {"speaker": "Host", "text": "one two three"},
        {"speaker": "Co-host", "text": "four five"},
    ]}]}
    assert sw.script_word_count(script) == 5
    assert "Host: one two three" in sw.to_transcript(script)


def test_split_text_respects_limit():
    text = " ".join(f"Sentence number {i}." for i in range(500))
    chunks = tts.split_text(text, max_chars=200)
    assert all(len(c) <= 200 for c in chunks)
    assert " ".join(chunks).replace("  ", " ").strip() == text.strip()


def test_cast_assignment():
    cast = voices.assign_cast("hi-IN", 2, ["Host", "Co-host"])
    assert set(cast) == {"Host", "Co-host"}
    assert cast["Host"] in voices.V3_ALL
    assert cast["Host"] != cast["Co-host"]
    # language-appropriate picks
    assert cast["Host"] in voices.recommend("hi-IN", "female")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all script tests passed")
