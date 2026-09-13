# book2audio

Convert EPUB and PDF books into per-chapter audiobook MP3s using [Piper](https://github.com/rhasspy/piper) neural text-to-speech. Free, local, no API keys.

## Quick start

```bash
# 1. Install dependencies and download a voice
./setup.sh

# 2. Convert a book
python3 convert.py your_book.epub output/

# 3. Listen
open output/
```

## How it works

1. **Pandoc** converts your EPUB/PDF to markdown
2. The markdown is split into chapters based on headings
3. Markdown formatting is stripped to plain text
4. **Piper TTS** synthesizes each chapter to audio
5. **ffmpeg** encodes each chapter as a separate MP3

You get one MP3 per chapter (e.g., `chapter_01_Mind_the_Semantic_Gap.mp3`), plus front/back matter as separate files.

## Requirements

- **macOS** or **Linux**
- **Python 3.11+**
- **Homebrew** (macOS) or **apt** (Linux) for system packages

The setup script installs everything: pandoc, ffmpeg, piper-tts, and a default voice model.

## Usage

```bash
# Basic usage
python3 convert.py book.epub output/

# Use a different voice
python3 convert.py book.epub output/ --voice path/to/voice.onnx

# Skip certain sections (default: Bibliography, Glossary, Index)
python3 convert.py book.epub output/ --skip-sections Bibliography Glossary Index

# Adjust chunk size (smaller = more granular audio, slower)
python3 convert.py book.epub output/ --max-chars 300

# Convert a PDF
python3 convert.py document.pdf output/

# Convert markdown directly
python3 convert.py book.md output/
```

## Voices

The default voice is `en_GB-cori-high` (British female, high quality). To use a different voice:

1. Browse available voices at [huggingface.co/rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices/tree/v1.0.0)
2. Download the `.onnx` and `.onnx.json` files
3. Pass the path with `--voice`:
   ```bash
   python3 convert.py book.epub output/ --voice ~/Downloads/en_US-ryan-high.onnx
   ```

Or set the `PIPER_VOICE` environment variable:
```bash
export PIPER_VOICE=~/Downloads/en_US-ryan-high.onnx
python3 convert.py book.epub output/
```

### Recommended voices

| Voice | Gender | Accent | Quality |
|---|---|---|---|
| `en_GB-cori-high` | Female | British | High |
| `en_US-libritts-high` | Mixed | US | High |
| `en_US-ryan-high` | Male | US | High |
| `en_GB-alba-medium` | Female | British | Medium |
| `en_US-amy-medium` | Female | US | Medium |

## GitHub Actions (CI/CD)

This repo includes a GitHub Actions workflow that automatically converts books pushed to the `input/` folder.

### Setup

1. Create an `input/` folder in the repo:
   ```bash
   mkdir -p input && touch input/.gitkeep
   ```

2. Add your book:
   ```bash
   cp your_book.epub input/
   git add input/your_book.epub
   git commit -m "Add book for conversion"
   git push
   ```

3. The workflow runs automatically. Go to **Actions** tab to watch progress.

4. When done, download the **audiobook** artifact (MP3s). It auto-deletes after 3 days.

### Manual trigger

You can also trigger the workflow manually from the Actions tab (Workflow dispatch), specifying a filename in `input/`.

### Changing the voice in CI

Edit `.github/workflows/convert.yml` and change the `VOICE` environment variable at the top:
```yaml
env:
  VOICE: en_US-ryan-high
```

## Performance

- A typical book (~2700 text chunks) takes 30-60 minutes on an M-series Mac
- On GitHub Actions (2-core runner), expect 1-2 hours
- Output is ~100-150 MB of MP3 audio per book at 128kbps
- Memory usage is modest (~500 MB) -- audio is written incrementally

## Privacy

Everything runs locally on your machine. No data is sent to any API. The Piper voice model is downloaded once from HuggingFace and cached locally.

For the GitHub Actions workflow, your book is uploaded to GitHub's servers during the workflow run. Use a **private repo** if you don't want others to see your files.

## License

MIT
