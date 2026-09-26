"""Hook grounding: rewrite hook + title from a clip's frames when the render
put its meaning on the screen (hook_grounding.py).

The bug this fixes: a SCREENCAST clip of someone configuring an MCP
connector shipped with the hook "I automated my clips with AI", because the
detail pass only ever reads the transcript.
"""
import pytest

import gemini_worker
import hook_grounding as hg


SCREEN = [{"start": 0, "end": 30, "layout": "screencast"}]
FACE = [{"start": 0, "end": 30, "layout": "track"}]
MIXED = [{"start": 0, "end": 5, "layout": "track"},
         {"start": 5, "end": 30, "layout": "wide"}]


# --- when to run -----------------------------------------------------------

def test_screen_layouts_trigger_and_face_layouts_do_not(monkeypatch):
    monkeypatch.setattr(hg, "screen_video", lambda: False)
    assert hg.wanted(SCREEN, 30) is True
    assert hg.wanted(MIXED, 30) is True
    assert hg.wanted(FACE, 30) is False
    assert hg.wanted([], 30) is False


def test_general_counts_as_screen_only_on_a_screencast_video(monkeypatch):
    # The reported case: picker said screencast, the render emitted
    # track/general only (stats cards have no face), grounding never ran.
    general = [{"start": 0, "end": 8, "layout": "track"},
               {"start": 8, "end": 30, "layout": "general"}]
    monkeypatch.setattr(hg, "screen_video", lambda: True)
    assert hg.wanted(general, 30) is True
    monkeypatch.setattr(hg, "screen_video", lambda: False)
    assert hg.wanted(general, 30) is False  # a group shot is not a screen


def test_a_blip_is_not_enough(monkeypatch):
    blip = [{"start": 0, "end": 2, "layout": "screencast"},
            {"start": 2, "end": 30, "layout": "track"}]
    assert hg.wanted(blip, 30) is False


def test_env_switch_disables(monkeypatch):
    monkeypatch.setenv("HOOK_GROUNDING", "0")
    assert hg.wanted(SCREEN, 30) is False


# --- inputs to the model ---------------------------------------------------

def test_frames_are_sampled_inside_the_screen_stretches():
    times = hg.sample_times(MIXED, 30, n=3)
    assert len(times) == 3
    assert all(5 <= t <= 30 for t in times)
    assert times == sorted(times)


def test_without_sidecar_frames_spread_over_the_clip():
    assert hg.sample_times([], 60, n=3) == [10, 30, 50]


def test_clip_words_uses_word_timestamps_and_falls_back_to_segment_text():
    transcript = {"segments": [
        {"start": 0, "end": 10, "text": "hello there",
         "words": [{"word": "hello", "start": 0, "end": 1},
                   {"word": "there", "start": 9, "end": 10}]},
        {"start": 10, "end": 20, "text": "no words here"},
        {"start": 40, "end": 50, "text": "outside"},
    ]}
    assert hg.clip_words(transcript, 8, 15) == "there no words here"


# --- the rewrite -----------------------------------------------------------

@pytest.fixture
def gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(hg, "frames_at", lambda path, times, width=None: [b"jpg"] * len(times))
    seen = {}

    def fake(frames, prompt, api_key):
        seen["frames"] = frames
        seen["prompt"] = prompt
        return {"on_screen": "Claude settings, MCP connector dialog for OpenShorts",
                "viral_hook_text": "Conectando OpenShorts a Claude por MCP",
                "video_title_for_youtube_short": "Así se conecta OpenShorts a Claude (MCP)"}

    monkeypatch.setattr(hg, "_ask_gemini", fake)
    return seen


def test_rewrites_hook_and_title_and_keeps_the_originals(gemini):
    clip = {"viral_hook_text": "He automatizado la creación de mis clips con IA.",
            "video_title_for_youtube_short": "Clips con IA",
            "layout_ranges": SCREEN}
    transcript = {"language": "es", "segments": [
        {"start": 100, "end": 110, "text": "añadimos el conector de OpenShorts"}]}

    changed = hg.reground("clip.mp4", clip, transcript, 100, 130)

    assert clip["viral_hook_text"] == "Conectando OpenShorts a Claude por MCP"
    assert clip["video_title_for_youtube_short"].startswith("Así se conecta")
    assert clip["hook_grounding"]["before"]["viral_hook_text"].startswith("He automatizado")
    assert changed["on_screen"].startswith("Claude settings")
    assert len(gemini["frames"]) == 3
    assert "añadimos el conector" in gemini["prompt"]
    assert "He automatizado" in gemini["prompt"]  # the model sees the current hook
    assert "TRANSCRIPT_LANGUAGE: es" in gemini["prompt"]


def test_without_a_gemini_key_the_transcript_hook_stands(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    clip = {"viral_hook_text": "old", "layout_ranges": SCREEN}
    assert hg.reground("clip.mp4", clip, {"segments": []}, 0, 30) is None
    assert clip["viral_hook_text"] == "old" and "hook_grounding" not in clip


def test_model_failure_never_touches_the_clip(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(hg, "frames_at", lambda *a, **k: [b"jpg"])
    monkeypatch.setattr(hg, "_ask_gemini", lambda *a: (_ for _ in ()).throw(RuntimeError("503")))
    clip = {"viral_hook_text": "old", "layout_ranges": SCREEN}
    assert hg.reground("clip.mp4", clip, {"segments": []}, 0, 30) is None
    assert clip["viral_hook_text"] == "old"


def test_empty_answer_keeps_the_old_hook(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(hg, "frames_at", lambda *a, **k: [b"jpg"])
    monkeypatch.setattr(hg, "_ask_gemini", lambda *a: {"viral_hook_text": ""})
    clip = {"viral_hook_text": "old", "layout_ranges": SCREEN}
    assert hg.reground("clip.mp4", clip, {"segments": []}, 0, 30) is None
    assert clip["viral_hook_text"] == "old"


# --- the cheap half: the detail prompt itself -------------------------------

def test_detail_prompt_forbids_topic_summary_hooks():
    assert "ABOUT THIS MOMENT, NOT THE VIDEO" in gemini_worker.DETAIL_PROMPT_TEMPLATE
    assert "{on_screen" not in gemini_worker.DETAIL_PROMPT_TEMPLATE  # no stray placeholders
    gemini_worker.GROUNDED_HOOK_PROMPT.format(
        language="es", current_hook="a", current_title="b", transcript="c")
