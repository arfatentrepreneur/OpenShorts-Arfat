"""Free public tools (free_tools.py): URL parsing, caption track choice,
json3 parsing, the rate limiter and the shape of the generator output.

The network paths (yt-dlp, Gemini) are not exercised here; the prod check
runs them for real. What is pinned down is what decides cost and honesty:
nothing but one video id ever reaches yt-dlp, machine translations are never
served as a transcript, and the limiter refuses before any work is done.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import free_tools as ft


class TestExtractVideoId:
    @pytest.mark.parametrize("url", [
        "https://www.youtube.com/watch?v=arj7oStGLkU",
        "https://youtube.com/watch?v=arj7oStGLkU&t=42s",
        "https://m.youtube.com/watch?v=arj7oStGLkU&list=PL123",
        "youtube.com/watch?v=arj7oStGLkU",
        "https://youtu.be/arj7oStGLkU?si=abc",
        "https://www.youtube.com/shorts/arj7oStGLkU",
        "https://www.youtube.com/live/arj7oStGLkU",
        "https://www.youtube.com/embed/arj7oStGLkU",
        "arj7oStGLkU",
    ])
    def test_single_video_links(self, url):
        assert ft.extract_video_id(url) == "arj7oStGLkU"

    @pytest.mark.parametrize("url", [
        "", "hello", "https://www.youtube.com/playlist?list=PL123",
        "https://www.youtube.com/@ted", "https://www.youtube.com/results?search_query=x",
        "https://evil.example/watch?v=arj7oStGLkU", "https://youtube.com.evil.io/watch?v=arj7oStGLkU",
        "https://www.youtube.com/watch?v=short",
    ])
    def test_everything_else_is_refused(self, url):
        assert ft.extract_video_id(url) is None


def _fmt(name="English"):
    return [{"ext": "json3", "url": "u", "name": name}]


class TestChooseTrack:
    def test_manual_in_spoken_language_wins(self):
        info = {"language": "en", "subtitles": {"es": _fmt("Spanish"), "en": _fmt()},
                "automatic_captions": {"en-orig": _fmt("English (Original)"), "fr": _fmt()}}
        kind, key, langs = ft.choose_track(info)
        assert (kind, key) == ("manual", "en")
        codes = {(l["code"], l["kind"]) for l in langs}
        # auto translations ("fr") are never offered
        assert codes == {("es", "manual"), ("en", "manual"), ("en", "auto")}

    def test_auto_original_when_no_human_track(self):
        info = {"language": "es", "subtitles": {},
                "automatic_captions": {"es-orig": _fmt(), "en": _fmt(), "de": _fmt()}}
        assert ft.choose_track(info)[:2] == ("auto", "es-orig")

    def test_plain_code_auto_track_counts_as_original(self):
        info = {"language": "en", "automatic_captions": {"en": _fmt(), "de": _fmt()}}
        assert ft.choose_track(info)[:2] == ("auto", "en")

    def test_live_chat_is_not_a_caption(self):
        info = {"subtitles": {"live_chat": _fmt()}, "automatic_captions": {}}
        assert ft.choose_track(info)[:2] == (None, None)

    def test_requested_language(self):
        info = {"language": "en", "subtitles": {"es": _fmt(), "en": _fmt()},
                "automatic_captions": {"en-orig": _fmt()}}
        assert ft.choose_track(info, "es")[:2] == ("manual", "es")
        assert ft.choose_track(info, "en-orig")[:2] == ("auto", "en-orig")
        # a translation that is not a real track falls back to the default
        assert ft.choose_track(info, "ja")[:2] == ("manual", "en")


def test_parse_json3_drops_markers_and_clamps_overlaps():
    data = {"events": [
        {"tStartMs": 0, "dDurationMs": 5000},
        {"tStartMs": 100, "dDurationMs": 4000, "segs": [{"utf8": "hello"}, {"utf8": " world"}]},
        {"tStartMs": 2000, "dDurationMs": 10, "aAppend": 1, "segs": [{"utf8": "\n"}]},
        {"tStartMs": 3000, "dDurationMs": 2500, "segs": [{"utf8": "second\nline"}]},
    ]}
    out = ft.parse_json3(data)
    assert out == [
        {"start": 0.1, "dur": 2.9, "text": "hello world"},
        {"start": 3.0, "dur": 2.5, "text": "second line"},
    ]


def test_rate_limiter_per_ip_and_global():
    now = [1000.0]
    lim = ft.RateLimiter({"t": {"per_ip": [(60, 2)], "global_day": 3}}, clock=lambda: now[0])
    assert lim.check("t", "a") is None
    assert lim.check("t", "a") is None
    assert lim.check("t", "a") == "ip"
    assert lim.check("t", "b") is None
    assert lim.check("t", "c") == "global"
    now[0] += 86400
    assert lim.check("t", "c") is None


class TestShapeResult:
    def test_tags_respect_the_500_character_limit(self):
        tags = [f"tag number {i:02d} with padding" for i in range(40)]
        out = ft.shape_result("tags", {"tags": tags + ["#Dup", "dup"]})
        assert out["characters"] <= 500
        assert out["characters"] == len(",".join(out["tags"]))

    def test_tags_are_deduped_and_cleaned(self):
        out = ft.shape_result("tags", {"tags": ["#Procrastination", "procrastination", "tim urban"]})
        assert out["tags"] == ["Procrastination", "tim urban"]

    def test_titles_cut_at_100_and_no_em_dash(self):
        out = ft.shape_result("titles", {"titles": [{"title": "A — B" + "x" * 200, "angle": "how-to"}]})
        t = out["titles"][0]["title"]
        assert len(t) == 100 and "—" not in t

    def test_empty_output_is_an_error(self):
        with pytest.raises(ValueError):
            ft.shape_result("description", {"description": ""})


def test_prompt_carries_the_keyword_and_rules():
    p = ft.build_prompt("titles", "A talk about procrastination", "procrastination", "students")
    assert '"procrastination"' in p and "TARGET AUDIENCE: students" in p
    assert "Do not invent" in p
    p2 = ft.build_prompt("description", "x" * 30)
    assert "write no chapters" in p2


def _client():
    app = FastAPI()
    app.include_router(ft.router)
    return TestClient(app)


def test_transcript_endpoint_rejects_non_video_before_any_work(monkeypatch):
    called = []
    monkeypatch.setattr(ft, "fetch_transcript", lambda *a: called.append(a))
    r = _client().get("/api/tools/youtube-transcript", params={"url": "https://youtube.com/@ted"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_url"
    assert not called


def test_transcript_endpoint_caches_and_maps_errors(monkeypatch):
    ft._TRANSCRIPT_CACHE.clear()
    monkeypatch.setattr(ft, "_limiter", ft.RateLimiter(ft.LIMITS))
    calls = []

    def fake(video_id, lang):
        calls.append(video_id)
        if video_id == "AAAAAAAAAAA":
            raise ft.TranscriptError("no_captions", "none", 404)
        return {"video_id": video_id, "title": "t", "channel": "c", "duration": 10,
                "languages": [], "language": "en", "kind": "manual",
                "segments": [{"start": 0, "dur": 1, "text": "hi"}]}

    monkeypatch.setattr(ft, "fetch_transcript", fake)
    c = _client()
    r1 = c.get("/api/tools/youtube-transcript", params={"url": "https://youtu.be/arj7oStGLkU"})
    r2 = c.get("/api/tools/youtube-transcript", params={"url": "arj7oStGLkU"})
    assert r1.status_code == 200 and r1.json()["cached"] is False
    assert r2.status_code == 200 and r2.json()["cached"] is True
    for _ in range(2):
        r = c.get("/api/tools/youtube-transcript", params={"url": "AAAAAAAAAAA"})
        assert r.status_code == 404 and r.json()["detail"]["code"] == "no_captions"
    assert calls == ["arj7oStGLkU", "AAAAAAAAAAA"]


def test_metadata_endpoint_validates_input(monkeypatch):
    monkeypatch.setattr(ft, "_gemini_key", lambda: "k")
    c = _client()
    assert c.post("/api/tools/youtube-metadata", json={"mode": "x", "topic": "a" * 40}).status_code == 400
    assert c.post("/api/tools/youtube-metadata", json={"mode": "tags", "topic": "short"}).status_code == 400
    monkeypatch.setattr(ft, "_generate", lambda prompt: {"tags": ["a b", "c"]})
    r = c.post("/api/tools/youtube-metadata", json={"mode": "tags", "topic": "A video about sourdough bread at home"})
    assert r.status_code == 200 and r.json()["tags"] == ["a b", "c"]


def test_degraded_response_is_the_route_not_the_video():
    # anonymous answer from a throttled static: title only
    assert ft.is_degraded({"title": "Inside the Mind", "formats": [], "duration": None})
    # a finished 24/7 stream: no formats, but a real player response
    assert not ft.is_degraded({"title": "lofi", "formats": [], "duration": 121601512})
    assert not ft.is_degraded({"formats": [{"id": 1}], "duration": 844})
