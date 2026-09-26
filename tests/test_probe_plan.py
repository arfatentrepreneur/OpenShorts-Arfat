"""Duration-probe proxy ordering: cheapest bandwidth first.

The probe runs on every managed YouTube submission. It read PROXY_URL only
until 21-aug-2026, so it kept paying the per-GB proxy for metadata long after
downloads had moved to the flat-rate static pool — invisibly, because the
PROXY_BYTES counter only sees download bytes.
"""
import pytest

metering = pytest.importorskip("cloud.metering")

plan = metering.plan_probe_proxies

STATICS = ["http://s1", "http://s2", "http://s3"]
PAID = "http://paid"


class TestOrdering:
    def test_full_chain(self):
        assert plan(True, STATICS, PAID) == [None] + STATICS + [PAID]

    def test_paid_is_last_resort(self):
        got = plan(False, STATICS, PAID)
        assert got == STATICS + [PAID]
        assert got.index(PAID) == len(got) - 1

    def test_statics_only_never_reaches_a_paid_proxy(self):
        assert plan(False, STATICS, "") == STATICS

    def test_selfhost_no_proxies_probes_direct(self):
        assert plan(False, [], "") == [None]
        assert plan(True, [], "") == [None]

    def test_no_statics_matches_legacy_paid_only_behavior(self):
        assert plan(False, [], PAID) == [PAID]


class TestDirectFileProbe:
    """yt-dlp's generic extractor reports no duration for a plain mp4 URL; the
    probe must fall back to ffprobe over HTTP instead of 400-ing the job."""

    def test_generic_extractor_falls_back_to_ffprobe(self, monkeypatch):
        import types, sys, security_utils
        monkeypatch.setattr(security_utils, "assert_public_url", lambda u: u)
        class _YDL:
            def __init__(self, opts): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def extract_info(self, url, download=False):
                return {"extractor": "generic", "duration": None}
        monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=_YDL))
        monkeypatch.setattr(metering, "_ffprobe_url_seconds", lambda url, timeout=30: 559.4)
        assert abs(metering.probe_url_minutes("https://cdn.example.com/v.mp4") - 559.4 / 60) < 1e-6

    def test_both_fail_raises(self, monkeypatch):
        import types, sys, security_utils
        monkeypatch.setattr(security_utils, "assert_public_url", lambda u: u)
        class _YDL:
            def __init__(self, opts): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def extract_info(self, url, download=False):
                raise RuntimeError("Unsupported URL")
        monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=_YDL))
        def boom(url, timeout=30): raise RuntimeError("no moov")
        monkeypatch.setattr(metering, "_ffprobe_url_seconds", boom)
        with pytest.raises(ValueError):
            metering.probe_url_minutes("https://cdn.example.com/v.mp4")
