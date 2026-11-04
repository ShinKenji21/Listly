"""Data shapes passed between steps, with validation for everything that comes from the model."""

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime

UNKNOWN = "unknown"
CONDITIONS = ["new", "like new", "good", "fair", "poor"]
CONFIDENCES = ["high", "medium", "low"]
STATUSES = ["draft", "listed", "sold"]  # where a saved listing is in the seller's own process


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
    features: list[str] = field(default_factory=list)  # visible selling points, e.g. "gold rims"
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
            features=_text_list(data.get("features")),
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
    listing_price: int | None = None  # a good price to list at, leaving room to negotiate
    suggested_lowest: int | None = None  # the lowest price worth accepting (private to the seller)
    reason: str = ""  # one line, e.g. "similar items sell for ₱2,500–₱3,200"

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
        summary, reason = _text(data.get("summary")), _text(data.get("reason"))
        confidence = _choice(data.get("confidence"), CONFIDENCES)
        low, high = min(low, high), max(low, high)  # in case the model swaps them
        listing = _peso(data.get("listing_price"))
        if listing is None or not low <= listing <= high:
            listing = int(round((low + high) / 2, -2))  # a sensible middle if the model's is missing or odd
        lowest = _peso(data.get("suggested_lowest"))
        if lowest is None or lowest > listing:
            lowest = int(round(listing * 0.9, -2))  # never suggest a "lowest" above the listing price
        return cls(
            price_low=low,
            price_high=high,
            summary="" if summary == UNKNOWN else summary,
            confidence="low" if confidence == UNKNOWN else confidence,
            comparables=[c for c in found if c is not None],
            new_price=_peso(data.get("new_price")),
            listing_price=listing,
            suggested_lowest=lowest,
            reason="" if reason == UNKNOWN else reason,
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PlatformListing:
    """Title, description and tags written for one platform."""

    title: str
    description: str
    tags: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)  # checker problems the model couldn't fix

    @classmethod
    def from_dict(cls, data: dict) -> "PlatformListing":
        """Validate the model's JSON. Raises ValueError if the title or description is missing."""
        if not isinstance(data, dict):
            raise ValueError("reply was not a JSON object")
        title, description = _text(data.get("title")), str(data.get("description") or "").strip()
        if title == UNKNOWN or not description:
            raise ValueError("reply is missing the title or description")
        tags = [t.lstrip("#") for t in _text_list(data.get("tags"))]  # we add "#" ourselves where needed
        return cls(title=title, description=description, tags=tags, warnings=_text_list(data.get("warnings")))


@dataclass
class ListingDraft:
    """One listing, from the first photo to the finished texts. Saved to disk as JSON.

    `info` is the seller's edited copy, not the raw model answer: the seller knows their item
    better than the model, so their corrections must win.
    """

    photo_id: str  # also the listing's id: listing the same photo again updates the same listing
    info: ItemInfo
    answers: dict[str, str] = field(default_factory=dict)  # follow-up question -> seller's answer
    platforms: list[str] = field(default_factory=list)  # keys from listly.platforms
    price: PriceEstimate | None = None
    asking_price: int | None = None  # what the seller decided, which may differ from the suggestion
    language: str = "English"
    listings: dict[str, PlatformListing] = field(default_factory=dict)  # platform key -> texts
    created: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"))
    status: str = "draft"  # one of STATUSES; the seller changes it (Listly never posts anything itself)
    lowest_price: int | None = None  # private: used for buyer replies, never put in listing texts
    reply_history: list[dict] = field(default_factory=list)  # last few buyer replies: message, reply, date

    def describe(self) -> str:
        """The item details as plain text lines, for prompts."""
        info = self.info
        lines = [f"Item: {info.item}"]
        for label, value in [("Brand", info.brand), ("Model", info.model), ("Color", info.color)]:
            if value != UNKNOWN:  # leave out unknowns so the model doesn't write or search "unknown"
                lines.append(f"{label}: {value}")
        lines.append(f"Condition: {info.condition}")
        if info.features:
            lines.append("Highlights: " + "; ".join(info.features))
        lines.append("Flaws: " + ("; ".join(info.flaws) if info.flaws else "none known"))
        for question, answer in self.answers.items():
            lines.append(f"{question} {answer}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ListingDraft":
        """Load a saved listing. Raises ValueError if the file is unusable."""
        price = data.get("price")
        return cls(
            photo_id=str(data["photo_id"]),
            info=ItemInfo.from_dict(data["info"]),
            answers=dict(data.get("answers") or {}),
            platforms=list(data.get("platforms") or []),
            price=PriceEstimate.from_dict(price) if price else None,
            asking_price=_peso(data.get("asking_price")),
            language=str(data.get("language") or "English"),
            listings={k: PlatformListing.from_dict(v) for k, v in (data.get("listings") or {}).items()},
            created=str(data.get("created") or ""),
            status=data.get("status") if data.get("status") in STATUSES else "draft",
            lowest_price=_peso(data.get("lowest_price")),
            reply_history=[h for h in (data.get("reply_history") or []) if isinstance(h, dict)],
        )


@dataclass
class SellerSettings:
    """How the seller sells: saved once, used to answer buyers' questions."""

    meetup_spots: str = ""
    available_times: str = ""
    shipping: str = ""
    payment: str = ""
    swaps: bool = False

    def describe(self) -> str:
        """As plain text lines for prompts. "not set" tells the model to ask the seller instead of guessing."""
        def value(text: str) -> str:
            return text.strip() or "not set"
        return "\n".join([
            f"Meet-up spots: {value(self.meetup_spots)}",
            f"Available times: {value(self.available_times)}",
            f"Shipping: {value(self.shipping)}",
            f"Payment methods: {value(self.payment)}",
            f"Open to swaps: {'yes' if self.swaps else 'no'}",
        ])

    def is_empty(self) -> bool:
        return not any([self.meetup_spots, self.available_times, self.shipping, self.payment])

    @classmethod
    def from_dict(cls, data: dict) -> "SellerSettings":
        return cls(
            meetup_spots=str(data.get("meetup_spots") or ""),
            available_times=str(data.get("available_times") or ""),
            shipping=str(data.get("shipping") or ""),
            payment=str(data.get("payment") or ""),
            swaps=data.get("swaps") is True,
        )

    def to_dict(self) -> dict:
        return asdict(self)
