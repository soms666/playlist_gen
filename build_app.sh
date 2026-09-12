#!/bin/zsh
set -e
cd "$(dirname "$0")"
.venv/bin/pyinstaller --noconfirm --clean --windowed --name "Gen Playlist" desktop.py
echo "Built: dist/Gen Playlist.app"
