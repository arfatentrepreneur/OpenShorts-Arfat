"""The clip a job in flight shows must be the FINISHED clip.

Before this, the status poller guessed each clip's file as the clean reframe
name, so every clip appeared stripped of its hook and its captions until the
whole job ended and the result was rebuilt through _canonical_clip_file. A
six-clip job meant clip 1 sat there hook-less for the five clips after it, and
it read as "the hooks are broken" (reported 24-ago-2026).

main.py now announces each clip once its whole chain is done and names the file
to serve; app.py consumes the marker the way it already consumes PROXY_BYTES.
"""
import io

import pytest

app = pytest.importorskip("app")


def _feed(job_id, *lines):
    """Run enqueue_output over these stdout lines, as the log thread would."""
    stream = io.BytesIO(b"".join(line.encode("utf-8") + b"\n" for line in lines))
    app.enqueue_output(stream, job_id)


class TestClipReadyMarker:
    def setup_method(self):
        self.job_id = "test-clip-ready"
        app.jobs[self.job_id] = {"logs": []}

    def teardown_method(self):
        app.jobs.pop(self.job_id, None)

    def test_records_the_file_to_serve_per_clip(self):
        _feed(self.job_id,
              "CLIP_READY 0 subtitled_1_hooked_2_My_Video_clip_1.mp4",
              "CLIP_READY 2 hooked_3_My_Video_clip_3.mp4")
        assert app.jobs[self.job_id]["ready_files"] == {
            0: "subtitled_1_hooked_2_My_Video_clip_1.mp4",
            2: "hooked_3_My_Video_clip_3.mp4",
        }

    def test_the_marker_never_reaches_the_user_log(self):
        _feed(self.job_id,
              "🎬 Processing Clip 1",
              "CLIP_READY 0 subtitled_1_My_Video_clip_1.mp4")
        assert app.jobs[self.job_id]["logs"] == ["🎬 Processing Clip 1"]

    def test_clips_arriving_out_of_order_keep_their_own_index(self):
        # CLIP_WORKERS renders three clips at once, so clip 3 can finish first.
        _feed(self.job_id,
              "CLIP_READY 2 subtitled_9_My_Video_clip_3.mp4",
              "CLIP_READY 0 subtitled_7_My_Video_clip_1.mp4")
        ready = app.jobs[self.job_id]["ready_files"]
        assert ready[2].endswith("_clip_3.mp4")
        assert ready[0].endswith("_clip_1.mp4")

    def test_a_malformed_marker_is_ignored_not_fatal(self):
        _feed(self.job_id, "CLIP_READY notanumber file.mp4", "CLIP_READY 1 ok.mp4")
        assert app.jobs[self.job_id]["ready_files"] == {1: "ok.mp4"}

    def test_an_unknown_job_does_not_raise(self):
        _feed("no-such-job", "CLIP_READY 0 whatever.mp4")


class TestMainAnnouncesTheDeliveredFile:
    def test_main_prints_the_marker_after_the_caption_step(self):
        """The marker must sit AFTER auto_caption_clip and carry its result.

        Announcing the pre-caption path would put the poller back on a file the
        pipeline is about to supersede, which is the bug this fixes.
        """
        main_src = open("main.py", encoding="utf-8").read()
        caption_at = main_src.index("captioned = auto_caption_clip(")
        marker_at = main_src.index('print(f"CLIP_READY {i} "')
        assert caption_at < marker_at
        marker_line = main_src[marker_at:marker_at + 200]
        assert "captioned or deliver_path" in marker_line
