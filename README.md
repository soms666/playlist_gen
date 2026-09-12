# Gen Playlist

Gen Playlist is a local macOS Spotify playlist generator. You describe a mood or situation, Ollama interprets the prompt locally, and Spotify finds fresh tracks based on your listening taste. Generated playlists are private by default.

## Requirements

- macOS (the menu-bar app uses native macOS WebKit)
- Python 3.11+
- A Spotify account and a Spotify Developer application
- [Ollama](https://ollama.com/) with the configured model available:

```bash
ollama pull ornith:9b
```

The Spotify app must allow this redirect URI:

```text
http://127.0.0.1:8000/callback
```

The app uses Spotify Authorization Code with PKCE, so no Spotify client secret is required. Set `SPOTIFY_CLIENT_ID` if you want to use another client ID.

## Install

```bash
git clone <repository-url>
cd playlist_gen
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
ollama serve
```

## Run as a webserver

```bash
python3 app.py
```

Open <http://127.0.0.1:8000/> and log in with Spotify.

## Build the macOS menu-bar app

```bash
./build_app.sh
open "dist/Gen Playlist.app"
```

The app adds a **✦** menu-bar item. It can open the native GUI, open the web URL, restart the local server, start Ollama, and autostart at macOS login.

## Notes

- Spotify access and refresh tokens are kept in memory only.
- The local AI receives the user prompt, not the Spotify track history.
- The generated macOS app is unsigned, so macOS may show a warning when it is moved to another computer.
