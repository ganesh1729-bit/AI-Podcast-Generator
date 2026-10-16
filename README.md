# AI Podcast Generator (Sarvam API)

Generate complete, production-ready podcast episodes from a single prompt, a
document, or a topic — research, outline, multi-speaker script, per-speaker
synthesis with **Bulbul** voices, and a mixed, export-ready audio file.

Built on the Sarvam API:

| Stage | Sarvam endpoint | Model |
| --- | --- | --- |
| Research | `POST /v1/chat/completions` | `sarvam-105b` |
| Outline & script | `POST /v1/chat/completions` | `sarvam-105b` |
| Voice synthesis | `POST /text-to-speech` | `bulbul:v3` (or `bulbul:v4-flash`) |
| (optional) translate / transcribe | `/translate`, `/speech-to-text` | — |

Everything runs locally in Python. Audio assembly (concatenation, gaps,
background-music mixing with ducking) is pure Python + numpy — **no ffmpeg
required**. If `ffmpeg` happens to be on your PATH, MP3 export is enabled too.

---

## What it does

```
topic / document
      │
      ▼
[1] Research      → structured brief (hooks, facts, counterpoints, questions)
      │
      ▼
[2] Outline       → title, logline, 3–5 chapters with beats
      │
      ▼
[3] Script        → multi-speaker dialogue, JSON, per-turn pace & pause
      │
      ▼
[4] Cast          → language-aware voice assignment (Bulbul v3 speakers)
      │
      ▼
[5] TTS           → one WAV per turn (auto-splits >2500-char turns)
      │
      ▼
[6] Assemble      → gaps + chapter breaks + music bed + ducking → episode.wav
```

Alongside the audio you get `episode.json` (metadata), `transcript.txt`,
`show_notes.md`, `script.json`, `outline.json`, and `research.md` — so you can
re-edit the script and re-render without paying for the LLM stages again.

---

## Install

### Windows (easiest)

Two helper scripts are included so you don't have to fight the terminal:

1. **Install Python first** — get 3.10+ from
   <https://www.python.org/downloads/windows/>. On the very first installer
   screen, tick **“Add python.exe to PATH”**, then finish and close.
   (If `python` still opens the Microsoft Store, open *Settings → Apps →
   Advanced app settings → App execution aliases* and switch **off**
   `python.exe` and `python3.exe`.)
2. **Extract** `ai-podcast-generator.zip` somewhere (e.g. your Desktop).
3. **Double-click `setup_windows.bat`** — it creates a virtual environment and
   installs everything.
4. **Open `.env` in Notepad** and set `SARVAM_API_KEY=your-key-here`.
5. **Double-click `run_windows.bat`** (or run it from a Command Prompt with
   arguments) — see below.

From a Command Prompt, in the extracted folder:

```bat
run_windows.bat generate --topic "The future of UPI in India" --lang en-IN --minutes 8 --out episode.wav
run_windows.bat voices --lang ta-IN
```

> Windows notes: environment variables use `set` in Command Prompt
> (`set SARVAM_API_KEY=...`) or `$env:SARVAM_API_KEY="..."` in PowerShell —
> **not** `export`, which is Linux/macOS. And always run commands from inside
> the project folder (the `.bat` files handle this for you).

### macOS / Linux

```bash
git clone <this repo> podcast-generator   # or just copy the folder
cd podcast-generator
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Configure your key

Get a key from <https://dashboard.sarvam.ai>, then:

```bash
cp .env.example .env
# edit .env and set SARVAM_API_KEY=...
# or:
export SARVAM_API_KEY=...
```

The key is read from the environment and is **never** written to disk or logged
by this project. Rotate any key that has been shared in plaintext.

---

## Quick start

```bash
# 1. A full 8-minute English episode from a topic
python -m podcastgen generate --topic "The future of UPI in India" \
    --lang en-IN --minutes 8 --out episode.wav

# 2. Hindi episode with background music
python -m podcastgen generate --topic "गगनयान मिशन की तैयारी" \
    --lang hi-IN --music bed.wav --out gagan.wav

# 3. From a document (Markdown, txt, PDF or docx)
python -m podcastgen generate --from-file notes.md --title "Deep dive" --out ep.wav

# 4. Script only — no TTS cost, edit it, then render
python -m podcastgen generate --topic "ISRO's Gaganyaan" --script-only
python -m podcastgen from-script episode_assets/script.json --out episode.wav

# 5. See which voices suit a language
python -m podcastgen voices --lang ta-IN
```

### Useful flags

| Flag | Meaning |
| --- | --- |
| `--lang` | Episode language (BCP-47): `en-IN`, `hi-IN`, `ta-IN`, `bn-IN`, `mr-IN`, `te-IN`, `kn-IN`, `ml-IN`, `gu-IN`, `pa-IN`, `od-IN` |
| `--minutes` | Target length (word-budgeted; actual length depends on script) |
| `--speakers` | Number of speakers (2 = host + co-host) |
| `--roles` | Custom role names, e.g. `"Host,Co-host,Expert"` |
| `--music` | Background music WAV; `--music-gain` sets its level |
| `--tts-model` | `bulbul:v3` (default) or `bulbul:v4-flash` (200+ persona voices) |
| `--script-only` | Stop after the script, skip all TTS calls |
| `--clean` | Delete per-turn WAVs after the episode is built |

---

## Use it as a library

```python
from podcastgen import PodcastGenerator, Config

cfg = Config.from_env(language="hi-IN", target_minutes=10, num_speakers=2)
gen = PodcastGenerator(cfg)

result = gen.generate(
    "How India's semiconductor push is going",
    out_path="episode.wav",
    music_path="bed.wav",         # optional
)
print(result.summary())
print(result.transcript[:500])
```

Render an edited script:

```python
import json
from podcastgen import PodcastGenerator, Config

gen = PodcastGenerator(Config.from_env())
script = json.load(open("script.json"))
gen.from_script(script, out_path="episode.wav",
                cast={"Host": "priya", "Co-host": "shubh"})
```

---

## Voices

Bulbul v3 ships 30+ speakers; this project picks language-appropriate voices
automatically and alternates genders across hosts. See the full list with:

```bash
python -m podcastgen voices --lang hi-IN
```

Top picks per Sarvam's own guide: `priya` & `ishita` (female, work across many
languages), `shubh` (male, Hindi/Telugu/Kannada/Odia/Malayalam), `ratan` (male,
English/Telugu/Kannada/Tamil/Marathi/Gujarati), `mani` (male, Punjabi).

For `bulbul:v4-flash`, speakers are *persona ids* (e.g. `simran_en_customer`);
v3 short names like `shubh` are **not** valid on v4. Set `--tts-model
bulbul:v4-flash` and pass a persona id via `--cast` on `from-script`.

---

## Notes, limits, and honest caveats

- **Script language vs TTS language.** The script stage writes dialogue in the
  target language. For Indic languages it is told to use **native script** and
  keep only English words in Latin — romanised Indic text ("Aapka order confirm
  ho gaya") measurably degrades Bulbul's output.
- **Research is model-knowledge based.** `sarvam-105b` does not browse the web
  on its own here. For factual episodes, pass your own sources with
  `--from-file` (or the `sources=` argument) so the brief is grounded.
- **Text length.** A single REST TTS request is capped at 2,500 characters; the
  pipeline splits longer turns at sentence boundaries automatically.
- **Sample rates.** 8k/16k/22.05k/24k everywhere; 32k/44.1k/48k only on the REST
  API with `bulbul:v3`.
- **MP3 export** needs `ffmpeg`. Without it, the episode is written as `.wav`
  (lossless) and you'll get a clear message telling you so.
- **Costs.** Each episode makes 1 research + 1 outline + 1 script chat call and
  one TTS call per turn. Use `--script-only` while iterating on content.

---

## Project layout

```
podcast-generator/
├── podcastgen/
│   ├── config.py        # endpoints, models, defaults, .env loading
│   ├── client.py        # Sarvam REST client (chat / tts / translate / stt)
│   ├── voices.py        # Bulbul catalog + language-aware casting
│   ├── research.py      # research brief stage
│   ├── scriptwriter.py  # outline + multi-speaker script (JSON)
│   ├── tts.py           # per-turn synthesis + long-text splitting
│   ├── audio.py         # WAV I/O, assembly, music mixing, ducking, export
│   ├── pipeline.py      # orchestration (PodcastGenerator)
│   └── cli.py           # command-line interface
├── examples/
├── tests/               # offline tests (no API key needed)
├── requirements.txt
└── .env.example
```

## Tests

Offline (no key, no network):

```bash
python tests/test_audio.py
python tests/test_script.py
python tests/test_pipeline.py
```

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `No Sarvam API key found` | Set `SARVAM_API_KEY` or create `.env` |
| `HTTP 422 ... invalid speaker/model` | Speaker must match the model version (v3 short names vs v4 persona ids) |
| `HTTP 429` | Rate limit — the client retries with backoff; lower concurrency or upgrade the plan |
| Choppy/robotic Indic audio | Make sure Indic words are in native script, not romanised |
| No MP3 produced | Install `ffmpeg`, or use `.wav` output |

## License

MIT — do what you like. Voices, models, and the API are governed by Sarvam's terms.
