"""Step 5: Muse Spark writes a title, description and tags for each platform, then a checker validates them."""

import json
import re
from dataclasses import asdict, replace

from listly import cache
from listly.api import StepError, create_response, parse_json
from listly.config import DEMO_MODE, MODEL
from listly.images import image_hash
from listly.models import ListingDraft, PlatformListing
from listly.platforms import Platform

STEP = "writer"

LANGUAGES = {
    "English": "Write in clear, natural English.",
    "Filipino": "Write in natural Filipino (Tagalog), the way Filipino sellers write online. "
    "Keep brand names, model names and technical terms in English.",
    "Taglish": "Write in Taglish (a natural mix of Tagalog and English), the way Filipino sellers casually post online.",
}

PROMPT = """You are writing a {platform} listing for a seller in the Philippines.

Item details (confirmed by the seller):
{details}
Asking price: {price}

Platform rules:
- Tone: {tone}.
- Title: at most {max_title} characters. Put the most important words first (brand, model, key spec).
- Description: {description_tips}
- {hashtag_rule}
- Tags: {min_tags} to {max_tags} short search keywords, without "#".
- Language: {language}

Honesty rules (most important):
- Mention every flaw listed in the item details clearly in the description. Never hide or soften a flaw.
- Only state facts from the item details. Don't invent specs, accessories, warranty or history.
- Don't include phone numbers, addresses or payment instructions.

Reply with ONLY a JSON object, no other text:
{{"title": "...", "description": "...", "tags": ["...", "..."]}}"""

FIX_PROMPT = """{prompt}

Your previous answer was:
{previous}

It has these problems:
{problems}

Fix them and reply with the corrected JSON object only."""


def _price_text(draft: ListingDraft) -> str:
    return f"₱{draft.asking_price:,}" if draft.asking_price else "not set (don't mention a price)"


def _build_prompt(draft: ListingDraft, platform: Platform) -> str:
    hashtag_rule = (
        "End the description with 5 to 10 relevant hashtags."
        if platform.hashtags
        else "Don't use hashtags anywhere."
    )
    return PROMPT.format(
        platform=platform.name,
        details=draft.describe(),
        price=_price_text(draft),
        tone=platform.tone,
        max_title=platform.max_title,
        description_tips=platform.description_tips,
        hashtag_rule=hashtag_rule,
        min_tags=platform.min_tags,
        max_tags=platform.max_tags,
        language=LANGUAGES.get(draft.language, LANGUAGES["English"]),
    )


def check(listing: PlatformListing, platform: Platform, draft: ListingDraft) -> list[str]:
    """Rules we can verify in code. Returns a list of problems (empty = all good)."""
    problems = []
    if len(listing.title) > platform.max_title:
        problems.append(f"The title is {len(listing.title)} characters; the limit is {platform.max_title}.")
    if len(listing.description) < 80:
        problems.append("The description is too short; add the key details.")
    if not platform.hashtags and "#" in listing.description:
        problems.append("Remove the hashtags; this platform doesn't use them.")
    if not platform.min_tags <= len(listing.tags) <= platform.max_tags:
        problems.append(f"Give {platform.min_tags} to {platform.max_tags} tags (you gave {len(listing.tags)}).")
    # The flaw check compares words, so it only works when the listing is in English;
    # in Filipino or Taglish the flaw words are translated, so we rely on the prompt instead.
    if draft.language == "English":
        text = listing.description.lower()
        for flaw in draft.info.flaws:
            words = re.findall(r"[a-z]{4,}", flaw.lower()) or [flaw.lower()]
            if not any(word in text for word in words):
                problems.append(f'The description must mention this flaw: "{flaw}".')
    return problems


def _ask(prompt: str) -> PlatformListing:
    response = create_response("Muse Spark", model=MODEL, input=prompt)
    try:
        return PlatformListing.from_dict(parse_json(response.output_text or ""))
    except ValueError as e:  # json.JSONDecodeError is a ValueError too
        raise StepError(f"Muse Spark's listing didn't make sense ({e}). Try again.") from e


def write_listing(draft: ListingDraft, platform: Platform) -> PlatformListing:
    """Write one platform's listing. Cached by the full prompt, so unchanged details cost nothing."""
    if DEMO_MODE:
        return demo_listing(platform)

    prompt = _build_prompt(draft, platform)
    key = image_hash(prompt.encode())  # the prompt contains every input: details, price, language, rules
    cached = cache.load(STEP, key)
    if cached is not None:
        try:
            return PlatformListing.from_dict(cached)
        except ValueError:
            pass  # stale cache; write it again

    listing = _ask(prompt)
    problems = check(listing, platform, draft)
    if problems:
        # One fix attempt only: each try costs credits, and the seller can still edit by hand.
        previous = json.dumps({"title": listing.title, "description": listing.description, "tags": listing.tags})
        fixed = _ask(FIX_PROMPT.format(prompt=prompt, previous=previous, problems="\n".join(problems)))
        listing = replace(fixed, warnings=check(fixed, platform, draft))

    cache.save(STEP, key, asdict(listing))
    return listing


DEMO_LISTINGS = {
    "facebook": {
        "title": "Nike Running Shoes US 9 – White/Grey, Good Condition",
        "description": "Selling my Nike running shoes, white and grey, size US 9. Worn about 10 times, "
        "still comfortable with plenty of life left.\n\nFlaws: small scuff on the left toe and slightly "
        "worn soles (see photo).\n\nMeet-up or delivery available. Still available!",
        "tags": ["nike", "running shoes", "us 9", "sneakers", "preloved"],
    },
    "shopee": {
        "title": "Nike Running Shoes Men's US 9 White Grey Preloved Good Condition",
        "description": "Preloved Nike running shoes in good condition.\n\n• Size: US 9\n• Color: white and grey\n"
        "• Worn about 10 times\n\nFlaws:\n• Small scuff on the left toe\n• Slightly worn soles\n\n"
        "Inclusions: shoes only.\n\n#nike #runningshoes #sneakers #preloved #us9",
        "tags": ["nike", "running shoes", "sneakers", "preloved", "us 9"],
    },
    "carousell": {
        "title": "Nike Running Shoes US 9 (Good Condition)",
        "description": "Nike running shoes, US 9, white/grey. Worn ~10 times.\n\nFlaws: scuff on left toe, "
        "slightly worn soles.\n\nMeet-up or delivery. Message me!",
        "tags": ["nike", "running shoes", "us 9", "sneakers"],
    },
}


def demo_listing(platform: Platform) -> PlatformListing:
    return PlatformListing.from_dict(DEMO_LISTINGS[platform.key])
