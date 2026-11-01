"""A ready-made sample listing, so anyone can see the finished result without an API key or credits."""

import io

from PIL import Image, ImageDraw

from listly import identify, pricing
from listly.models import ItemInfo, ListingDraft, PriceEstimate
from listly.platforms import PLATFORMS
from listly.writer import demo_listing

SAMPLE_ID = "sample"


def _sample_photo() -> bytes:
    # Drawn in code so the repo needs no image files of anyone's real belongings.
    img = Image.new("RGB", (600, 600), (236, 240, 245))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((110, 300, 500, 420), radius=60, fill=(250, 250, 250), outline=(120, 130, 140), width=6)
    draw.rounded_rectangle((110, 380, 500, 430), radius=25, fill=(150, 155, 160))
    draw.text((235, 200), "Sample photo", fill=(90, 100, 110))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def make_sample() -> tuple[ListingDraft, bytes]:
    """Build the sample from the same demo data that demo mode uses."""
    draft = ListingDraft(
        photo_id=SAMPLE_ID,
        info=ItemInfo.from_dict(identify.DEMO_REPLY),
        answers={"What size are they?": "US 9", "How many times have they been worn?": "About 10 times"},
        platforms=list(PLATFORMS),
        price=PriceEstimate.from_dict(pricing.DEMO_REPLY),
        asking_price=1800,
        listings={key: demo_listing(platform) for key, platform in PLATFORMS.items()},
    )
    return draft, _sample_photo()
