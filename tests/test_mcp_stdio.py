"""Stdio transport (mcp_stdio.py), exercised as the subprocess a host launches.

It has to be a real subprocess: the thing most likely to break this transport
is the pipeline's own chatter (the app prints on import and on startup), and
that only shows up when stdout is a pipe. Every line the host reads must be
JSON-RPC and nothing else.
"""
import json
import os
import subprocess
import sys

import pytest

from mcp_server import TOOLS

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MESSAGES = [
    {"jsonrpc": "2.0", "id": 1, "method": "initialize",
     "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "1"}}},
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
]


@pytest.fixture(scope="module")
def responses():
    env = dict(os.environ, BILLING_ENABLED="0", PYTHONPATH=REPO)
    env.pop("PROXY_URL", None)
    proc = subprocess.run(
        [sys.executable, "-u", os.path.join(REPO, "mcp_stdio.py")],
        input="".join(json.dumps(m) + "\n" for m in MESSAGES),
        capture_output=True, text=True, cwd=REPO, env=env, timeout=300,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]


class TestStdioTransport:
    def test_stdout_carries_only_protocol_lines(self, responses):
        # The notification gets no reply, and no print() leaked into the stream.
        assert [r["id"] for r in responses] == [1, 2]
        assert all(r["jsonrpc"] == "2.0" for r in responses)

    def test_initialize_reports_the_same_server(self, responses):
        result = responses[0]["result"]
        assert result["serverInfo"]["name"] == "openshorts"
        assert result["protocolVersion"] == "2025-06-18"

    def test_tools_match_the_http_transport(self, responses):
        names = [t["name"] for t in responses[1]["result"]["tools"]]
        assert names == [t["name"] for t in TOOLS]
