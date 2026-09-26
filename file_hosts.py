"""Resolvers for throwaway file hosts agents upload to when they cannot reach
our own upload endpoint (claude.ai's sandbox could reach tmpfiles.org but not
0x0.st, for instance).

tmpfiles.org: the `/dl/<stamp>.<sig>/<id>/<name>` link an upload returns is
signed with a short-lived stamp. Once stale it 302s to the HTML page
`/<id>/<name>`, whose Download button carries a freshly signed `/dl/` link;
yt-dlp then chokes on the HTML. Resolving through the page first gives the
live link every time. Files there expire 60 minutes after upload.
"""
from __future__ import annotations

import re
import urllib.request
from urllib.parse import urlparse

_TMPFILES_HOSTS = ("tmpfiles.org", "www.tmpfiles.org")
_DL_RE = re.compile(r'href="(https://tmpfiles\.org/dl/[^"]+)"')


def is_tmpfiles(url: str) -> bool:
    try:
        return urlparse(url).hostname in _TMPFILES_HOSTS
    except Exception:
        return False


def _page_url(url: str) -> str:
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    if parts and parts[0] == "dl":
        # /dl/<stamp>/<id>/<name>  ->  /<id>/<name>
        parts = parts[2:] if len(parts) >= 3 else parts[1:]
    return f"https://tmpfiles.org/{'/'.join(parts)}"


def resolve_tmpfiles(url: str, fetch=None) -> str:
    """The currently valid direct-download URL for a tmpfiles.org link.

    ``fetch(url) -> str`` is injectable for tests. Falls back to the input
    on any failure so the caller's normal error path still runs."""
    fetch = fetch or _fetch
    try:
        html = fetch(_page_url(url))
        m = _DL_RE.search(html)
        return m.group(1) if m else url
    except Exception:
        return url


def resolve(url: str) -> str:
    """Swap a known temp-host link for one yt-dlp can download, else return it."""
    if is_tmpfiles(url):
        fresh = resolve_tmpfiles(url)
        if fresh != url:
            print("🔗 tmpfiles.org link refreshed for download")
        return fresh
    return url


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (OpenShorts)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read(200_000).decode("utf-8", "ignore")
