#!/bin/zsh
set -e
cd "$(dirname "$0")"
config_dir="$HOME/Library/Application Support/Gen Playlist"
mkdir -p "$config_dir"
cp config.toml "$config_dir/config.toml"
.venv/bin/pyinstaller --noconfirm --clean --windowed --name "Gen Playlist" desktop.py
echo "Built: dist/Gen Playlist.app"
