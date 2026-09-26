"""A video whose title is not ASCII must still reach the Gemini Files API.

The SDK, handed a path, puts ``os.path.basename(path)`` into the
``X-Goog-Upload-File-Name`` header, and httpx encodes header values as ASCII.
The downloaded source is named after the video's title, so on 20-sep-2026 a
job died with ``'ascii' codec can't encode characters in position 0-4`` before
a byte was sent, and the pipeline reported it as "the AI model did not return
usable clips for this video".
"""
import io

import httpx
import pytest

import gemini_worker


def _prepared_headers(file_arg, mime_type=None):
    """The headers the real SDK would build for this upload argument."""
    from google.genai import _extra_utils
    http_options, _size, _mime = _extra_utils.prepare_resumable_upload(
        file_arg, user_mime_type=mime_type)
    return http_options.headers


class _FakeFiles:
    def __init__(self):
        self.calls = []

    def upload(self, *, file, config=None):
        self.calls.append((file, config))
        # Reproduce the SDK's own header building and httpx's ASCII encoding:
        # this is exactly where the prod failure happened.
        httpx.Headers(_prepared_headers(file, (config or {}).get("mime_type")))
        return "uploaded"


class _FakeClient:
    def __init__(self):
        self.files = _FakeFiles()


@pytest.fixture
def unicode_video(tmp_path):
    path = tmp_path / "日本語のタイトル_video.mp4"
    path.write_bytes(b"\0" * 2048)
    return str(path)


def test_the_path_form_is_what_breaks(unicode_video):
    """Guard rail: if a future SDK stops sending that header, drop the helper."""
    with pytest.raises(UnicodeEncodeError):
        httpx.Headers(_prepared_headers(unicode_video))


def test_upload_media_survives_a_non_ascii_title(unicode_video):
    client = _FakeClient()
    assert gemini_worker.upload_media(client, unicode_video) == "uploaded"
    file_arg, config = client.files.calls[0]
    assert isinstance(file_arg, io.IOBase), "must upload by handle, not by path"
    assert config["mime_type"] == "video/mp4"
    # The readable name still travels — in the JSON body, which is UTF-8.
    assert config["display_name"] == "日本語のタイトル_video.mp4"


def test_an_unknown_extension_still_gets_a_mime_type(tmp_path):
    path = tmp_path / "clip.bin"
    path.write_bytes(b"\0" * 16)
    client = _FakeClient()
    gemini_worker.upload_media(client, str(path))
    assert client.files.calls[0][1]["mime_type"] == "video/mp4"


def test_every_whole_file_upload_goes_through_the_helper():
    """The three stages that send Gemini the file itself, not frames."""
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parent.parent
    offenders = []
    for name in ("main.py", "editor.py", "screencast_layout.py", "thumbnail.py"):
        src = (root / name).read_text()
        if re.search(r"\.files\.upload\(", src):
            offenders.append(name)
    assert offenders == [], f"{offenders} call files.upload directly (use upload_media)"
