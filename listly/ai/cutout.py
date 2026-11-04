"""Step 2: SAM 3.1 finds the item in the photo and cuts it out of the background."""

import io
import re
from dataclasses import dataclass

import numpy as np
from PIL import Image

from listly import cache
from listly.ai.api import StepError, create_response
from listly.config import DEMO_MODE
from listly.images import image_hash, to_data_url
from listly.models import UNKNOWN, ItemInfo

STEP = "cutout"
MODEL = "sam-3.1"

# One object in SAM's reply looks like: 0<|box;x1=..;y1=..;x2=..;y2=..;w=..;h=..|><|mask;x=0;y=0;data=H,W,!payload|>
# (grammar from Meta's "reading segmentation output" page). The optional ";c=" is a confidence score.
RECORD = re.compile(
    r"(\d+)<\|box;x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+);w=(\d+);h=(\d+)(?:;c=[\d.]+)?\|>"
    r"<\|mask;x=0;y=0(?:;c=[\d.]+)?;data=(\d+),(\d+),([~!])(.*?)\|>"
)


@dataclass
class Cutout:
    png: bytes  # the item on a transparent background, or just cropped if exact is False
    exact: bool  # True = traced the item's outline; False = only cropped to the box around it


def _to_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")  # PNG, not JPEG, because JPEG can't store transparency
    return buf.getvalue()


# --- one_bit mask decoder ---------------------------------------------------------------------
# Ported to Python from Meta's @meta-sam/parser 0.1.0 (dist/mask-codec.js), which is the official
# decoder but only exists for TypeScript. Used under the SAM License: see third_party/SAM-LICENSE.txt. Masks are compressed hard (a 639x567 mask
# fits in ~500 bytes): base85 text -> bytes -> a range coder that predicts each pixel from its neighbours.

# Base85 digits: printable ASCII minus the characters the reply grammar uses as separators.
_ALPHABET = "".join(chr(c) for c in range(0x21, 0x7F) if chr(c) not in '"\\,;<>|')[:85]
_DIGIT = {ch: i for i, ch in enumerate(_ALPHABET)}
_M32, _TOP, _BOTTOM = 0xFFFFFFFF, 1 << 24, 1 << 16


def _unpack(text: str) -> bytes:
    """Base85 text -> bytes. The first 5 characters hold the byte length."""
    length = 0
    for ch in text[:5]:
        length = length * 85 + _DIGIT[ch]
    out, src = bytearray(), 5
    while src < len(text):
        group = text[src : src + 5]
        value = 0
        for i in range(5):  # a short last group is padded with the highest digit
            value = value * 85 + (_DIGIT[group[i]] if i < len(group) else 84)
        out += value.to_bytes(4, "big")  # OverflowError if the group is out of range
        src += 5
    if len(out) < length:
        raise ValueError("mask payload is shorter than its length prefix")
    return bytes(out[:length])


class _RangeDecoder:
    def __init__(self, data: bytes):
        self.data, self.pos = data, 0
        self.low, self.range, self.code, self.scaled = 0, _M32, 0, 0
        for _ in range(4):
            self.code = ((self.code << 8) | self._read()) & _M32

    def _read(self) -> int:
        byte = self.data[self.pos]  # IndexError if the payload ends too early
        self.pos += 1
        return byte

    def frequency(self, total: int) -> int:
        self.scaled = self.range // total
        if self.scaled == 0:
            raise ValueError("invalid coding state")
        return min(((self.code - self.low) & _M32) // self.scaled, total - 1)

    def decode(self, cumulative: int, frequency: int) -> None:
        self.low = (self.low + self.scaled * cumulative) & _M32
        self.range = self.scaled * frequency
        while True:
            if (self.low ^ ((self.low + self.range) & _M32)) < _TOP:
                pass
            elif self.range < _BOTTOM:
                self.range = -self.low & (_BOTTOM - 1)
            else:
                break
            self.code = ((self.code << 8) | self._read()) & _M32
            self.low = (self.low << 8) & _M32
            self.range = (self.range << 8) & _M32


def _decode_one_bit(payload: str, rows: int, cols: int) -> np.ndarray:
    """Turn a one_bit mask payload into a rows x cols grid of True (item) / False (background)."""
    try:
        decoder = _RangeDecoder(_unpack(payload))
        counts = [1] * (2 * 4096)  # how often each 12-neighbour pattern was followed by a 0 or a 1
        width = cols + 4  # 2 columns of zero padding on each side, 2 rows on top
        padded = bytearray(width * (rows + 2))
        out = bytearray(rows * cols)
        for y in range(rows):
            row = (y + 2) * width + 2
            for x in range(cols):
                p = row + x
                up, up2 = p - width, p - 2 * width
                context = (
                    padded[p - 1] | padded[p - 2] << 1
                    | padded[up - 2] << 2 | padded[up - 1] << 3 | padded[up] << 4
                    | padded[up + 1] << 5 | padded[up + 2] << 6
                    | padded[up2 - 2] << 7 | padded[up2 - 1] << 8 | padded[up2] << 9
                    | padded[up2 + 1] << 10 | padded[up2 + 2] << 11
                )
                k = context << 1
                zero, one = counts[k], counts[k + 1]
                if decoder.frequency(zero + one) < zero:
                    bit = 0
                    decoder.decode(0, zero)
                else:
                    bit = 1
                    decoder.decode(zero, one)
                padded[p] = out[y * cols + x] = bit
                counts[k + bit] += 14
                if counts[k] + counts[k + 1] >= 4096:  # halve old counts so the model keeps adapting
                    counts[k] = counts[k] >> 1 or 1
                    counts[k + 1] = counts[k + 1] >> 1 or 1
    except (KeyError, IndexError, OverflowError) as e:  # bad character, truncated, out-of-range group
        raise ValueError("mask payload didn't decode") from e
    return np.frombuffer(bytes(out), dtype=np.uint8).reshape(rows, cols).astype(bool)


def _ask_sam(image_bytes: bytes, item: str) -> str:
    """Get SAM's raw reply, or "" if it found nothing. Cached by photo + name, since a new name is a new search."""
    key = image_hash(image_bytes + item.lower().encode())
    cached = cache.load(STEP, key)
    if cached is not None:
        return cached["reply"]

    response = create_response(
        "SAM 3.1",
        model=MODEL,
        input=[
            {
                "type": "message",
                "role": "user",
                "content": [
                    # SAM works best with a short noun phrase naming one object, e.g. "running shoes".
                    {"type": "input_text", "text": item},
                    {"type": "input_image", "image_url": to_data_url(image_bytes)},
                ],
            }
        ],
        # one_bit is the mask format we know how to read (the default "lossless" one isn't documented).
        metadata={"mask_encoding": "one_bit"},
    )
    reply = response.output_text or ""
    if not RECORD.search(reply):
        reply = ""
    # "Found nothing" is cached too: asking again with the same name would cost credits for the same answer.
    cache.save(STEP, key, {"reply": reply})
    return reply


def _names_to_try(info: ItemInfo) -> list[str]:
    """SAM finds "scooter" but can miss "motor scooter", so try the short name first, then fall back."""
    names = [info.object_name, info.item, info.item.split()[-1]]
    return list(dict.fromkeys(n for n in names if n != UNKNOWN))  # drop unknowns and repeats, keep order


def cut_out(image_bytes: bytes, info: ItemInfo) -> Cutout:
    """Cut the item out of an already-shrunk JPEG. Raises StepError if SAM can't find it."""
    photo = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    if DEMO_MODE:
        return Cutout(png=_to_png(photo), exact=True)

    names = _names_to_try(info)
    for name in names:
        reply = _ask_sam(image_bytes, name)
        if reply:
            break
    else:
        raise StepError(f"SAM 3.1 couldn't find the {names[0]} in the photo.")

    # Decoding the mask takes about a second in Python, so keep the finished cut-out too.
    png_key = image_hash(image_bytes + reply.encode())
    cached_png = cache.load_bytes(STEP, png_key, "png")
    if cached_png is not None:
        return Cutout(png=cached_png, exact=True)  # only exact cut-outs are saved below

    records = RECORD.findall(reply)
    # SAM can return several matches; the item being sold is usually the biggest one in the photo.
    best = max(records, key=lambda r: (int(r[3]) - int(r[1])) * (int(r[4]) - int(r[2])))
    x1, y1, x2, y2, frame_w, frame_h, rows, cols = (int(v) for v in best[1:9])
    encoding, payload = best[9], best[10]

    # Box coordinates are in SAM's frame size; scale them in case that differs from our photo.
    sx, sy = photo.width / frame_w, photo.height / frame_h
    # x2/y2 are inclusive (a box from x1=353 to x2=453 is 101 pixels wide), hence the +1.
    crop = photo.crop((round(x1 * sx), round(y1 * sy), round((x2 + 1) * sx), round((y2 + 1) * sy)))

    try:
        if encoding != "!":
            raise ValueError("not a one_bit mask")
        mask = _decode_one_bit(payload, rows, cols)
    except ValueError:
        # Better a tight crop than nothing: the seller still gets a usable photo.
        return Cutout(png=_to_png(crop.convert("RGB")), exact=False)

    alpha = Image.fromarray(mask.astype(np.uint8) * 255).resize(crop.size)
    crop.putalpha(alpha)  # background pixels become transparent
    png = _to_png(crop)
    cache.save_bytes(STEP, png_key, "png", png)
    return Cutout(png=png, exact=True)
