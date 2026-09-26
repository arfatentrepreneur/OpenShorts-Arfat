"""The duration probe must drop the cookies before it reaches the paid proxy.

With YOUTUBE_COOKIES attached, YouTube answers UNPLAYABLE for *every* client
(web_embedded, tv_downgraded, web and mweb) on a share of videos, and yt-dlp
reports that as "Video unavailable". Measured in prod on 9-sep-2026, same
video, same static IP, minutes apart: cookies -> UNPLAYABLE on all three
statics; anonymous -> 1080p (137+140). The download already recovers from
this through its anonymous 'fallback-static' attempt (main.plan_download_
attempts); the probe did not, so it read a cookie problem as an IP problem
and escalated to the per-GB proxy -- which carries the same cookies and fails
the same way. That is what fired the two "Paid proxy used" alerts that day.
"""
import sys
import types

import pytest

metering = pytest.importorskip("cloud.metering")

URL = "https://www.youtube.com/watch?v=e_04ZrNroTo"
NETSCAPE = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tx\n"


def _fake_ytdl(monkeypatch, attempts, playable_anonymously=True):
    """yt-dlp stand-in: UNPLAYABLE whenever a cookiefile is attached."""

    class _YDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=False):
            attempts.append({"proxy": self.opts.get("proxy"),
                             "cookies": bool(self.opts.get("cookiefile"))})
            if self.opts.get("cookiefile") or not playable_anonymously:
                raise RuntimeError("ERROR: [youtube] e_04ZrNroTo: Video unavailable")
            return {"extractor": "youtube", "duration": 214}

    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=_YDL))


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    import security_utils
    monkeypatch.setattr(security_utils, "assert_public_url", lambda u: u)
    monkeypatch.setenv("STATIC_PROXY_URLS", "http://s1")
    monkeypatch.setenv("PROXY_URL", "http://paid")
    monkeypatch.setenv("YOUTUBE_COOKIES", NETSCAPE)
    monkeypatch.delenv("DIRECT_FIRST", raising=False)
    metering.pop_paid_probe_events()
    yield
    metering.pop_paid_probe_events()


class TestTheAnonymousRetryComesBeforeTheMoney:
    def test_the_static_is_retried_without_cookies(self, monkeypatch):
        monkeypatch.setenv("BGUTIL_BASE_URL", "http://127.0.0.1:4416")
        attempts = []
        _fake_ytdl(monkeypatch, attempts)

        assert abs(metering.probe_url_minutes(URL) - 214 / 60) < 1e-6

        assert [(a["proxy"], a["cookies"]) for a in attempts] == [
            ("http://s1", True),    # HD with the account cookies
            ("http://s1", False),   # same IP, anonymous -> answers
        ]

    def test_the_paid_proxy_is_never_reached(self, monkeypatch):
        monkeypatch.setenv("BGUTIL_BASE_URL", "http://127.0.0.1:4416")
        attempts = []
        _fake_ytdl(monkeypatch, attempts)

        metering.probe_url_minutes(URL)

        assert not any(a["proxy"] == "http://paid" for a in attempts)
        assert metering.pop_paid_probe_events() == []

    def test_a_genuinely_dead_video_still_escalates_once(self, monkeypatch):
        """The anonymous retry is a free extra chance, not a new gate: when it
        fails too, "Video unavailable" stays IP-suspect and the paid proxy is
        still allowed its one look."""
        monkeypatch.setenv("BGUTIL_BASE_URL", "http://127.0.0.1:4416")
        attempts = []
        _fake_ytdl(monkeypatch, attempts, playable_anonymously=False)
        monkeypatch.setattr(metering, "_ffprobe_url_seconds",
                            lambda url, timeout=30: 0)

        with pytest.raises(ValueError):
            metering.probe_url_minutes(URL)

        assert any(a["proxy"] == "http://paid" for a in attempts)

    def test_selfhost_without_a_po_token_provider_keeps_its_cookies(self, monkeypatch):
        """No HD path means the fallback is the only attempt: dropping the
        operator's cookies there would remove the only session they have."""
        monkeypatch.delenv("BGUTIL_BASE_URL", raising=False)
        monkeypatch.delenv("BGUTIL_SCRIPT_PATH", raising=False)
        attempts = []
        _fake_ytdl(monkeypatch, attempts)
        monkeypatch.setattr(metering, "_ffprobe_url_seconds",
                            lambda url, timeout=30: 0)

        with pytest.raises(ValueError):
            metering.probe_url_minutes(URL)

        assert all(a["cookies"] for a in attempts)
