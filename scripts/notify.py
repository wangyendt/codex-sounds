#!/usr/bin/env python3
"""Passive macOS sound hooks. Never approve, deny, or continue an agent turn."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time

SOUNDS = {"complete": "Glass", "input": "Ping", "approval": "Pop"}
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
    with sqlite3.connect(str(directory / "events.sqlite3"), timeout=0.2) as db:
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


def play(kind):
    if sys.platform != "darwin":
        return False
    sound = Path("/System/Library/Sounds") / (SOUNDS[kind] + ".aiff")
    if not sound.is_file():
        return False
    try:
        result = subprocess.run(
            ["/usr/bin/afplay", "-v", "0.5", str(sound)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=5, check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired) as error:
        print("codex-sounds: audio " + type(error).__name__, file=sys.stderr)
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
            directory = Path(os.environ.get("PLUGIN_DATA") or os.environ.get("CLAUDE_PLUGIN_DATA")
                             or str(Path.home() / "Library/Caches/codex-sounds"))
            if claim(event, kind, directory):
                play(kind)
    except Exception as error:
        # Audio failure must not change tool decisions or interrupt work.
        print("codex-sounds: " + type(error).__name__, file=sys.stderr)
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
