"""Stdio transport for the same MCP server that ``/mcp`` serves over HTTP.

``mcp_server.py`` owns the protocol; this file is only a transport: it reads
newline-delimited JSON-RPC from stdin, hands each message to
``mcp_server.handle_message`` and writes the response to stdout. Tool calls go
through the identical in-process path (``call_tool`` -> httpx ASGITransport ->
this app), so stdio and HTTP can never answer differently.

Why it exists: some hosts only launch MCP servers as a subprocess (Glama's
Dockerfile deployments wrap a stdio command, and a local client that would
rather not run a web server can do
``claude mcp add openshorts -- python mcp_stdio.py``). The hosted endpoint at
mcp.openshorts.app stays the HTTP one.

Two things this transport has to get right:

- **stdout belongs to the protocol.** The pipeline prints progress everywhere
  (main.py, app.py, yt-dlp), and one stray line corrupts the JSON-RPC stream,
  so ``sys.stdout`` is swapped for stderr before the app is imported and the
  real handle is kept private to the writer below.
- **The app's lifespan must run.** Job queues, output dirs and the resume scan
  are set up there; ASGITransport does not run it on its own.
"""
import asyncio
import json
import os
import sys

# Must happen before importing app: import-time prints would land on stdout.
_PROTOCOL_OUT = sys.stdout
sys.stdout = sys.stderr

from starlette.requests import Request  # noqa: E402

import app as app_module  # noqa: E402
import mcp_server  # noqa: E402

# BYOK credentials reach the tools the same way an HTTP client would send them:
# as forwarded headers (mcp_server._FORWARD_HEADERS), not as a second code path.
_ENV_HEADERS = {
    "authorization": lambda: (
        f"Bearer {os.environ['OPENSHORTS_API_KEY']}"
        if os.environ.get("OPENSHORTS_API_KEY") else None
    ),
    "x-gemini-key": lambda: os.environ.get("GEMINI_API_KEY"),
    "x-upload-post-key": lambda: os.environ.get("UPLOAD_POST_API_KEY"),
}


def _request() -> Request:
    """A synthetic ASGI request carrying the app and the auth headers.

    ``mcp_server.call_tool`` only reads ``.app`` and ``.headers`` off it."""
    headers = []
    for name, read in _ENV_HEADERS.items():
        value = read()
        if value:
            headers.append((name.encode(), value.encode()))
    return Request({
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/mcp",
        "raw_path": b"/mcp",
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 0),
        "server": ("openshorts.internal", 80),
        "app": app_module.app,
    })


def _write(response: dict) -> None:
    _PROTOCOL_OUT.write(json.dumps(response, ensure_ascii=False) + "\n")
    _PROTOCOL_OUT.flush()


async def _stdin_lines():
    """Yield stdin lines without blocking the loop (tool calls run for minutes)."""
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)
    while True:
        line = await reader.readline()
        if not line:  # EOF: the host closed the pipe
            return
        yield line


async def _serve() -> None:
    async with app_module.app.router.lifespan_context(app_module.app):
        request = _request()

        async def tool_caller(name, args):
            return await mcp_server.call_tool(request, name, args)

        async for line in _stdin_lines():
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except Exception:
                _write(mcp_server._rpc_error(None, -32700, "Parse error"))
                continue
            if isinstance(msg, list):
                _write(mcp_server._rpc_error(None, -32600, "Batching is not supported"))
                continue
            response = await mcp_server.handle_message(msg, tool_caller)
            if response is not None:
                _write(response)


def main() -> None:
    try:
        asyncio.run(_serve())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
