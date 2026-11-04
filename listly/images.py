"""Image helpers: shrink photos before sending and hash them for the cache."""

import base64
import hashlib
import io

from PIL import Image, ImageOps

from listly.config import MAX_IMAGE_SIDE


def shrink_image(raw: bytes, max_side: int = MAX_IMAGE_SIDE) -> bytes:
    """Resize to at most max_side px and re-encode as JPEG so each request costs fewer credits.

    Raises PIL.UnidentifiedImageError if the bytes aren't an image.
    """
    img = Image.open(io.BytesIO(raw))
    # Phone cameras store rotation in EXIF instead of rotating pixels;
    # without this the model can get a sideways photo.
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def image_hash(image_bytes: bytes) -> str:
    """Short fingerprint of the photo, used as the cache key."""
    return hashlib.sha256(image_bytes).hexdigest()[:16]


def thumbnail(image_bytes: bytes, size: int = 160) -> bytes:
    """Small square JPEG for listing cards, so the home screen stays light even with many listings."""
    img = ImageOps.fit(Image.open(io.BytesIO(image_bytes)).convert("RGB"), (size, size))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def to_data_url(image_bytes: bytes, mime: str = "image/jpeg") -> str:
    """Embed the image in the request so we don't need to host it anywhere."""
    b64 = base64.b64encode(image_bytes).decode()
    return f"data:{mime};base64,{b64}"
