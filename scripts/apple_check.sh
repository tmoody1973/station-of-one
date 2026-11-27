#!/usr/bin/env bash
# Sign a fresh Apple Music developer token, ask Apple if it works (prints only the HTTP status),
# and copy the bare token to the clipboard for the Sprites "Apple Music" connector.
# Usage: bash scripts/apple_check.sh [--bearer] [path/to/AuthKey_2N39U995V2.p8]
# --bearer copies "Bearer <token>" (for a connector whose prefix field is empty).
set -euo pipefail
cd "$(dirname "$0")/.."
KEY_ID=2N39U995V2
TEAM_ID=PNMWMBQ26H
MODE=--bare
if [ "${1:-}" = "--bearer" ]; then MODE=""; shift; fi
KEY="${1:-}"
if [ -z "$KEY" ]; then
  for d in ~/Keys ~/Downloads ~/Desktop ~/Documents; do
    [ -f "$d/AuthKey_$KEY_ID.p8" ] && KEY="$d/AuthKey_$KEY_ID.p8" && break
  done
fi
[ -n "$KEY" ] || { echo "Could not find AuthKey_$KEY_ID.p8 in ~/Keys, ~/Downloads, ~/Desktop or ~/Documents. Pass its path: bash scripts/apple_check.sh /path/to/AuthKey_$KEY_ID.p8"; exit 1; }
echo "Using key file: $KEY"
uv run -q --with pyjwt --with cryptography scripts/apple_music_token.py --key "$KEY" --key-id "$KEY_ID" --team-id "$TEAM_ID" $MODE --check
