"""Show the non-secret parts of the Apple Music token on the clipboard: header (alg, kid) and claims (iss, dates).
The signature is never printed.  Run: python3 scripts/apple_token_info.py"""
import base64
import json
import subprocess
from datetime import UTC, datetime

token = subprocess.run(["pbpaste"], capture_output=True, text=True).stdout.strip().removeprefix("Bearer ").strip()
parts = token.split(".")
if len(parts) != 3:
    raise SystemExit(f"Clipboard does not hold a token (found {len(parts)} parts). Run apple_music_token.py first.")


def decode(s: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)))


header, claims = decode(parts[0]), decode(parts[1])
print("header:", header)
print("claims:", {k: (datetime.fromtimestamp(v, UTC).isoformat() if k in ("iat", "exp") else v) for k, v in claims.items()})
