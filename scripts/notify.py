#!/usr/bin/env python3
"""Passive cross-platform sound hooks. Never change an agent's decisions."""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import time

SOUNDS = ("complete", "input", "approval")
ASSETS = Path(__file__).resolve().parents[1] / "assets"
PLAYBACK_BUDGET = 5
WINDOWS_PLAYER = (
    "import sys,winsound;"
    "winsound.PlaySound(sys.argv[1],winsound.SND_FILENAME|winsound.SND_NODEFAULT)"
)
QUESTION = re.compile(r"(?:^|[.__])(?:request_user_input(?:_async)?|AskUserQuestion)$")


def classify(event):
    name = event.get("hook_event_name")
    if name == "Stop":
        return "complete"
    if name == "PermissionRequest":
        return "approval"
    if name == "PreToolUse" and QUESTION.search(str(event.get("tool_name", ""))):
        return "input"
    return None


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def claim(event, kind, directory, now=None):
    """Atomically deduplicate callbacks; persist hashes, not prompts or commands."""
    now = time.time() if now is None else now
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    scope = fingerprint([event.get("session_id"), event.get("turn_id")])
    identity = event.get("tool_use_id") or fingerprint(event.get("tool_input"))
    key = fingerprint([scope, kind, identity if kind != "complete" else None])
    # A missing turn id should not suppress future turns for an entire day.
    ttl = 86400 if event.get("turn_id") and (kind == "complete" or event.get("tool_use_id")) else 3
    # sqlite's transaction context alone does not close the handle on Windows.
    with closing(sqlite3.connect(str(directory / "events.sqlite3"), timeout=0.2)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS events (key TEXT PRIMARY KEY, scope TEXT, kind TEXT, at REAL)")
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM events WHERE at < ?", (now - 86400,))
        row = db.execute("SELECT at FROM events WHERE key = ?", (key,)).fetchone()
        if row and 0 <= now - row[0] < ttl:
            return False
        # Async questions can be immediately followed by Stop; keep the question sound.
        if kind == "complete" and db.execute(
            "SELECT 1 FROM events WHERE scope = ? AND kind = 'input' AND at > ?", (scope, now - 3)
        ).fetchone():
            return False
        db.execute("INSERT OR REPLACE INTO events VALUES (?, ?, ?, ?)", (key, scope, kind, now))
        db.execute("DELETE FROM events WHERE key IN (SELECT key FROM events ORDER BY at DESC LIMIT -1 OFFSET 2048)")
    return True


def data_directory():
    override = os.environ.get("PLUGIN_DATA") or os.environ.get("CLAUDE_PLUGIN_DATA")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData/Local")) / "codex-sounds"
    if sys.platform == "darwin":
        return Path.home() / "Library/Caches/codex-sounds"
    cache = os.environ.get("XDG_CACHE_HOME", "")
    root = Path(cache) if cache and Path(cache).is_absolute() else Path.home() / ".cache"
    return root / "codex-sounds"


def player_commands(sound):
    if sys.platform == "darwin":
        return [["/usr/bin/afplay", str(sound)]]
    if sys.platform == "win32":
        # Keep synchronous winsound alive in a bounded child process.
        return [[sys.executable, "-c", WINDOWS_PLAYER, str(sound)]]
    if sys.platform.startswith("linux"):
        commands = []
        for name in ("pw-play", "paplay", "aplay"):
            executable = shutil.which(name)
            if executable:
                commands.append([executable, str(sound)])
        return commands
    return []


def play(kind):
    if kind not in SOUNDS:
        return False
    sound = ASSETS / (kind + ".wav")
    if not sound.is_file():
        print("codex-sounds: missing WAV asset", file=sys.stderr)
        return False
    commands = player_commands(sound)
    deadline = time.monotonic() + PLAYBACK_BUDGET
    for index, command in enumerate(commands):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        # Reserve time for Linux fallbacks if an installed server is unavailable.
        timeout = min(2, remaining) if index < len(commands) - 1 else remaining
        try:
            options = {}
            if sys.platform == "win32":
                options["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            result = subprocess.run(
                command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=timeout, check=False, **options,
            )
            if result.returncode == 0:
                return True
        except (OSError, subprocess.TimeoutExpired):
            pass
    print("codex-sounds: no working audio backend; check player and audio session", file=sys.stderr)
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", choices=SOUNDS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.preview:
        return 0 if play(args.preview) else 1
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            raise ValueError("expected an event object")
        kind = classify(event)
        if args.dry_run:
            print(json.dumps({"sound": kind}))
            return 0
        if kind and os.environ.get("CODEX_SOUNDS_MUTE") != "1":
            if claim(event, kind, data_directory()):
                play(kind)
    except Exception as error:
        # Audio failure must not change tool decisions or interrupt work.
        print("codex-sounds: " + type(error).__name__, file=sys.stderr)
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
