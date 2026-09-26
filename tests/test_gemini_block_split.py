"""A policy block on a batch of windows must bisect, not kill the job."""
import pytest
main = pytest.importorskip("main")
import gemini_worker


def _windows(n):
    return [{"id": f"w{i}", "start": i * 10, "end": i * 10 + 10, "text": f"t{i}"} for i in range(n)]


def test_block_on_pair_isolates_and_drops_only_the_culprit(monkeypatch):
    calls = []
    def fake_stage(client, model, prompt, schema):
        ids = [w["id"] for w in __import__("json").loads(prompt)]
        calls.append(ids)
        if "w5" in ids and "w6" in ids:      # the pair that trips the filter
            raise gemini_worker.GeminiBlockedError("PROHIBITED_CONTENT")
        if ids == ["w3"]:                    # and w3 blocks even on its own
            raise gemini_worker.GeminiBlockedError("PROHIBITED_CONTENT")
        return {"windows": [{"id": i, "score": 50} for i in ids]}, {"input_tokens": 1}
    monkeypatch.setattr(main, "_run_gemini_stage", fake_stage)
    costs = []
    out = main._run_stage_split(None, "m", _windows(8), lambda ws: __import__("json").dumps(ws),
                                None, "windows", costs, "score")
    got = sorted(w["id"] for w in out)
    # w5 and w6 each survive once separated; w3 only ever reached the model on
    # its own inside the [0-3] batch, which passed, so it is kept too.
    assert got == [f"w{i}" for i in range(8)]
    assert calls[0] == [f"w{i}" for i in range(8)]  # tried the whole batch first
    # Halving [4-7] separates w5 from w6 at once: two blocked calls, then
    # three that pass: [0-3], [4,5], [6,7].
    assert [c for c in calls if "w5" in c and "w6" in c] == [calls[0], ["w4", "w5", "w6", "w7"]]
    assert len(costs) == 3


def test_no_block_is_a_single_call(monkeypatch):
    calls = []
    def fake_stage(client, model, prompt, schema):
        calls.append(prompt)
        return {"shorts": [{"start": 0, "end": 20}]}, None
    monkeypatch.setattr(main, "_run_gemini_stage", fake_stage)
    out = main._run_stage_split(None, "m", _windows(3), lambda ws: "p", None, "shorts", [], "detail")
    assert out == [{"start": 0, "end": 20}] and len(calls) == 1
