"""Local-disk purge on account erasure (app._purge_local_jobs_for_user).

Two failure modes matter here and neither shows up in a unit-free reading of
the code: erasing one user's files must not touch another's (the API is
multi-tenant, and the three stores record ownership three different ways), and
a session id or output_dir that walks out of the working directories must not
delete anything at all.
"""
import os

import pytest

import app

MINE = "aaaa-1111"
THEIRS = "bbbb-2222"


def _write(path, body="x"):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w") as f:
        f.write(body)


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """A throwaway output/ + uploads/ tree, with the in-memory stores emptied.

    app.py holds OUTPUT_DIR / UPLOAD_DIR as relative paths, so chdir is enough
    to redirect every write the purge can make.
    """
    monkeypatch.chdir(tmp_path)
    os.makedirs("output/thumbnails", exist_ok=True)
    os.makedirs("uploads", exist_ok=True)
    monkeypatch.setattr(app, "jobs", {})
    monkeypatch.setattr(app, "saas_jobs", {})
    monkeypatch.setattr(app, "thumbnail_sessions", {})
    return tmp_path


class TestClipJobs:
    def test_erases_jobs_marked_with_an_owner_file(self, workdir):
        # No in-memory record: this is a job recovered from disk after a restart.
        _write("output/job1/.owner", MINE)
        _write("output/job1/clip.mp4")
        _write("uploads/job1_source.mp4")

        app._purge_local_jobs_for_user(MINE)

        assert not os.path.exists("output/job1")
        assert not os.path.exists("uploads/job1_source.mp4")

    def test_erases_in_memory_jobs_with_no_owner_file(self, workdir):
        _write("output/job2/clip.mp4")
        app.jobs["job2"] = {"user_id": MINE, "status": "completed"}

        app._purge_local_jobs_for_user(MINE)

        assert not os.path.exists("output/job2")
        assert "job2" not in app.jobs

    def test_leaves_another_users_jobs_alone(self, workdir):
        _write("output/theirs/.owner", THEIRS)
        _write("output/theirs/clip.mp4")
        _write("uploads/theirs_source.mp4")

        app._purge_local_jobs_for_user(MINE)

        assert os.path.exists("output/theirs/clip.mp4")
        assert os.path.exists("uploads/theirs_source.mp4")

    def test_leaves_unowned_self_host_jobs_alone(self, workdir):
        # BYOK jobs carry user_id=None; a str() comparison would match "None".
        _write("output/anon/clip.mp4")
        app.jobs["anon"] = {"user_id": None, "status": "completed"}

        app._purge_local_jobs_for_user(MINE)

        assert os.path.exists("output/anon/clip.mp4")


class TestOtherStores:
    def test_erases_saasshorts_output(self, workdir):
        _write("output/saas_s1/final.mp4")
        app.saas_jobs["s1"] = {"user_id": MINE, "output_dir": "output/saas_s1"}

        app._purge_local_jobs_for_user(MINE)

        assert not os.path.exists("output/saas_s1")
        assert "s1" not in app.saas_jobs

    def test_erases_generated_thumbnails_and_their_source(self, workdir):
        # Nothing else ever deletes these: the hourly sweep skips the whole
        # thumbnails directory, and they are served publicly at /thumbnails/.
        _write("output/thumbnails/t1/thumb.png")
        _write("uploads/thumb_t1_video.mp4")
        app.thumbnail_sessions["t1"] = {
            "user_id": MINE, "video_path": "uploads/thumb_t1_video.mp4"}

        app._purge_local_jobs_for_user(MINE)

        assert not os.path.exists("output/thumbnails/t1")
        assert not os.path.exists("uploads/thumb_t1_video.mp4")
        assert "t1" not in app.thumbnail_sessions

    def test_leaves_another_users_thumbnails_alone(self, workdir):
        _write("output/thumbnails/t2/thumb.png")
        app.thumbnail_sessions["t2"] = {"user_id": THEIRS}

        app._purge_local_jobs_for_user(MINE)

        assert os.path.exists("output/thumbnails/t2/thumb.png")

    def test_keeps_the_thumbnails_directory_itself(self, workdir):
        # It backs a StaticFiles mount; removing it 500s every /thumbnails
        # request until the process restarts.
        _write("output/thumbnails/t1/thumb.png")
        app.thumbnail_sessions["t1"] = {"user_id": MINE}

        app._purge_local_jobs_for_user(MINE)

        assert os.path.isdir("output/thumbnails")


class TestPathTraversal:
    def test_a_poisoned_session_id_deletes_nothing(self, workdir):
        _write("secret.txt", "keep me")
        app.thumbnail_sessions["../../secret.txt"] = {"user_id": MINE}

        app._purge_local_jobs_for_user(MINE)

        assert os.path.exists("secret.txt")

    def test_a_poisoned_output_dir_deletes_nothing(self, workdir):
        _write("secret.txt", "keep me")
        app.saas_jobs["evil"] = {
            "user_id": MINE, "output_dir": "output/../../secret.txt"}

        app._purge_local_jobs_for_user(MINE)

        assert os.path.exists("secret.txt")
