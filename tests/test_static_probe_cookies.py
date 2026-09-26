"""The static-pool probe must ask the way the download asks.

The watcher fetched the YouTube watch page through each static IP with a bare
httpx client: no cookies. Anonymously, a datacenter IP making ~400 YouTube hits
a day is rate-limited into "Sign in to confirm you're not a bot", so
playabilityStatus comes back LOGIN_REQUIRED and the watcher declared the pool
down. The same IPs were serving every real download fine, because those carry
YOUTUBE_COOKIES.

Measured in production on 8-sep-2026, all three statics, same request, same
minute: anonymous LOGIN_REQUIRED, with the download's cookies OK — while
proxy_usage showed 119 YouTube jobs routed to HD-static1 in 24 h and zero paid
bytes. The alert said "every download costs money until the statics are back"
and not one cent was being spent.

CLAUDE.md already recorded this for cloud/metering.probe_url_minutes ("The
probe also carries YOUTUBE_COOKIES, like the download does"); the watcher probe
never got the same treatment.
"""
import asyncio

import pytest

alerts = pytest.importorskip("cloud.alerts")

NETSCAPE = (
    "# Netscape HTTP Cookie File\n"
    ".youtube.com\tTRUE\t/\tTRUE\t0\tSID\tsomevalue\n"
    ".youtube.com\tTRUE\t/\tTRUE\t0\tHSID\tanother\n"
)


@pytest.fixture(autouse=True)
def _clear_cache():
    alerts._static_cookie_src = None
    alerts._static_cookie_jar = None
    yield
    alerts._static_cookie_src = None
    alerts._static_cookie_jar = None


def _spy(monkeypatch, body='{"playabilityStatus":{"status":"OK"}}'):
    seen = {}

    class _Resp:
        status_code = 200
        text = body

    class _Client:
        def __init__(self, **kw):
            seen["cookies"] = kw.get("cookies")
            seen["proxy"] = kw.get("proxy")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **kw):
            seen["url"] = url
            return _Resp()

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    return seen


class TestTheProbeCarriesTheDownloadsCookies:
    def test_the_static_probe_sends_them(self, monkeypatch):
        monkeypatch.setenv("PROXY_URL", "http://paid")
        monkeypatch.setenv("YOUTUBE_COOKIES", NETSCAPE)
        seen = _spy(monkeypatch)
        ok, _ = asyncio.run(alerts._probe_one("http://static1"))
        assert ok
        assert seen["cookies"] is not None, "static probe went out anonymously"
        assert len(seen["cookies"]) == 2

    def test_a_headerless_blob_is_still_accepted(self, monkeypatch):
        """The env var is pasted by hand; the Netscape header is often missing."""
        monkeypatch.setenv("PROXY_URL", "http://paid")
        monkeypatch.setenv("YOUTUBE_COOKIES",
                           ".youtube.com\tTRUE\t/\tTRUE\t0\tSID\tsomevalue\n")
        seen = _spy(monkeypatch)
        asyncio.run(alerts._probe_one("http://static1"))
        assert seen["cookies"] is not None and len(seen["cookies"]) == 1

    def test_no_cookies_configured_still_probes(self, monkeypatch):
        """Self-host has no cookies: probe anonymously rather than crash."""
        monkeypatch.setenv("PROXY_URL", "http://paid")
        monkeypatch.delenv("YOUTUBE_COOKIES", raising=False)
        seen = _spy(monkeypatch)
        ok, _ = asyncio.run(alerts._probe_one("http://static1"))
        assert ok and seen["cookies"] is None

    def test_an_unparseable_blob_does_not_break_the_watcher(self, monkeypatch):
        monkeypatch.setenv("PROXY_URL", "http://paid")
        monkeypatch.setenv("YOUTUBE_COOKIES", "not a cookie file at all")
        seen = _spy(monkeypatch)
        ok, _ = asyncio.run(alerts._probe_one("http://static1"))
        assert ok and seen["cookies"] is None

    def test_the_paid_probe_stays_anonymous_and_cheap(self, monkeypatch):
        """DataImpulse is billed per GB: keep the 204, and send it no session."""
        monkeypatch.setenv("PROXY_URL", "http://paid")
        monkeypatch.setenv("YOUTUBE_COOKIES", NETSCAPE)
        seen = _spy(monkeypatch, body="")
        ok, _ = asyncio.run(alerts._probe_one("http://paid"))
        assert ok
        assert seen["cookies"] is None
        assert seen["url"].startswith("http://www.google.com")

    def test_the_jar_is_parsed_once(self, monkeypatch):
        monkeypatch.setenv("YOUTUBE_COOKIES", NETSCAPE)
        first = alerts._probe_cookies()
        assert alerts._probe_cookies() is first
