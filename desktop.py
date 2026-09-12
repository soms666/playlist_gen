#!/usr/bin/env python3
"""Menu-bar launcher for the local Spotify playlist web app."""

import os
import plistlib
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

import rumps
from Cocoa import (
    NSApp,
    NSBackingStoreBuffered,
    NSMakeRect,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSURL, NSURLRequest
from WebKit import WKWebView

from app import Handler


HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}/"
OLLAMA_URL = "http://127.0.0.1:11434/api/tags"
server = None
ollama_process = None


def start_server():
    global server
    try:
        server = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError:
        server = None
        return False
    threading.Thread(target=server.serve_forever, name="playlist-webserver", daemon=True).start()
    return True


def restart_server():
    global server
    if server is not None:
        server.shutdown()
        server.server_close()
        server = None
    return start_server()


def ollama_running():
    try:
        with urlopen(OLLAMA_URL, timeout=1):
            return True
    except Exception:
        return False


def start_ollama():
    global ollama_process
    if ollama_running():
        return True
    try:
        ollama = shutil.which("ollama") or "/opt/homebrew/bin/ollama"
        ollama_process = subprocess.Popen(
            [ollama, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except FileNotFoundError:
        return False
    for _ in range(20):
        if ollama_running():
            return True
        time.sleep(0.25)
    return False


def install_autostart():
    if not getattr(sys, "frozen", False):
        return
    label = "com.genplaylist.app"
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "Label": label,
        "ProgramArguments": [sys.executable],
        "RunAtLoad": True,
        "KeepAlive": False,
        "LimitLoadToSessionType": "Aqua",
    }
    encoded = plistlib.dumps(data)
    if plist_path.exists() and plist_path.read_bytes() == encoded:
        return
    plist_path.write_bytes(encoded)
    uid = str(os.getuid())
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{label}"], capture_output=True)
    subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(plist_path)], capture_output=True)


class PlaylistGenMenuBar(rumps.App):
    def __init__(self):
        super().__init__("Gen Playlist", title="✦")
        self.menu = ["Open GUI", "Open Web URL", "Restart server", "Start Ollama"]
        self.gui_window = None

    @rumps.clicked("Open GUI")
    def open_gui(self, _):
        if self.gui_window is None:
            style = (
                NSWindowStyleMaskTitled
                | NSWindowStyleMaskClosable
                | NSWindowStyleMaskMiniaturizable
                | NSWindowStyleMaskResizable
            )
            self.gui_window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(0, 0, 1100, 760), style, NSBackingStoreBuffered, False
            )
            self.gui_window.setTitle_("Gen Playlist")
            self.gui_window.setReleasedWhenClosed_(False)
            self.gui_window.setContentView_(WKWebView.alloc().initWithFrame_(NSMakeRect(0, 0, 1100, 760)))
            self.gui_window.contentView().loadRequest_(NSURLRequest.requestWithURL_(NSURL.URLWithString_(URL)))
        self.gui_window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

    @rumps.clicked("Open Web URL")
    def open_web(self, _):
        webbrowser.open(URL)

    @rumps.clicked("Restart server")
    def restart(self, _):
        if restart_server():
            rumps.notification("Gen Playlist", "Server restarted", URL)
        else:
            rumps.notification("Gen Playlist", "Server could not start", f"Port {PORT} may already be in use")

    @rumps.clicked("Start Ollama")
    def start_ai(self, _):
        if start_ollama():
            rumps.notification("Gen Playlist", "Ollama is ready", "Local AI is available")
        else:
            rumps.notification("Gen Playlist", "Ollama could not start", "Is Ollama installed and on PATH?")

if __name__ == "__main__":
    install_autostart()
    start_ollama()
    start_server()
    PlaylistGenMenuBar().run()
