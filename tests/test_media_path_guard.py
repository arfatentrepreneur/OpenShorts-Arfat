"""/videos must hand out deliverables, not the whole working directory.

The mount was a plain StaticFiles over OUTPUT_DIR, so anyone holding a job id
(it travels in every clip URL) could also fetch `.owner` (a user uuid),
`.resume.json` (the customer's own webhook_secret), `.transcript_checkpoint.json`
and `<title>_metadata.json`, which carries the full transcript of their video.
All four were verified served, unauthenticated, against production on
7-sep-2026. media_auth shipped the allowlist in 96f0139 but nothing imported it.

This is the path half only: the clips and the untouched source video in the
same directory are still public to whoever has the job id.
"""
import pytest

media_auth = pytest.importorskip("media_auth")
restoring_static = pytest.importorskip("restoring_static")


class TestTheGuardIsWiredIn:
    def test_the_videos_mount_carries_the_allowlist(self):
        app = pytest.importorskip("app")
        mount = next(r for r in app.app.routes
                     if getattr(r, "name", None) == "videos")
        assert mount.app.guard is media_auth.is_servable, \
            "/videos is serving the working directory with no allowlist"


class TestWhatMayLeave:
    @pytest.mark.parametrize("rel", [
        "job/clip_1.mp4", "job/subtitled_1_clip_1.mp4", "job/a.webm",
        "job/autosubs_1.ass", "job/subs.srt", "job/thumb.jpg", "job/clips.zip",
    ])
    def test_deliverables_pass(self, rel):
        assert media_auth.is_servable(rel)

    @pytest.mark.parametrize("rel", [
        "job/.owner",
        "job/.resume.json",
        "job/.transcript_checkpoint.json",
        "job/My_Video_metadata.json",
        "job/clip_1.mp4.layout.json",
        "job/.instance",
        "../app.py",
        "job/../../app.py",
        "/etc/passwd",
        "",
    ])
    def test_everything_else_is_refused(self, rel):
        assert not media_auth.is_servable(rel)
