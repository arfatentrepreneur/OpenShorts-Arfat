"""OAuth 2.1 for the MCP endpoint: discovery documents, dynamic registration
input rules, PKCE and redirect building. The database-backed pieces
(register/authorize/token) are exercised against prod after deploy; what is
pinned here is every rule a client can trip over without a database."""
import base64
import hashlib
import secrets

from fastapi import FastAPI
from fastapi.testclient import TestClient

from cloud import mcp_oauth


class TestHelpers:
    def test_redirect_uri_rules(self):
        ok = ["https://claude.ai/api/mcp/auth_callback", "https://chatgpt.com/connector_platform_oauth_redirect",
              "http://localhost:3334/callback", "http://127.0.0.1:8080/cb"]
        bad = ["http://evil.com/cb", "https://x.com/cb#frag", "ftp://x/cb", "not a url", ""]
        assert all(mcp_oauth.valid_redirect_uri(u) for u in ok)
        assert not any(mcp_oauth.valid_redirect_uri(u) for u in bad)

    def test_pkce_s256(self):
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        assert mcp_oauth.pkce_matches(verifier, challenge)
        assert not mcp_oauth.pkce_matches(verifier + "x", challenge)
        assert not mcp_oauth.pkce_matches("short", challenge)   # < 43 chars
        assert not mcp_oauth.pkce_matches("", challenge)

    def test_add_query_keeps_existing_params_and_drops_none(self):
        out = mcp_oauth.add_query("https://c.ai/cb?a=1", code="xyz", state=None)
        assert out == "https://c.ai/cb?a=1&code=xyz"

    def test_consent_url_targets_the_hash_router(self):
        url = mcp_oauth.consent_url("https://www.openshorts.app/", {"client_id": "abc", "state": "s"})
        assert url.startswith("https://www.openshorts.app/#/oauth/authorize?")
        assert "client_id=abc" in url and "state=s" in url

    def test_metadata_points_at_the_same_host(self):
        m = mcp_oauth.server_metadata("https://mcp.openshorts.app")
        assert m["issuer"] == "https://mcp.openshorts.app"
        assert m["token_endpoint"] == "https://mcp.openshorts.app/oauth/token"
        assert m["code_challenge_methods_supported"] == ["S256"]
        assert m["token_endpoint_auth_methods_supported"] == ["none"]
        r = mcp_oauth.resource_metadata("https://mcp.openshorts.app")
        assert r["resource"] == "https://mcp.openshorts.app/mcp"
        assert r["authorization_servers"] == ["https://mcp.openshorts.app"]


class TestDiscoveryEndpoints:
    def _client(self):
        # The router is mounted by cloud.setup_sync in cloud mode only; test it
        # on a bare app so the checks don't depend on BILLING_ENABLED.
        app = FastAPI()
        app.include_router(mcp_oauth.router)
        return TestClient(app)

    def test_well_known_documents_are_served(self):
        c = self._client()
        for path in ("/.well-known/oauth-protected-resource",
                     "/.well-known/oauth-protected-resource/mcp",
                     "/.well-known/oauth-authorization-server",
                     "/.well-known/oauth-authorization-server/mcp"):
            r = c.get(path)
            assert r.status_code == 200, path
            assert r.headers.get("access-control-allow-origin") == "*"
            body = r.json()
            assert ("resource" in body) or ("issuer" in body)

    def test_register_rejects_bad_redirects_and_secrets(self):
        c = self._client()
        r = c.post("/oauth/register", json={"client_name": "x", "redirect_uris": ["http://evil.com/cb"]})
        assert r.status_code == 400 and r.json()["error"] == "invalid_redirect_uri"
        r = c.post("/oauth/register", json={"redirect_uris": ["https://ok.com/cb"],
                                           "token_endpoint_auth_method": "client_secret_basic"})
        assert r.status_code == 400 and r.json()["error"] == "invalid_client_metadata"
        r = c.post("/oauth/register", json={"redirect_uris": []})
        assert r.status_code == 400

    def test_token_rejects_other_grants(self):
        r = self._client().post("/oauth/token", data={"grant_type": "client_credentials"})
        assert r.status_code == 400 and r.json()["error"] == "unsupported_grant_type"
