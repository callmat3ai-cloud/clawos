#!/bin/bash
# install.sh — ClawOS macOS Install Script
# Run from the ClawOS directory after cloning

set -e

echo "⚡ ClawOS Installer for macOS"
echo "=============================="
echo ""

# Detect OS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "⚠️  This script is for macOS. For other platforms, see README."
fi

# Check Python version
PYTHON=$(command -v python3 || command -v python)
if [ -z "$PYTHON" ]; then
    echo "❌ Python not found. Install from python.org or: brew install python"
    exit 1
fi

PYTHON_VERSION=$($PYTHON --version 2>&1 | awk '{print $2}')
echo "✓ Python $PYTHON_VERSION detected"

# Require Python 3.10+
PY_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PY_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]); then
    echo "❌ Python 3.10+ required. You have $PYTHON_VERSION"
    echo "   Update: brew install python@3.12"
    exit 1
fi

# Step 1: Create virtual environment
echo ""
echo "📦 Step 1: Creating virtual environment..."
if [ -d "venv" ]; then
    echo "   (Removing existing venv)"
    rm -rf venv
fi
$PYTHON -m venv venv
source venv/bin/activate

# Step 2: Upgrade pip
echo "📦 Step 2: Upgrading pip..."
pip install --upgrade pip

# Step 3: Install requirements
echo "📦 Step 3: Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# macOS: install portaudio for sounddevice
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "📦 Step 3b: Installing macOS audio dependencies..."
    if command -v brew &> /dev/null; then
        brew install portaudio 2>/dev/null || true
        echo "   ✅ portaudio installed (or already present)"
    else
        echo "   ⚠️  Homebrew not found — install portaudio manually if voice doesn't work"
        echo "       brew install portaudio"
    fi
fi

# Step 4: Create config directory
echo "📦 Step 4: Creating config..."
mkdir -p config

# Step 5: Create api_keys.json if it doesn't exist
if [ ! -f "config/api_keys.json" ]; then
    echo '{
  "gemini_api_key": "",
  "composio_api_key": ""
}' > config/api_keys.json
    echo "   ✅ Created config/api_keys.json — add your API keys"
else
    echo "   ✅ config/api_keys.json already exists"
fi

# Step 6: Install Composio CLI
echo "📦 Step 5: Installing Composio CLI..."
pip install composio-cli || true
composio --version 2>/dev/null && echo "   ✅ Composio CLI installed" || echo "   ⚠️  Composio CLI not installed (optional)"

# Step 7: Verify PyQt6
echo "📦 Step 6: Verifying PyQt6..."
python3 -c "from PyQt6.QtWidgets import QApplication; print('   ✅ PyQt6 OK')" || {
    echo "❌ PyQt6 failed to install. Try: pip install PyQt6 --force-reinstall"
    exit 1
}

echo ""
echo "=============================="
echo "✅ Installation complete!"
echo ""
echo "Next steps:"
echo "1. Add your API keys to config/api_keys.json"
echo "   - Gemini: aistudio.google.com/apikey (free tier)"
echo "   - Composio: app.composio.dev/settings/api-keys (free: 20k/mo)"
echo ""
echo "2. Connect Composio apps (optional):"
echo "   source venv/bin/activate"
echo "   composio login"
echo "   composio connect gmail github slack"
echo ""
echo "3. Run ClawOS:"
echo "   source venv/bin/activate"
echo "   python main.py"
echo ""
echo "=============================="
