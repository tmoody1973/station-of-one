#!/usr/bin/env bash
# Plan C: put the MusicKit web token on the Sprite. Run on Tarik's Mac AFTER signing it with:
#   uv run --with pyjwt --with cryptography scripts/apple_music_token.py --key ~/Keys/AuthKey_XXXXXXXXXX.p8 \
#       --key-id XXXXXXXXXX --team-id PNMWMBQ26H --origin https://patient-mountain-3400.fly.storage.tigris.dev --bare --days 60
# The token is read from the clipboard and never printed. The next hourly build publishes /data/musickit.json.
set -euo pipefail
n=$(pbpaste | tr -d '[:space:]' | wc -c | tr -d ' ')
[ "$n" -gt 100 ] || { echo "Clipboard doesn't look like a token ($n characters). Sign it first."; exit 1; }
pbpaste | tr -d '[:space:]' | sprite exec -s brave-indigo-lion -- bash -c 'umask 077; cat > /home/sprite/station/data/musickit_token; wc -c < /home/sprite/station/data/musickit_token' | sed 's/^/bytes on the Sprite: /'
