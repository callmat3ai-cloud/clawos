#!/bin/bash
# ClawOS.command — Double-click launcher for macOS
# Place this file inside the ClawOS folder

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Activate venv and run
if [ -f "$DIR/venv/bin/activate" ]; then
    source "$DIR/venv/bin/activate"
    python main.py
else
    echo "Virtual environment not found."
    echo "Run ./install.sh first."
    echo ""
    read -p "Press Enter to close..."
fi
