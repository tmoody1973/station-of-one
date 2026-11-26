"""Test doubles for gateway calls. Real code paths, fake network."""
from __future__ import annotations

import io
import json
import urllib.error
from typing import Any

from station.gateway import Response


class _Resp:
    def __init__(self, r: Response):
        self.status = r.status
        self.headers = r.headers
        self._body = r.body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_urlopen(listing: dict, responses: list[Response] | None = None, seen: list | None = None):
    """urlopen stand-in: the gateway listing URL returns `listing`; other URLs pop `responses`."""
    queue = list(responses or [])

    def urlopen(req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        if seen is not None:
            seen.append(req)
        if url.endswith("/v1/gateway/list"):
            return _Resp(Response(200, {}, json.dumps(listing).encode()))
        r = queue.pop(0)
        if isinstance(r, Exception):
            raise r
        if r.status >= 400:
            raise urllib.error.HTTPError(url, r.status, "err", r.headers, io.BytesIO(r.body))
        return _Resp(r)

    return urlopen


LISTING = {"connections": [
    {"provider": p, "gateway_base_url": f"https://api.sprites.dev/v1/gateway/{p}/conn-{p}"}
    for p in ("typesafe", "gemini", "apify", "ollama", "anthropic", "tigris", "box", "pinecone", "deepgram")
]}


class FakeGateway:
    """Stands in for station.gateway.Gateway in step tests.

    routes: {(method, provider, path_prefix): [Response, ...]} popped in order.
    """

    def __init__(self, routes: dict[tuple[str, str, str], list[Response]]):
        self.routes = {k: list(v) for k, v in routes.items()}
        self.calls: list[tuple[str, str, str, Any]] = []

    def base(self, provider: str) -> str:
        return f"https://api.sprites.dev/v1/gateway/{provider}/conn-{provider}"

    def request(self, method, provider, path, body=None, headers=None, timeout=120) -> Response:
        self.calls.append((method, provider, path, body))
        for (m, p, prefix), queue in self.routes.items():
            if m == method and p == provider and path.startswith(prefix) and queue:
                return queue.pop(0) if len(queue) > 1 else queue[0]
        raise AssertionError(f"FakeGateway: no route for {method} {provider} {path}")

    def json(self, method, provider, path, body=None, timeout=120) -> Any:
        from station.gateway import GatewayError

        r = self.request(method, provider, path, body, timeout=timeout)
        if r.status >= 300:
            raise GatewayError(provider, r.status, r.body.decode(errors="replace")[:500])
        return json.loads(r.body) if r.body else None


def ok(data: Any, status: int = 200) -> Response:
    return Response(status, {}, json.dumps(data).encode())
