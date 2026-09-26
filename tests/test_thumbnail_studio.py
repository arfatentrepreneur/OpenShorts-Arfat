"""Thumbnail Studio pieces that run without Gemini or a video."""
import io
import os
import sys

import pytest
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import thumbnail  # noqa: E402


def test_burn_text_wraps_and_stays_in_its_half():
    img = Image.new("RGB", (1280, 720), (20, 20, 20))
    out = thumbnail.burn_thumbnail_text(img, "0 A 10K EN 30 DÍAS", "left", "yellow")
    px = out.convert("RGB")
    # Something got drawn on the left half...
    left = px.crop((0, 0, 640, 720))
    assert max(left.getextrema()[0]) > 200
    # ...and the right half (where the subject lives) is untouched.
    right = px.crop((700, 0, 1280, 720))
    assert max(right.getextrema()[0]) < 60


def test_burn_text_no_text_is_a_noop():
    img = Image.new("RGB", (1280, 720), (0, 0, 0))
    assert thumbnail.burn_thumbnail_text(img, "  ", "left") is img


def test_finalize_cover_crops_to_1280x720_under_2mb(tmp_path):
    # A 2K-ish image with a different aspect ratio, full of noise so JPEG is heavy.
    import random
    noisy = Image.effect_noise((2048, 1536), 80).convert("RGB")
    out = tmp_path / "t.jpg"
    thumbnail.finalize_thumbnail(noisy, str(out))
    with Image.open(out) as saved:
        assert saved.size == (1280, 720)
    assert out.stat().st_size <= thumbnail.THUMB_MAX_BYTES


def test_rank_frame_rejects_tiny_faces():
    assert thumbnail.rank_frame(0, 0.0, None, [0, 0, 50, 50], (1920, 1080), 100) is None
    big = thumbnail.rank_frame(0, 0.0, None, [0, 0, 400, 400], (1920, 1080), 100)
    assert big and big["score"] > 0


def test_pick_spread_keeps_picks_apart_in_time():
    total = 1000
    # Three near-identical best frames at 500/505/510 and a weaker one far away.
    scored = [
        {"idx": 500, "score": 1.0}, {"idx": 505, "score": 0.99}, {"idx": 510, "score": 0.98},
        {"idx": 100, "score": 0.5}, {"idx": 900, "score": 0.4},
    ]
    picked = thumbnail.pick_spread(scored, 3, total)
    assert [p["idx"] for p in picked] == [100, 500, 900]


def test_normalise_concepts_clamps_and_pads():
    raw = [
        {"text": "esto funciona", "text_position": "diagonal", "text_color": "red", "scene": "a desk"},
        {"scene": ""},  # dropped
        "garbage",
    ]
    out = thumbnail.normalise_concepts(raw, 3, "My title", thumbnail_text_hint="hint")
    assert len(out) == 3
    assert out[0] == {"text": "ESTO FUNCIONA", "text_position": "left", "text_color": "white",
                      "scene": "a desk", "why": ""}
    assert out[1]["why"] == "fallback" and out[1]["text"] == "HINT"


def test_parse_json_tolerates_fences_and_prose():
    assert thumbnail._parse_json('Sure!\n```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_ignores_trailing_garbage():
    assert thumbnail._parse_json('{"a": [1]}\n  ]\n}') == {"a": [1]}
