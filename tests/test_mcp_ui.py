"""MCP Apps surface: the clip picker resource and its wiring.

Pure protocol-layer tests (handle_message with a fake tool_caller), same
pattern as test_mcp_protocol.py.
"""
import asyncio

import mcp_ui
from mcp_server import TOOLS, handle_message


def _run(msg, tool_caller=None):
    async def _noop(name, args):
        return {}, False
    return asyncio.run(handle_message(msg, tool_caller or _noop))


def _req(method, params=None, msg_id=1):
    m = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        m["params"] = params
    return m


class TestResourceSurface:
    def test_initialize_advertises_resources(self):
        resp = _run(_req("initialize", {"protocolVersion": "2025-06-18"}))
        assert "resources" in resp["result"]["capabilities"]

    def test_resources_list_contains_the_picker(self):
        resp = _run(_req("resources/list"))
        uris = [r["uri"] for r in resp["result"]["resources"]]
        assert mcp_ui.CLIP_PICKER_URI in uris

    def test_resources_read_serves_the_template(self):
        resp = _run(_req("resources/read", {"uri": mcp_ui.CLIP_PICKER_URI}))
        content = resp["result"]["contents"][0]
        assert content["mimeType"] == mcp_ui.MIME_TYPE
        # Template mode: no baked data, the bridge provides it.
        assert "__OPENSHORTS_DATA__" not in content["text"]
        assert "var inline = null;" in content["text"]

    def test_resources_read_accepts_per_call_uris(self):
        resp = _run(_req("resources/read", {"uri": mcp_ui.CLIP_PICKER_URI + "/job42"}))
        assert resp["result"]["contents"][0]["uri"].endswith("/job42")

    def test_unknown_resource_is_not_found(self):
        resp = _run(_req("resources/read", {"uri": "ui://other/thing"}))
        assert resp["error"]["code"] == -32002


class TestToolWiring:
    def test_list_clips_declares_the_template_in_meta(self):
        tool = next(t for t in TOOLS if t["name"] == "list_clips")
        assert tool["_meta"]["ui"]["resourceUri"] == mcp_ui.CLIP_PICKER_URI
        assert tool["_meta"]["openai/outputTemplate"] == mcp_ui.CLIP_PICKER_URI

    def test_list_clips_result_embeds_the_picker_with_data(self):
        clips = {"job_id": "j1", "clips": [{"index": 0, "title": "A", "video_url": "http://x/v.mp4"}]}

        async def fake(name, args):
            return clips, False

        resp = _run(_req("tools/call", {"name": "list_clips",
                                        "arguments": {"job_id": "j1"}}), fake)
        content = resp["result"]["content"]
        assert content[0]["type"] == "text"
        embedded = content[1]
        assert embedded["type"] == "resource"
        assert embedded["resource"]["mimeType"] == mcp_ui.MIME_TYPE
        assert embedded["resource"]["uri"] == mcp_ui.CLIP_PICKER_URI + "/j1"
        assert '"job_id": "j1"' in embedded["resource"]["text"]

    def test_other_tools_stay_text_only(self):
        async def fake(name, args):
            return {"clips": [{"index": 0}]}, False  # even with clips in result

        resp = _run(_req("tools/call", {"name": "get_quota", "arguments": {}}), fake)
        assert len(resp["result"]["content"]) == 1

    def test_failed_list_clips_embeds_nothing(self):
        async def fake(name, args):
            return {"error": "job is processing", "clips": []}, True

        resp = _run(_req("tools/call", {"name": "list_clips",
                                        "arguments": {"job_id": "j1"}}), fake)
        assert len(resp["result"]["content"]) == 1


class TestTemplateSafety:
    def test_titles_cannot_break_out_of_the_script_tag(self):
        html = mcp_ui.clip_picker_html(
            {"job_id": "j", "clips": [{"index": 0, "title": "</script><img onerror=x>"}]})
        assert "</script><img" not in html
        assert "\\u003c/script" in html

    def test_template_is_self_contained(self):
        html = mcp_ui.clip_picker_html()
        for marker in ("http://", "https://"):
            # No external fetches: host CSPs block them and the picker must
            # render anyway. (Clip video URLs are data, not template.)
            assert marker not in html
