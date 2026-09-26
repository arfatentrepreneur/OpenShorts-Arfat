"""What burning captions costs the user.

Captions are mandatory for short-form to work at all, and the normal path costs
the server nothing beyond one short FFmpeg pass — the transcript is already in
metadata.json. Charging for it (2 min, 10% of the free monthly quota per clip)
priced captions out of the product: only 9% of delivered clips had them in the
25-jul-2026 prod audit. Only the dubbed path, which re-runs Whisper, still pays.
"""
from cloud.config import SUBTITLE_MINUTES, subtitle_minutes_for


class TestSubtitleMetering:
    def test_normal_clip_is_free(self):
        assert subtitle_minutes_for("Some_Video_Title_clip_1.mp4") == 0

    def test_already_subtitled_clip_is_free(self):
        # Restyling captions must not cost anything either.
        assert subtitle_minutes_for("subtitled_1784974487_My_Video_clip_1.mp4") == 0

    def test_hooked_or_edited_clip_is_free(self):
        assert subtitle_minutes_for("edited_My_Video_clip_2.mp4") == 0

    def test_dubbed_clip_still_pays_for_the_transcription(self):
        # This path runs a fresh Whisper pass over the translated audio.
        assert subtitle_minutes_for("translated_es_My_Video_clip_1.mp4") == SUBTITLE_MINUTES

    def test_dubbed_prefix_must_be_at_the_start(self):
        # A clip merely containing the word must not be charged.
        assert subtitle_minutes_for("my_translated_notes_clip_1.mp4") == 0

    def test_handles_non_string_input(self):
        assert subtitle_minutes_for(None) == 0
