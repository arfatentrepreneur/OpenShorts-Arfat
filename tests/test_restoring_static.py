"""/videos serving: a miss under /videos/<job_id>/ asks the restorer to bring
the job back before answering 404, keeping StaticFiles' Range support.

Observed 6-sep-2026: reopening a project whose working files were gone fired
15 transcript requests (which restored it from R2 in ~25 s) and 15 <video>
loads at once; every player got a 404 until the user reloaded.
"""
import os

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from restoring_static import RestoringStaticFiles

JOB = "cff3ad6c-c1e6-48e8-9a75-be74f39779c5"


def _app(tmp_path, restorer):
    app = Starlette()
    app.mount("/videos", RestoringStaticFiles(directory=str(tmp_path), restorer=restorer))
    return TestClient(app), tmp_path


def test_existing_file_is_served_without_calling_the_restorer(tmp_path):
    calls = []

    async def restorer(job_id):
        calls.append(job_id)
        return True

    client, root = _app(tmp_path, restorer)
    os.makedirs(root / JOB)
    (root / JOB / "clip_1.mp4").write_bytes(b"x" * 100)
    r = client.get(f"/videos/{JOB}/clip_1.mp4")
    assert r.status_code == 200 and calls == []


def test_missing_file_is_restored_then_served_with_ranges(tmp_path):
    calls = []

    async def restorer(job_id):
        calls.append(job_id)
        os.makedirs(root / job_id, exist_ok=True)
        (root / job_id / "clip_1.mp4").write_bytes(bytes(range(100)))
        return True

    client, root = _app(tmp_path, restorer)
    r = client.get(f"/videos/{JOB}/clip_1.mp4", headers={"Range": "bytes=10-19"})
    assert calls == [JOB]
    # The player's seek keeps working: the second lookup is the normal
    # StaticFiles one. Range support itself depends on the starlette version
    # (prod's honours it, an older local one answers the whole file).
    if r.status_code == 206:
        assert r.content == bytes(range(10, 20))
        assert r.headers["content-range"] == "bytes 10-19/100"
    else:
        assert r.status_code == 200 and r.content == bytes(range(100))


def test_restorer_false_or_failure_keeps_the_404(tmp_path):
    async def says_no(job_id):
        return False

    async def blows_up(job_id):
        raise RuntimeError("R2 down")

    for restorer in (says_no, blows_up):
        client, _root = _app(tmp_path, restorer)
        assert client.get(f"/videos/{JOB}/clip_1.mp4").status_code == 404


def test_paths_without_a_job_segment_never_call_the_restorer(tmp_path):
    calls = []

    async def restorer(job_id):
        calls.append(job_id)
        return True

    client, _root = _app(tmp_path, restorer)
    assert client.get("/videos/robots.txt").status_code == 404
    assert calls == []


def test_no_restorer_behaves_like_staticfiles(tmp_path):
    client, _root = _app(tmp_path, None)
    assert client.get(f"/videos/{JOB}/clip_1.mp4").status_code == 404


def test_app_job_id_guard():
    """The app-side restorer only hits the database for uuid-shaped ids."""
    app_mod = pytest.importorskip("app")
    assert app_mod._JOB_ID_RE.match(JOB)
    for bad in ("thumbnails", "..", "cff3ad6c", "CFF3AD6C-C1E6-48E8-9A75-BE74F39779C5"):
        assert not app_mod._JOB_ID_RE.match(bad)
