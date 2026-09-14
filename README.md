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

The app uses Spotify Authorization Code with PKCE, so no Spotify client secret is required. Set `spotify.client_id` in `config.toml` for your own Spotify app.

## Create your own Spotify API app

Every user running a local copy needs their own Spotify Developer application. Spotify access tokens belong to the person who logs in and are not shared by this repository.

1. Sign in at <https://developer.spotify.com/dashboard>.
2. Create a new app.
3. Add `http://127.0.0.1:8000/callback` as the Redirect URI.
4. Copy the app's Client ID into `config.toml`:

```toml
[spotify]
client_id = "YOUR_SPOTIFY_CLIENT_ID"
```

The Client Secret is not needed because the application uses Spotify's PKCE login flow. Each user authorizes the app with their own Spotify account when they log in.

## Install

```bash
git clone <repository-url>
cd playlist_gen
cp config.toml.example config.toml
# Edit config.toml with your Spotify client ID and local settings.
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

The build copies `config.toml` to `~/Library/Application Support/Gen Playlist/` so the packaged app can find it even when macOS starts it automatically. The app adds a **✦** menu-bar item. It can open the native GUI, open the web URL, restart the local server, start Ollama, and autostart at macOS login.

## Notes

- Spotify access and refresh tokens are kept in memory only.
- The local AI receives the user prompt, not the Spotify track history.
- The generated macOS app is unsigned, so macOS may show a warning when it is moved to another computer.
