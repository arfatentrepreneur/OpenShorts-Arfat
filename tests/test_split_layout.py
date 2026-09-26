import split_layout
from split_layout import (
    analyze_scene,
    split_filtergraph,
    split_geometry,
)


def face(cx, cy, w=200, h=200):
    """A detector candidate centred on (cx, cy), in the shape main.py returns."""
    box = [int(cx - w / 2), int(cy - h / 2), w, h]
    return {'box': box, 'score': w * h}


def two_shot(left_cx=600, right_cx=1400):
    return [face(left_cx, 400), face(right_cx, 400)]


class TestAnalyzeScene:
    def test_steady_two_shot_qualifies(self):
        frames = [two_shot() for _ in range(10)]
        left, right = analyze_scene(frames, frame_w=1920)
        assert left[0] == 600
        assert right[0] == 1400

    def test_single_speaker_is_rejected(self):
        frames = [[face(900, 400)] for _ in range(10)]
        assert analyze_scene(frames, frame_w=1920) is None

    def test_empty_input_is_rejected(self):
        assert analyze_scene([], frame_w=1920) is None

    def test_faces_sitting_too_close_are_rejected(self):
        # 200px apart on a 1920 frame is 10%, under MIN_SEPARATION — one crop
        # already frames both.
        frames = [two_shot(left_cx=900, right_cx=1100) for _ in range(10)]
        assert analyze_scene(frames, frame_w=1920) is None

    def test_a_second_face_that_comes_and_goes_is_rejected(self):
        frames = [two_shot() for _ in range(4)] + [[face(600, 400)]] * 6
        assert analyze_scene(frames, frame_w=1920) is None

    def test_occasional_detector_miss_still_qualifies(self):
        frames = [two_shot() for _ in range(8)] + [[face(600, 400)]] * 2
        assert analyze_scene(frames, frame_w=1920) is not None

    def test_profile_turns_do_not_demote_a_real_two_shot(self):
        # The measured case: 6 of 10 samples show both faces, the rest catch one
        # speaker turned towards the other. Both are in frame throughout.
        frames = [two_shot() for _ in range(6)] + [[face(600, 400)]] * 4
        assert analyze_scene(frames, frame_w=1920) is not None

    def test_shot_reverse_shot_is_rejected(self):
        # Two cameras cutting between speakers: each face is on screen most of
        # the time, never both at once. Stacking would duplicate one person.
        frames = [[face(900, 400)], [face(1000, 400)]] * 5
        assert analyze_scene(frames, frame_w=1920) is None

    def test_background_extras_are_ignored(self):
        # A tiny third face further right must not be picked over the speaker.
        frames = [two_shot() + [face(1800, 200, w=40, h=40)] for _ in range(10)]
        left, right = analyze_scene(frames, frame_w=1920)
        assert (left[0], right[0]) == (600, 1400)

    def test_one_stray_detection_does_not_drag_the_crop(self):
        # Median, not mean: a single frame latching onto a bystander at x=1900
        # would move a mean by ~130px.
        frames = [two_shot() for _ in range(9)] + [[face(600, 400), face(1900, 400)]]
        _left, right = analyze_scene(frames, frame_w=1920)
        assert right[0] == 1400

    def test_result_is_ordered_left_then_right(self):
        frames = [[face(1400, 400), face(600, 400)] for _ in range(10)]
        left, right = analyze_scene(frames, frame_w=1920)
        assert left[0] < right[0]


class TestSplitGeometry:
    def test_half_frame_crop_never_exceeds_the_source(self):
        w, h, x, y, half_h = split_geometry(1920, 1080, 1080, 1920, (600, 400))
        assert w <= 1920 and h <= 1080
        assert 0 <= x <= 1920 - w
        assert 0 <= y <= 1080 - h
        assert half_h == 960

    def test_crop_is_clamped_inside_the_frame_at_the_edges(self):
        for cx in (0, 60, 1860, 1920):
            w, _h, x, _y, _half = split_geometry(1920, 1080, 1080, 1920, (cx, 400))
            assert 0 <= x <= 1920 - w

    def test_dimensions_are_even(self):
        w, h, x, y, half_h = split_geometry(1920, 1080, 1080, 1920, (777, 333))
        assert w % 2 == 0 and h % 2 == 0
        assert x % 2 == 0 and y % 2 == 0 and half_h % 2 == 0

    def test_crop_aspect_matches_the_half_frame(self):
        w, h, _x, _y, half_h = split_geometry(1920, 1080, 1080, 1920, (900, 400))
        assert abs((w / h) - (1080 / half_h)) < 0.02

    def test_tightness_trades_width_for_a_closer_frame(self, monkeypatch):
        monkeypatch.setattr(split_layout, "SPLIT_TIGHTNESS", 1.0)
        wide, _, _, _, _ = split_geometry(1920, 1080, 1080, 1920, (900, 400))
        monkeypatch.setattr(split_layout, "SPLIT_TIGHTNESS", 0.75)
        tight, _, _, _, _ = split_geometry(1920, 1080, 1080, 1920, (900, 400))
        assert tight < wide

    def test_tightness_is_bounded(self, monkeypatch):
        # An out-of-range env value must not produce a zero-sized crop.
        monkeypatch.setattr(split_layout, "SPLIT_TIGHTNESS", 0.0)
        w, h, _x, _y, _half = split_geometry(1920, 1080, 1080, 1920, (900, 400))
        assert w > 0 and h > 0

    def test_portrait_source_falls_back_to_full_width(self):
        w, _h, x, _y, _half = split_geometry(1080, 1920, 1080, 1920, (540, 600))
        assert w == 1080 and x == 0


class TestSplitFiltergraph:
    def test_graph_stacks_two_crops_into_the_output_size(self):
        graph = split_filtergraph(1920, 1080, 1080, 1920, (600, 400), (1400, 400))
        assert "vstack=inputs=2" in graph
        assert "pad=1080:1920" in graph
        assert graph.endswith("[v]")

    def test_left_speaker_goes_on_top(self):
        graph = split_filtergraph(1920, 1080, 1080, 1920, (600, 400), (1400, 400))
        top = graph.split("[ta]crop=")[1].split(",")[0]
        bottom = graph.split("[ba]crop=")[1].split(",")[0]
        top_x = int(top.split("x=")[1].split(":")[0])
        bottom_x = int(bottom.split("x=")[1].split(":")[0])
        assert top_x < bottom_x

    def test_both_halves_scale_to_the_same_size(self):
        graph = split_filtergraph(1920, 1080, 1080, 1920, (600, 400), (1400, 400))
        assert graph.count("scale=1080:960") == 2
