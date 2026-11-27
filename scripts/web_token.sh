#!/usr/bin/env bash
# Plan C, one step: sign the MusicKit web token (origin-locked, 60 days) and put it on the Sprite.
# Run on Tarik's Mac from the project folder:  ./scripts/web_token.sh  [path/to/AuthKey.p8]
# The token goes clipboard -> Sprite and is never printed. Re-run every 60 days (next: late January).
set -euo pipefail
KEY="${1:-$HOME/Keys/AuthKey_2N39U995V2.p8}"
[ -f "$KEY" ] || { echo "Key not found: $KEY"; exit 1; }
cd "$(dirname "$0")/.."
uv run --with pyjwt --with cryptography scripts/apple_music_token.py --key "$KEY" --key-id 2N39U995V2 --team-id PNMWMBQ26H \
  --origin https://patient-mountain-3400.fly.storage.tigris.dev --bare --days 60
./scripts/set_web_token.sh
