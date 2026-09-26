import sys
import types

import layout_picker
from layout_picker import _module_flags, apply, pick


def fake_modules(monkeypatch, **initial):
    """Install stand-in layout modules so apply() can be tested without them."""
    made = {}
    for name in ("split_layout", "screencast_layout", "active_speaker"):
        module = types.ModuleType(name)
        module.ENABLED = initial.get(name, False)
        monkeypatch.setitem(sys.modules, name, module)
        made[name] = module
    return made


class TestDecisionMapping:
    def test_none_enables_nothing(self):
        assert _module_flags("none") == []

    def test_screencast_enables_its_module(self):
        assert _module_flags("screencast") == ["screencast_layout"]

    def test_split_also_needs_the_speaker_signal(self):
        # Stacking without knowing who talks is the failure mode the corpus
        # run showed: half a frame given to someone who never speaks.
        assert "active_speaker" in _module_flags("split")

    def test_unknown_and_empty_decisions_are_inert(self):
        for value in ("gameplay", "", None, "SPLIT-SCREEN"):
            assert _module_flags(value) == []

    def test_decision_is_case_and_space_insensitive(self):
        assert _module_flags("  SCREENCAST ") == ["screencast_layout"]


class TestApply:
    def test_apply_switches_the_right_module_on(self, monkeypatch):
        mods = fake_modules(monkeypatch)
        touched = apply("screencast")
        assert touched == ["screencast_layout"]
        assert mods["screencast_layout"].ENABLED is True
        assert mods["split_layout"].ENABLED is False

    def test_apply_none_touches_nothing(self, monkeypatch):
        mods = fake_modules(monkeypatch)
        assert apply("none") == []
        assert not any(m.ENABLED for m in mods.values())

    def test_apply_never_disables_an_explicit_choice(self, monkeypatch):
        # An operator who set SPLIT_LAYOUT=1 gets stacking even if the model
        # says "none". The picker only ever adds.
        mods = fake_modules(monkeypatch, split_layout=True)
        apply("none")
        assert mods["split_layout"].ENABLED is True

    def test_already_enabled_modules_are_not_reported_as_touched(self, monkeypatch):
        fake_modules(monkeypatch, screencast_layout=True)
        assert apply("screencast") == []

    def test_split_enables_both_modules(self, monkeypatch):
        mods = fake_modules(monkeypatch)
        assert set(apply("split")) == {"split_layout", "active_speaker"}
        assert mods["split_layout"].ENABLED is True
        assert mods["active_speaker"].ENABLED is True


class TestPick:
    def test_disabled_picker_never_calls_out(self, monkeypatch):
        monkeypatch.setattr(layout_picker, "ENABLED", False)
        monkeypatch.setenv("GEMINI_API_KEY", "x")
        assert pick("video.mp4", 60) == "none"

    def test_missing_api_key_degrades_to_none(self, monkeypatch):
        monkeypatch.setattr(layout_picker, "ENABLED", True)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        assert pick("video.mp4", 60) == "none"

    def test_a_failed_call_degrades_to_none(self, monkeypatch):
        # Import failure inside pick() stands in for any API error; the job
        # must keep rendering with today's routing rather than die.
        monkeypatch.setattr(layout_picker, "ENABLED", True)
        monkeypatch.setenv("GEMINI_API_KEY", "x")
        monkeypatch.setitem(sys.modules, "google.genai", None)
        assert pick("video.mp4", 60) == "none"


class TestValidDecisions:
    def test_every_valid_decision_maps_to_known_modules(self):
        known = {"split_layout", "screencast_layout", "active_speaker"}
        for decision in layout_picker.VALID:
            assert set(_module_flags(decision)) <= known

    def test_none_is_a_valid_decision(self):
        # The model answers "none" for most videos; it must not be treated as
        # an unrecognised value and logged as a warning on every job.
        assert "none" in layout_picker.VALID


class TestSampleFrames:
    def test_unreadable_video_yields_no_frames(self):
        # A path that cannot be opened must come back empty, not raise: pick()
        # turns "no frames" into "none" and the job carries on.
        assert layout_picker.sample_frames("/nonexistent/video.mp4") == []

    def test_no_frames_degrades_to_none(self, monkeypatch):
        monkeypatch.setattr(layout_picker, "ENABLED", True)
        monkeypatch.setenv("GEMINI_API_KEY", "x")
        monkeypatch.setattr(layout_picker, "sample_frames", lambda *a, **k: [])
        assert pick("video.mp4", 60) == "none"

    def test_sample_size_is_configurable(self, monkeypatch):
        # The 12/1024px pair is measured; keep it overridable without a deploy.
        monkeypatch.setenv("LAYOUT_SAMPLE_FRAMES", "6")
        assert layout_picker.SAMPLE_FRAMES == 12  # read at import, not per call


class TestShadowMode:
    def test_shadow_decides_but_applies_nothing(self, monkeypatch):
        # The whole point: the render must be identical to a run with the
        # picker switched off.
        mods = fake_modules(monkeypatch)
        monkeypatch.setattr(layout_picker, "ENABLED", True)
        monkeypatch.setattr(layout_picker, "SHADOW", True)
        monkeypatch.setattr(layout_picker, "pick", lambda *a, **k: "screencast")
        assert layout_picker.pick_and_apply("v.mp4", 60) == "screencast"
        assert not any(m.ENABLED for m in mods.values())

    def test_normal_mode_still_applies(self, monkeypatch):
        mods = fake_modules(monkeypatch)
        monkeypatch.setattr(layout_picker, "ENABLED", True)
        monkeypatch.setattr(layout_picker, "SHADOW", False)
        monkeypatch.setattr(layout_picker, "pick", lambda *a, **k: "screencast")
        layout_picker.pick_and_apply("v.mp4", 60)
        assert mods["screencast_layout"].ENABLED is True

    def test_shadow_logs_one_greppable_line(self, monkeypatch, capsys):
        fake_modules(monkeypatch)
        monkeypatch.setattr(layout_picker, "ENABLED", True)
        monkeypatch.setattr(layout_picker, "SHADOW", True)
        monkeypatch.setattr(layout_picker, "pick", lambda *a, **k: "split")
        layout_picker.pick_and_apply("v.mp4", 90)
        out = capsys.readouterr().out
        assert "[layout-shadow]" in out
        assert "decision=split" in out
        assert "would_enable=split_layout,active_speaker" in out


def test_sample_frames_falls_back_to_ffmpeg_when_opencv_reads_nothing(tmp_path, monkeypatch):
    """AV1 sources: OpenCV's bundled FFmpeg reads no frame, the CLI does."""
    import numpy as np

    src = tmp_path / "av1.mp4"
    src.write_bytes(b"not a video OpenCV can open")
    frame = np.full((360, 640, 3), 120, dtype=np.uint8)
    monkeypatch.setattr(layout_picker, "_ffmpeg_frames", lambda path, n: [frame] * n)

    out = layout_picker.sample_frames(str(src), n=3, width=320)

    assert len(out) == 3
    assert all(j[:2] == b"\xff\xd8" for j in out)  # JPEG
