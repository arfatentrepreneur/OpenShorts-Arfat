"""OAuth 2.1 authorization server for the MCP endpoint (cloud mode).

claude.ai and ChatGPT connect to a remote MCP server by URL alone: the user
pastes ``https://mcp.openshorts.app/mcp`` and the client discovers how to log
in from the server's metadata. That takes the pieces those clients actually
use, and nothing else:

* RFC 9728 protected-resource metadata (``/.well-known/oauth-protected-resource``),
  which the ``/mcp`` 401 points at via ``WWW-Authenticate``;
* RFC 8414 authorization-server metadata (``/.well-known/oauth-authorization-server``);
* RFC 7591 dynamic client registration (``POST /oauth/register``), because
  neither client ships a pre-shared client id;
* the authorization-code grant with PKCE S256 and **no client secret**: these
  are public clients, PKCE is what binds the code to whoever started the flow.

The consent screen lives in the dashboard (``#/oauth/authorize``), not here:
the session is a bearer JWT in localStorage on www.openshorts.app, which a
plain browser GET to the API cannot see. So ``GET /oauth/authorize`` validates
the request and bounces to the dashboard, the dashboard signs the user in if
needed and asks "connect Claude to your account?", and ``POST /api/oauth/authorize``
(session-authenticated) mints the code and hands back the redirect.

Redeeming the code mints an ordinary ``osk_`` API key named after the client
and returns it as the access token. That is deliberate: every existing auth,
quota and ownership rule already understands those keys, the connection shows
up in the account page next to hand-made keys, and revoking it there is how
the user disconnects the client. No refresh tokens: the key does not expire.
"""
import base64
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select

from . import database, api_keys
from .config import settings
from .models import OAuthClient, OAuthCode, ApiKey

router = APIRouter()

SCOPE = "openshorts"
CODE_TTL = timedelta(minutes=10)
MAX_REDIRECT_URIS = 10


def _now():
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Pure helpers (unit-tested without a database)
# --------------------------------------------------------------------------- #
def base_url(request: Request) -> str:
    """The origin the client is talking to, so the metadata names the host the
    client actually used (mcp.openshorts.app or api.openshorts.app both route
    here). uvicorn runs with --proxy-headers, so the scheme is the public one."""
    u = request.base_url
    return f"{u.scheme}://{u.netloc}"


def resource_metadata(base: str) -> dict:
    return {
        "resource": f"{base}/mcp",
        "authorization_servers": [base],
        "bearer_methods_supported": ["header"],
        "scopes_supported": [SCOPE],
        "resource_name": "OpenShorts",
        "resource_documentation": "https://www.openshorts.app/mcp",
    }


def server_metadata(base: str) -> dict:
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/register",
        "response_types_supported": ["code"],
        "response_modes_supported": ["query"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": [SCOPE],
        "service_documentation": "https://www.openshorts.app/mcp",
    }


def valid_redirect_uri(uri: str) -> bool:
    """https anywhere, or plain http only on the loopback (CLI clients open a
    local listener to catch the redirect). No fragments, no wildcards."""
    try:
        p = urlsplit(uri)
    except ValueError:
        return False
    if p.fragment or not p.netloc:
        return False
    host = (p.hostname or "").lower()
    if p.scheme == "https":
        return True
    if p.scheme == "http":
        return host in ("localhost", "127.0.0.1", "::1")
    return False


def pkce_matches(code_verifier: str, code_challenge: str) -> bool:
    if not code_verifier or not code_challenge:
        return False
    if not (43 <= len(code_verifier) <= 128):
        return False
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return secrets.compare_digest(expected, code_challenge)


def add_query(uri: str, **params) -> str:
    """Append params to a redirect URI, keeping any query it already has."""
    p = urlsplit(uri)
    q = parse_qsl(p.query, keep_blank_values=True)
    q.extend((k, v) for k, v in params.items() if v is not None)
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), ""))


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def consent_url(base_frontend: str, params: dict) -> str:
    """Where the dashboard renders the consent screen. The params ride in the
    hash's query so the SPA (hash router) can read them."""
    return f"{base_frontend.rstrip('/')}/#/oauth/authorize?{urlencode(params)}"


def _oauth_error(status: int, error: str, description: str):
    return JSONResponse({"error": error, "error_description": description}, status_code=status)


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
@router.get("/.well-known/oauth-protected-resource")
@router.get("/.well-known/oauth-protected-resource/mcp")
async def protected_resource(request: Request):
    return JSONResponse(resource_metadata(base_url(request)),
                        headers={"Access-Control-Allow-Origin": "*"})


@router.get("/.well-known/oauth-authorization-server")
@router.get("/.well-known/oauth-authorization-server/mcp")
async def authorization_server(request: Request):
    return JSONResponse(server_metadata(base_url(request)),
                        headers={"Access-Control-Allow-Origin": "*"})


# --------------------------------------------------------------------------- #
# Dynamic client registration (RFC 7591)
# --------------------------------------------------------------------------- #
@router.post("/oauth/register", status_code=201)
async def register_client(request: Request):
    try:
        body = json.loads(await request.body() or b"{}")
    except ValueError:
        return _oauth_error(400, "invalid_client_metadata", "Body must be JSON.")
    if not isinstance(body, dict):
        return _oauth_error(400, "invalid_client_metadata", "Body must be a JSON object.")

    uris = body.get("redirect_uris")
    if not isinstance(uris, list) or not uris or len(uris) > MAX_REDIRECT_URIS:
        return _oauth_error(400, "invalid_redirect_uri",
                            f"redirect_uris must list 1 to {MAX_REDIRECT_URIS} URIs.")
    uris = [str(u) for u in uris]
    bad = [u for u in uris if not valid_redirect_uri(u)]
    if bad:
        return _oauth_error(400, "invalid_redirect_uri",
                            f"redirect_uris must be https (or http on localhost): {bad[0]}")

    auth_method = body.get("token_endpoint_auth_method") or "none"
    if auth_method != "none":
        return _oauth_error(400, "invalid_client_metadata",
                            "Only public clients (token_endpoint_auth_method=none) are supported.")
    grants = body.get("grant_types") or ["authorization_code"]
    if any(g not in ("authorization_code", "refresh_token") for g in grants):
        return _oauth_error(400, "invalid_client_metadata",
                            "Only the authorization_code grant is supported.")

    name = str(body.get("client_name") or "MCP client").strip()[:80] or "MCP client"
    client_id = secrets.token_urlsafe(24)
    async with database.session() as session:
        session.add(OAuthClient(id=client_id, client_name=name, redirect_uris=json.dumps(uris)))
        await session.commit()

    return JSONResponse({
        "client_id": client_id,
        "client_id_issued_at": int(_now().timestamp()),
        "client_name": name,
        "redirect_uris": uris,
        "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "scope": SCOPE,
    }, status_code=201, headers={"Access-Control-Allow-Origin": "*"})


async def _load_client(client_id: str) -> Optional[OAuthClient]:
    if not client_id:
        return None
    async with database.session() as session:
        return (await session.execute(
            select(OAuthClient).where(OAuthClient.id == client_id))).scalar_one_or_none()


def _client_allows(client: OAuthClient, redirect_uri: str) -> bool:
    try:
        return redirect_uri in json.loads(client.redirect_uris)
    except ValueError:
        return False


# --------------------------------------------------------------------------- #
# Authorization: browser GET bounces to the dashboard consent screen
# --------------------------------------------------------------------------- #
AUTHORIZE_PARAMS = ("client_id", "redirect_uri", "response_type", "state",
                    "code_challenge", "code_challenge_method", "scope", "resource")


async def _validate_authorize(params: dict):
    """Returns (client, error) where error is (code, description). A bad
    client_id / redirect_uri is reported to the user, never redirected: the
    spec forbids sending the browser to an unverified URI."""
    client = await _load_client(params.get("client_id", ""))
    if client is None:
        raise HTTPException(status_code=400, detail="Unknown client_id.")
    redirect_uri = params.get("redirect_uri", "")
    if not redirect_uri or not _client_allows(client, redirect_uri):
        raise HTTPException(status_code=400, detail="redirect_uri is not registered for this client.")
    if params.get("response_type") != "code":
        return client, ("unsupported_response_type", "Only response_type=code is supported.")
    if not params.get("code_challenge"):
        return client, ("invalid_request", "PKCE code_challenge is required.")
    if (params.get("code_challenge_method") or "S256") != "S256":
        return client, ("invalid_request", "Only code_challenge_method=S256 is supported.")
    return client, None


@router.get("/oauth/authorize")
async def authorize(request: Request):
    params = {k: request.query_params.get(k) for k in AUTHORIZE_PARAMS if request.query_params.get(k)}
    client, err = await _validate_authorize(params)
    if err:
        return RedirectResponse(add_query(params["redirect_uri"], error=err[0],
                                          error_description=err[1], state=params.get("state")),
                                status_code=302)
    return RedirectResponse(consent_url(settings.frontend_url, params), status_code=302)


@router.get("/api/oauth/client/{client_id}")
async def client_info(client_id: str):
    """What the consent screen shows: the name the client registered with."""
    client = await _load_client(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Unknown client_id.")
    return {"client_id": client.id, "client_name": client.client_name}


class ConsentRequest(BaseModel):
    client_id: str
    redirect_uri: str
    state: Optional[str] = None
    code_challenge: str
    code_challenge_method: Optional[str] = "S256"
    scope: Optional[str] = None
    response_type: Optional[str] = "code"


@router.post("/api/oauth/authorize")
async def consent(payload: ConsentRequest, request: Request):
    """The user said yes on the dashboard: mint the code, return where to go."""
    from .auth import get_current_user_required
    user = await get_current_user_required(request)
    params = payload.model_dump(exclude_none=True)
    client, err = await _validate_authorize(params)
    if err:
        return {"redirect": add_query(payload.redirect_uri, error=err[0],
                                      error_description=err[1], state=payload.state)}
    code = secrets.token_urlsafe(32)
    async with database.session() as session:
        session.add(OAuthCode(
            code_hash=hash_code(code), client_id=client.id, user_id=user.id,
            redirect_uri=payload.redirect_uri, code_challenge=payload.code_challenge,
            scope=payload.scope or SCOPE, expires_at=_now() + CODE_TTL))
        await session.commit()
    return {"redirect": add_query(payload.redirect_uri, code=code, state=payload.state)}


# --------------------------------------------------------------------------- #
# Token
# --------------------------------------------------------------------------- #
@router.post("/oauth/token")
async def token(request: Request):
    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        try:
            form = json.loads(await request.body() or b"{}")
        except ValueError:
            return _oauth_error(400, "invalid_request", "Malformed JSON body.")
    else:
        form = dict(await request.form())
    grant = form.get("grant_type")
    if grant != "authorization_code":
        return _oauth_error(400, "unsupported_grant_type",
                            "Only authorization_code is supported (tokens do not expire).")
    code = str(form.get("code") or "")
    verifier = str(form.get("code_verifier") or "")
    client_id = str(form.get("client_id") or "")
    redirect_uri = str(form.get("redirect_uri") or "")

    async with database.session() as session:
        row = (await session.execute(
            select(OAuthCode).where(OAuthCode.code_hash == hash_code(code)))).scalar_one_or_none()
        if row is None or row.used_at is not None or row.expires_at < _now():
            return _oauth_error(400, "invalid_grant", "Unknown, used or expired code.")
        if row.client_id != client_id or (redirect_uri and row.redirect_uri != redirect_uri):
            return _oauth_error(400, "invalid_grant", "Code was issued to another client or redirect_uri.")
        if not pkce_matches(verifier, row.code_challenge):
            return _oauth_error(400, "invalid_grant", "PKCE verification failed.")
        client = (await session.execute(
            select(OAuthClient).where(OAuthClient.id == client_id))).scalar_one_or_none()
        row.used_at = _now()

        raw, key_hash, prefix = api_keys.generate_key()
        session.add(ApiKey(user_id=row.user_id, key_hash=key_hash, prefix=prefix,
                           name=f"{(client.client_name if client else 'MCP client')[:50]} · connected via OAuth"))
        await session.commit()

    return JSONResponse({"access_token": raw, "token_type": "bearer", "scope": row.scope or SCOPE},
                        headers={"Cache-Control": "no-store", "Access-Control-Allow-Origin": "*"})


@router.options("/oauth/register")
@router.options("/oauth/token")
async def preflight():
    return JSONResponse({}, headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
    })


def www_authenticate(base: str) -> str:
    """Value for the 401 on /mcp: tells an OAuth-capable client where to look."""
    return f'Bearer resource_metadata="{base}/.well-known/oauth-protected-resource"'
