#!/bin/bash
# Toggle start/Stop force transcribe

# Find the actual python process, not the uv wrapper
pkill -SIGUSR1 -f "python.*stt.py" || echo "No process found"
