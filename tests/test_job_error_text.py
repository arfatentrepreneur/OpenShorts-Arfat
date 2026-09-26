"""Picking the real error out of a job log, for the failure-rate alert.

Regression cover for two prod alerts (22-jul-2026) that named the wrong
subsystem because the classifier read the tail of the log instead of the error:
a Gemini blip was reported as "ffmpeg/render" and a silent upload as a broken
download path.
"""
import pytest

# app pulls in dotenv/fastapi/cloud at import time; the minimal CI env lacks
# them, so skip there. Runs fully in the container/local where deps exist.
app = pytest.importorskip("app")
from cloud.alerts import _classify_failure


def _classify(logs):
    return _classify_failure(app._job_error_text(logs))


def test_gemini_blip_is_not_blamed_on_ffmpeg():
    # The render noise that followed the error used to win, because it was last.
    logs = [
        "🤖  Analyzing with Gemini (2-pass: score → detail)...",
        "   Built 5 scoring window(s).",
        "❌ Gemini Error: Gemini returned an empty response body.",
        "🚀 Reframe engine v2 (ffmpeg-native render)",
        "/app/scene_detection.py:109: UserWarning: The given NumPy array is not writable",
        "🎬 Scene engine: TransNetV2 — 67 scenes",
        "Analyzing Scenes:   0%|          | 0/67 [00:00<?, ?it/s]",
        "Process failed with exit code 1",
    ]
    assert _classify(logs) == "gemini"


def test_download_failure_survives_trailing_noise():
    logs = [
        "📥 Download attempt: HD",
        "⚠️  Download attempt 'HD' failed: ERROR: unable to download video data: HTTP Error 403: Forbidden",
        "❌ FATAL ERROR: YOUTUBE DOWNLOAD FAILED (all strategies)",
        "🗑️  Cleaned up downloaded video.",
        "⏱️  Total execution time: 12.00s",
    ]
    assert _classify(logs) == "youtube download"


def test_silent_upload_reports_no_audio():
    logs = [
        "🎙️  Transcribing video...",
        "❌ NO_AUDIO: This video has no audio track.",
        "Process failed with exit code 1",
    ]
    assert _classify(logs) == "no audio"


def test_falls_back_to_tail_when_nothing_looks_like_an_error():
    logs = [f"line {i}" for i in range(20)]
    assert app._job_error_text(logs) == " ".join(f"line {i}" for i in range(10, 20))


def test_keeps_only_the_most_recent_errors():
    logs = [f"❌ error {i}" for i in range(12)]
    out = app._job_error_text(logs)
    assert "❌ error 11" in out
    assert "❌ error 0" not in out
