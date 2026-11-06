#!/usr/bin/env bash
# Webhook Scanner - Linux / Ubuntu Launcher

set -e

# Change to script directory
cd "$(dirname "$0")"

# Check if python3 is installed
if ! command -v python3 &>/dev/null; then
    echo "[!] Error: python3 is not installed. Run: sudo apt update && sudo apt install -y python3"
    exit 1
fi

# Set up virtual environment if it does not exist
if [ ! -d "venv" ]; then
    echo "[*] Setting up virtual environment..."
    python3 -m venv venv 2>/dev/null || {
        echo "[!] Need python3-venv. Installing..."
        sudo apt update && sudo apt install -y python3-venv python3-pip
        python3 -m venv venv
    }
fi

# Activate virtual environment
source venv/bin/activate

# Install requirements if requests is missing
if ! python3 -c "import requests" &>/dev/null; then
    echo "[*] Installing dependencies from requirements.txt..."
    pip install -r requirements.txt
fi

# Run CMD interactive shell by default or pass arguments
if [ $# -eq 0 ]; then
    python3 github_cmd.py
else
    python3 github_cmd.py "$@"
fi
