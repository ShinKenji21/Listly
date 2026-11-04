"""Saved listings ("My listings"), kept on the seller's own computer.

    data/listings/<id>.json      the listing (details, price, texts, status)
    data/photos/<id>-photo.jpg   the original photo (shrunk)
    data/photos/<id>-clean.jpg   the clean photo, if one was made
    data/settings.json           the seller's meet-up, shipping and payment info

Nothing is uploaded anywhere, and data/ is in .gitignore.
"""

import json
import shutil
from pathlib import Path

from listly.models import STATUSES, ListingDraft, SellerSettings

DATA_DIR = Path("data")
OLD_DIR = Path("listings")  # where earlier versions of Listly saved listings


def _listing_path(listing_id: str) -> Path:
    return DATA_DIR / "listings" / f"{listing_id}.json"


def _photo_path(listing_id: str, kind: str) -> Path:
    return DATA_DIR / "photos" / f"{listing_id}-{kind}.jpg"


def save_listing(draft: ListingDraft, photo: bytes | None = None, clean: bytes | None = None) -> None:
    """Save the listing. Photos are only written when given, so later edits keep the saved ones."""
    path = _listing_path(draft.photo_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(draft.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    for kind, data in [("photo", photo), ("clean", clean)]:
        if data:
            _photo_path(draft.photo_id, kind).parent.mkdir(parents=True, exist_ok=True)
            _photo_path(draft.photo_id, kind).write_bytes(data)


def load_listing(listing_id: str) -> ListingDraft | None:
    try:
        return ListingDraft.from_dict(json.loads(_listing_path(listing_id).read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError):
        return None  # missing or hand-edited file: skip it rather than crash the home screen


def list_listings() -> list[ListingDraft]:
    """All saved listings, newest first."""
    _move_old_listings()
    folder = DATA_DIR / "listings"
    if not folder.exists():
        return []
    listings = [load_listing(path.stem) for path in folder.glob("*.json")]
    return sorted((d for d in listings if d), key=lambda d: d.created, reverse=True)


def update_status(listing_id: str, status: str) -> None:
    draft = load_listing(listing_id)
    if draft and status in STATUSES:
        draft.status = status
        save_listing(draft)


def delete_listing(listing_id: str) -> None:
    for path in [_listing_path(listing_id), _photo_path(listing_id, "photo"), _photo_path(listing_id, "clean")]:
        path.unlink(missing_ok=True)


def load_photo(listing_id: str, kind: str) -> bytes | None:
    """kind is "photo" (the original, shrunk) or "clean"."""
    path = _photo_path(listing_id, kind)
    return path.read_bytes() if path.exists() else None


def load_settings() -> SellerSettings:
    try:
        return SellerSettings.from_dict(json.loads((DATA_DIR / "settings.json").read_text(encoding="utf-8")))
    except (OSError, ValueError, AttributeError):
        return SellerSettings()  # not saved yet (or unreadable): start empty


def save_settings(settings: SellerSettings) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "settings.json").write_text(json.dumps(settings.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")


def _move_old_listings() -> None:
    """Earlier versions saved listings/<id>/listing.json; move them into data/ so nothing is lost."""
    if not OLD_DIR.is_dir():
        return
    for folder in OLD_DIR.iterdir():
        old_json = folder / "listing.json"
        if not old_json.exists() or _listing_path(folder.name).exists():
            continue
        _listing_path(folder.name).parent.mkdir(parents=True, exist_ok=True)
        _photo_path(folder.name, "photo").parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(old_json, _listing_path(folder.name))
        for kind in ["photo", "clean"]:
            if (folder / f"{kind}.jpg").exists():
                shutil.copyfile(folder / f"{kind}.jpg", _photo_path(folder.name, kind))
    shutil.rmtree(OLD_DIR, ignore_errors=True)
