from camera_inset import (
    INSET_ASPECT,
    inset_box,
    inset_filtergraph,
    is_cornered,
    nearest_corner,
    usable,
)

HD = (1920, 1080)


class TestNearestCorner:
    def test_reads_the_quadrant(self):
        assert nearest_corner([10, 10, 100, 100], *HD) == ("left", "top")
        assert nearest_corner([1800, 980, 100, 100], *HD) == ("right", "bottom")
        assert nearest_corner([1800, 10, 100, 100], *HD) == ("right", "top")
        assert nearest_corner([10, 980, 100, 100], *HD) == ("left", "bottom")


class TestIsCornered:
    def test_small_subject_against_an_edge_qualifies(self):
        # A webcam pinned to the bottom-right: the exact case YOLO reports as a
        # short, wide upper-body box.
        assert is_cornered([1500, 900, 350, 120], *HD)

    def test_a_presenter_filling_the_shot_is_rejected(self):
        assert not is_cornered([600, 100, 700, 900], *HD)

    def test_a_small_but_centred_subject_is_rejected(self):
        assert not is_cornered([900, 500, 150, 100], *HD)

    def test_box_not_touching_the_bottom_still_counts(self):
        # Measured failure: an inset pinned to the right edge sat 18% clear of
        # the bottom because the detector stopped at the chest. Requiring two
        # edges threw it away.
        assert is_cornered([991 * 1.5, 502 * 1.5, 246 * 1.5, 86 * 1.5], *HD)

    def test_a_tall_subject_is_never_an_inset(self):
        assert not is_cornered([1700, 100, 200, 800], *HD)


class TestInsetBox:
    def test_box_stays_inside_the_frame(self):
        for box in ([0, 980, 200, 100], [1800, 0, 120, 120],
                    [1850, 1000, 70, 80]):
            x, y, w, h = inset_box(box, *HD)
            assert 0 <= x and x + w <= 1920
            assert 0 <= y and y + h <= 1080

    def test_bottom_anchored_inset_reaches_the_bottom_edge(self):
        # The head sits above the detection, so the box must extend upward
        # while staying pinned to the edge the inset actually touches.
        x, y, w, h = inset_box([1500, 950, 300, 100], *HD)
        assert y + h == 1080
        assert y < 950

    def test_height_follows_the_16_9_assumption(self):
        # A wide, flat torso detection must still yield a webcam-shaped box.
        _x, _y, w, h = inset_box([1000, 800, 300, 80], *HD)
        assert h >= w / INSET_ASPECT - 1

    def test_box_grows_around_the_subject(self):
        x, y, w, h = inset_box([1600, 900, 200, 120], *HD)
        assert w >= 200 and h >= 120


class TestUsable:
    def test_rejects_a_speck(self):
        assert not usable((0, 0, 40, 20), 1080)

    def test_rejects_something_that_fills_the_frame(self):
        assert not usable((0, 0, 1920, 900), 1080)

    def test_accepts_a_normal_webcam(self):
        assert usable((1500, 850, 350, 200), 1080)


class TestInsetFiltergraph:
    def test_graph_places_screen_and_camera(self):
        graph = inset_filtergraph(1920, 1080, 1080, 1920, (1500, 880, 350, 200))
        assert "split=3" in graph
        assert "[screen]" in graph and "[cam]" in graph
        assert graph.endswith("[v]")

    def test_screen_band_is_never_cropped(self):
        # The whole point: a game HUD or a desktop keeps its edges.
        graph = inset_filtergraph(1920, 1080, 1080, 1920, (1500, 880, 350, 200))
        screen = graph.split("[sa]")[-1].split("[screen]")[0]
        assert "crop" not in screen
        assert "scale=1080:608" in screen

    def test_camera_band_keeps_the_inset_aspect(self):
        # A 16:9 inset must not be stretched into a wider band; that shows up
        # instantly on a face.
        graph = inset_filtergraph(1920, 1080, 1080, 1920, (1500, 880, 356, 200))
        cam = graph.split("[ca]")[-1].split("[cam]")[0]
        crop_w = int(cam.split("w=")[1].split(":")[0])
        crop_h = int(cam.split("h=")[1].split(":")[0])
        band_h = int(cam.split("scale=1080:")[1].split("[")[0])
        assert abs((crop_w / crop_h) - (1080 / band_h)) < 0.05

    def test_camera_band_is_capped(self):
        # A near-square inset would otherwise claim most of the frame.
        graph = inset_filtergraph(1920, 1080, 1080, 1920, (1500, 700, 300, 290))
        band_h = int(graph.split("[cam]")[0].split("scale=1080:")[-1])
        assert band_h <= 1920 * 0.40 + 2

    def test_crop_coordinates_stay_inside_the_source(self):
        graph = inset_filtergraph(1920, 1080, 1080, 1920, (1850, 1000, 70, 80))
        cam = graph.split("[ca]")[-1].split("[cam]")[0]
        x = int(cam.split("x=")[1].split(":")[0])
        w = int(cam.split("w=")[1].split(":")[0])
        assert x >= 0 and x + w <= 1920

    def test_every_dimension_is_even(self):
        graph = inset_filtergraph(1920, 1080, 1080, 1920, (1501, 881, 351, 201))
        cam = graph.split("[ca]")[-1].split("[cam]")[0]
        for key in ("w=", "h=", "x=", "y="):
            assert int(cam.split(key)[1].split(":")[0].split(",")[0]) % 2 == 0
