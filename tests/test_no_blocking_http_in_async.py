"""A blocking HTTP call inside an ``async def`` handler freezes the whole
uvicorn event loop for as long as the request takes.

23-sep-2026 19:47:48 UTC: /api/social/post uploaded a clip to Upload-Post with
a sync ``httpx.Client`` inline; every request, /health included, stalled for
42 s and the uptime monitor paged "openshorts-api down". Blocking clients are
fine in a plain ``def`` called through ``asyncio.to_thread``; this test only
rejects them lexically inside a coroutine body (nested sync ``def``s are
skipped, since those are what gets handed to the thread).
"""
import ast
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app.py"


def _is_blocking_call(node: ast.Call) -> bool:
    f = node.func
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
        if f.value.id == "httpx" and f.attr == "Client":
            return True
        if f.value.id == "requests" and f.attr in {
            "get", "post", "put", "patch", "delete", "head", "request",
        }:
            return True
    return False


def _blocking_calls_in(fn: ast.AsyncFunctionDef):
    stack = list(fn.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(node, ast.Call) and _is_blocking_call(node):
            yield node.lineno
        stack.extend(ast.iter_child_nodes(node))


def test_no_blocking_http_client_inside_async_handlers():
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    offenders = [
        f"{fn.name}:{line}"
        for fn in ast.walk(tree)
        if isinstance(fn, ast.AsyncFunctionDef)
        for line in _blocking_calls_in(fn)
    ]
    assert not offenders, (
        "blocking HTTP call inside async def (wrap it in asyncio.to_thread): "
        + ", ".join(sorted(offenders))
    )
