"""Transient failures retry by themselves; a shutdown never fails a job.

22-sep-2026: 30-60% of jobs per hour failed at peak on a full GPU, and a
deploy's drain timeout marked six running jobs failed and refunded at once.
Users saw "failed" for problems that were entirely ours.
"""
import asyncio
import json
import os

import pytest

app_module = pytest.importorskip("app")


@pytest.fixture
def env(tmp_path, monkeypatch):
    root = tmp_path / "output"
    root.mkdir()
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(root))
    monkeypatch.setattr(app_module, "INSTANCE_ID", "me")
    monkeypatch.setattr(app_module, "_draining", False)
    monkeypatch.setattr(app_module, "_stopping", False)
    monkeypatch.setattr(app_module, "_running_jobs", set())
    monkeypatch.setattr(app_module, "jobs", {})
    monkeypatch.setattr(app_module, "AUTO_RETRY_DELAY_SECONDS", 0)
    calls = {"settled": [], "enqueued": []}

    async def fake_settle(job_id, job=None):
        calls["settled"].append(job_id)
    for name in ("_archive_managed_job", "_notify_job_webhook", "_record_job_alert",
                 "_track_proxy_usage", "_notify_clips_ready", "_notify_clip_activity"):
        async def _noop(*a, **k):
            return None
        monkeypatch.setattr(app_module, name, _noop)

    async def _noop2(*a, **k):
        return None
    monkeypatch.setattr(app_module, "_autopilot_job_finished", _noop2)
    monkeypatch.setattr(app_module, "_settle_reservation", fake_settle)
    monkeypatch.setattr(app_module, "_enqueue_job",
                        lambda job_id, priority=2: calls["enqueued"].append((job_id, priority)))
    return root, calls


def _job(root, job_id, logs):
    d = root / job_id
    d.mkdir()
    (d / app_module._RESUME_FILE).write_text(json.dumps({"cmd": ["x"], "priority": 1}))
    (d / "My_Video.mp4").write_bytes(b"src")
    (d / ".transcript_checkpoint.json").write_text("{}")
    (d / "My_Video_metadata.json").write_text("{}")
    (d / "My_Video_clip_1.mp4").write_bytes(b"half")
    job = {"status": "queued", "logs": list(logs), "cmd": ["x"], "env": {},
           "output_dir": str(d), "user_id": "u", "reservation_id": "r"}
    app_module.jobs[job_id] = job
    return d, job


def _run_wrapper(monkeypatch, job_id, final_status, raise_cancel=False):
    async def fake_run_job(jid, job):
        if raise_cancel:
            raise asyncio.CancelledError()
        job["status"] = final_status

    monkeypatch.setattr(app_module, "run_job", fake_run_job)

    async def go():
        sem = asyncio.Semaphore(1)
        await sem.acquire()
        monkeypatch.setattr(app_module, "concurrency_semaphore", sem)
        q = asyncio.PriorityQueue()
        q.put_nowait((1, 0, job_id))
        await q.get()
        monkeypatch.setattr(app_module, "job_queue", q)
        try:
            await app_module.run_job_wrapper(job_id)
        except asyncio.CancelledError:
            pass
        await asyncio.sleep(0.05)   # let the scheduled retry fire
        return sem
    return asyncio.run(go())


class TestClassification:
    def test_gpu_oom_is_transient(self):
        assert app_module.is_transient_failure(
            ["❌ Clip 1 failed: RuntimeError: CUDA out of memory"])

    def test_nvenc_is_transient(self):
        assert app_module.is_transient_failure(
            ["ERROR: Generic error in an external library", "Process failed with exit code 187"])

    def test_content_problems_are_not(self):
        assert not app_module.is_transient_failure(
            ["❌ RuntimeError: Clip detection failed — the AI model did not return usable clips"])
        assert not app_module.is_transient_failure(["ERROR: [youtube] x: Video unavailable"])
        assert not app_module.is_transient_failure(["❌ This video has no audio track."])

    def test_unknown_is_not(self):
        assert not app_module.is_transient_failure(["Process failed with exit code 1"])


class TestWrapper:
    def test_transient_failure_is_retried_once(self, env, monkeypatch):
        root, calls = env
        d, job = _job(root, "j1", ["❌ CUDA out of memory"])
        sem = _run_wrapper(monkeypatch, "j1", "failed")
        assert job["status"] == "queued" and job["auto_retries"] == 1
        assert calls["enqueued"] == [("j1", 1)]
        assert calls["settled"] == []                         # reservation kept
        assert (d / app_module._RESUME_FILE).exists()         # still resumable
        assert (d / "My_Video.mp4").exists() and (d / ".transcript_checkpoint.json").exists()
        assert not (d / "My_Video_clip_1.mp4").exists()
        assert not (d / "My_Video_metadata.json").exists()
        assert sem._value == 1                                # slot released

    def test_second_failure_is_final(self, env, monkeypatch):
        root, calls = env
        d, job = _job(root, "j2", ["❌ CUDA out of memory"])
        job["auto_retries"] = 1
        _run_wrapper(monkeypatch, "j2", "failed")
        assert job["status"] == "failed"
        assert calls["settled"] == ["j2"] and calls["enqueued"] == []
        assert not (d / app_module._RESUME_FILE).exists()

    def test_content_failure_is_not_retried(self, env, monkeypatch):
        root, calls = env
        d, job = _job(root, "j3", ["❌ Clip detection failed"])
        _run_wrapper(monkeypatch, "j3", "failed")
        assert job["status"] == "failed" and calls["enqueued"] == []

    def test_shutdown_leaves_the_job_for_the_next_instance(self, env, monkeypatch):
        root, calls = env
        d, job = _job(root, "j4", [])
        sem = _run_wrapper(monkeypatch, "j4", None, raise_cancel=True)
        assert calls["settled"] == []                         # no refund, no failure
        assert (d / app_module._RESUME_FILE).exists()
        assert sem._value == 1


class TestResumeMidRender:
    def test_manifest_with_metadata_is_resumed_not_recovered(self, env, monkeypatch):
        root, calls = env
        d = root / "j5"
        d.mkdir()
        (d / app_module._RESUME_FILE).write_text(json.dumps(
            {"cmd": ["python", "main.py"], "priority": 1, "attempts": 0}))
        (d / "V_metadata.json").write_text(json.dumps({"shorts": [{}]}))
        app_module._recover_jobs_from_disk()
        assert "j5" not in app_module.jobs                    # not "completed"
        app_module._resume_interrupted_jobs()
        assert app_module.jobs["j5"]["status"] == "queued"
        assert calls["enqueued"] == [("j5", 1)]


class TestQueueEstimate:
    def test_free_slot_starts_now(self):
        assert app_module.queue_estimate(ahead=0, running=3, slots=8, typical_seconds=240) == 15

    def test_grows_with_the_line(self):
        a = app_module.queue_estimate(ahead=8, running=8, slots=8, typical_seconds=240)
        b = app_module.queue_estimate(ahead=16, running=8, slots=8, typical_seconds=240)
        assert 30 <= a < b

    def test_snapshot_positions(self, env, monkeypatch):
        import asyncio as _a
        q = _a.PriorityQueue()
        for i, (prio, jid) in enumerate([(1, "a"), (2, "b"), (1, "c")]):
            q.put_nowait((prio, i, jid))
            app_module.jobs[jid] = {"status": "queued", "logs": []}
        monkeypatch.setattr(app_module, "job_queue", q)
        monkeypatch.setattr(app_module, "_admitting", {"z"})
        app_module.jobs["z"] = {"status": "queued", "logs": []}
        assert app_module.queue_snapshot("z")["position"] == 1
        assert app_module.queue_snapshot("a")["position"] == 2
        assert app_module.queue_snapshot("c")["position"] == 3
        assert app_module.queue_snapshot("b")["position"] == 4
        app_module.jobs["a"]["status"] = "processing"
        assert app_module.queue_snapshot("a") is None
