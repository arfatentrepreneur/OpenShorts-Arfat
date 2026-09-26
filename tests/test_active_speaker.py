from active_speaker import (
    attribute_windows,
    hold,
    is_conversation,
    mouth_region,
    normalise_activity,
    shares,
    speaker_xs,
)


class TestMouthRegion:
    def test_region_sits_below_the_face_centre(self):
        box = [800, 300, 200, 200]          # centre y = 400
        _x0, y0, _x1, y1 = mouth_region(box, 1920, 1080)
        assert (y0 + y1) / 2 > 400

    def test_region_stays_inside_the_frame(self):
        for box in ([0, 0, 100, 100], [1850, 1000, 100, 100]):
            x0, y0, x1, y1 = mouth_region(box, 1920, 1080)
            assert 0 <= x0 < x1 <= 1920
            assert 0 <= y0 < y1 <= 1080

    def test_region_is_never_empty(self):
        x0, y0, x1, y1 = mouth_region([10, 10, 4, 4], 1920, 1080)
        assert x1 > x0 and y1 > y0

    def test_scale_maps_back_to_analysis_resolution(self):
        # Boxes arrive in original coordinates; the frames analysed are smaller.
        big = mouth_region([800, 300, 200, 200], 1920, 1080, scale=1.0)
        small = mouth_region([800, 300, 200, 200], 480, 270, scale=4.0)
        assert small[0] < big[0] and small[2] < big[2]


class TestNormaliseActivity:
    def test_a_brighter_face_does_not_win_every_window(self):
        # Same pattern, one speaker's magnitudes 10x the other's. Raw values
        # would hand every window to the loud column; this is the measured
        # failure that made one speaker hold 90-100% of a real scene.
        pattern = [1.0, 5.0, 1.0, 5.0]
        activity = [[p * 10, q] for p, q in zip(pattern, reversed(pattern))]
        normalised = normalise_activity(activity)
        winners = {0 if a > b else 1 for a, b in normalised}
        assert winners == {0, 1}

    def test_empty_input_is_safe(self):
        assert normalise_activity([]) == []

    def test_flat_input_does_not_divide_by_zero(self):
        out = normalise_activity([[2.0, 2.0]] * 5)
        assert all(all(v == v for v in row) for row in out)   # no NaN


class TestAttributeWindows:
    def test_silence_is_never_attributed(self):
        activity = [[0.0, 9.0]]
        assert attribute_windows(activity, loudness=[0.01]) == [None]

    def test_clear_winner_takes_the_window(self):
        assert attribute_windows([[9.0, 1.0]], loudness=[1.0]) == [0]
        assert attribute_windows([[1.0, 9.0]], loudness=[1.0]) == [1]

    def test_a_tie_is_left_unattributed(self):
        assert attribute_windows([[5.0, 5.0]], loudness=[1.0]) == [None]

    def test_missing_audio_still_decides(self):
        # No audio track: mouth movement alone should still vote.
        assert attribute_windows([[9.0, 1.0]], loudness=[]) == [0]

    def test_zero_activity_is_unattributed(self):
        assert attribute_windows([[0.0, 0.0]], loudness=[1.0]) == [None]


class TestShares:
    def test_shares_ignore_unattributed_windows(self):
        assert shares([0, 1, None, None]) == (0.5, 0.5)

    def test_no_evidence_reports_zero_not_a_tie(self):
        assert shares([None, None]) == (0.0, 0.0)

    def test_conversation_needs_both_voices(self):
        assert is_conversation([0, 1, 0, 1, 0])
        assert not is_conversation([0] * 9 + [1])
        assert not is_conversation([None, None])


class TestHold:
    def test_a_single_interjection_does_not_steal_the_frame(self):
        held = hold([0, 0, 0, 1, 0, 0, 0], min_windows=3)
        assert set(held) == {0}

    def test_a_sustained_turn_takes_over(self):
        held = hold([0, 0, 0, 1, 1, 1, 1], min_windows=3)
        assert held[-1] == 1

    def test_unclear_windows_inherit_the_current_speaker(self):
        assert hold([0, None, None, 0], min_windows=3) == [0, 0, 0, 0]

    def test_lead_in_is_backfilled(self):
        assert hold([None, None, 1, 1, 1], min_windows=1)[0] == 1

    def test_all_unclear_stays_unclear(self):
        assert hold([None, None, None]) == [None, None, None]


class TestSpeakerXs:
    def test_x_follows_the_held_speaker(self):
        centres = [(400, 500, 200, 200), (1500, 500, 200, 200)]
        xs = speaker_xs([0, 1], centres, crop_w=600, orig_w=1920,
                        n_frames=60, fps=30.0, window_s=1.0)
        assert xs[0] < xs[-1]

    def test_x_stays_inside_the_frame(self):
        centres = [(10, 500, 200, 200), (1910, 500, 200, 200)]
        xs = speaker_xs([0, 1], centres, crop_w=600, orig_w=1920,
                        n_frames=60, fps=30.0, window_s=1.0)
        assert all(0 <= x <= 1920 - 600 for x in xs)

    def test_one_value_per_frame(self):
        centres = [(400, 500, 200, 200), (1500, 500, 200, 200)]
        assert len(speaker_xs([0], centres, 600, 1920, 45, 30.0)) == 45

    def test_empty_verdicts_do_not_crash(self):
        centres = [(400, 500, 200, 200), (1500, 500, 200, 200)]
        assert len(speaker_xs([], centres, 600, 1920, 10, 30.0)) == 10
