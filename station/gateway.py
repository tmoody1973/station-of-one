"""Every outside call goes through the Sprites connector gateway.

The gateway identifies this Sprite from Fly's request signature and attaches the stored
credential, so no key ever exists here and no Authorization header is sent.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

LIST_URL = "https://api.sprites.dev/v1/gateway/list"
RETRY_STATUSES = {429, 500, 502, 503, 504, 529}
BACKOFF_S = (2, 4, 8)


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str]
    body: bytes


class GatewayError(Exception):
    def __init__(self, provider: str, status: int, body: str):
        super().__init__(f"{provider}: HTTP {status}: {body[:200]}")
        self.provider = provider
        self.status = status
        self.body = body[:500]


class Gateway:
    def __init__(self, list_url: str = LIST_URL, sleep: Callable[[float], None] = time.sleep,
                 urlopen: Callable = urllib.request.urlopen):
        self._list_url = list_url
        self._sleep = sleep
        self._urlopen = urlopen
        self._bases: dict[str, str] | None = None

    def base(self, provider: str) -> str:
        if self._bases is None:
            with self._urlopen(self._list_url, timeout=30) as r:
                listing = json.loads(r.read())
            conns = listing.get("connections", [])
            self._bases = {c["provider"]: c["gateway_base_url"].rstrip("/") for c in conns}
            # a connection id also works, for providers with more than one connector (custom_api)
            self._bases.update({c["id"]: c["gateway_base_url"].rstrip("/") for c in conns if c.get("id")})
        if provider not in self._bases:
            raise GatewayError(provider, 0, f"no '{provider}' connector is visible to this Sprite; "
                                            f"add it in the Fly dashboard and grant access")
        return self._bases[provider]

    def request(self, method: str, provider: str, path: str, body: Any = None,
                headers: dict | None = None, timeout: float = 120) -> Response:
        hdrs = dict(headers or {})
        data = None
        if isinstance(body, (bytes, bytearray)):
            data = bytes(body)
        elif body is not None:
            data = json.dumps(body).encode()
            hdrs.setdefault("Content-Type", "application/json")
        url = self.base(provider) + path
        for attempt in range(len(BACKOFF_S) + 1):
            req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
            try:
                with self._urlopen(req, timeout=timeout) as r:
                    return Response(r.status, dict(r.headers), r.read())
            except urllib.error.HTTPError as e:
                resp = Response(e.code, dict(e.headers or {}), e.read())
                if e.code not in RETRY_STATUSES or attempt == len(BACKOFF_S):
                    return resp
                self._sleep(self._wait(resp, attempt))
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt == len(BACKOFF_S):
                    raise GatewayError(provider, 0, f"network error: {e}") from e
                self._sleep(BACKOFF_S[attempt])
        raise AssertionError("unreachable")

    def json(self, method: str, provider: str, path: str, body: Any = None, timeout: float = 120) -> Any:
        r = self.request(method, provider, path, body, timeout=timeout)
        if not 200 <= r.status < 300:
            raise GatewayError(provider, r.status, r.body.decode(errors="replace"))
        return json.loads(r.body) if r.body else None

    @staticmethod
    def _wait(resp: Response, attempt: int) -> float:
        retry_after = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
        return BACKOFF_S[attempt]
