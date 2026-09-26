import punch_in
from punch_in import MAX_ZOOM, crop_boxes, sendcmd_lines, zoom_curve


class TestZoomCurve:
    def test_no_beats_means_no_movement(self):
        assert set(zoom_curve(90, 30.0, [])) == {1.0}

    def test_a_beat_reaches_full_zoom_and_comes_back(self):
        zooms = zoom_curve(150, 30.0, [1.0])
        assert max(zooms) == MAX_ZOOM
        assert zooms[0] == 1.0
        assert zooms[-1] == 1.0

    def test_the_push_is_faster_in_than_out(self):
        zooms = zoom_curve(300, 30.0, [1.0])
        peak = zooms.index(max(zooms))
        release = next(i for i in range(peak, len(zooms)) if zooms[i] == 1.0)
        rise = peak - int(1.0 * 30)
        assert rise < (release - peak)

    def test_overlapping_beats_do_not_compound(self):
        zooms = zoom_curve(300, 30.0, [1.0, 1.2, 1.4])
        assert max(zooms) == MAX_ZOOM

    def test_beats_outside_the_scene_are_ignored(self):
        assert set(zoom_curve(60, 30.0, [45.0])) == {1.0}

    def test_start_offset_shifts_a_clip_level_beat_into_the_scene(self):
        # Same beat, scene starting at 10s: only the offset version moves.
        assert set(zoom_curve(60, 30.0, [10.5])) == {1.0}
        assert max(zoom_curve(60, 30.0, [10.5], start_offset=10.0)) > 1.0

    def test_zero_length_scene_is_safe(self):
        assert zoom_curve(0, 30.0, [1.0]) == []


class TestCropBoxes:
    def test_unzoomed_frames_keep_the_tracked_crop(self):
        boxes = crop_boxes([100, 100], [1.0, 1.0], 600, 1080, 1920, 1080)
        assert boxes[0][0] == 600 and boxes[0][1] == 1080

    def test_zoom_shrinks_the_crop(self):
        boxes = crop_boxes([100], [1.12], 600, 1080, 1920, 1080)
        assert boxes[0][0] < 600 and boxes[0][1] < 1080

    def test_the_centre_holds_while_zooming(self):
        # A push must not read as a pan: same x in, same centre out.
        wide = crop_boxes([600], [1.0], 600, 1080, 1920, 1080)[0]
        tight = crop_boxes([600], [1.12], 600, 1080, 1920, 1080)[0]
        assert abs((wide[2] + wide[0] / 2) - (tight[2] + tight[0] / 2)) <= 2

    def test_boxes_stay_inside_the_frame(self):
        for x in (0, 1320):
            box = crop_boxes([x], [1.12], 600, 1080, 1920, 1080)[0]
            assert 0 <= box[2] <= 1920 - box[0]
            assert 0 <= box[3] <= 1080 - box[1]

    def test_all_dimensions_are_even(self):
        for z in (1.0, 1.03, 1.07, 1.12):
            w, h, x, y = crop_boxes([333], [z], 601, 1079, 1920, 1080)[0]
            assert w % 2 == 0 and h % 2 == 0 and x % 2 == 0 and y % 2 == 0


class TestSendcmdLines:
    def test_first_frame_sets_every_parameter(self):
        lines = sendcmd_lines([(600, 1080, 100, 0)], fps=30.0)
        assert len(lines) == 4
        assert {ln.split()[2] for ln in lines} == {"w", "h", "x", "y"}

    def test_repeated_boxes_emit_nothing(self):
        box = (600, 1080, 100, 0)
        assert len(sendcmd_lines([box, box, box], fps=30.0)) == 4

    def test_only_changed_parameters_are_re_emitted(self):
        lines = sendcmd_lines([(600, 1080, 100, 0), (600, 1080, 104, 0)],
                              fps=30.0)
        assert len(lines) == 5
        assert lines[-1].endswith("x 104;")

    def test_timestamps_are_scene_relative(self):
        lines = sendcmd_lines([(600, 1080, 100, 0), (598, 1078, 101, 1)],
                              fps=30.0)
        assert lines[0].startswith("0.0000")
        assert lines[-1].startswith("0.0333")


class TestEmphasisTimes:
    def test_silent_or_unreadable_audio_yields_no_beats(self, monkeypatch):
        import active_speaker
        monkeypatch.setattr(active_speaker, "audio_envelope",
                            lambda *a, **k: [])
        assert punch_in.emphasis_times("x.mp4", 30.0) == []

    def test_flat_audio_yields_no_beats(self, monkeypatch):
        import active_speaker
        monkeypatch.setattr(active_speaker, "audio_envelope",
                            lambda *a, **k: [0.5] * 50)
        assert punch_in.emphasis_times("x.mp4", 10.0) == []

    def test_beats_respect_the_minimum_gap(self, monkeypatch):
        import active_speaker
        envelope = [1.0 if i % 2 == 0 else 0.0 for i in range(100)]
        monkeypatch.setattr(active_speaker, "audio_envelope",
                            lambda *a, **k: envelope)
        times = punch_in.emphasis_times("x.mp4", 20.0, window=0.2, min_gap=4.0)
        assert all(b - a >= 4.0 for a, b in zip(times, times[1:]))
