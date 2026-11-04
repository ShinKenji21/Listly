"""Buyer replies: the lowest-price guard, scam warnings and questions for the seller."""

import pytest

from listly.ai.api import StepError
from listly.ai.replies import draft_reply, prices_in, scam_check
from listly.models import ItemInfo, ListingDraft, SellerSettings

SETTINGS = SellerSettings(meetup_spots="Trinoma, SM North", payment="Cash, GCash")


@pytest.fixture
def draft():
    info = ItemInfo.from_dict({"item": "smartphone", "brand": "Apple", "model": "iPhone 12", "condition": "good"})
    return ListingDraft("phone-1", info, platforms=["facebook"], asking_price=15500)


def reply(fake_api, text, ask=(), scam=None):
    fake_api.reply_json({"reply": text, "needs_seller_input": list(ask), "scam_warning": scam})


@pytest.mark.parametrize("message", [
    "Sent na po bayad, here is the GCash screenshot",
    "Pls click https://lbc-verify.co to confirm shipping",
    "Can you send me the OTP I sent to your phone",
    "I overpaid by 2000 pls refund the extra",
    "Lets talk on WhatsApp instead",
    "The rider needs you to fill the courier form and pay insurance fee",
])
def test_scam_signs_are_flagged(message):
    assert scam_check(message)


@pytest.mark.parametrize("message", ["Hi available pa? Last price?", "Pwede meet sa Trinoma 6pm?", "May charger ba?"])
def test_normal_messages_are_not_flagged(message):
    assert scam_check(message) is None


def test_prices_in_finds_peso_amounts_but_not_other_numbers():
    assert prices_in("I can do P1500 or 1,700 pesos, PHP 2,000. It has 14,800 km.") == [1500, 1700, 2000]


def test_reply_uses_settings_and_returns_questions_for_the_seller(draft, fake_api):
    reply(fake_api, "Hi! Available pa po. Meet tayo sa Trinoma. ₱15,000 is my best.", ask=["Does it come with the charger?"])
    result = draft_reply(draft, "May charger? 14k?", 14500, SETTINGS, "facebook", "Taglish")
    assert result.needs_seller_input == ["Does it come with the charger?"]
    prompt = fake_api.requests[0]["input"]
    assert "Trinoma" in prompt and "Facebook Marketplace" in prompt and "Taglish" in prompt and "₱14,500" in prompt


def test_reply_below_lowest_price_is_rejected_and_redone(draft, fake_api):
    reply(fake_api, "Ok ₱13,000 deal!")
    reply(fake_api, "Sorry, ₱15,000 is my best.")
    result = draft_reply(draft, "13k na lang", 14500, SETTINGS, "facebook", "English")
    assert result.reply == "Sorry, ₱15,000 is my best."
    assert len(fake_api.requests) == 2


def test_gives_up_rather_than_undercut_the_seller(draft, fake_api):
    reply(fake_api, "Ok ₱13,000")
    reply(fake_api, "Fine, 12,000 pesos")
    with pytest.raises(StepError):
        draft_reply(draft, "12k?", 14500, SETTINGS, "facebook", "English")


def test_backup_scam_warning_when_the_model_misses_it(draft, fake_api):
    reply(fake_api, "Sure, send the screenshot!")
    result = draft_reply(draft, "Paid na, here is the GCash screenshot", 14500, SETTINGS, "facebook", "English")
    assert result.scam_warning and "screenshot" in result.scam_warning.lower()
