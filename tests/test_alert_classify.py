"""Failure classification for the high-failure-rate alert."""
from cloud.alerts import _classify_failure


def test_no_audio():
    assert _classify_failure("❌ NO_AUDIO: This video has no audio track.") == "no audio"


def test_youtube_bot_block():
    assert _classify_failure("ERROR: [youtube] x: Sign in to confirm you're not a bot") == "youtube download"
    assert _classify_failure("HTTP Error 403: Forbidden") == "youtube download"
    assert _classify_failure("HTTP Error 429: Too Many Requests") == "youtube download"


def test_proxy():
    assert _classify_failure("cannot connect to proxy") == "proxy"
    assert _classify_failure("402 payment required") == "proxy"


def test_transcription():
    assert _classify_failure("File faster_whisper/audio.py IndexError") == "transcription"
    assert _classify_failure("av/container/streams.py tuple index out of range") == "transcription"


def test_gemini():
    assert _classify_failure("google.genai error 500") == "gemini"


def test_ffmpeg():
    assert _classify_failure("ffmpeg failed during reframe") == "ffmpeg/render"


def test_unknown_is_mixed():
    assert _classify_failure("something weird happened") == "mixed"


def test_blocked_content_is_not_reported_as_outage():
    assert _classify_failure(
        "🚫 Gemini blocked this video's content (PROHIBITED_CONTENT)."
    ) == "blocked content (user video)"


def test_no_usable_clips_is_not_reported_as_outage():
    assert _classify_failure(
        "RuntimeError: Clip detection failed — Gemini did not return usable clips for this video."
    ) == "no clips found (user video)"


# --- _job_error_text: which log lines feed the classifier -----------------------

def test_recovered_download_attempts_do_not_mask_the_terminal_error():
    """HD-direct fails on every job (banned server IP) and a later attempt
    succeeds; that per-attempt noise must not turn a Gemini failure into a
    'youtube download' alert (prod 20-ago)."""
    import pytest
    app_module = pytest.importorskip("app")
    logs = [
        "📥 Download attempt: HD-direct",
        "⚠️  Download attempt 'HD-direct' failed: ERROR: [youtube] x: Video unavailable.",
        "📥 Download attempt: HD-static1",
        "✅ Download succeeded (HD-static1).",
        "Traceback (most recent call last):",
        "RuntimeError: Clip detection failed — Gemini did not return usable clips for this video.",
    ]
    err = app_module._job_error_text(logs)
    assert "Video unavailable" not in err
    assert _classify_failure(err) == "no clips found (user video)"


def test_terminal_download_failure_still_classifies_as_download():
    import pytest
    app_module = pytest.importorskip("app")
    logs = [
        "⚠️  Download attempt 'HD-direct' failed: ERROR: [youtube] x: Video unavailable.",
        "❌ FATAL ERROR: YOUTUBE DOWNLOAD FAILED (all strategies)",
        "Technical Details: ERROR: [youtube] x: Video unavailable. This content isn't available.",
        "Process failed with exit code 1",
    ]
    err = app_module._job_error_text(logs)
    assert _classify_failure(err) == "youtube download"
