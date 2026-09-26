import screencast_layout
from screencast_layout import (
    content_bands,
    overlapping_width,
    screencast_filtergraph,
    speaker_crop,
)


class TestContentBands:
    def test_bands_fill_the_output_exactly(self):
        content_h, speaker_h = content_bands(1920, 1080, 1080, 1920)
        assert content_h + speaker_h == 1920

    def test_sixteen_by_nine_content_keeps_its_full_width(self):
        # 1080 wide at 16:9 is 608 tall. Anything else means the sides were cut,
        # which is the one thing this layout exists to prevent.
        content_h, _ = content_bands(1920, 1080, 1080, 1920)
        assert content_h == 608

    def test_bands_are_even(self):
        for src_h in (1080, 1000, 817):
            content_h, speaker_h = content_bands(1920, src_h, 1080, 1920)
            assert content_h % 2 == 0 and speaker_h % 2 == 0

    def test_tall_source_still_leaves_room_for_the_speaker(self):
        # A portrait source would want more height than the frame has.
        content_h, speaker_h = content_bands(1080, 1920, 1080, 1920)
        assert speaker_h >= 2
        assert content_h + speaker_h == 1920


class TestSpeakerCrop:
    def test_crop_stays_inside_the_source(self):
        w, h, x, y = speaker_crop(1920, 1080, 1080, 1312, (1748, 832))
        assert 0 <= x <= 1920 - w
        assert 0 <= y <= 1080 - h

    def test_crop_is_even(self):
        w, h, x, y = speaker_crop(1920, 1080, 1080, 1312, (777, 333))
        assert w % 2 == 0 and h % 2 == 0 and x % 2 == 0 and y % 2 == 0

    def test_crop_follows_the_face_horizontally(self):
        _, _, left_x, _ = speaker_crop(1920, 1080, 1080, 1312, (400, 500))
        _, _, right_x, _ = speaker_crop(1920, 1080, 1080, 1312, (1500, 500))
        assert left_x < right_x

    def test_corner_presenter_is_clamped_not_dropped(self):
        w, _h, x, _y = speaker_crop(1920, 1080, 1080, 1312, (1900, 1000))
        assert x == 1920 - w


class TestOverlappingWidth:
    def test_no_ranges_means_no_width(self):
        assert overlapping_width(0, 10, []) == 0.0

    def test_returns_the_width_of_an_overlapping_range(self):
        assert overlapping_width(5, 15, [(0, 20, "chart", 0.7)]) == 0.7

    def test_ignores_ranges_that_do_not_overlap(self):
        assert overlapping_width(30, 40, [(0, 20, "chart", 0.9)]) == 0.0

    def test_a_brush_of_overlap_does_not_count(self):
        # Under MIN_OVERLAP_SECONDS: a scene that merely touches the range.
        assert overlapping_width(19.9, 30, [(0, 20, "chart", 0.9)]) == 0.0

    def test_widest_overlapping_range_wins(self):
        ranges = [(0, 20, "ticker", 0.15), (0, 20, "spreadsheet", 0.95)]
        assert overlapping_width(5, 15, ranges) == 0.95

    def test_corner_ticker_width_is_reported_not_swallowed(self):
        # The gate lives in detect_content_ranges; this function must report
        # small widths faithfully so that gate can do its job.
        assert overlapping_width(5, 15, [(0, 20, "ticker", 0.15)]) == 0.15


class TestScreencastFiltergraph:
    def test_content_band_is_scaled_never_cropped(self):
        graph = screencast_filtergraph(1920, 1080, 1080, 1920, (1748, 832))
        # [-1]: the first "[ca]" is the split= output label, not the filter.
        content = graph.split("[ca]")[-1].split("[content]")[0]
        assert "crop" not in content
        assert "scale=1080:608" in content

    def test_graph_stacks_and_pads_to_the_output(self):
        graph = screencast_filtergraph(1920, 1080, 1080, 1920, (1748, 832))
        assert "vstack=inputs=2" in graph
        assert "pad=1080:1920" in graph
        assert graph.endswith("[v]")

    def test_speaker_band_is_cropped_around_the_face(self):
        graph = screencast_filtergraph(1920, 1080, 1080, 1920, (1748, 832))
        speaker = graph.split("[sa]")[-1].split("[speaker]")[0]
        assert "crop=" in speaker
        assert "scale=1080:1312" in speaker


class TestGating:
    def test_disabled_module_detects_nothing(self, monkeypatch):
        monkeypatch.setattr(screencast_layout, "ENABLED", False)
        assert screencast_layout.detect_content_ranges("x.mp4", 10) == []

    def test_no_ranges_means_no_scenes_touched(self, monkeypatch):
        monkeypatch.setattr(screencast_layout, "ENABLED", True)
        assert screencast_layout.detect_screencast_scenes(
            "x.mp4", [], [], []) == {}
