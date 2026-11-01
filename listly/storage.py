"""Saved listings ("My listings"), kept on the seller's own computer.

Each listing is a folder: listings/<id>/listing.json plus photo.jpg and (if made) clean.jpg.
Nothing is uploaded anywhere, and the folder is in .gitignore.
"""

import json
import shutil
from pathlib import Path

from listly.models import ListingDraft

LISTINGS_DIR = Path("listings")


def _folder(listing_id: str) -> Path:
    return LISTINGS_DIR / listing_id


def save(draft: ListingDraft, photo: bytes | None = None, clean: bytes | None = None) -> None:
    """Save the listing. Photos are only written when given, so later edits keep the saved ones."""
    folder = _folder(draft.photo_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "listing.json").write_text(
        json.dumps(draft.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if photo:
        (folder / "photo.jpg").write_bytes(photo)
    if clean:
        (folder / "clean.jpg").write_bytes(clean)


def load(listing_id: str) -> ListingDraft | None:
    path = _folder(listing_id) / "listing.json"
    try:
        return ListingDraft.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError):
        return None  # missing or hand-edited file: skip it rather than crash the home screen


def load_all() -> list[ListingDraft]:
    """All saved listings, newest first."""
    if not LISTINGS_DIR.exists():
        return []
    listings = [load(folder.name) for folder in LISTINGS_DIR.iterdir() if folder.is_dir()]
    return sorted((d for d in listings if d), key=lambda d: d.created, reverse=True)


def photo(listing_id: str, name: str) -> bytes | None:
    """name is "photo" (the original, shrunk) or "clean"."""
    path = _folder(listing_id) / f"{name}.jpg"
    return path.read_bytes() if path.exists() else None


def delete(listing_id: str) -> None:
    shutil.rmtree(_folder(listing_id), ignore_errors=True)
