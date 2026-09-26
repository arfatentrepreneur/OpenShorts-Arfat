"""Capability tokens and path rules for the ``/videos`` and ``/thumbnails`` bytes.

Both paths used to be ``StaticFiles`` mounts, i.e. the whole working directory
served to the internet with a UUID for a lock. That handed out more than the
clips: the ``.resume.json`` manifest (which carries the customer's own
``webhook_secret``), the ``.owner`` sidecar (a user uuid), the ``.instance``
deploy marker, the face crops under ``thumbnails/`` and every actor photo a user
had uploaded. ``app.py`` now serves those two prefixes through real handlers
that ask who is calling; this module is the part of that with no FastAPI in it,
so both ``app.py`` and ``mcp_server.py`` can sign a URL without importing each
other.

Two token shapes, because there are two kinds of consumer:

* **path capability** (``?exp=…&sig=…``) — an HMAC over one relative path and an
  expiry. This is what goes to a consumer that cannot send a header at all: the
  webhook payload and the absolute URLs the MCP tools return. Same idea as the
  R2 ``presigned_get`` links the history endpoint already hands out, and as
  ``/api/source-url``.
* **user token** (``?mt=<uid>.<exp>.<sig>``) — a short-lived bearer for one
  user, minted at ``/api/media-token``. A ``<video src>`` or ``<img src>``
  cannot carry an ``Authorization`` header, so the dashboard appends this to
  every media URL it builds (one place: ``getApiUrl``) instead of leaking the
  30-day session JWT into query strings, access logs and referrers.

A request that arrives with an ordinary ``Authorization: Bearer`` / ``X-API-Key``
header (agents, ``curl``, the MCP client) needs neither: ``app.py`` resolves the
user from the header and compares it to the owner directly.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import posixpath
import time
from typing import Optional

# A signed media link has to outlive the page that was handed it. Local working
# files are swept after an hour anyway (JOB_RETENTION_SECONDS), so the ceiling
# here is about the link, not the file.
MEDIA_URL_TTL_SECONDS = int(os.environ.get("MEDIA_URL_TTL_SECONDS", "86400"))
# The dashboard's per-user media token. Deliberately much shorter than the
# session JWT (30 days): it travels in URLs, so it must die quickly.
MEDIA_TOKEN_TTL_SECONDS = int(os.environ.get("MEDIA_TOKEN_TTL_SECONDS", "43200"))

# Nothing outside this list is a deliverable: the working directories also hold
# transcripts, metadata JSON, resume manifests and ownership sidecars, and an
# allowlist is the only version of this rule that stays correct when the
# pipeline starts writing a new kind of scratch file.
SERVABLE_EXTENSIONS = frozenset({
    ".mp4", ".webm", ".mov", ".m4v", ".mkv", ".ogv",
    ".mp3", ".m4a", ".wav", ".aac", ".flac", ".opus",
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif",
    ".srt", ".vtt", ".ass", ".zip",
})


class MediaPathError(ValueError):
    """The requested path is not something these prefixes may ever serve."""


def normalise_relpath(rel_path: str) -> str:
    """Return ``rel_path`` as a clean forward-slash relative path.

    Raises ``MediaPathError`` for absolute paths, traversal, and any segment
    starting with a dot — which is what keeps ``.resume.json`` (webhook secret),
    ``.owner`` (user uuid), ``.instance`` and ``.transcript_checkpoint.json``
    unreachable no matter who is asking.
    """
    if not rel_path or not isinstance(rel_path, str):
        raise MediaPathError("Empty path")
    cleaned = rel_path.replace("\\", "/").strip("/")
    if not cleaned:
        raise MediaPathError("Empty path")
    if "\x00" in cleaned:
        raise MediaPathError("Invalid path")
    segments = [s for s in cleaned.split("/") if s != ""]
    if not segments:
        raise MediaPathError("Empty path")
    for segment in segments:
        if segment.startswith("."):
            # Covers "." and ".." as well as every dotfile the pipeline writes.
            raise MediaPathError(f"Hidden or relative segment: {segment!r}")
    return posixpath.join(*segments)


def is_servable(rel_path: str) -> bool:
    """True if this relative path is both visible and of a deliverable type."""
    try:
        cleaned = normalise_relpath(rel_path)
    except MediaPathError:
        return False
    return posixpath.splitext(cleaned)[1].lower() in SERVABLE_EXTENSIONS


def _digest(secret: str, message: str) -> str:
    return hmac.new((secret or "").encode(), message.encode(),
                    hashlib.sha256).hexdigest()[:32]


# --- path capability -------------------------------------------------------

def path_signature(rel_path: str, exp: int, secret: str) -> str:
    """HMAC tying one relative media path to an expiry."""
    return _digest(secret, f"media:{normalise_relpath(rel_path)}:{int(exp)}")


def sign_media_url(url_path: str, secret: str, ttl: Optional[int] = None) -> str:
    """Append ``?exp=…&sig=…`` to ``/videos/<rel>`` or ``/thumbnails/<rel>``.

    Returns the URL untouched when there is no secret to sign with (self-host:
    nothing to protect, and a signature keyed on "" would be theatre) or when
    the path is not one of the two protected prefixes.
    """
    if not secret or not url_path or "?" in url_path:
        return url_path
    rel = strip_media_prefix(url_path)
    if rel is None:
        return url_path
    try:
        exp = int(time.time()) + int(ttl or MEDIA_URL_TTL_SECONDS)
        sig = path_signature(rel, exp, secret)
    except MediaPathError:
        return url_path
    return f"{url_path}?exp={exp}&sig={sig}"


def verify_path_signature(rel_path: str, exp, sig: str, secret: str) -> bool:
    """Constant-time check of a path capability token."""
    if not secret or not sig:
        return False
    try:
        exp_i = int(exp)
    except (TypeError, ValueError):
        return False
    if exp_i <= int(time.time()):
        return False
    try:
        expected = path_signature(rel_path, exp_i, secret)
    except MediaPathError:
        return False
    return hmac.compare_digest(sig, expected)


# --- per-user token --------------------------------------------------------

def mint_user_token(user_id, secret: str, ttl: Optional[int] = None) -> str:
    """``<uid>.<exp>.<sig>`` — a short-lived media bearer for one user."""
    uid = str(user_id)
    exp = int(time.time()) + int(ttl or MEDIA_TOKEN_TTL_SECONDS)
    return f"{uid}.{exp}.{_digest(secret, f'mediatoken:{uid}:{exp}')}"


def verify_user_token(token: str, secret: str) -> Optional[str]:
    """Return the user id a media token proves, or None if it proves nothing."""
    if not secret or not token or token.count(".") != 2:
        return None
    uid, exp_s, sig = token.split(".")
    try:
        exp = int(exp_s)
    except ValueError:
        return None
    if exp <= int(time.time()):
        return None
    if not hmac.compare_digest(sig, _digest(secret, f"mediatoken:{uid}:{exp}")):
        return None
    return uid


# --- prefix helpers --------------------------------------------------------

MEDIA_PREFIXES = ("/videos/", "/thumbnails/")


def strip_media_prefix(url_path: str) -> Optional[str]:
    """``/videos/a/b.mp4`` -> ``videos-relative`` path, or None if not ours.

    ``/thumbnails/<x>`` is mounted on ``output/thumbnails`` while ``/videos/<x>``
    is mounted on ``output``, so the returned path is relative to whichever base
    the caller's prefix names — the signature only has to be stable, not to
    describe the filesystem.
    """
    if not url_path:
        return None
    for prefix in MEDIA_PREFIXES:
        if url_path.startswith(prefix):
            return prefix.strip("/") + "/" + url_path[len(prefix):]
    return None
