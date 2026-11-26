import urllib.error

import pytest

from station.gateway import Gateway, GatewayError, Response
from tests.fakes import LISTING, fake_urlopen


def gateway_with(responses, sleep=lambda s: None, seen=None):
    return Gateway(urlopen=fake_urlopen(LISTING, responses, seen), sleep=sleep)


def test_base_reads_listing():  # listing JSON shape from check 1
    gw = Gateway(urlopen=fake_urlopen({"connections": [{"provider": "typesafe",
                 "gateway_base_url": "https://api.sprites.dev/v1/gateway/typesafe/abc"}]}))
    assert gw.base("typesafe") == "https://api.sprites.dev/v1/gateway/typesafe/abc"


def test_missing_connection_names_provider():
    gw = Gateway(urlopen=fake_urlopen({"connections": []}))
    with pytest.raises(GatewayError, match="ollama"):
        gw.base("ollama")


def test_retries_429_then_succeeds():  # Review Focus 2
    sleeps = []
    gw = gateway_with([Response(429, {"Retry-After": "1"}, b""), Response(200, {}, b'{"ok": 1}')],
                      sleep=sleeps.append)
    assert gw.json("POST", "typesafe", "/v1/systemone", {}) == {"ok": 1}
    assert sleeps == [1]


def test_retries_529_with_backoff():
    sleeps = []
    gw = gateway_with([Response(529, {}, b""), Response(529, {}, b""), Response(200, {}, b"{}")],
                      sleep=sleeps.append)
    assert gw.json("POST", "typesafe", "/v1/systemone", {}) == {}
    assert sleeps == [2, 4]


def test_timeout_retried():
    gw = gateway_with([urllib.error.URLError("timed out"), Response(200, {}, b"[]")])
    assert gw.json("GET", "apify", "/v2/datasets/x/items") == []


def test_gives_up_after_three_retries():
    gw = gateway_with([Response(503, {}, b"down")] * 4)
    with pytest.raises(GatewayError) as e:
        gw.json("GET", "apify", "/v2/x")
    assert e.value.status == 503


def test_403_not_retried_and_raises():  # connector refusals (checks 2, 3) are permanent
    gw = gateway_with([Response(403, {}, b'{"error":"endpoint is not supported"}')])
    with pytest.raises(GatewayError) as e:
        gw.json("POST", "apify", "/v2/x", {})
    assert e.value.status == 403 and "not supported" in e.value.body


def test_sends_no_auth_header_and_json_body():
    seen = []
    gw = gateway_with([Response(200, {}, b"{}")], seen=seen)
    gw.json("POST", "typesafe", "/v1/systemone", {"a": 1})
    req = seen[-1]
    assert req.full_url == "https://api.sprites.dev/v1/gateway/typesafe/conn-typesafe/v1/systemone"
    assert "Authorization" not in req.headers and req.get_header("Content-type") == "application/json"
    assert req.data == b'{"a": 1}'
