"""The model's JSON is validated into dataclasses: these are the rules that keep bad answers out."""

import pytest

from listly.models import UNKNOWN, Comparable, ItemInfo, ListingDraft, PlatformListing, PriceEstimate, SellerSettings


def test_item_info_turns_empty_or_null_values_into_unknown():
    info = ItemInfo.from_dict({"item": "bag", "brand": "null", "model": "", "color": None, "condition": "brand new"})
    assert (info.brand, info.model, info.color) == (UNKNOWN, UNKNOWN, UNKNOWN)
    assert info.condition == UNKNOWN  # not one of the allowed conditions


def test_item_info_lowers_confidence_when_brand_or_model_is_unknown():
    info = ItemInfo.from_dict({"item": "shoes", "brand": "Nike", "confidence": "high"})
    assert info.confidence == "medium"


def test_item_info_needs_an_item():
    with pytest.raises(ValueError):
        ItemInfo.from_dict({"brand": "Nike"})


def test_price_estimate_reads_pesos_and_fixes_swapped_range():
    price = PriceEstimate.from_dict({"price_low": "₱2,200", "price_high": 1500})
    assert (price.price_low, price.price_high) == (1500, 2200)


def test_price_estimate_keeps_listing_and_lowest_price_sensible():
    price = PriceEstimate.from_dict({"price_low": 80000, "price_high": 100000, "listing_price": 120000, "suggested_lowest": 130000})
    assert price.price_low <= price.listing_price <= price.price_high
    assert price.suggested_lowest <= price.listing_price


def test_price_estimate_needs_a_range():
    with pytest.raises(ValueError):
        PriceEstimate.from_dict({"summary": "no idea"})


@pytest.mark.parametrize("url", ["javascript:alert(1)", "ftp://x", "", "not a link"])
def test_comparable_only_accepts_web_links(url):
    assert Comparable.from_dict({"title": "x", "url": url}) is None


def test_platform_listing_strips_hash_from_tags():
    listing = PlatformListing.from_dict({"title": "T", "description": "D", "tags": ["#nike", "shoes"]})
    assert listing.tags == ["nike", "shoes"]


def test_listing_draft_survives_saving_and_loading():
    draft = ListingDraft(
        photo_id="abc",
        info=ItemInfo.from_dict({"item": "phone", "flaws": ["scratch"]}),
        answers={"Openline?": "Yes"},
        platforms=["facebook"],
        price=PriceEstimate.from_dict({"price_low": 100, "price_high": 200}),
        asking_price=150,
        lowest_price=120,
        listings={"facebook": PlatformListing("Title", "Description", ["tag"])},
        status="listed",
    )
    assert ListingDraft.from_dict(draft.to_dict()) == draft


def test_describe_leaves_out_unknowns_so_the_model_never_sees_the_word():
    draft = ListingDraft("abc", ItemInfo.from_dict({"item": "phone", "brand": "unknown"}))
    assert "unknown" not in draft.describe().lower()


def test_empty_seller_settings_tell_the_model_to_ask():
    settings = SellerSettings()
    assert settings.is_empty()
    assert "Meet-up spots: not set" in settings.describe()
