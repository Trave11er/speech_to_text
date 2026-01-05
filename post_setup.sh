#!/usr/bin/env bash
# Requires sudo for apt only. Creates user systemd service.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USER_HOME="$(eval echo ~"$USER")"

# Resolve uv before sudo can taint environment
export PATH="$USER_HOME/.local/bin:$PATH"
if ! UV_PATH="$(which uv)"; then
  echo "uv not found. Run setup.sh first."
  exit 1
fi

# System deps
echo "Installing system dependencies..."
sudo apt install -y xclip xdotool portaudio19-dev

# Create systemd service
SERVICE_DIR="$USER_HOME/.config/systemd/user"
SERVICE_FILE="$SERVICE_DIR/stt.service"
mkdir -p "$SERVICE_DIR"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Speech to Text

[Service]
WorkingDirectory=$SCRIPT_DIR
ExecStart=$UV_PATH run stt.py
Restart=on-failure

[Install]
WantedBy=default.target
EOF

echo "Created $SERVICE_FILE"

# Enable and start service
if systemctl --user daemon-reload 2>/dev/null; then
  systemctl --user enable stt
  systemctl --user start stt
  echo "Done. STT service running."
else
  echo "Created $SERVICE_FILE but no user session bus found."
  echo "Run manually: systemctl --user enable stt && systemctl --user start stt"
fi
