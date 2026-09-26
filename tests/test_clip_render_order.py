"""The strongest clip renders first, so it is the first one the user sees."""
import pytest

main = pytest.importorskip("main")


def test_best_score_first():
    shorts = [{"predicted_score": 40}, {"predicted_score": 91}, {"predicted_score": 77}]
    assert main.clip_render_order(shorts) == [1, 2, 0]


def test_unscored_keep_order_after_scored():
    shorts = [{}, {"predicted_score": "60"}, {"predicted_score": None}, {}]
    assert main.clip_render_order(shorts) == [1, 0, 2, 3]


def test_empty():
    assert main.clip_render_order([]) == []
