#!/usr/bin/env python3
"""Small local Spotify OAuth smoke test."""

import base64
import hashlib
import html
import http.server
import json
import os
import random
import secrets
import subprocess
import traceback
import urllib.parse
import urllib.request
import urllib.error


CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "ffbdc5b52bc949d596df17992ce2634e")
REDIRECT_URI = "http://127.0.0.1:8000/callback"
SCOPES = "user-read-private user-top-read user-read-recently-played playlist-modify-private"
AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_URL = "https://api.spotify.com/v1"
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "ornith:9b")

oauth_state = None
oauth_verifier = None
access_token = None
refresh_token = None


def spotify_json(url, *, method="GET", data=None, headers=None, timeout=20):
    # ponytail: use macOS curl/SecureTransport for the local Python CA-chain issue.
    command = ["curl", "--silent", "--show-error", "--fail-with-body", "--max-time", str(timeout), "--request", method, url]
    for name, value in (headers or {}).items():
        command.extend(["--header", f"{name}: {value}"])
    if data is not None:
        command.extend(["--data-binary", data])
    result = subprocess.run(
        command,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        details = result.stdout.decode("utf-8", "replace").strip()
        message = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"{message}: {details}" if details else message)
    return json.loads(result.stdout)


def start_login():
    global oauth_state, oauth_verifier
    oauth_state = secrets.token_urlsafe(24)
    oauth_verifier = secrets.token_urlsafe(64)
    challenge = base64_url(hashlib.sha256(oauth_verifier.encode()).digest())
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": oauth_state,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
    }
    return AUTH_URL + "?" + urllib.parse.urlencode(params)


def base64_url(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def exchange_code(code):
    global refresh_token
    body = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "code_verifier": oauth_verifier,
        }
    ).encode()
    result = spotify_json(
        TOKEN_URL,
        method="POST",
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    refresh_token = result.get("refresh_token")
    return result["access_token"]


def refresh_access_token():
    global access_token, refresh_token
    if not refresh_token:
        raise RuntimeError("No Spotify refresh token; login required")
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
    }).encode()
    result = spotify_json(
        TOKEN_URL,
        method="POST",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    access_token = result["access_token"]
    refresh_token = result.get("refresh_token", refresh_token)


def spotify_get(path):
    if not access_token:
        raise RuntimeError("Not logged in")
    try:
        return spotify_json(API_URL + path, headers={"Authorization": f"Bearer {access_token}"})
    except RuntimeError as error:
        if "401" not in str(error):
            raise
        refresh_access_token()
        return spotify_json(API_URL + path, headers={"Authorization": f"Bearer {access_token}"})


def spotify_post(path, payload):
    if not access_token:
        raise RuntimeError("Not logged in")
    try:
        return spotify_json(
            API_URL + path,
            method="POST",
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        )
    except RuntimeError as error:
        if "401" not in str(error):
            raise
        refresh_access_token()
        return spotify_json(
            API_URL + path,
            method="POST",
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        )


def track_list(title, tracks):
    rows = "".join(
        f"<li>{html.escape(track['name'])} — {html.escape(', '.join(a['name'] for a in track['artists']))}</li>"
        for track in tracks
    )
    return f"<h2>{html.escape(title)}</h2><ol>{rows}</ol>"


def taste_tracks():
    top = spotify_get("/me/top/tracks?limit=20&time_range=medium_term")["items"]
    recent = spotify_get("/me/player/recently-played?limit=20")["items"]
    return top, [item["track"] for item in recent]


def parse_prompt(prompt):
    instruction = (
        "Interpret the user's music request without using or assuming any Spotify data. "
        "Return JSON only with keys title, description, target_energy, target_valence, "
        "target_danceability, target_acousticness, novelty, search_queries. "
        "search_queries must be 6 short music-search phrases based only on the user's request. "
        "Numeric targets must be 0.0 to 1.0. "
        f"User request: {prompt}"
    )
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "stream": False,
        "format": "json",
        "messages": [{"role": "user", "content": instruction}],
    }).encode()
    result = spotify_json(OLLAMA_URL, method="POST", data=payload, headers={"Content-Type": "application/json"}, timeout=120)
    return json.loads(result["message"]["content"])


def search_artist(artist):
    query = urllib.parse.quote(f"artist:{artist}")
    return spotify_get(f"/search?q={query}&type=track&limit=5")["tracks"]["items"]


def search_tracks(query):
    encoded = urllib.parse.quote(query)
    return spotify_get(f"/search?q={encoded}&type=track&limit=10")["tracks"]["items"]


def random_artists(limit=100):
    artists = {}
    queries = ["a", "e", "i", "o", "u", "n", "r", "s", "m", "t", "pop", "rock", "jazz", "electronic"]
    for _ in range(4):
        params = {
            "q": random.choice(queries),
            "type": "artist",
            "limit": 50,
            "offset": random.randrange(0, 1000, 50),
        }
        try:
            result = spotify_get("/search?" + urllib.parse.urlencode(params))
        except RuntimeError as error:
            print(f"artist pool search skipped: {error}")
            continue
        for artist in result.get("artists", {}).get("items", []):
            if artist.get("name"):
                artists[artist["id"]] = artist["name"]
        if len(artists) >= limit:
            break
    if len(artists) < limit:
        try:
            for artist in spotify_get("/me/top/artists?limit=50&time_range=medium_term").get("items", []):
                if artist.get("name"):
                    artists[artist["id"]] = artist["name"]
        except RuntimeError as error:
            print(f"top artist fallback skipped: {error}")
    if len(artists) < limit:
        try:
            top, recent = taste_tracks()
            for track in top + recent:
                for artist in track.get("artists", []):
                    if artist.get("name"):
                        artists[artist["id"]] = artist["name"]
        except RuntimeError as error:
            print(f"taste artist fallback skipped: {error}")
    names = list(artists.values())
    random.shuffle(names)
    return names[:limit]


def spotify_recommendations(preferences, top):
    artists = []
    tracks = []
    for item in top:
        if item["id"] not in tracks:
            tracks.append(item["id"])
        for artist in item["artists"]:
            if artist["id"] not in artists:
                artists.append(artist["id"])
    params = {
        "limit": "30",
        "seed_artists": ",".join(artists[:3]),
        "seed_tracks": ",".join(tracks[:2]),
    }
    for name in ("target_energy", "target_valence", "target_danceability", "target_acousticness"):
        value = preferences.get(name)
        if isinstance(value, (int, float)):
            params[name] = str(max(0, min(1, value)))
    return spotify_get("/recommendations?" + urllib.parse.urlencode(params))["tracks"]


def generate_playlist_idea(prompt):
    top, recent = taste_tracks()
    history = {track["id"]: track for track in top + recent}
    preferences = parse_prompt(prompt)
    try:
        discovered = spotify_recommendations(preferences, top)
    except RuntimeError:
        discovered = []
        queries = [query for query in preferences.get("search_queries", []) if isinstance(query, str) and query.strip()]
        for artist in {artist["id"] for track in top[:5] for artist in track["artists"]}:
            try:
                genres = spotify_get(f"/artists/{artist}").get("genres", [])
                queries.extend(f"genre:{genre}" for genre in genres[:2])
            except RuntimeError:
                continue
        for query in queries[:12]:
            discovered.extend(search_tracks(query))
    discovered = {track["id"]: track for track in discovered if track["id"] not in history}
    unique = {}
    for track in discovered.values():
        key = (track["name"].strip().casefold(), tuple(a["name"].strip().casefold() for a in track["artists"]))
        unique.setdefault(key, track)
    tracks = list(unique.values())[:20]
    if not tracks:
        raise RuntimeError("Spotify returned no new discovery tracks")
    pool = {track["id"]: track for track in tracks}
    idea = {
        "title": preferences.get("title", "New discoveries"),
        "description": preferences.get("description", "New music based on your Spotify taste."),
        "track_ids": [track["id"] for track in tracks],
    }
    return idea, pool


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"{self.address_string()} - {format % args}")

    def send_page(self, title, body, status=200, show_back=True):
        back = "<a href='/' class='back'>← Back to start</a>" if show_back else ""
        content = f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{title}</title><style>:root{{color-scheme:dark}}*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;overflow-x:hidden;background:radial-gradient(circle at top,#26345e 0,#0d1020 42%,#080a12 100%);color:#f5f7ff;font:16px system-ui,sans-serif}}body:before,body:after{{content:'';position:fixed;z-index:-1;width:42vw;height:42vw;border-radius:50%;filter:blur(70px);opacity:.28;pointer-events:none;animation:float 18s ease-in-out infinite alternate}}body:before{{background:#687cff;top:-14vw;left:-10vw}}body:after{{background:#c26dff;right:-12vw;bottom:-18vw;animation-delay:-7s}}.space{{position:fixed;z-index:-1;width:18vw;height:18vw;border-radius:50%;background:#38d8c8;filter:blur(80px);opacity:.13;right:26vw;top:42vh;pointer-events:none;animation:drift 24s ease-in-out infinite alternate}}.shell{{max-width:860px;margin:auto;padding:56px 22px 80px}}.nav{{display:flex;justify-content:space-between;align-items:center;margin-bottom:64px;color:#aeb7d4}}.brand{{font-weight:800;letter-spacing:.04em;color:#fff;text-decoration:none}}.back{{color:#aebdff;text-decoration:none;font-size:14px}}a{{color:#aebdff}}.hero{{margin-bottom:28px}}.eyebrow{{color:#9baaff;text-transform:uppercase;letter-spacing:.14em;font-size:12px;font-weight:700}}h1{{font-size:clamp(34px,7vw,64px);line-height:1.02;margin:12px 0}}h2{{margin-top:0}}.muted{{color:#aeb7d4;line-height:1.6}}.card{{background:rgba(22,27,50,.82);border:1px solid rgba(171,185,255,.18);border-radius:24px;padding:26px;box-shadow:0 20px 70px rgba(0,0,0,.28);backdrop-filter:blur(14px)}}textarea{{width:100%;resize:vertical;background:#0c1020;color:#fff;border:1px solid #39446e;border-radius:14px;padding:16px;font:inherit;line-height:1.5}}button{{border:0;border-radius:999px;padding:12px 18px;background:linear-gradient(135deg,#8b9cff,#b67cff);color:#0b0d18;font-weight:800;cursor:pointer;margin-top:14px;transition:transform .2s,box-shadow .2s}}button:hover{{transform:translateY(-2px);box-shadow:0 10px 28px rgba(157,133,255,.32)}}button:disabled{{opacity:.6;cursor:wait}}.generate-btn{{animation:glow 2.4s ease-in-out infinite}}.secondary{{background:#293354;color:#e9ecff}}#status{{margin-top:16px;color:#aeb7d4;display:flex;align-items:center;gap:8px;min-height:20px}}.spinner{{width:14px;height:14px;border:2px solid #46517a;border-top-color:#fff;border-radius:50%;animation:spin .8s linear infinite}}.artist-cloud{{position:fixed;inset:0;z-index:20;overflow:hidden;pointer-events:none;background:radial-gradient(circle,rgba(17,23,53,.2),rgba(5,7,17,.78));backdrop-filter:blur(3px)}}.artist-cloud-title{{position:absolute;top:10%;width:100%;text-align:center;color:#dce2ff;font-size:clamp(16px,3vw,28px);font-weight:800;letter-spacing:.08em;text-transform:uppercase;text-shadow:0 0 24px #8d9cff}}.artist-chip{{position:absolute;transform:translate(-50%,-50%) scale(.75);opacity:.45;padding:7px 13px;border:1px solid rgba(190,201,255,.3);border-radius:999px;background:rgba(34,43,86,.82);color:#eef0ff;white-space:nowrap;box-shadow:0 0 22px rgba(130,145,255,.32);animation:pop-artist 2.4s cubic-bezier(.2,.8,.25,1.1) infinite}}@keyframes spin{{to{{transform:rotate(360deg)}}}}@keyframes float{{to{{transform:translate(12vw,8vh) scale(1.2)}}}}@keyframes drift{{to{{transform:translate(-16vw,-10vh) scale(.8)}}}}@keyframes glow{{0%,100%{{box-shadow:0 0 0 rgba(167,143,255,0)}}50%{{box-shadow:0 0 26px rgba(167,143,255,.38)}}}}@keyframes pop-artist{{0%{{opacity:.35;transform:translate(-50%,-50%) scale(.78) rotate(-5deg)}}45%{{opacity:1;transform:translate(-50%,-50%) scale(1.08) rotate(2deg)}}100%{{opacity:.52;transform:translate(-50%,-50%) scale(.9) rotate(-1deg)}}}}</style></head><body><div class='space'></div><main class='shell'><nav class='nav'><a href='/' class='brand'>✦ GEN PLAYLIST</a>{back}</nav>{body}</main></body></html>"
        encoded = content.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        global access_token, oauth_state
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)

        try:
            if parsed.path == "/":
                if not access_token:
                    self.send_response(302)
                    self.send_header("Location", "/login")
                    self.end_headers()
                    return
                body = """<section class='hero'><div class='eyebrow'>Your personal discovery engine</div><h1>Find your next favorite song.</h1><p class='muted'>Describe the mood, moment or adventure. Local AI interprets your prompt; Spotify finds the music.</p></section><section class='card'><form id='generator' method='post' action='/generate' onsubmit='generatePlaylist(event, this)'><label class='muted'>What do you want to hear?<br><textarea name='prompt' rows='4'>Create a dark, melodic playlist for an evening drive.</textarea></label><br><button class='generate-btn' type='submit'>Generate playlist</button><div id='status' aria-live='polite'></div></form></section><p class='muted'><a href='/taste'>Explore my Spotify taste</a></p><script>
async function generatePlaylist(event, form) {
  event.preventDefault();
  const button = form.querySelector('button');
  const status = document.getElementById('status');
  const previewArtists = ['Radiohead', 'Björk', 'Tame Impala', 'The Weeknd', 'Massive Attack', 'M83', 'James Blake', 'Fleetwood Mac', 'Sade', 'Lana Del Rey', 'Arctic Monkeys', 'Daft Punk', 'Portishead', 'Frank Ocean', 'Phoenix', 'Solange', 'Bonobo', 'The xx', 'Kendrick Lamar', 'Beach House'];
  button.disabled = true;
  button.textContent = 'Searching…';
  status.innerHTML = '<span class="spinner"></span> Finding artists on Spotify…';
  showArtistCloud(previewArtists);
  try {
    const poolResponse = await fetch('/artist-pool');
    if (!poolResponse.ok) throw new Error('Spotify login required');
    const pool = await poolResponse.json();
    showArtistCloud(pool.artists.length ? pool.artists : previewArtists);
    button.textContent = 'Building playlist…';
    status.innerHTML = '<span class="spinner"></span> Building your playlist from fresh discoveries…';
    const result = await fetch(form.action, {method: 'POST', body: new URLSearchParams(new FormData(form))});
    document.open();
    document.write(await result.text());
    document.close();
  } catch (error) {
    button.disabled = false;
    button.textContent = 'Generate playlist';
    status.textContent = 'Could not start generation: ' + error.message;
  }
}
function showArtistCloud(artists) {
  document.querySelector('.artist-cloud')?.remove();
  const cloud = document.createElement('div');
  cloud.className = 'artist-cloud';
  cloud.innerHTML = '<div class="artist-cloud-title">Searching the Spotify universe</div>';
  artists.forEach((artist, index) => {
    const chip = document.createElement('span');
    chip.className = 'artist-chip';
    chip.textContent = artist;
    chip.style.left = (5 + Math.random() * 90) + '%';
    chip.style.top = (18 + Math.random() * 72) + '%';
    chip.style.fontSize = (12 + Math.random() * 14) + 'px';
    chip.style.animationDelay = (index * 0.035) + 's';
    cloud.appendChild(chip);
  });
  document.body.appendChild(cloud);
}
</script>"""
                self.send_page("Spotify playlist AI", body, show_back=False)
            elif parsed.path == "/login":
                self.send_response(302)
                self.send_header("Location", start_login())
                self.end_headers()
            elif parsed.path == "/callback":
                if query.get("state", [None])[0] != oauth_state:
                    raise ValueError("OAuth state mismatch")
                access_token = exchange_code(query["code"][0])
                self.send_response(302)
                self.send_header("Location", "/")
                self.end_headers()
            elif parsed.path == "/artist-pool":
                if not access_token:
                    self.send_response(401)
                    self.end_headers()
                    return
                payload = json.dumps({"artists": random_artists()}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            elif parsed.path == "/me":
                if not access_token:
                    self.send_page("Not logged in", "<a href='/login'>Login with Spotify</a>", 401)
                    return
                profile = spotify_get("/me")
                self.send_page("Spotify profile", f"<h1>Logged in</h1><p>User: {profile.get('display_name') or profile.get('id')}</p>")
            elif parsed.path == "/taste":
                top, recent_tracks = taste_tracks()
                body = "<h1>My Spotify taste</h1>" + track_list("Top tracks", top) + track_list("Recently played", recent_tracks)
                self.send_page("My Spotify taste", body)
            else:
                self.send_page("Not found", "Not found", 404)
        except Exception as error:
            traceback.print_exc()
            self.send_page("Error", f"<h1>Login failed</h1><pre>{error}</pre>", 500)

    def do_POST(self):
        try:
            if self.path == "/create-playlist":
                length = int(self.headers.get("Content-Length", "0"))
                form = urllib.parse.parse_qs(self.rfile.read(length).decode())
                title = form.get("title", ["New discoveries"])[0][:100]
                description = form.get("description", [""])[0][:300]
                track_ids = [track_id for track_id in form.get("track_ids", [""])[0].split(",") if track_id]
                playlist = spotify_post("/me/playlists", {"name": title, "description": description, "public": False})
                spotify_post(f"/playlists/{playlist['id']}/items", {"uris": [f"spotify:track:{track_id}" for track_id in track_ids]})
                spotify_url = playlist["external_urls"]["spotify"]
                app_url = f"spotify:playlist:{playlist['id']}"
                self.send_page("Playlist created", f"<section class='hero'><div class='eyebrow'>Ready to play</div><h1>Playlist created.</h1><p class='muted'>Your private playlist is ready in Spotify.</p><div class='actions'><a href='{html.escape(app_url, quote=True)}'><button>Open in Spotify app</button></a><a href='{html.escape(spotify_url, quote=True)}'><button class='secondary'>Open web fallback</button></a></div></section>")
                return
            if self.path != "/generate":
                self.send_page("Not found", "Not found", 404)
                return
            if not access_token:
                self.send_response(303)
                self.send_header("Location", "/login")
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length", "0"))
            form = urllib.parse.parse_qs(self.rfile.read(length).decode())
            prompt = form.get("prompt", [""])[0].strip()
            if not prompt:
                self.send_page("Missing request", "<h1>Write what you want to hear.</h1>", 400)
                return
            idea, candidates = generate_playlist_idea(prompt)
            selected = [candidates[track_id] for track_id in idea.get("track_ids", []) if track_id in candidates]
            title = idea.get("title", "Playlist idea")
            description = idea.get("description", "")
            ids = ",".join(track["id"] for track in selected)
            create_form = f"<form method='post' action='/create-playlist'><input type='hidden' name='title' value='{html.escape(title, quote=True)}'><input type='hidden' name='description' value='{html.escape(description, quote=True)}'><input type='hidden' name='track_ids' value='{html.escape(ids, quote=True)}'><button type='submit'>Create and open in Spotify</button></form>"
            body = f"<section class='hero'><div class='eyebrow'>Your next soundtrack</div><h1>{html.escape(title)}</h1><p class='muted'>{html.escape(description)}</p></section><section class='card'>{track_list('Tracks', selected)}{create_form}</section><p class='muted'><a href='/'>Create another</a></p>"
            self.send_page("Playlist idea", body)
        except Exception as error:
            traceback.print_exc()
            self.send_page("Error", f"<h1>Generation failed</h1><pre>{html.escape(str(error))}</pre>", 500)


if __name__ == "__main__":
    print("Open http://127.0.0.1:8000/ in your browser")
    http.server.ThreadingHTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
