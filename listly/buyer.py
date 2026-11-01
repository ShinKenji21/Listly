"""Buyer reply helper: Muse Spark drafts a polite reply to a buyer's message.

The seller's lowest price is a hard rule: we check the reply in code, not just in the prompt.
"""

import re

from listly import cache
from listly.api import StepError, create_response, parse_json
from listly.config import DEMO_MODE, MODEL
from listly.images import image_hash
from listly.models import ListingDraft
from listly.writer import LANGUAGES

STEP = "buyer_reply"

PROMPT = """You help a seller in the Philippines reply to a buyer on an online marketplace.

The item (confirmed by the seller):
{details}
Listed price: {asking}
The seller's lowest acceptable price (private, never say it is the lowest): ₱{lowest:,}

The buyer wrote:
\"\"\"{message}\"\"\"

Write the seller's reply:
- Polite, friendly and short (1 to 4 sentences). {language}
- Answer questions only with facts from the item details. If you don't know, say the seller will check.
- Never agree to, offer or suggest any price below ₱{lowest:,}. If the buyer offers less,
  decline kindly and counter with a price between ₱{lowest:,} and the listed price.
- For meet-ups, suggest a safe public place. Never share an address, phone number or payment details.
{extra}
Reply with ONLY a JSON object, no other text:
{{"reply": "..."}}"""

# Peso amounts like ₱1,500 / P1500 / PHP 1,500 / 1,500 pesos. Plain numbers ("14,800 km") are left alone.
PRICE = re.compile(r"(?:₱|\bPHP\s?|\bP)\s?(\d[\d,]*)|(\d[\d,]*)\s?(?:pesos|php)\b", re.IGNORECASE)

DEMO_REPLY = "Hi! Thanks for your interest 😊 I can't go that low, but I can do ₱1,700 for you. Meet-up at a mall is fine!"


def prices_in(text: str) -> list[int]:
    amounts = []
    for match in PRICE.finditer(text):
        digits = (match.group(1) or match.group(2)).replace(",", "")
        if digits:
            amounts.append(int(digits))
    return amounts


def draft_reply(draft: ListingDraft, message: str, lowest: int) -> str:
    """Draft a reply to the buyer. Raises StepError if no reply respects the lowest price."""
    if DEMO_MODE:
        return DEMO_REPLY

    asking = f"₱{draft.asking_price:,}" if draft.asking_price else "not set"
    language = LANGUAGES.get(draft.language, LANGUAGES["English"])
    base = dict(details=draft.describe(), asking=asking, lowest=lowest, message=message.strip(), language=language)
    prompt = PROMPT.format(**base, extra="")
    key = image_hash(prompt.encode())
    cached = cache.load(STEP, key)
    if cached is not None:
        return cached["reply"]

    for extra in ["", f"IMPORTANT: your last draft mentioned a price below ₱{lowest:,}. Don't."]:
        response = create_response("Muse Spark", model=MODEL, input=PROMPT.format(**base, extra=extra))
        try:
            reply = str(parse_json(response.output_text or "")["reply"]).strip()
        except (ValueError, KeyError) as e:
            raise StepError(f"Muse Spark's reply didn't make sense ({e}). Try again.") from e
        # Double-check the model: a reply that undercuts the seller would cost them real money.
        if reply and all(amount >= lowest for amount in prices_in(reply)):
            cache.save(STEP, key, {"reply": reply})
            return reply
    raise StepError("Couldn't write a reply that respects your lowest price. Try again or edit it yourself.")
