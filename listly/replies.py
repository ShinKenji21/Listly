"""Buyer reply helper: Muse Spark drafts a reply to a buyer's message, from any platform.

Three things are checked in code, not just asked for in the prompt:
- the reply never offers a price below the seller's lowest price,
- likely scams are flagged even if the model misses them,
- the model doesn't make up answers: it returns questions for the seller instead.
"""

import re
from dataclasses import dataclass, field

from listly import cache
from listly.api import StepError, create_response, parse_json
from listly.config import DEMO_MODE, MODEL
from listly.images import image_hash
from listly.models import ListingDraft, SellerSettings, _text_list
from listly.platforms import PLATFORMS
from listly.writer import LANGUAGES

STEP = "buyer_reply"

PROMPT = """You help a seller in the Philippines reply to a buyer on {platform}.

The item (confirmed by the seller):
{details}
Listed price: {asking}
The seller's lowest acceptable price (private, never reveal it or call it "the lowest"): ₱{lowest:,}

The seller's selling info:
{settings}

The buyer wrote:
\"\"\"{message}\"\"\"

Write the seller's reply:
- Tone: {tone}. Short: 1 to 4 sentences. A simple "Hi!" is fine; no slang or long greetings. {language}
- Only use facts from the item details and the seller's selling info above. Never invent anything.
- If the buyer asks something that information doesn't answer (or it says "not set"), don't guess:
  put a short question for the seller in "needs_seller_input" (e.g. "Does it come with the box?"),
  and keep the reply to what you do know.
- Price: never agree to, offer or suggest any price below ₱{lowest:,}, and don't repeat the buyer's
  lower offer. If they offer less, decline kindly and counter with a price between ₱{lowest:,} and the listed price.
- Safety: never share an address, phone number or payment account details. For meet-ups, suggest the
  seller's meet-up spots (public places).
- Scams: if the message shows signs of a common scam (fake payment screenshots, links to "courier" or
  "verification" pages, overpaying and asking for a refund, asking for codes or OTPs, moving the chat or
  payment off the platform), set "scam_warning" to one short sentence for the seller and keep the reply cautious.
  Otherwise set it to null.
{extra}
Reply with ONLY a JSON object, no other text:
{{"reply": "...", "needs_seller_input": [], "scam_warning": null}}"""

# Peso amounts like ₱1,500 / P1500 / PHP 1,500 / 1,500 pesos. Plain numbers ("14,800 km") are left alone.
PRICE = re.compile(r"(?:₱|\bPHP\s?|\bP)\s?(\d[\d,]*)|(\d[\d,]*)\s?(?:pesos|php)\b", re.IGNORECASE)

# Backup scam checks on the buyer's message, so a warning shows even if the model misses it.
SCAM_SIGNS = [
    (r"https?://|www\.|bit\.ly|tinyurl", "The message has a link. Scammers often send fake courier or 'verification' pages."),
    (r"\b(otp|verification code|one[- ]time (pin|code))\b", "The buyer is asking for a code. Never share OTPs or verification codes."),
    (r"\b(overpa\w*|sobra\w*)\b.*\b(refund|ibalik|balik)\w*", "Overpaying and asking for the difference back is a common scam."),
    (r"\b(whatsapp|telegram)\b", "The buyer wants to move off the platform, which removes its buyer and seller protection."),
    (r"\b(screenshot|receipt)\b.{0,60}\b(gcash|maya|paid|bayad|sent|transfer)\w*|\b(gcash|maya|paid|bayad|sent)\b.{0,60}\b(screenshot|receipt)\b",
     "Payment screenshots are easy to fake. Check your own GCash or bank app before handing over the item."),
    (r"\b(courier|rider|lalamove|grab)\b.{0,60}\b(link|form|fee|insurance)\b", "Fake courier links and 'fees' are a common scam."),
]


@dataclass
class Reply:
    reply: str
    needs_seller_input: list[str] = field(default_factory=list)  # questions only the seller can answer
    scam_warning: str | None = None


def prices_in(text: str) -> list[int]:
    amounts = []
    for match in PRICE.finditer(text):
        digits = (match.group(1) or match.group(2)).replace(",", "")
        if digits:
            amounts.append(int(digits))
    return amounts


def scam_check(message: str) -> str | None:
    text = message.lower()
    for pattern, warning in SCAM_SIGNS:
        if re.search(pattern, text, re.IGNORECASE | re.DOTALL):
            return warning
    return None


def draft_reply(
    draft: ListingDraft, message: str, lowest: int, settings: SellerSettings, platform_key: str, language: str
) -> Reply:
    """Draft a reply to the buyer. Raises StepError if no reply respects the lowest price."""
    backup_warning = scam_check(message)
    if DEMO_MODE:
        counter = max(lowest, int(round((draft.asking_price or lowest) * 0.95, -2)))
        return Reply(
            reply=f"Hi! Yes, it's still available. The best I can do is ₱{counter:,}. Meet-up is fine.",
            needs_seller_input=["Demo mode: Muse Spark would list anything it can't answer from your details here."],
            scam_warning=backup_warning,
        )

    platform = PLATFORMS.get(platform_key)
    base = dict(
        platform=platform.name if platform else "an online marketplace",
        tone=platform.tone if platform else "friendly and clear",
        details=draft.describe(),
        asking=f"₱{draft.asking_price:,}" if draft.asking_price else "not set",
        lowest=lowest,
        settings=settings.describe(),
        message=message.strip(),
        language=LANGUAGES.get(language, LANGUAGES["English"]),
    )
    prompt = PROMPT.format(**base, extra="")
    key = image_hash(prompt.encode())
    cached = cache.load(STEP, key)
    if cached is not None:
        return Reply(cached["reply"], cached.get("needs_seller_input", []), cached.get("scam_warning"))

    for extra in ["", f"IMPORTANT: your last draft mentioned a price below ₱{lowest:,}. Don't."]:
        response = create_response("Muse Spark", model=MODEL, input=PROMPT.format(**base, extra=extra))
        try:
            data = parse_json(response.output_text or "")
            reply = str(data["reply"]).strip()
        except (ValueError, KeyError) as e:
            raise StepError(f"Muse Spark's reply didn't make sense ({e}). Try again.") from e
        # Double-check the model: a reply that undercuts the seller would cost them real money.
        if reply and all(amount >= lowest for amount in prices_in(reply)):
            warning = data.get("scam_warning")
            result = Reply(
                reply=reply,
                needs_seller_input=_text_list(data.get("needs_seller_input")),
                scam_warning=str(warning).strip() if warning else backup_warning,
            )
            cache.save(STEP, key, result.__dict__)
            return result
    raise StepError("Couldn't write a reply that respects your lowest price. Try again or edit it yourself.")
