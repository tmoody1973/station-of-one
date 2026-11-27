"""Sign an Apple Music developer token on your own Mac and copy it to the clipboard. Never prints it.

Apple docs (Generating Developer Tokens): ES256, header kid = Key ID, claims iss = Team ID, iat, exp at most
15,777,000 s (6 months) ahead. --origin adds the origin claim for a web player (MusicKit on JS, Plan C).

  uv run --with pyjwt --with cryptography scripts/apple_music_token.py \
      --key ~/Keys/AuthKey_XXXXXXXXXX.p8 --key-id XXXXXXXXXX --team-id PNMWMBQ26H

Then paste into the Sprites "Apple Music" Custom API connector as the Authorization header value.
"""
import argparse
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import jwt

MAX_SECONDS = 15_777_000  # Apple's limit
DAYS = 180

p = argparse.ArgumentParser()
p.add_argument("--key", required=True, type=Path, help="AuthKey_XXXXXXXXXX.p8 from Apple")
p.add_argument("--key-id", required=True)
p.add_argument("--team-id", required=True)
p.add_argument("--days", type=int, default=DAYS)
p.add_argument("--origin", action="append", help="web origin allowed to use the token (repeatable)")
p.add_argument("--bare", action="store_true", help="copy only the token, without the 'Bearer ' prefix")
a = p.parse_args()

now = int(time.time())
exp = now + min(a.days * 86400, MAX_SECONDS)
claims = {"iss": a.team_id, "iat": now, "exp": exp}
if a.origin:
    claims["origin"] = a.origin
token = jwt.encode(claims, a.key.expanduser().read_bytes(), algorithm="ES256", headers={"kid": a.key_id})
subprocess.run(["pbcopy"], input=(token if a.bare else f"Bearer {token}").encode(), check=True)
print(f"Copied a developer token to the clipboard ({'token only' if a.bare else 'with Bearer prefix'}).")
print(f"Key ID {a.key_id}, Team ID {a.team_id}, expires {datetime.fromtimestamp(exp, UTC):%Y-%m-%d}."
      + (f" Origins: {', '.join(a.origin)}." if a.origin else ""))
