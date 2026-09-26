"""Wordless footage must be clipped by vision, not fail on an empty transcript.

The vision path used to fire only on a missing audio track. Three prod jobs
on 25-aug-2026 had audio but no speech (a nursery rhyme transcribed as
"Uh uh", a dashcam drive as "Yeah."), went through the transcript path and
died with "Gemini did not return usable clips".
"""
import pytest

main = pytest.importorskip("main")  # needs cv2/mediapipe, absent in minimal CI


def _t(*texts):
    return {"language": "en",
            "segments": [{"start": i, "end": i + 1, "text": t} for i, t in enumerate(texts)]}


class TestRealFailures:
    def test_nursery_rhyme_uh_uh_is_sparse(self):
        assert main.speech_is_sparse(_t("Uh uh"), 169)

    def test_dashcam_yeah_is_sparse(self):
        assert main.speech_is_sparse(_t("Yeah."), 621)


class TestRealSpeechIsKept:
    def test_a_talk_is_not_sparse(self):
        words = ["so today we are going to look at how this works"] * 60   # ~10 w/segment
        assert not main.speech_is_sparse(_t(*words), 600)

    def test_a_short_clip_with_a_sentence_is_not_sparse(self):
        # 20s with one real sentence: nothing to gain from vision.
        assert not main.speech_is_sparse(_t("welcome back everyone to another episode of the show"), 20)

    def test_a_song_with_lyrics_is_not_sparse(self):
        # "Wheels on the Bus" style: repetitive but plenty of words.
        assert not main.speech_is_sparse(_t(*["the wheels on the bus go round and round"] * 30), 180)


class TestEdges:
    def test_empty_segments_is_sparse(self):
        assert main.speech_is_sparse({"segments": []}, 100)

    def test_none_transcript_is_sparse(self):
        assert main.speech_is_sparse(None, 100)

    def test_zero_duration_does_not_divide_by_zero(self):
        assert main.speech_is_sparse(_t("hi"), 0)
        assert not main.speech_is_sparse(_t(*["a b c d e f g h i j"] * 3), 0)
