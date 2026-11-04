"""The listing writer: the checker's rules, the one automatic fix, and caching."""

import pytest

from listly.ai.writer import check, revise_listing, write_listing
from listly.models import ItemInfo, ListingDraft, PlatformListing
from listly.platforms import PLATFORMS

CAROUSELL = PLATFORMS["carousell"]  # 80-character titles, no hashtags

GOOD = {
    "title": "Yamaha NMAX 155 (2026), 14,800 km",
    "description": "Yamaha NMAX 155, 2026, good condition, 14,800 km. Small scratch on the left side panel. "
    "OR/CR complete. Meet-up or delivery.",
    "tags": ["nmax", "yamaha", "scooter"],
}


@pytest.fixture
def draft():
    info = ItemInfo.from_dict({"item": "scooter", "brand": "Yamaha", "condition": "good", "flaws": ["scratch on left side panel"]})
    return ListingDraft("scooter-1", info, platforms=["carousell"], asking_price=95000)


def problems(draft, **changes):
    return check(PlatformListing.from_dict({**GOOD, **changes}), CAROUSELL, draft)


def test_a_good_listing_passes(draft):
    assert problems(draft) == []


def test_title_too_long(draft):
    assert any("limit is 80" in p for p in problems(draft, title="x" * 81))


def test_no_hashtags_on_platforms_without_them(draft):
    assert any("hashtags" in p for p in problems(draft, description=GOOD["description"] + " #nmax"))


def test_every_flaw_must_be_mentioned(draft):
    no_flaw = "Yamaha NMAX 155, 2026, good condition, 14,800 km. OR/CR complete. Meet-up or delivery available anytime."
    assert any("flaw" in p for p in problems(draft, description=no_flaw))


@pytest.mark.parametrize("opener", ["Hi mga kapitbahay! ", "Hello mga pare, ", "Hi po! ", "👋 Hello! "])
def test_greeting_openers_are_caught(draft, opener):
    assert any("greeting" in p for p in problems(draft, description=opener + GOOD["description"]))


@pytest.mark.parametrize("start", ["Pareho pa ang kulay. ", "Mga kasama: box. ", "Binebenta ko ang "])
def test_normal_filipino_starts_are_not_greetings(draft, start):
    assert not any("greeting" in p for p in problems(draft, description=start + GOOD["description"]))


def test_flaw_word_check_is_skipped_for_filipino(draft):
    draft.language = "Filipino"  # flaw words get translated, so only the prompt can enforce it
    translated = "Yamaha NMAX 155, 2026, maayos ang kondisyon. May gasgas sa kaliwang panel. Kumpleto ang OR/CR. Meet-up."
    assert problems(draft, description=translated) == []


def test_broken_listing_gets_one_fix_then_is_cached(draft, fake_api):
    fake_api.reply_json({**GOOD, "title": "x" * 90}, GOOD)  # first answer breaks the rules, the fix is fine
    listing = write_listing(draft, CAROUSELL)
    assert listing.title == GOOD["title"] and listing.warnings == []
    assert len(fake_api.requests) == 2
    assert "limit is 80" in fake_api.requests[1]["input"]  # the fix request names the problem

    write_listing(draft, CAROUSELL)
    assert len(fake_api.requests) == 2  # second time comes from the cache


def test_rewrite_request_cannot_drop_a_flaw(draft, fake_api):
    current = PlatformListing.from_dict(GOOD)
    dropped_flaw = {**GOOD, "description": "Yamaha NMAX 155, 2026. Comes with 2 helmets. Meet-up or delivery available anytime."}
    fake_api.reply_json(dropped_flaw, {**GOOD, "description": GOOD["description"] + " Comes with 2 helmets."})
    revised = revise_listing(draft, CAROUSELL, current, "add that it comes with 2 helmets")
    assert "scratch" in revised.description and "helmets" in revised.description
    assert "2 helmets" in fake_api.requests[0]["input"]
