"""AI Act art. 50(2) marking on the images the thumbnail studio generates.

Videos have carried an mp4 ``comment`` tag since the doubling/AI-Shorts work
(``ffmpeg_utils.mark_ai_generated``). Thumbnails carried nothing — and they are
the output most likely to be a synthetic image *of a real person*, because the
studio hands the model the presenter's own face as a reference. The mark is XMP
``Iptc4xmpExt:DigitalSourceType = trainedAlgorithmicMedia``, which is the
vocabulary the platforms actually read.
"""
import io
import os

import pytest

Image = pytest.importorskip("PIL.Image")
thumbnail = pytest.importorskip("thumbnail")

TRAINED = b"trainedAlgorithmicMedia"


@pytest.fixture()
def saved(tmp_path):
    img = Image.new("RGB", (1600, 900), (12, 14, 20))
    out = os.path.join(str(tmp_path), "thumb.jpg")
    thumbnail.finalize_thumbnail(img, out)
    return out


class TestTheFileIsMarked:
    def test_the_xmp_packet_names_the_iptc_value(self, saved):
        assert TRAINED in open(saved, "rb").read()

    def test_pillow_reads_the_marking_back(self, saved):
        with Image.open(saved) as img:
            xmp = img.info.get("xmp") or b""
            assert TRAINED in xmp
            assert b"Iptc4xmpExt:DigitalSourceType" in xmp

    def test_exif_carries_the_same_claim(self, saved):
        # Second signal on purpose: a re-encode commonly keeps EXIF and drops
        # XMP, so the two together survive more pipelines than either alone.
        with Image.open(saved) as img:
            exif = img.getexif()
            assert "OpenShorts" in str(exif.get(0x0131, ""))
            assert "AI-generated" in str(exif.get(0x010E, ""))


class TestItStaysAThumbnail:
    def test_the_marking_does_not_break_the_crop_or_the_size_budget(self, saved):
        with Image.open(saved) as img:
            assert img.size == (thumbnail.THUMB_W, thumbnail.THUMB_H)
        assert os.path.getsize(saved) <= thumbnail.THUMB_MAX_BYTES

    def test_an_older_pillow_still_produces_a_thumbnail(self, tmp_path, monkeypatch):
        # The xmp= save argument is recent. Losing it must cost the XMP half of
        # the marking, never the image the user paid minutes for.
        original = Image.Image.save

        def no_xmp(self, fp, *args, **kwargs):
            if "xmp" in kwargs:
                raise TypeError("save() got an unexpected keyword argument 'xmp'")
            return original(self, fp, *args, **kwargs)

        monkeypatch.setattr(Image.Image, "save", no_xmp)
        out = os.path.join(str(tmp_path), "legacy.jpg")
        thumbnail.finalize_thumbnail(Image.new("RGB", (1600, 900)), out)
        assert os.path.getsize(out) > 0
        with Image.open(out) as img:
            assert "OpenShorts" in str(img.getexif().get(0x0131, ""))


def test_the_packet_is_well_formed_xml():
    import xml.etree.ElementTree as ET
    body = thumbnail.AI_XMP_PACKET.decode("utf-8")
    body = body.split("?>", 1)[1].rsplit("<?xpacket", 1)[0]
    ET.fromstring(body)   # raises if the packet is malformed
