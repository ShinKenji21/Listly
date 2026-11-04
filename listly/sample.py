"""Ready-made sample listings, so anyone can see the finished app without an API key or credits."""

import io

from PIL import Image, ImageDraw

from listly import identify, pricing
from listly.models import ItemInfo, ListingDraft, PlatformListing, PriceEstimate
from listly.platforms import PLATFORMS
from listly.writer import demo_listing

SAMPLE_PREFIX = "sample-"


def _photo(background: tuple, draw_item) -> bytes:
    # Drawn in code so the repo needs no photos of anyone's real belongings.
    img = Image.new("RGB", (600, 600), background)
    draw_item(ImageDraw.Draw(img))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _shoes(d):
    d.rounded_rectangle((110, 290, 500, 410), radius=60, fill=(250, 250, 250), outline=(120, 130, 140), width=6)
    d.rounded_rectangle((110, 380, 500, 430), radius=25, fill=(150, 155, 160))


def _phone(d):
    d.rounded_rectangle((210, 110, 390, 490), radius=36, fill=(30, 34, 40))
    d.rounded_rectangle((228, 130, 300, 210), radius=18, fill=(70, 76, 86))
    d.ellipse((244, 146, 284, 186), fill=(20, 22, 26))


def _bag(d):
    d.polygon([(170, 250), (430, 250), (470, 480), (130, 480)], fill=(196, 140, 92))
    d.arc((220, 130, 380, 330), start=180, end=360, fill=(150, 100, 60), width=14)


def _same_text_everywhere(title: str, description: str, tags: list[str]) -> dict[str, PlatformListing]:
    return {key: PlatformListing(title=title, description=description, tags=tags) for key in PLATFORMS}


def make_samples() -> list[tuple[ListingDraft, bytes]]:
    """Three sample listings, one in each status, built from the same demo data demo mode uses."""
    shoes = ListingDraft(
        photo_id=SAMPLE_PREFIX + "shoes",
        info=ItemInfo.from_dict(identify.DEMO_REPLY),
        answers={"What size are they?": "US 9", "How many times have they been worn?": "About 10 times"},
        platforms=list(PLATFORMS),
        price=PriceEstimate.from_dict(pricing.DEMO_REPLY),
        asking_price=1800,
        listings={key: demo_listing(platform) for key, platform in PLATFORMS.items()},
        created="2026-11-03 18:20",
        status="listed",
    )
    phone = ListingDraft(
        photo_id=SAMPLE_PREFIX + "phone",
        info=ItemInfo.from_dict({
            "item": "smartphone", "object_name": "phone", "brand": "Apple", "model": "iPhone 12",
            "category": "Electronics", "color": "black", "condition": "good",
            "flaws": ["light scratches on the back"], "features": ["128GB", "battery health 86%"],
            "confidence": "high", "questions_for_seller": ["Is it openline?", "Does it come with the box and charger?"],
        }),
        answers={"Is it openline?": "Yes, openline", "Does it come with the box and charger?": "Box only"},
        platforms=["facebook", "carousell"],
        price=PriceEstimate.from_dict({
            "price_low": 14000, "price_high": 17000, "new_price": 32990, "confidence": "medium",
            "summary": "Used iPhone 12 128GB units in good condition list for ₱14,000–₱17,000.",
        }),
        asking_price=15500,
        listings=_same_text_everywhere(
            "iPhone 12 128GB Black – Openline, Battery 86%",
            "Selling my iPhone 12, 128GB, black. Openline, battery health 86%. Comes with the box.\n\n"
            "Flaws: light scratches on the back (see photos).\n\nMeet-up or delivery.",
            ["iphone 12", "apple", "128gb", "openline", "preloved"],
        ),
        created="2026-11-04 09:05",
        status="draft",
    )
    bag = ListingDraft(
        photo_id=SAMPLE_PREFIX + "bag",
        info=ItemInfo.from_dict({
            "item": "tote bag", "object_name": "bag", "category": "Bags", "color": "tan",
            "condition": "like new", "features": ["roomy inside", "sturdy handles"], "confidence": "medium",
        }),
        platforms=["facebook", "shopee"],
        asking_price=650,
        listings=_same_text_everywhere(
            "Tan Tote Bag – Like New",
            "Roomy tan tote bag with sturdy handles. Used twice, like new. No flaws.\n\nMeet-up or shipping.",
            ["tote bag", "bag", "preloved", "like new"],
        ),
        created="2026-10-31 14:40",
        status="sold",
    )
    return [
        (shoes, _photo((236, 240, 245), _shoes)),
        (phone, _photo((232, 236, 241), _phone)),
        (bag, _photo((244, 238, 230), _bag)),
    ]
