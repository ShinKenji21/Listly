"""Identification: the request Meta receives, validation of the answer, and caching."""

import io

import pytest
from PIL import Image

from listly.ai.api import StepError
from listly.ai.identify import identify_item


def jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(buf, "JPEG")
    return buf.getvalue()


def test_sends_the_photo_and_reads_the_answer(fake_api):
    fake_api.reply_json({"item": "motor scooter", "object_name": "scooter", "brand": "Yamaha", "condition": "good",
                         "flaws": ["scratch on side panel"], "features": ["gold rims"], "confidence": "medium"})
    info = identify_item(jpeg())
    assert (info.item, info.brand, info.features) == ("motor scooter", "Yamaha", ["gold rims"])

    content = fake_api.requests[0]["input"][0]["content"]
    assert [part["type"] for part in content] == ["input_text", "input_image"]
    assert content[1]["image_url"].startswith("data:image/jpeg;base64,")

    identify_item(jpeg())
    assert len(fake_api.requests) == 1  # same photo: answered from the cache


def test_a_reply_that_is_not_json_gives_a_friendly_error(fake_api):
    fake_api.reply_text("Sorry, I can't help with that.")
    with pytest.raises(StepError, match="didn't make sense"):
        identify_item(jpeg())
