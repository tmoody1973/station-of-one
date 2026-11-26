"""Tiny Sprites-gateway helper for the spikes. Stdlib only.

Runs only inside the Sprite: the gateway identifies the caller from Fly's request
signature, so no Authorization header is sent and no key exists here.
"""
import json
import sys
import urllib.error
import urllib.request

LIST_URL = "https://api.sprites.dev/v1/gateway/list"


def connection(provider: str) -> dict:
    """Return the gateway listing entry for a connected provider, or exit with a clear message."""
    with urllib.request.urlopen(LIST_URL, timeout=30) as r:
        listing = json.load(r)
    for c in listing.get("connections", []):
        if c.get("provider") == provider:
            return c
    sys.exit(f"No '{provider}' connection is visible to this Sprite. "
             f"Add it in the Fly dashboard and grant this Sprite access. "
             f"Connected now: {[c.get('provider') for c in listing.get('connections', [])]}")


def call(method: str, url: str, body=None, headers=None, timeout=120):
    """Send a request; return (status, headers, raw bytes). Never raises on HTTP errors."""
    data = None
    hdrs = dict(headers or {})
    if body is not None and not isinstance(body, (bytes, bytearray)):
        data = json.dumps(body).encode()
        hdrs.setdefault("Content-Type", "application/json")
    elif body is not None:
        data = bytes(body)
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()
