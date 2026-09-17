#!/bin/sh
# Prefer an independent Python on macOS over the Xcode-managed system shim.
ROOT=${PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-}}
if [ -z "$ROOT" ]; then
    ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd) || exit 0
fi
for candidate in /opt/homebrew/bin/python3 /usr/local/bin/python3 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 &&
       "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1; then
        exec "$candidate" -X utf8 "$ROOT/scripts/notify.py" "$@"
    fi
done
printf '%s\n' 'codex-sounds: Python 3.9+ is required' >&2
printf '{}\n'
exit 0
