"""Static file serving that can bring a job's files back before answering 404.

``OUTPUT_DIR`` is not durable: a redeploy or the hourly sweep wipes a
finished job, while the user's library still points at
``/videos/<job_id>/<file>``. The API endpoints re-pull a project from R2 on
demand (``app._ensure_job_files``), but ``/videos`` was a plain
``StaticFiles`` mount, so when the dashboard reopened a project it fired the
15 transcript requests (which restored the job, ~25 s for 2 GB) and the 15
``<video>`` loads at the same instant, and every player got a 404 that only
a reload fixed (job cff3ad6c, 6-sep-2026 00:37 UTC).

This subclass keeps everything StaticFiles does (Range requests, ETags, HEAD)
and adds one step: on a miss it hands the first path segment (the job id) to
``restorer``; when that reports the files may now be there, it looks once
more. The restorer is awaited on the request, so a player that arrives while
a restore is in flight simply waits for it (the per-job lock lives in the
restorer) instead of failing.
"""
from typing import Awaitable, Callable, Optional

from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles

Restorer = Callable[[str], Awaitable[bool]]
Guard = Callable[[str], bool]


class RestoringStaticFiles(StaticFiles):
    """StaticFiles that can restore a missing job, and refuses non-deliverables.

    ``guard`` is the allowlist (``media_auth.is_servable``). Without it this
    mount hands out the whole working directory to anyone holding the job id:
    ``.owner`` (a user uuid), ``.resume.json`` (the customer's own
    ``webhook_secret``), ``.transcript_checkpoint.json``, and the
    ``*_metadata.json`` carrying the full transcript of the user's video.
    Verified served, unauthenticated, on 7-sep-2026.

    This is only the path half of media_auth: the clips themselves, and the
    untouched source video sitting in the same directory, are still public to
    anyone who has the job id. Closing that needs the capability tokens the
    module was written for, which is a bigger change (request handlers, an
    /api/media-token endpoint, and the dashboard appending the token to every
    media URL) and must ship with its frontend half.
    """

    def __init__(self, *args, restorer: Optional[Restorer] = None,
                 guard: Optional[Guard] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.restorer = restorer
        self.guard = guard

    async def get_response(self, path: str, scope):
        # Before the filesystem: a refused path must look exactly like a
        # missing one, or the 404-vs-403 difference confirms the file is there.
        if self.guard is not None and not self.guard(path):
            raise HTTPException(status_code=404)
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or self.restorer is None:
                raise
            job_id = path.split("/", 1)[0] if "/" in path else ""
            if not job_id:
                raise
            try:
                restored = await self.restorer(job_id)
            except Exception:
                restored = False
            if not restored:
                raise
            return await super().get_response(path, scope)
