"""SAM 3.1 cut-out (including the mask decoder) and the Muse Image clean photo."""

import base64
import io

import numpy as np
import pytest
from PIL import Image

from listly.ai.api import StepError
from listly.ai.clean_photo import make_clean_photo
from listly.ai.cutout import RECORD, _decode_one_bit, cut_out
from listly.models import ItemInfo

from .conftest import FIXTURES

SAM_REPLY = (FIXTURES / "sam_scooter_reply.txt").read_text(encoding="utf-8").strip()


def photo(width=720, height=960) -> bytes:
    # Same size as the photo SAM's reply was made for, so the box fits.
    buf = io.BytesIO()
    Image.new("RGB", (width, height), "blue").save(buf, "JPEG")
    return buf.getvalue()


def test_decoder_reads_a_real_sam_mask():
    record = RECORD.findall(SAM_REPLY)[0]
    rows, cols, payload = int(record[7]), int(record[8]), record[10]
    mask = _decode_one_bit(payload, rows, cols)
    assert mask.shape == (639, 567)
    assert 0.4 < mask.mean() < 0.8  # the scooter fills a good part of its box, not all of it


def test_decoder_rejects_garbage():
    with pytest.raises(ValueError):
        _decode_one_bit("not a mask payload", 10, 10)


def test_short_name_is_tried_first_then_falls_back(fake_api):
    fake_api.reply_text("<0f>", SAM_REPLY)  # nothing found for "motor scooter", found for "scooter"
    cut = cut_out(photo(), ItemInfo.from_dict({"item": "motor scooter"}))
    assert cut.exact
    assert [r["input"][0]["content"][0]["text"] for r in fake_api.requests] == ["motor scooter", "scooter"]
    assert fake_api.requests[0]["metadata"] == {"mask_encoding": "one_bit"}

    cut_png = Image.open(io.BytesIO(cut.png))
    alpha = np.array(cut_png.getchannel("A"))
    assert cut_png.mode == "RGBA" and alpha.min() == 0 and alpha.max() == 255  # background made transparent


def test_nothing_found_is_a_friendly_error(fake_api):
    fake_api.reply_text("<0f>")
    with pytest.raises(StepError, match="couldn't find"):
        cut_out(photo(), ItemInfo.from_dict({"item": "bicycle", "object_name": "bicycle"}))


def test_clean_photo_picks_the_image_and_returns_jpeg(fake_api):
    webp = io.BytesIO()
    Image.new("RGBA", (64, 64), (255, 0, 0, 255)).save(webp, "WEBP")
    fake_api.reply_output([
        {"type": "reasoning", "id": "rs", "summary": [{"type": "summary_text", "text": "plan"}], "status": "completed"},
        {"type": "image_generation_call", "id": "ig", "status": "completed", "result": base64.b64encode(webp.getvalue()).decode()},
    ])
    clean = make_clean_photo(photo(64, 64))
    assert Image.open(io.BytesIO(clean)).format == "JPEG"
    assert "Do not change the item" in fake_api.requests[0]["input"][0]["content"][0]["text"]
