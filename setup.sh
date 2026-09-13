#!/usr/bin/env bash
set -euo pipefail

# Setup script for book2audio
# Installs dependencies and downloads a Piper voice model

DATA_DIR="${HOME}/.local/share/book2audio"
VENV_DIR="${DATA_DIR}/venv"
VOICES_DIR="${DATA_DIR}/voices"

DEFAULT_VOICE="en_GB-cori-high"
VOICE_BASE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"

echo "=== book2audio setup ==="
echo ""

# Detect OS
OS_TYPE="$(uname -s)"
case "${OS_TYPE}" in
    Darwin*) OS="macos" ;;
    Linux*)  OS="linux" ;;
    *)       echo "ERROR: unsupported OS: ${OS_TYPE}"; exit 1 ;;
esac

echo "Detected OS: ${OS}"
echo "Install directory: ${DATA_DIR}"
echo ""

# Install system dependencies
echo "--- Checking system dependencies ---"

if [ "${OS}" = "macos" ]; then
    if ! command -v brew &>/dev/null; then
        echo "ERROR: Homebrew not found. Install: https://brew.sh"
        exit 1
    fi
    for pkg in pandoc ffmpeg python@3.14; do
        if ! brew list "${pkg}" &>/dev/null 2>&1; then
            echo "Installing ${pkg}..."
            brew install "${pkg}" 2>&1 | tail -3
        else
            echo "  ${pkg}: ok"
        fi
    done
else
    # Linux
    if command -v apt-get &>/dev/null; then
        for pkg in pandoc ffmpeg python3 python3-venv; do
            if ! dpkg -l "${pkg}" &>/dev/null 2>&1; then
                echo "Installing ${pkg}..."
                sudo apt-get install -y "${pkg}" 2>&1 | tail -3
            else
                echo "  ${pkg}: ok"
            fi
        done
    else
        echo "ERROR: no supported package manager found (apt-get)"
        exit 1
    fi
fi

# Find Python
PYTHON=""
for candidate in python3.14 python3.13 python3.12 python3.11 python3; do
    if command -v "${candidate}" &>/dev/null; then
        PYTHON="${candidate}"
        break
    fi
done

if [ -z "${PYTHON}" ]; then
    echo "ERROR: Python 3 not found"
    exit 1
fi

echo "  Python: ${PYTHON} ($(${PYTHON} --version))"
echo ""

# Create venv and install piper
echo "--- Setting up Python virtual environment ---"
mkdir -p "${DATA_DIR}"

if [ ! -d "${VENV_DIR}" ]; then
    echo "Creating venv at ${VENV_DIR}..."
    "${PYTHON}" -m venv "${VENV_DIR}"
fi

echo "Installing piper-tts..."
"${VENV_DIR}/bin/pip" install --quiet --upgrade pip
"${VENV_DIR}/bin/pip" install --quiet piper-tts numpy
echo "  piper-tts: ok"
echo ""

# Download default voice
echo "--- Downloading voice model: ${DEFAULT_VOICE} ---"
mkdir -p "${VOICES_DIR}"

ONNX_FILE="${VOICES_DIR}/${DEFAULT_VOICE}.onnx"
JSON_FILE="${VOICES_DIR}/${DEFAULT_VOICE}.onnx.json"

# Extract voice path components from the name
# Voice name format: {LANG}-{SPEAKER}-{QUALITY} e.g. en_GB-cori-high
LANG="${DEFAULT_VOICE%%-*}"
REST="${DEFAULT_VOICE#*-}"
SPEAKER="${REST%-*}"
QUALITY="${REST##*-}"

VOICE_URL="${VOICE_BASE_URL}/${LANG}/${LANG}_${SPEAKER}/${QUALITY}/${DEFAULT_VOICE}.onnx"
JSON_URL="${VOICE_BASE_URL}/${LANG}/${LANG}_${SPEAKER}/${QUALITY}/${DEFAULT_VOICE}.onnx.json"

if [ ! -f "${ONNX_FILE}" ]; then
    echo "Downloading ${DEFAULT_VOICE}.onnx..."
    curl -sL -o "${ONNX_FILE}" "${VOICE_URL}?download=true"
    echo "  Downloaded: $(du -h "${ONNX_FILE}" | cut -f1)"
else
    echo "  ${DEFAULT_VOICE}.onnx: already exists"
fi

if [ ! -f "${JSON_FILE}" ]; then
    echo "Downloading ${DEFAULT_VOICE}.onnx.json..."
    curl -sL -o "${JSON_FILE}" "${JSON_URL}?download=true"
else
    echo "  ${DEFAULT_VOICE}.onnx.json: already exists"
fi

echo ""

# Verify
echo "--- Verification ---"
echo "  pandoc:   $(command -v pandoc || echo 'MISSING')"
echo "  ffmpeg:   $(command -v ffmpeg || echo 'MISSING')"
echo "  piper:    ${VENV_DIR}/bin/python -c 'import piper' ($(${VENV_DIR}/bin/python -c 'import piper; print(piper.__version__)' 2>/dev/null || echo 'check failed')"
echo "  voice:    ${ONNX_FILE} ($([ -f "${ONNX_FILE}" ] && du -h "${ONNX_FILE}" | cut -f1 || echo 'MISSING'))"
echo ""
echo "=== Setup complete! ==="
echo ""
echo "Usage:"
echo "  python3 convert.py your_book.epub output_dir/"
echo "  python3 convert.py your_book.epub output_dir/ --voice ${ONNX_FILE}"
echo ""
echo "To use a different voice, download from:"
echo "  https://huggingface.co/rhasspy/piper-voices/tree/v1.0.0"
