"""Step 1: ask Muse Spark what the item in the photo is."""

from listly import cache
from listly.api import StepError, create_response, parse_json
from listly.config import DEMO_MODE, MODEL
from listly.images import image_hash, to_data_url
from listly.models import ItemInfo

STEP = "identify"

PROMPT = """You are helping a small online seller in the Philippines list an item for sale.
Look at the photo and reply with ONLY a JSON object, no other text:
{
  "item": "what the item is, e.g. 'running shoes'",
  "object_name": "the plain 1-2 word name of the object, e.g. 'shoes', 'scooter', 'phone'",
  "brand": "brand name, or 'unknown' if you can't tell",
  "model": "specific model, or 'unknown' if you can't tell",
  "category": "e.g. 'Shoes', 'Electronics', 'Kitchen', 'Clothing'",
  "color": "main color(s)",
  "condition": "one of: new, like new, good, fair, poor",
  "flaws": ["visible scratches, stains, tears, etc. Empty list if none"],
  "confidence": "high, medium, or low",
  "questions_for_seller": ["things you can't tell from the photo, e.g. size, does it work"],
  "prohibited": false,
  "prohibited_reason": ""
}
Be honest. Never guess a brand or model: if you are unsure, write "unknown" and lower your confidence.
Set "prohibited" to true, with a short reason, if the item is a weapon, drugs,
a counterfeit or replica of a branded product, or a live animal."""

# Shaped like a real reply so demo mode still goes through the same validation.
DEMO_REPLY = {
    "item": "running shoes",
    "object_name": "shoes",
    "brand": "Nike",
    "model": "unknown",
    "category": "Shoes",
    "color": "white and grey",
    "condition": "good",
    "flaws": ["scuff on left toe", "slightly worn soles"],
    "confidence": "medium",
    "questions_for_seller": ["What size are they?", "How many times have they been worn?"],
    "prohibited": False,
    "prohibited_reason": "",
}


def identify_item(image_bytes: bytes) -> ItemInfo:
    """Identify the item in an already-shrunk JPEG. Cached by image hash."""
    if DEMO_MODE:
        return ItemInfo.from_dict(DEMO_REPLY)

    key = image_hash(image_bytes)
    cached = cache.load(STEP, key)
    if cached is not None:
        try:
            return ItemInfo.from_dict(cached)
        except ValueError:
            pass  # stale cache from an older format; ask the model again

    # Images go in an "input_image" part as a base64 data URL (confirmed in Meta's docs).
    response = create_response(
        "Muse Spark",
        model=MODEL,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": PROMPT},
                    {"type": "input_image", "image_url": to_data_url(image_bytes)},
                ],
            }
        ],
    )

    reply = response.output_text or ""  # the SDK joins all text parts of the reply for us
    try:
        info = ItemInfo.from_dict(parse_json(reply))
    except ValueError as e:  # json.JSONDecodeError is a ValueError too
        raise StepError(f"Muse Spark's answer didn't make sense ({e}). Try again.") from e

    # Only cache answers that passed validation, so a bad reply can be retried.
    cache.save(STEP, key, info.to_dict())
    return info
