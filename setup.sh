#!/usr/bin/env bash
# No sudo required. Installs uv, downloads models, creates lock file.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Install uv
if ! command -v uv &>/dev/null; then
  echo "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
else
  echo "uv already installed"
fi

# Download models
cd "$SCRIPT_DIR"

if [ ! -f silero_vad_v4.onnx ]; then
  echo "Downloading Silero VAD model..."
  curl -L -o silero_vad_v4.onnx https://github.com/cjpais/Handy/raw/main/src-tauri/resources/models/silero_vad_v4.onnx
else
  echo "Silero VAD model already exists"
fi

if [ ! -d sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8 ]; then
  echo "Downloading Parakeet model (~600MB)..."
  wget https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8.tar.bz2
  tar xvf sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8.tar.bz2
  rm -f sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8.tar.bz2
else
  echo "Parakeet model already exists"
fi

# Create lock file
echo "Creating lock file..."
uv lock

# This is needed to fix "ImportError: libonnxruntime.so: cannot open shared object file: No such file or directory"
echo "Installing dependencies (copy mode)..."
uv venv
uv pip install --link-mode=copy -e .
uv pip install --link-mode=copy --force-reinstall sherpa-onnx onnxruntime

echo "Done. Run post_setup.sh (requires sudo) to install system deps and systemd service."
