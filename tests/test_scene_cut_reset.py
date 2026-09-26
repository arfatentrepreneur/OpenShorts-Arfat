"""Camera behaviour across a scene cut.

Regression cover for the slow pan after every shot change (24-aug-2026, a
two-camera podcast): the jump damping in SmoothedCameraman and the hysteresis
in SpeakerTracker both exist to reject noise INSIDE a shot, and across a cut
they held the previous shot's subject while the new face sat unframed, then
panned over to it. A cut must cut.
"""
import pytest

main = pytest.importorskip("main")  # needs cv2/mediapipe, absent in minimal CI

W, H = 1920, 1080


def _cam():
    cam = main.SmoothedCameraman(1080, 1920, W, H, aspect_ratio=9 / 16)
    cam.jump_confirm_frames = 3
    return cam


def _box(cx, size=200):
    return [cx - size / 2, 200, size, size]


def _settle(cam, cx, n=6):
    for _ in range(n):
        cam.update_target(_box(cx))
        cam.get_crop_box(force_snap=True)
    assert abs(cam.current_center_x - cx) < 1


class TestCameramanBeginScene:
    def test_first_target_after_a_cut_is_framed_at_once(self):
        cam = _cam()
        _settle(cam, 400)
        cam.begin_scene()
        cam.update_target(_box(1500))          # one detection, far away
        x1, _, x2, _ = cam.get_crop_box()
        assert abs((x1 + x2) / 2 - 1500) <= 1, "must cut to the new face, not pan"

    def test_without_a_cut_a_lone_big_jump_is_still_ignored(self):
        # The in-shot damping is untouched.
        cam = _cam()
        _settle(cam, 400)
        cam.update_target(_box(1500))
        assert cam.target_center_x == 400

    def test_a_pending_jump_from_the_old_shot_is_dropped(self):
        cam = _cam()
        _settle(cam, 400)
        cam.update_target(_box(1500))          # 1 of 3 confirmations
        cam.update_target(_box(1500))          # 2 of 3
        cam.begin_scene()
        cam.update_target(_box(900))           # new shot, different place
        assert cam.target_center_x == 900
        assert cam.current_center_x == 900

    def test_snap_is_consumed_once(self):
        cam = _cam()
        cam.begin_scene()
        cam.update_target(_box(900))
        cam.update_target(_box(1600))          # a lone jump inside the new shot
        assert cam.target_center_x == 900


class TestTrackerReset:
    def test_reset_releases_the_cooldown_hold(self):
        t = main.SpeakerTracker(cooldown_frames=30)
        for f in range(5):
            t.get_target([{"box": _box(300), "score": 1}], f, W)
        t.get_target([{"box": _box(1500), "score": 1}], 40, W)  # switch -> cooldown
        assert t.get_target([{"box": _box(300), "score": 1}], 42, W) is None, "held (sanity)"
        t.reset()
        assert t.get_target([{"box": _box(300), "score": 1}], 43, W) is not None
        assert t.active_speaker_id is not None

