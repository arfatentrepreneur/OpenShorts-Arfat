"""Layer bookkeeping for burned hooks (app.py helpers).

The hook is a derived file (hooked_<ts>_<clean>) exactly like captions
(subtitled_<ts>_<clean>): replacing or removing a hook walks the prefix back
to the clean file instead of stacking a second overlay — the bug this design
replaced. These tests pin the walk-back and the canonical-file resolution.
"""
import os
import time

import pytest

app_module = pytest.importorskip("app")

_strip_burned_captions = app_module._strip_burned_captions
_strip_burned_hook = app_module._strip_burned_hook
_canonical_clip_file = app_module._canonical_clip_file


def _touch(directory, name, mtime=None):
    path = os.path.join(str(directory), name)
    with open(path, "wb") as f:
        f.write(b"x")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


CLEAN = "base_clip_1.mp4"
HOOKED = f"hooked_123_{CLEAN}"
CAPTIONED_HOOKED = f"subtitled_456_{HOOKED}"


class TestStripBurnedHook:
    def test_walks_hooked_prefix_back_to_clean(self, tmp_path):
        _touch(tmp_path, CLEAN)
        assert _strip_burned_hook(str(tmp_path), HOOKED) == CLEAN

    def test_walks_legacy_hook_prefix(self, tmp_path):
        _touch(tmp_path, CLEAN)
        assert _strip_burned_hook(str(tmp_path), f"hook_{CLEAN}") == CLEAN

    def test_no_prefix_is_returned_unchanged(self, tmp_path):
        _touch(tmp_path, CLEAN)
        assert _strip_burned_hook(str(tmp_path), CLEAN) == CLEAN

    def test_missing_underlying_file_stops_the_walk(self, tmp_path):
        # Restored project that only kept the current version: never point at
        # a file that does not exist.
        assert _strip_burned_hook(str(tmp_path), HOOKED) == HOOKED


class TestLayerChain:
    def test_captioned_hook_strips_in_two_steps(self, tmp_path):
        """subtitled_<ts>_hooked_<ts>_<clean> -> hooked -> clean, the exact
        order /api/hook uses to REPLACE a hook without stacking."""
        _touch(tmp_path, CLEAN)
        _touch(tmp_path, HOOKED)
        _touch(tmp_path, CAPTIONED_HOOKED)
        no_captions = _strip_burned_captions(str(tmp_path), CAPTIONED_HOOKED)
        assert no_captions == HOOKED
        assert _strip_burned_hook(str(tmp_path), no_captions) == CLEAN


class TestCanonicalClipFile:
    def test_captioned_hook_chain_resolves(self, tmp_path):
        now = time.time()
        _touch(tmp_path, CLEAN, mtime=now - 60)
        _touch(tmp_path, HOOKED, mtime=now - 30)
        _touch(tmp_path, CAPTIONED_HOOKED, mtime=now)
        assert _canonical_clip_file(str(tmp_path), "base", 0) == CAPTIONED_HOOKED

    def test_uncaptioned_hook_resolves(self, tmp_path):
        now = time.time()
        _touch(tmp_path, CLEAN, mtime=now - 60)
        _touch(tmp_path, HOOKED, mtime=now)
        assert _canonical_clip_file(str(tmp_path), "base", 0) == HOOKED

    def test_legacy_manual_hook_resolves(self, tmp_path):
        now = time.time()
        _touch(tmp_path, CLEAN, mtime=now - 60)
        _touch(tmp_path, f"hook_{CLEAN}", mtime=now)
        assert _canonical_clip_file(str(tmp_path), "base", 0) == f"hook_{CLEAN}"

    def test_newest_derivation_wins(self, tmp_path):
        """After a hook replacement both chains exist on disk; the newer one
        must be served or the replace would appear to do nothing."""
        now = time.time()
        _touch(tmp_path, CLEAN, mtime=now - 90)
        _touch(tmp_path, HOOKED, mtime=now - 60)
        _touch(tmp_path, CAPTIONED_HOOKED, mtime=now - 40)
        new_chain = f"subtitled_900_hooked_800_{CLEAN}"
        _touch(tmp_path, f"hooked_800_{CLEAN}", mtime=now - 20)
        _touch(tmp_path, new_chain, mtime=now)
        assert _canonical_clip_file(str(tmp_path), "base", 0) == new_chain

    def test_clean_only_returns_clean(self, tmp_path):
        _touch(tmp_path, CLEAN)
        assert _canonical_clip_file(str(tmp_path), "base", 0) == CLEAN
