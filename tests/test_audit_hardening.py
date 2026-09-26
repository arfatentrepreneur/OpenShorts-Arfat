"""Hardening from the 22-sep-2026 audit, pinned at the HTTP surface.

- /api/process refuses a tailnet / private URL before any probe runs, and the
  quality probe runs only AFTER the metering step (balance, job limit, the
  hourly probe cap), handing the reservation back when it refuses the job.
- A metered whole-video URL job carries SOURCE_CAP_MINUTES = the reserved
  minutes, in the job env and in the resume manifest.
- main.py and the probe get an environment without the server secrets.
- Thumbnail publish status, thumbnail generation and render status are
  owner-only in cloud mode.
- The public /video/{id} page escapes everything it interpolates.
"""
import asyncio
import json
import os

import httpx
import pytest

app_module = pytest.importorskip("app")


def _client_call(method, path, **kw):
    async def _do():
        transport = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            return await getattr(c, method)(path, **kw)
    return asyncio.run(_do())


def _post_process(body):
    return _client_call("post", "/api/process", json=body,
                        headers={"X-Gemini-Key": "test-key"})


@pytest.fixture()
def dirs(tmp_path, monkeypatch):
    out_root = tmp_path / "output"
    up_root = tmp_path / "uploads"
    out_root.mkdir()
    up_root.mkdir()
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(out_root))
    monkeypatch.setattr(app_module, "UPLOAD_DIR", str(up_root))
    monkeypatch.setattr(app_module, "jobs", {})
    monkeypatch.setattr(app_module, "job_queue", asyncio.PriorityQueue())
    return out_root


@pytest.fixture()
def calls(monkeypatch):
    """Record the order of the metering step and the quality probe."""
    order = []

    async def _probe(url):
        order.append("probe")
        return order_probe_result[0]

    async def _reserve(request, url, input_path, job_id, max_minutes=None):
        order.append("reserve")
        request.state.reserved_minutes = 12
        return 7, 1, "res-1", "starter", None

    released = []

    class _FakeMetering:
        @staticmethod
        async def release_reservation(rid):
            released.append(rid)

    order_probe_result = [{"max_height": 1080, "duration": 600}]
    monkeypatch.setattr(app_module, "_probe_youtube_quality", _probe)
    monkeypatch.setattr(app_module, "reserve_process_minutes", _reserve)
    monkeypatch.setattr(app_module, "_metering", _FakeMetering)
    monkeypatch.setattr(app_module, "_validate_source_url", _allow_url)
    return {"order": order, "released": released, "probe_result": order_probe_result}


async def _allow_url(url):
    return None


# --------------------------------------------------------------------------- #
# /api/process: URL validation, probe ordering, reservation cap
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("url", [
    "http://100.101.1.2:22/",
    "http://100.90.3.4:8080/admin",
    "http://127.0.0.1:8000/health",
    "file:///etc/passwd",
])
def test_unsafe_url_is_refused_before_any_probe(dirs, monkeypatch, url):
    probed = []

    async def _probe(u):
        probed.append(u)
        return {}
    monkeypatch.setattr(app_module, "_probe_youtube_quality", _probe)
    resp = _post_process({"url": url, "acknowledged": True})
    assert resp.status_code == 400
    assert probed == []
    assert os.listdir(dirs) == []


def test_youtube_search_page_is_refused_before_any_probe(dirs, monkeypatch):
    probed = []

    async def _probe(u):
        probed.append(u)
        return {}
    monkeypatch.setattr(app_module, "_probe_youtube_quality", _probe)
    monkeypatch.setattr("security_utils.assert_public_url", lambda u: u)
    resp = _post_process({"url": "https://www.youtube.com/results?search_query=x",
                          "acknowledged": True})
    assert resp.status_code == 400
    assert "search results" in resp.json()["detail"]
    assert probed == []


def test_quality_probe_runs_after_metering(dirs, calls):
    resp = _post_process({"url": "https://www.youtube.com/watch?v=ok", "acknowledged": True})
    assert resp.status_code == 200, resp.text
    assert calls["order"] == ["reserve", "probe"]
    assert calls["released"] == []


def test_low_quality_confirmation_releases_the_reservation(dirs, calls):
    calls["probe_result"][0] = {"max_height": 360, "duration": 600}
    resp = _post_process({"url": "https://www.youtube.com/watch?v=lowq", "acknowledged": True})
    assert resp.status_code == 200
    assert resp.json()["needs_confirmation"] is True
    assert calls["released"] == ["res-1"]
    assert os.listdir(dirs) == []          # no orphan job dir
    assert app_module.jobs == {}


def test_short_source_rejection_releases_the_reservation(dirs, calls):
    calls["probe_result"][0] = {"max_height": 1080, "duration": 20}
    resp = _post_process({"url": "https://www.youtube.com/watch?v=short", "acknowledged": True})
    assert resp.status_code == 400
    assert calls["released"] == ["res-1"]
    assert os.listdir(dirs) == []


def test_metered_url_job_is_capped_at_the_reserved_minutes(dirs, calls):
    resp = _post_process({"url": "https://www.youtube.com/watch?v=ok", "acknowledged": True})
    job_id = resp.json()["job_id"]
    job = app_module.jobs[job_id]
    assert job["env"]["SOURCE_CAP_MINUTES"] == "12"
    assert "MAX_SOURCE_MINUTES" not in job["env"]
    manifest = json.load(open(os.path.join(dirs, job_id, app_module._RESUME_FILE)))
    assert manifest["source_cap_minutes"] == 12


def test_resumed_job_keeps_its_safety_cap(dirs, monkeypatch):
    monkeypatch.setattr(app_module, "INSTANCE_ID", "me")
    monkeypatch.setattr(app_module, "_draining", False)
    monkeypatch.setattr(app_module, "_running_jobs", set())
    for name, cap in (("capped", 12), ("plain", None)):
        d = dirs / name
        d.mkdir()
        (d / app_module._RESUME_FILE).write_text(json.dumps({
            "cmd": ["python", "main.py"], "priority": 2, "user_id": None,
            "reservation_id": f"res-{name}", "watermark": False, "attempts": 0,
            "source_cap_minutes": cap,
        }))
    monkeypatch.setenv("SOURCE_CAP_MINUTES", "3")  # a stale value must not leak in
    app_module._resume_interrupted_jobs()
    assert app_module.jobs["capped"]["env"]["SOURCE_CAP_MINUTES"] == "12"
    assert "SOURCE_CAP_MINUTES" not in app_module.jobs["plain"]["env"]


# --------------------------------------------------------------------------- #
# Subprocess environment
# --------------------------------------------------------------------------- #
def test_child_env_drops_server_secrets(monkeypatch):
    for name in ("STRIPE_SECRET_KEY", "JWT_SECRET", "DATABASE_URL", "SMTP_PASSWORD",
                 "TELEGRAM_BOT_TOKEN", "AGENTLEDGER_API_KEY", "R2_SECRET_ACCESS_KEY",
                 "MANAGED_UPLOAD_POST_API_KEY", "GOOGLE_CLIENT_SECRET"):
        monkeypatch.setenv(name, "secret")
    for name in ("YOUTUBE_COOKIES", "PROXY_URL", "STATIC_PROXY_URLS", "GEMINI_API_KEY",
                 "BGUTIL_SCRIPT_PATH", "FFMPEG_ENCODER", "WHISPER_MODEL"):
        monkeypatch.setenv(name, "keep")
    env = app_module.child_env()
    for name in app_module.CHILD_ENV_DENYLIST:
        assert name not in env
    for name in ("YOUTUBE_COOKIES", "PROXY_URL", "STATIC_PROXY_URLS", "GEMINI_API_KEY",
                 "BGUTIL_SCRIPT_PATH", "FFMPEG_ENCODER", "WHISPER_MODEL"):
        assert env[name] == "keep"


def test_pipeline_code_reads_none_of_the_dropped_secrets():
    """If main.py (or anything it imports) ever needs one of these, the
    denylist would silently break jobs: fail here instead."""
    import ast
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    local = {f[:-3] for f in os.listdir(root) if f.endswith(".py")}
    seen, stack = set(), ["main", "quality_probe"]
    while stack:
        mod = stack.pop()
        if mod in seen:
            continue
        seen.add(mod)
        src = open(os.path.join(root, mod + ".py"), encoding="utf-8").read()
        for name in app_module.CHILD_ENV_DENYLIST:
            assert f'"{name}"' not in src and f"'{name}'" not in src, (mod, name)
        for node in ast.walk(ast.parse(src)):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            for n in names:
                assert n != "cloud", f"{mod} imports cloud/, which reads server secrets"
                if n in local:
                    stack.append(n)


def test_job_env_has_no_server_secrets(dirs, calls, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_x")
    monkeypatch.setenv("JWT_SECRET", "jwt")
    resp = _post_process({"url": "https://www.youtube.com/watch?v=ok", "acknowledged": True})
    env = app_module.jobs[resp.json()["job_id"]]["env"]
    assert "STRIPE_SECRET_KEY" not in env and "JWT_SECRET" not in env
    assert env["GEMINI_API_KEY"] == "test-key"


# --------------------------------------------------------------------------- #
# Owner checks (cloud mode)
# --------------------------------------------------------------------------- #
class _User:
    def __init__(self, uid):
        self.id = uid
        self.plan = "starter"


@pytest.fixture()
def cloud_as(monkeypatch):
    who = {"user": None}

    async def _from_request(request):
        return who["user"]
    monkeypatch.setattr(app_module, "BILLING_ENABLED", True)
    monkeypatch.setattr(app_module, "_user_from_request", _from_request)
    return who


def test_publish_status_is_owner_only(cloud_as, monkeypatch):
    monkeypatch.setattr(app_module, "publish_jobs", {
        "p1": {"status": "done", "result": {"ok": 1}, "error": None, "user_id": "owner"}})
    cloud_as["user"] = _User("stranger")
    assert _client_call("get", "/api/thumbnail/publish/status/p1").status_code == 404
    cloud_as["user"] = None
    assert _client_call("get", "/api/thumbnail/publish/status/p1").status_code == 404
    cloud_as["user"] = _User("owner")
    resp = _client_call("get", "/api/thumbnail/publish/status/p1")
    assert resp.status_code == 200
    assert resp.json() == {"status": "done", "result": {"ok": 1}, "error": None}


def test_render_status_is_owner_only(cloud_as, monkeypatch):
    monkeypatch.setattr(app_module, "_render_owners", {"r-1": "owner"})
    cloud_as["user"] = _User("stranger")
    assert _client_call("get", "/api/render/r-1").status_code == 404
    # An id this instance never issued is not proxied at all.
    cloud_as["user"] = _User("owner")
    assert _client_call("get", "/api/render/unknown-id").status_code == 404


def test_thumbnail_generate_refuses_someone_elses_session(cloud_as, monkeypatch):
    async def _gemini(request):
        return "k"
    monkeypatch.setattr(app_module, "resolve_gemini", _gemini)
    monkeypatch.setattr(app_module, "thumbnail_sessions", {"s-1": {"user_id": "owner"}})
    cloud_as["user"] = _User("stranger")
    resp = _client_call("post", "/api/thumbnail/generate",
                        data={"session_id": "s-1", "title": "t"})
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# /video/{id} escaping
# --------------------------------------------------------------------------- #
def test_video_page_escapes_everything(monkeypatch):
    evil = '"><script>alert(1)</script>'
    meta = {
        "video_id": "v1", "title": "t", "caption": "c",
        "video_url": "https://cdn.example.com/v.mp4" + evil,
        "actor_url": "javascript:alert(1)",
        "product_url": "javascript:alert(2)", "product_name": "p",
        "hashtags": ["#ok", evil], "language": 'en"><script>',
        "duration": 30, "cost_estimate": {"total": 1.0},
    }
    monkeypatch.setattr(app_module, "list_video_gallery", lambda n: [meta])
    resp = _client_call("get", "/video/v1")
    assert resp.status_code == 200
    body = resp.text
    assert "<script>alert(1)</script>" not in body
    assert "javascript:" not in body
    assert '<html lang="en">' in body


# --------------------------------------------------------------------------- #
# main.cap_source_duration(safety=True): the whole-video cap
# --------------------------------------------------------------------------- #
import shutil
import subprocess


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="needs ffmpeg")
class TestSafetyCap:
    @pytest.fixture()
    def source(self, tmp_path):
        main = pytest.importorskip("main")
        path = tmp_path / "src.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=size=160x120:rate=25",
            "-t", "150", "-c:v", "libx264", "-preset", "ultrafast", str(path)], check=True)
        return main, str(path)

    @staticmethod
    def _seconds(path):
        return float(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1", path]).decode().strip())

    def test_a_download_clearly_longer_than_reserved_is_cut(self, source):
        main, path = source
        main.cap_source_duration(path, 1, safety=True)
        assert 59 <= self._seconds(path) <= 62

    def test_within_tolerance_is_left_alone(self, source):
        main, path = source
        main.cap_source_duration(path, 2.2, safety=True)   # 132 s + 30 s tolerance
        assert self._seconds(path) >= 149
