# vsub — subtitles and translation for your videos

[中文](README.md) · English · [Providers](docs/providers.md)

Local speech recognition (faster-whisper) + a pluggable translation backend
(Ollama / OpenAI-compatible / DeepL / Gemini).
**By default it only writes an external `.srt` next to the video — the original
file is never touched.**

```
video -> ffmpeg audio -> faster-whisper ASR -> translator -> .srt (next to video)
                                                         └─> optional: soft-sub mkv (--embed)
```

## Highlights

- **Never re-encodes your video.** Default output is an external `.srt`.
  `--embed` produces an MKV with switchable subtitle tracks via stream copy (lossless, reversible).
- **No hard-burning.** Burning subtitles into pixels is lossy and irreversible — `--burn` only prints a notice.
- **Auto language detection.** CJK languages automatically get narrower line breaks.
- **Pluggable translators.** Free local Ollama, or one line to switch to DeepSeek / Qwen / OpenAI / DeepL / Gemini.
- **Batch + resume.** Point it at a folder; finished files are skipped; the ASR model is loaded once.

## Install

```bash
# requires ffmpeg/ffprobe on PATH
pipx install vsub
# or
pip install -U vsub
```

## Quick start

```bash
# local Ollama (free, no API key)
ollama pull qwen3:8b
vsub video.mp4

# cloud API
export VSUB_API_KEY=sk-xxxxxx
vsub video.mp4 --provider openai --base-url https://api.deepseek.com/v1 --model deepseek-chat
```

Output next to your video:

```
video.srt        bilingual (translation on top, original below)
video.zh.srt     translation only
video.orig.srt   original only
```

Intermediate files (including `wav`, which can be used to reconstruct the whole
voice track) are deleted when the run finishes. Use `--keep-temp` to keep them.

## Configuration

Precedence: **CLI > environment variables > config file > defaults**

```bash
vsub config init      # write ~/.vsub/config.toml
vsub config show      # print effective config (keys masked)
vsub config check     # translate one sentence to verify connectivity
```

Env vars: `VSUB_PROVIDER` `VSUB_MODEL` `VSUB_BASE_URL` `VSUB_API_KEY` `VSUB_TGT`
`VSUB_ASR_MODEL` `VSUB_DEVICE` `VSUB_MODE` `VSUB_CONFIG`

See **[docs/providers.md](docs/providers.md)** for per-vendor `base_url` / model names.

## Common flags

| Flag | Default | Meaning |
|---|---|---|
| `--provider` | `ollama` | `ollama` / `openai` / `deepl` / `gemini` |
| `--base-url` | per provider | switch vendor with just this |
| `--model` | per provider | translator model name |
| `--tgt` | `zh` | target language |
| `--asr-model` | `small` | tiny/base/small/medium/large-v3 or a local dir |
| `--mode` | `bilingual` | `bilingual` (translation on top) / `tgt` / `src` |
| `--src-first` | off | put the original line on top |
| `--embed` | off | also write a switchable soft-sub MKV |
| `--force` | off | redo files that already have subtitles |
| `--recursive` | off | scan sub-folders |

## Privacy

Audio and video never leave your machine — only subtitle text is sent to the
translator (≤25 lines / ≤1100 chars per request). See [docs/privacy.md](docs/privacy.md).

## License

MIT. The core dependency, faster-whisper, is MIT as well.
