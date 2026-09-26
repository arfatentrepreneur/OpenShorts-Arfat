"""YouTube client selection shared by the download and the duration probe.

Measured 6-sep-2026 in the prod container, same static proxy, same video:
cookies + yt-dlp's authed defaults -> "Video unavailable" (no formats);
cookies + mweb with a PO token, or no cookies at all -> 1080p. The explicit
`default,mweb` list is what keeps those videos off the per-GB proxy.
"""
import pytest

yt_clients = pytest.importorskip("yt_clients")


def test_hd_needs_a_pot_provider():
    assert yt_clients.hd_extractor_args("", "") is None


def test_hd_lists_default_and_mweb_with_the_provider():
    got = yt_clients.hd_extractor_args("", "/opt/gen.js")
    assert got["youtube"]["player_client"] == ["default", "mweb"]
    assert got["youtubepot-bgutilscript"] == {"script_path": ["/opt/gen.js"]}
    http = yt_clients.hd_extractor_args("http://pot:4416", "/opt/gen.js")
    assert http["youtubepot-bgutilhttp"] == {"base_url": ["http://pot:4416"]}
    assert "youtubepot-bgutilscript" not in http


def test_fallback_never_skips_the_webpage():
    # player_skip=webpage drops the account's Data Sync ID and mweb then
    # cannot get its PO token: only the 360p progressive format survives.
    for args in (yt_clients.fallback_extractor_args("", ""),
                 yt_clients.fallback_extractor_args("", "/opt/gen.js")):
        assert "player_skip" not in args["youtube"]
        assert "mweb" in args["youtube"]["player_client"]
        for dead in ("tv_embed", "android"):
            assert dead not in args["youtube"]["player_client"]


def test_fallback_keeps_the_provider_when_configured():
    assert "youtubepot-bgutilscript" in yt_clients.fallback_extractor_args("", "/x.js")
    assert "youtubepot-bgutilscript" not in yt_clients.fallback_extractor_args("", "")


def test_lists_are_copies():
    a = yt_clients.hd_extractor_args("", "/x.js")["youtube"]["player_client"]
    a.append("web_safari")
    assert yt_clients.hd_extractor_args("", "/x.js")["youtube"]["player_client"] == ["default", "mweb"]


def test_probe_uses_the_same_lists(monkeypatch):
    metering = pytest.importorskip("cloud.metering")
    monkeypatch.setenv("BGUTIL_SCRIPT_PATH", "/opt/gen.js")
    monkeypatch.delenv("BGUTIL_BASE_URL", raising=False)
    monkeypatch.setenv("STATIC_PROXY_URLS", "")
    monkeypatch.setenv("PROXY_URL", "")
    monkeypatch.delenv("YOUTUBE_COOKIES", raising=False)
    seen = {}

    def fake(url, proxies, strategies, static_errors, paid, ck_path):
        seen["strategies"] = strategies
        return 1.0

    monkeypatch.setattr(metering, "_probe_with_proxies", fake)
    metering.probe_url_minutes("https://www.youtube.com/watch?v=abc")
    # (extractor args, send the cookies): the fallback step goes out anonymously,
    # like the download's 'fallback-static' attempt — see
    # tests/test_probe_anonymous_fallback.py.
    assert seen["strategies"] == [
        (yt_clients.hd_extractor_args("", "/opt/gen.js"), True),
        (yt_clients.fallback_extractor_args("", "/opt/gen.js"), False),
    ]
