"""Step 4: Muse Spark + web search finds comparable listings and suggests a price range in PHP."""

import json

from listly import cache
from listly.api import StepError, create_response, parse_json
from listly.config import DEMO_MODE, MODEL
from listly.images import image_hash
from listly.models import ListingDraft, PriceEstimate

STEP = "pricing"

PROMPT = """You are helping a seller in the Philippines price a second-hand item.
Item details (confirmed by the seller):
{details}

Search the web for 3 to 5 listings of the same or a very similar item for sale in the Philippines.
Prefer used items in similar condition. Use different websites where you can (at most 2 listings
from the same site): any Philippine marketplace, classifieds site, or shop that suits this kind of item.
Also look up the current brand-new price (SRP) in the Philippines, if the item is still sold new.
Then suggest a fair price range in Philippine pesos (PHP), adjusted for this item's condition and flaws.
A used item should normally be priced below its brand-new price.

Reply with ONLY a JSON object, no other text:
{{
  "price_low": 1200,
  "price_high": 1800,
  "new_price": 2500,
  "summary": "one or two sentences explaining the range",
  "confidence": "high, medium, or low",
  "comparables": [
    {{"title": "listing title", "price": 1500, "url": "exact URL of the listing you found"}}
  ]
}}
Only include listings you actually found in your search, with their exact URL. Never make up a listing or URL.
Set "new_price" to null if you couldn't find a brand-new price.
If you found few or no good matches, say so in the summary and set confidence to "low"."""

# Shaped like a real reply so demo mode still goes through the same validation.
DEMO_REPLY = {
    "price_low": 1500,
    "price_high": 2200,
    "new_price": 5495,
    "summary": "Used Nike running shoes in good condition usually sell for ₱1,500–₱2,500; "
    "the toe scuff puts this pair toward the lower end.",
    "confidence": "medium",
    "comparables": [
        {"title": "Nike running shoes, used, US 9", "price": 1800, "url": "https://www.carousell.ph/"},
        {"title": "Nike Pegasus, lightly worn", "price": 2200, "url": "https://shopee.ph/"},
    ],
}

# Bias the search toward the Philippines (format from Meta's search grounding docs).
WEB_SEARCH = {
    "type": "web_search",
    "search_context_size": "medium",  # "high" costs more tokens; medium is the documented default
    "user_location": {"type": "approximate", "country": "PH", "timezone": "Asia/Manila"},
}


def _get(obj, name):
    # Extra fields can come back as plain dicts instead of SDK objects; handle both.
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


def _norm(url: str) -> str:
    return url.strip().rstrip("/")


def _found_urls(response) -> set[str]:
    """Every URL the search really returned or the model cited."""
    urls = set()
    for item in response.output:
        if item.type == "web_search_call":
            for result in _get(item, "results") or []:
                urls.add(_get(result, "url"))
        elif item.type == "message":
            for block in item.content:
                for annotation in _get(block, "annotations") or []:
                    if _get(annotation, "type") == "url_citation":
                        urls.add(_get(annotation, "url"))
    return {_norm(u) for u in urls if u}


def suggest_price(draft: ListingDraft) -> PriceEstimate:
    """Search for comparable listings and suggest a price range. Cached by the item details."""
    if DEMO_MODE:
        return PriceEstimate.from_dict(DEMO_REPLY)

    details = draft.describe()
    # Key on the details, not just the photo: if the seller fixes the brand, the price should be redone.
    # The prompt is in the key too, so improving the prompt doesn't keep serving old answers.
    key = image_hash((draft.photo_id + details + PROMPT).encode())
    cached = cache.load(STEP, key)
    if cached is not None:
        try:
            return PriceEstimate.from_dict(cached)
        except ValueError:
            pass  # stale cache from an older format; search again

    response = create_response(
        "Muse Spark",
        model=MODEL,
        input=PROMPT.format(details=details),
        tools=[WEB_SEARCH],
        # Ask for the raw search results so we can check the model's links against them.
        include=["web_search_call.results"],
    )
    try:
        estimate = PriceEstimate.from_dict(parse_json(response.output_text or ""))
    except ValueError as e:  # json.JSONDecodeError is a ValueError too
        raise StepError(f"Muse Spark's price answer didn't make sense ({e}). Try again.") from e

    # Models can invent believable URLs, so only keep links the search actually found.
    found = _found_urls(response)
    estimate.comparables = [c for c in estimate.comparables if _norm(c.url) in found]

    cache.save(STEP, key, estimate.to_dict())
    return estimate
