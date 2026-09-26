"""End-to-end MCP transport against the real app (self-host mode, no DB).

Exercises the exact path an agent takes: HTTP POST /mcp -> JSON-RPC -> tool ->
in-process call back into the REST API -> real jobs dict. BILLING is off in the
test environment, so no cloud auth or database is involved — which is itself
the contract being tested: self-host must serve MCP without any of that.
"""
import asyncio

# Self-host mode is guaranteed by tests/conftest.py (BILLING_ENABLED=0), which
# runs before any test module can import app.
import httpx

import app as app_module
from app import app


def _post(payload):
    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            return await client.post("/mcp", json=payload)
    return asyncio.run(_run())


def _call(tool, arguments, msg_id=1):
    return _post({"jsonrpc": "2.0", "id": msg_id, "method": "tools/call",
                  "params": {"name": tool, "arguments": arguments}})


class TestTransport:
    def test_initialize_over_http(self):
        resp = _post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                      "params": {"protocolVersion": "2025-06-18"}})
        assert resp.status_code == 200
        assert resp.json()["result"]["serverInfo"]["name"] == "openshorts"

    def test_notification_gets_202(self):
        resp = _post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        assert resp.status_code == 202

    def test_batch_is_rejected(self):
        resp = _post([{"jsonrpc": "2.0", "id": 1, "method": "ping"}])
        assert resp.status_code == 400

    def test_get_is_405(self):
        async def _run():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
                return await client.get("/mcp")
        assert asyncio.run(_run()).status_code == 405


class TestToolsThroughRealEndpoints:
    def test_get_job_status_of_a_real_in_memory_job(self):
        app_module.jobs["mcp-test-job"] = {
            "status": "completed",
            "logs": ["line"] * 30,
            "result": {"clips": [{"title": "A clip", "video_url": "/videos/mcp-test-job/c1.mp4",
                                  "start": 10.0, "end": 25.5}]},
        }
        try:
            resp = _call("get_job_status", {"job_id": "mcp-test-job"})
            result = resp.json()["result"]
            assert result["isError"] is False
            data = result["structuredContent"]
            assert data["status"] == "completed"
            assert len(data["recent_logs"]) == 10  # agents get the tail, not 30 lines
            assert data["clips"][0]["duration_seconds"] == 15.5
        finally:
            app_module.jobs.pop("mcp-test-job", None)

    def test_unknown_job_is_a_tool_error_not_a_crash(self):
        resp = _call("get_job_status", {"job_id": "no-such-job"})
        result = resp.json()["result"]
        assert result["isError"] is True
        assert result["structuredContent"]["http_status"] == 404

    def test_process_video_requires_rights_confirmation(self):
        resp = _call("process_video",
                     {"source_url": "https://example.com/v.mp4", "confirm_rights": False})
        result = resp.json()["result"]
        assert result["isError"] is True
        assert "confirm_rights" in result["structuredContent"]["error"]

    def test_unknown_tool_is_a_tool_error(self):
        resp = _call("make_coffee", {})
        assert resp.json()["result"]["isError"] is True


class TestSelfHostQuota:
    def test_get_quota_reports_no_quota_instead_of_erroring(self):
        # /api/me only exists in cloud mode; self-host must get the friendly
        # "no quota here" answer, not a 404 tool error.
        resp = _call("get_quota", {})
        result = resp.json()["result"]
        assert result["isError"] is False
        assert result["structuredContent"]["self_host_or_anonymous"] is True


class TestCloudModeAuth:
    """mcp_server reads BILLING_ENABLED per request (unlike app.py, which
    freezes it at import), so cloud-mode gating is testable by env patch."""

    def test_401_without_credentials(self, monkeypatch):
        monkeypatch.setenv("BILLING_ENABLED", "1")
        resp = _post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert resp.status_code == 401
        # OAuth-capable clients discover the login flow from this header.
        assert resp.headers.get("www-authenticate").startswith("Bearer resource_metadata=")
        assert "/.well-known/oauth-protected-resource" in resp.headers.get("www-authenticate")
        assert "osk_" in resp.json()["error"]  # the fix is named in the message

    def test_resolvable_user_passes(self, monkeypatch):
        monkeypatch.setenv("BILLING_ENABLED", "1")
        import cloud.auth as cloud_auth

        async def fake_user(request):
            return object()
        monkeypatch.setattr(cloud_auth, "get_current_user_optional", fake_user)
        resp = _post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert resp.status_code == 200
        assert resp.json()["result"]["serverInfo"]["name"] == "openshorts"


class TestWebhookSigning:
    def test_signature_is_deterministic_hmac(self):
        import hashlib
        import hmac
        body = b'{"event":"job.completed"}'
        expected = "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
        assert app_module._sign_webhook(body, "s3cret") == expected

    def test_process_rejects_private_webhook_targets(self, monkeypatch):
        # The endpoint resolves a Gemini key before validating the webhook; a
        # dummy env key keeps the test on the SSRF branch both on dev machines
        # (where .env provides one anyway) and in CI (where nothing does).
        monkeypatch.setenv("GEMINI_API_KEY", "test-dummy-key")

        async def _run():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
                return await client.post("/api/process", json={
                    "url": "https://example.com/v.mp4", "acknowledged": True,
                    "webhook_url": "http://169.254.169.254/latest/meta-data/",
                })
        resp = asyncio.run(_run())
        assert resp.status_code == 400
        assert "webhook_url" in resp.json()["detail"]
