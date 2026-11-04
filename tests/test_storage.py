"""Saved listings and settings on disk (in a temporary folder, see conftest.py)."""

import json

from listly import storage
from listly.models import ItemInfo, ListingDraft, SellerSettings


def make(photo_id, created="2026-11-01 10:00"):
    return ListingDraft(photo_id, ItemInfo.from_dict({"item": "bag"}), created=created)


def test_save_list_update_and_delete():
    storage.save_listing(make("old", "2026-10-01 10:00"), photo=b"jpg")
    storage.save_listing(make("new", "2026-11-01 10:00"))
    assert [d.photo_id for d in storage.list_listings()] == ["new", "old"]  # newest first
    assert storage.load_photo("old", "photo") == b"jpg"

    storage.update_status("old", "sold")
    assert storage.load_listing("old").status == "sold"
    storage.update_status("old", "not-a-status")
    assert storage.load_listing("old").status == "sold"

    storage.delete_listing("old")
    assert storage.load_listing("old") is None and storage.load_photo("old", "photo") is None


def test_a_broken_file_is_skipped_not_fatal():
    storage.save_listing(make("good"))
    (storage.DATA_DIR / "listings" / "broken.json").write_text("{ not json", encoding="utf-8")
    assert [d.photo_id for d in storage.list_listings()] == ["good"]


def test_settings_round_trip():
    assert storage.load_settings().is_empty()
    storage.save_settings(SellerSettings(meetup_spots="Trinoma", payment="GCash", swaps=True))
    assert storage.load_settings() == SellerSettings(meetup_spots="Trinoma", payment="GCash", swaps=True)


def test_listings_from_the_old_folder_are_moved_over():
    old = storage.OLD_DIR / "abc"
    old.mkdir(parents=True)
    (old / "listing.json").write_text(json.dumps(make("abc").to_dict()), encoding="utf-8")
    (old / "photo.jpg").write_bytes(b"jpg")
    assert [d.photo_id for d in storage.list_listings()] == ["abc"]
    assert storage.load_photo("abc", "photo") == b"jpg"
    assert not storage.OLD_DIR.exists()
