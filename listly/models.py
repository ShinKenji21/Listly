"""Data shapes passed between steps. Later days add PriceEstimate, PlatformListing, etc."""

import re
from dataclasses import asdict, dataclass, field

UNKNOWN = "unknown"
CONDITIONS = ["new", "like new", "good", "fair", "poor"]
CONFIDENCES = ["high", "medium", "low"]


def _text(value) -> str:
    """Model output can be null, empty, or a stray number; turn it into a clean string."""
    if value is None:
        return UNKNOWN
    text = str(value).strip()
    # Models sometimes write "null" or "N/A" as a string instead of following the prompt.
    if text.lower() in ("", "null", "none", "n/a", "unknown"):
        return UNKNOWN
    return text


def _text_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]  # one flaw given as a string instead of a list
    if not isinstance(value, list):
        raise ValueError(f"expected a list, got {type(value).__name__}")
    return [str(v).strip() for v in value if str(v).strip()]


def _choice(value, allowed: list[str]) -> str:
    text = _text(value).lower()
    return text if text in allowed else UNKNOWN


@dataclass
class ItemInfo:
    """What Muse Spark sees in the photo."""

    item: str
    object_name: str = UNKNOWN  # plain 1-2 word noun for SAM, e.g. "scooter" (SAM misses longer phrases)
    brand: str = UNKNOWN
    model: str = UNKNOWN
    category: str = UNKNOWN
    color: str = UNKNOWN
    condition: str = UNKNOWN
    flaws: list[str] = field(default_factory=list)
    confidence: str = "low"
    questions_for_seller: list[str] = field(default_factory=list)
    prohibited: bool = False
    prohibited_reason: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "ItemInfo":
        """Validate the model's JSON. Raises ValueError if it can't be used at all."""
        if not isinstance(data, dict):
            raise ValueError("reply was not a JSON object")
        item = _text(data.get("item"))
        if item == UNKNOWN:
            raise ValueError("reply is missing the 'item' field")

        info = cls(
            item=item,
            object_name=_text(data.get("object_name")),
            brand=_text(data.get("brand")),
            model=_text(data.get("model")),
            category=_text(data.get("category")),
            color=_text(data.get("color")),
            condition=_choice(data.get("condition"), CONDITIONS),
            flaws=_text_list(data.get("flaws")),
            confidence=_choice(data.get("confidence"), CONFIDENCES),
            questions_for_seller=_text_list(data.get("questions_for_seller")),
            prohibited=data.get("prohibited") is True,
            prohibited_reason=_text(data.get("prohibited_reason")) if data.get("prohibited") is True else "",
        )
        if info.confidence == UNKNOWN:
            info.confidence = "low"
        # Don't let the model claim high confidence about an item it couldn't name the brand/model of.
        if info.confidence == "high" and UNKNOWN in (info.brand, info.model):
            info.confidence = "medium"
        return info

    def to_dict(self) -> dict:
        return asdict(self)


def _peso(value) -> int | None:
    """Turn 1500, "1500.0" or "₱1,500" into 1500. None if it isn't a usable price."""
    if isinstance(value, (int, float)):
        number = value
    else:
        try:
            number = float(re.sub(r"[^\d.]", "", str(value or "")))  # drop ₱, commas, spaces
        except ValueError:
            return None
    return round(number) if number > 0 else None


@dataclass
class Comparable:
    """A similar listing found by web search."""

    title: str
    url: str
    price: int | None = None

    @classmethod
    def from_dict(cls, data) -> "Comparable | None":
        """None if the entry is unusable, so one bad comparable doesn't sink the whole estimate."""
        if not isinstance(data, dict):
            return None
        url = str(data.get("url") or "").strip()
        # Only web links: we show these as clickable links, so never allow "javascript:" and the like.
        if not url.startswith(("https://", "http://")):
            return None
        title = _text(data.get("title"))
        return cls(title=url if title == UNKNOWN else title, url=url, price=_peso(data.get("price")))


@dataclass
class PriceEstimate:
    """Suggested price range in PHP, with the listings it's based on."""

    # Same names as the model's JSON, so a cached to_dict() can be read back with from_dict().
    price_low: int
    price_high: int
    summary: str
    confidence: str = "low"
    comparables: list[Comparable] = field(default_factory=list)
    new_price: int | None = None  # brand-new price, as a sanity check for the used range

    @classmethod
    def from_dict(cls, data: dict) -> "PriceEstimate":
        """Validate the model's JSON. Raises ValueError if there's no usable price range."""
        if not isinstance(data, dict):
            raise ValueError("reply was not a JSON object")
        low, high = _peso(data.get("price_low")), _peso(data.get("price_high"))
        if low is None or high is None:
            raise ValueError("reply is missing a price range")
        comparables = data.get("comparables")
        found = [Comparable.from_dict(c) for c in comparables] if isinstance(comparables, list) else []
        summary = _text(data.get("summary"))
        confidence = _choice(data.get("confidence"), CONFIDENCES)
        return cls(
            price_low=min(low, high),  # in case the model swaps them
            price_high=max(low, high),
            summary="" if summary == UNKNOWN else summary,
            confidence="low" if confidence == UNKNOWN else confidence,
            comparables=[c for c in found if c is not None],
            new_price=_peso(data.get("new_price")),
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ListingDraft:
    """Everything the seller has confirmed so far. Later steps (price, listings) read from this.

    `info` is the seller's edited copy, not the raw model answer: the seller knows their item
    better than the model, so their corrections must win.
    """

    photo_id: str
    info: ItemInfo
    answers: dict[str, str] = field(default_factory=dict)  # follow-up question -> seller's answer

    def to_dict(self) -> dict:
        return asdict(self)
