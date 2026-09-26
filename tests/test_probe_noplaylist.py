"""The duration probe asks yt-dlp for ONE video, and a content verdict wins.

Two probe failures measured in prod between 7 and 17-sep-2026 (proxy_usage,
source='probe'): 26 of the 37 probes that reached the per-GB proxy were for a
`watch?v=X&list=...` or a `results?search_query=` URL. Without ``noplaylist``
yt-dlp walked the whole list, died on its first private / age-gated /
bot-checked entry (a video the user never pasted), the probe read that as an
IP problem, paid the proxy to walk the same list again, and the user got a
400 for a valid link.

The second: on a static route the attempt with the cookies said "Sign in to
confirm your age" (a content error, same on every IP) and the anonymous retry
said "not a bot"; only the last error was kept per route, so the bot-check
overrode the verdict and the paid proxy was spent on an age-gated video,
twice in 15 minutes.
"""
import sys
import types

import pytest

metering = pytest.importorskip("cloud.metering")

URL = "https://www.youtube.com/watch?v=3QFAEqE9-Kk&list=PLArw552Yzuwn&rco=1"
NETSCAPE = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tx\n"
AGE = "ERROR: [youtube] 3QFAEqE9-Kk: Sign in to confirm your age. Use --cookies"
BOT = "ERROR: [youtube] 3QFAEqE9-Kk: Sign in to confirm you’re not a bot."


def _fake_ytdl(monkeypatch, attempts, outcome):
    """``outcome(opts)`` returns an info dict or raises."""

    class _YDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=False):
            attempts.append(dict(self.opts))
            return outcome(self.opts)

    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=_YDL))


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    import security_utils
    monkeypatch.setattr(security_utils, "assert_public_url", lambda u: u)
    monkeypatch.setenv("STATIC_PROXY_URLS", "http://s1,http://s2")
    monkeypatch.setenv("PROXY_URL", "http://paid")
    monkeypatch.setenv("YOUTUBE_COOKIES", NETSCAPE)
    monkeypatch.setenv("BGUTIL_BASE_URL", "http://127.0.0.1:4416")
    monkeypatch.delenv("DIRECT_FIRST", raising=False)
    # No network: the last-resort ffprobe must not run either.
    monkeypatch.setattr(metering, "_ffprobe_url_seconds", lambda url, timeout=30: 0.0)
    metering.pop_paid_probe_events()
    yield
    metering.pop_paid_probe_events()


class TestOneVideoNotThePlaylist:
    def test_every_attempt_asks_for_the_single_video(self, monkeypatch):
        attempts = []
        _fake_ytdl(monkeypatch, attempts,
                   lambda o: {"extractor": "youtube", "duration": 600})

        assert abs(metering.probe_url_minutes(URL) - 10) < 1e-6
        assert attempts and all(a.get("noplaylist") is True for a in attempts)


class TestAContentVerdictOutranksTheAnonymousBotCheck:
    def _outcome(self, opts):
        # With the cookies: age-gated (same on every IP). Anonymous: bot-check.
        raise RuntimeError(AGE if opts.get("cookiefile") else BOT)

    def test_the_paid_proxy_is_not_spent(self, monkeypatch):
        attempts = []
        _fake_ytdl(monkeypatch, attempts, self._outcome)

        with pytest.raises(ValueError):
            metering.probe_url_minutes(URL)

        assert not any(a.get("proxy") == "http://paid" for a in attempts)
        assert metering.pop_paid_probe_events() == []

    def test_both_errors_are_kept_for_the_alert(self, monkeypatch):
        attempts = []
        _fake_ytdl(monkeypatch, attempts, self._outcome)
        seen = {}
        real = metering._probe_with_proxies

        def spy(url, proxies, strategies, static_errors, paid, ck_path):
            try:
                return real(url, proxies, strategies, static_errors, paid, ck_path)
            finally:
                seen.update(static_errors)

        monkeypatch.setattr(metering, "_probe_with_proxies", spy)
        with pytest.raises(ValueError):
            metering.probe_url_minutes(URL)

        assert "confirm your age" in seen["static1"]
        assert "not a bot" in seen["static1"]
        assert not metering.static_failure_warrants_paid(seen["static1"])


class TestAnIpProblemStillEscalates:
    def test_bot_check_on_every_attempt_reaches_the_paid_proxy(self, monkeypatch):
        attempts = []

        def outcome(opts):
            if opts.get("proxy") == "http://paid":
                return {"extractor": "youtube", "duration": 60}
            raise RuntimeError(BOT)

        _fake_ytdl(monkeypatch, attempts, outcome)
        assert abs(metering.probe_url_minutes(URL) - 1) < 1e-6
        assert attempts[-1]["proxy"] == "http://paid"
