#!/usr/bin/env python3
"""Convert an EPUB/PDF/markdown file to a per-chapter audiobook using Piper TTS."""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

# Add local venv to path so we can import piper
_VENV_PATHS = [
    os.path.expanduser("~/.local/share/book2audio/venv/lib"),
    "/opt/book2audio-venv/lib",
]
for _venv in _VENV_PATHS:
    if os.path.isdir(_venv):
        for entry in os.listdir(_venv):
            p = os.path.join(_venv, entry, "site-packages")
            if os.path.isdir(p):
                sys.path.insert(0, p)

try:
    from piper import PiperVoice
    import numpy as np
except ImportError:
    print("ERROR: piper-tts not installed. Run the setup script first:", file=sys.stderr)
    print("  ./setup.sh", file=sys.stderr)
    sys.exit(1)


def convert_to_markdown(input_file):
    """Convert EPUB or PDF to markdown using pandoc. Returns the markdown text."""
    input_path = Path(input_file)
    ext = input_path.suffix.lower()

    if ext in (".md", ".txt"):
        with open(input_path, "r", encoding="utf-8") as f:
            return f.read()

    if ext not in (".epub", ".pdf"):
        print(f"ERROR: unsupported input format: {ext}", file=sys.stderr)
        sys.exit(1)

    print(f"Converting input to markdown with pandoc...", flush=True)
    tmp_md = tempfile.NamedTemporaryFile(suffix=".md", delete=False)
    tmp_md.close()

    result = subprocess.run(
        ["pandoc", str(input_path), "-t", "gfm", "--wrap=none", "-o", tmp_md.name],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"ERROR: pandoc failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    with open(tmp_md.name, "r", encoding="utf-8") as f:
        text = f.read()
    os.unlink(tmp_md.name)
    return text


def clean_markdown(text):
    """Strip markdown and HTML formatting to plain text."""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"\[([^\]]*)\]\([^\)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\[[^\]]*\]", r"\1", text)
    text = re.sub(r"^\[.*?\]:\s*http.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}(.*?)_{1,3}", r"\1", text)
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^---+$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[\s]*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[\s]*\d+\.\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"\[\^[^\]]*\]", "", text)
    text = re.sub(r"<span[^>]*>.*?</span>", "", text, flags=re.DOTALL)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"http[s?]://\S+", "", text)
    return text.strip()


def split_into_chunks(text, max_chars=500):
    """Split text into chunks suitable for TTS, respecting sentence boundaries."""
    chunks = []
    for para in text.split("\n\n"):
        para = para.strip()
        if not para or len(para) < 2:
            continue
        if len(para) <= max_chars:
            chunks.append(para)
            continue

        sentences = re.split(r"(?<=[.!?])\s+", para)
        current = ""
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(sentence) > max_chars:
                for part in re.split(r"(?<=[,;:])\s+", sentence):
                    part = part.strip()
                    if not part:
                        continue
                    if len(current) + len(part) + 1 <= max_chars:
                        current = (current + " " + part).strip()
                    else:
                        if current:
                            chunks.append(current)
                        if len(part) <= max_chars:
                            current = part
                        else:
                            for word in part.split():
                                if len(current) + len(word) + 1 <= max_chars:
                                    current = (current + " " + word).strip()
                                else:
                                    if current:
                                        chunks.append(current)
                                    current = word
                continue
            if len(current) + len(sentence) + 1 <= max_chars:
                current = (current + " " + sentence).strip()
            else:
                if current:
                    chunks.append(current)
                current = sentence
        if current:
            chunks.append(current)

    return [c for c in chunks if len(c.strip()) > 1]


def split_by_chapter(raw_text):
    """Split the raw markdown into chapters based on top-level headings."""
    lines = raw_text.split("\n")
    chapters = []
    current_title = "Front Matter"
    current_lines = []

    back_matter = {
        "Bibliography", "Glossary", "Index", "About the Author", "Colophon",
        "References", "Appendix",
    }

    for line in lines:
        if re.match(r"^# ", line):
            clean_title = re.sub(r"<[^>]+>", "", line)
            clean_title = re.sub(r"^#{1,6}\s+", "", clean_title).strip()

            chapter_match = re.search(r"Chapter\s+(\d+)", clean_title)
            part_match = re.match(r"^Part\s+", clean_title)

            if chapter_match:
                if current_lines:
                    chapters.append((current_title, "\n".join(current_lines)))
                current_title = clean_title
                current_lines = [line]
            elif part_match:
                current_lines.append(line)
            elif clean_title in back_matter or clean_title.startswith(("Praise for", "Revision History")):
                if current_lines:
                    chapters.append((current_title, "\n".join(current_lines)))
                current_title = clean_title
                current_lines = [line]
            else:
                current_lines.append(line)
        else:
            current_lines.append(line)

    if current_lines:
        chapters.append((current_title, "\n".join(current_lines)))

    return chapters


def sanitize_title(title, index):
    """Create a filesystem-safe filename from a chapter title."""
    chapter_match = re.search(r"Chapter\s+(\d+)", title)
    if chapter_match:
        num = chapter_match.group(1)
        clean = re.sub(r"Chapter\s+\d+\.\s*", "", title)
        clean = re.sub(r"[^a-zA-Z0-9]+", "_", clean).strip("_")[:60]
        return f"chapter_{num.zfill(2)}_{clean}"
    else:
        clean = re.sub(r"[^a-zA-Z0-9]+", "_", title).strip("_")[:60]
        return f"{index:02d}_{clean}"


def main():
    parser = argparse.ArgumentParser(
        description="Convert an EPUB/PDF/markdown file to a per-chapter audiobook."
    )
    parser.add_argument("input", help="Input file (EPUB, PDF, or markdown)")
    parser.add_argument("output_dir", help="Output directory for chapter MP3s")
    parser.add_argument(
        "--voice", "-v",
        default=os.environ.get(
            "PIPER_VOICE",
            os.path.expanduser("~/.local/share/book2audio/voices/en_GB-cori-high.onnx"),
        ),
        help="Path to Piper voice .onnx file (default: en_GB-cori-high)",
    )
    parser.add_argument(
        "--max-chars", type=int, default=500,
        help="Max characters per TTS chunk (default: 500)",
    )
    parser.add_argument(
        "--skip-sections", nargs="*", default=["Bibliography", "Glossary", "Index"],
        help="Section titles to skip (default: Bibliography Glossary Index)",
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true",
        help="Suppress book content (chapter titles, filenames) from output for privacy",
    )
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"ERROR: input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(args.voice):
        print(f"ERROR: voice model not found: {args.voice}", file=sys.stderr)
        print("Run the setup script first: ./setup.sh", file=sys.stderr)
        sys.exit(1)

    if not shutil.which("ffmpeg"):
        print("ERROR: ffmpeg not found. Install: brew install ffmpeg (macOS) or apt install ffmpeg (Linux)", file=sys.stderr)
        sys.exit(1)

    if not shutil.which("pandoc"):
        print("ERROR: pandoc not found. Install: brew install pandoc (macOS) or apt install pandoc (Linux)", file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.output_dir, exist_ok=True)

    # Step 1: Convert to markdown
    raw_text = convert_to_markdown(args.input)
    print(f"Read {len(raw_text)} chars from input", flush=True)

    # Step 2: Split into chapters
    print("Splitting into chapters...", flush=True)
    chapters = split_by_chapter(raw_text)
    print(f"  {len(chapters)} sections found", flush=True)

    # Step 3: Clean and chunk each chapter
    chapter_chunks = []
    total_chunks = 0
    skip_set = set(args.skip_sections)
    for title, raw_content in chapters:
        if title in skip_set:
            if not args.quiet:
                print(f"  Skipping: {title}", flush=True)
            continue
        clean = clean_markdown(raw_content)
        chunks = split_into_chunks(clean, args.max_chars)
        if chunks:
            chapter_chunks.append((title, chunks))
            total_chunks += len(chunks)

    print(f"  {len(chapter_chunks)} sections with audio", flush=True)
    print(f"  {total_chunks} total chunks", flush=True)

    if total_chunks == 0:
        print("ERROR: no text to synthesize", file=sys.stderr)
        sys.exit(1)

    # Step 4: Load Piper voice
    print(f"Loading Piper voice: {args.voice}", flush=True)
    voice = PiperVoice.load(args.voice)
    sample_rate = voice.config.sample_rate
    print(f"  Sample rate: {sample_rate}", flush=True)

    # Step 5: Synthesize audio
    tmp_dir = tempfile.mkdtemp(prefix="book2audio_")
    start_time = time.time()
    global_idx = 0

    for ci, (title, chunks) in enumerate(chapter_chunks):
        filename = sanitize_title(title, ci)
        wav_path = os.path.join(tmp_dir, f"{filename}.wav")
        mp3_path = os.path.join(args.output_dir, f"{filename}.mp3")

        # Skip if MP3 already exists (resume support)
        if os.path.isfile(mp3_path) and os.path.getsize(mp3_path) > 0:
            print(f"\n[{ci+1}/{len(chapter_chunks)}] already exists, skipping", flush=True)
            global_idx += len(chunks)
            continue

        if not args.quiet:
            print(f"\n[{ci+1}/{len(chapter_chunks)}] {title} ({len(chunks)} chunks)", flush=True)
        else:
            print(f"\n[{ci+1}/{len(chapter_chunks)}] ({len(chunks)} chunks)", flush=True)

        wav_file = wave.open(wav_path, "wb")
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)

        for chunk in chunks:
            try:
                for audio_chunk in voice.synthesize(chunk):
                    int16 = (audio_chunk.audio_float_array * 32767).astype(np.int16)
                    wav_file.writeframes(int16.tobytes())
            except Exception as e:
                print(f"    WARNING: chunk failed: {e}", flush=True)

            global_idx += 1
            if global_idx % 25 == 0 or global_idx == total_chunks:
                elapsed = time.time() - start_time
                rate = global_idx / elapsed if elapsed > 0 else 0
                remaining = (total_chunks - global_idx) / rate if rate > 0 else 0
                print(f"  [{global_idx}/{total_chunks}] total | {elapsed:.0f}s elapsed | ~{remaining:.0f}s remaining", flush=True)

        wav_file.close()

        print(f"  Converting to MP3...", flush=True)
        subprocess.run(
            ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-b:a", "128k", mp3_path],
            capture_output=True,
        )
        os.unlink(wav_path)

    shutil.rmtree(tmp_dir)

    # Summary
    elapsed_total = time.time() - start_time
    total_size = sum(
        os.path.getsize(os.path.join(args.output_dir, f))
        for f in os.listdir(args.output_dir)
        if f.endswith(".mp3")
    )

    print(f"\n{'='*60}", flush=True)
    print(f"Done! {len(chapter_chunks)} chapter MP3s saved to: {args.output_dir}", flush=True)
    print(f"  Total size: {total_size / (1024*1024):.1f} MB", flush=True)
    print(f"  Generation time: {elapsed_total/60:.1f} minutes", flush=True)
    print(f"  Total chunks: {total_chunks}", flush=True)
    if not args.quiet:
        print(f"\nFiles:", flush=True)
        for f in sorted(os.listdir(args.output_dir)):
            if f.endswith(".mp3"):
                size = os.path.getsize(os.path.join(args.output_dir, f)) / (1024 * 1024)
                print(f"  {f} ({size:.1f} MB)", flush=True)
    else:
        print(f"  Files: {len(chapter_chunks)} MP3s", flush=True)


if __name__ == "__main__":
    main()
