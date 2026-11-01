"""Step 3: Muse Image turns the cut-out into a clean product photo. The original photo is always kept."""

import base64
import io

from PIL import Image

from listly import cache
from listly.api import StepError, create_response
from listly.config import DEMO_MODE
from listly.images import image_hash, to_data_url

STEP = "clean_photo"
MODEL = "muse-image-1.0"

# The item must stay exactly as it is: a photo that hides flaws would mislead buyers.
PROMPT = """Make a clean product photo for an online marketplace listing from this image.
Place the exact same item on a plain white background with soft, even lighting and a light natural shadow.
Do not change the item: keep its shape, color, logos, text, wear and any flaws exactly as they are.
Do not add or remove anything."""


def _to_jpeg(data: bytes) -> bytes:
    """Muse Image returns WebP by default; JPEG is accepted by every marketplace."""
    img = Image.open(io.BytesIO(data)).convert("RGBA")
    # JPEG has no transparency, so put any see-through areas on white instead of black.
    flat = Image.new("RGB", img.size, "white")
    flat.paste(img, mask=img.getchannel("A"))
    buf = io.BytesIO()
    flat.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def make_clean_photo(source_png: bytes) -> bytes:
    """Return a clean JPEG. Cached by the input image, so each photo costs $0.01 only once."""
    if DEMO_MODE:
        return _to_jpeg(source_png)

    key = image_hash(source_png)
    cached = cache.load_bytes(STEP, key, "jpg")
    if cached is not None:
        return cached

    response = create_response(
        "Muse Image",
        model=MODEL,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": PROMPT},
                    {"type": "input_image", "image_url": to_data_url(source_png, "image/png")},
                ],
            }
        ],
    )
    # Pick the image by type, not position: a reasoning or message item may come first.
    image_b64 = next(
        (getattr(o, "result", None) for o in response.output if o.type == "image_generation_call"),
        None,
    )
    if not image_b64:
        raise StepError("Muse Image didn't send back a picture. Try again.")
    try:
        jpeg = _to_jpeg(base64.b64decode(image_b64))
    except (ValueError, OSError):  # bad base64, or bytes Pillow can't open
        raise StepError("Muse Image sent back a picture we couldn't open. Try again.")

    cache.save_bytes(STEP, key, "jpg", jpeg)
    return jpeg
