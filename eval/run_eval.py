"""Score Listly on test items with known answers: identification, condition, flaws and price range.

Put photos in eval/photos/ and one row per photo in eval/items.csv, then run from the repo root:
    python eval/run_eval.py            # shows how many API calls it would make, then stops
    python eval/run_eval.py --yes      # actually runs (results are cached, so re-runs are free)
    python eval/run_eval.py --yes --no-price   # identification only (cheaper)
"""

import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so "listly" imports from the repo root

from listly import cache  # noqa: E402
from listly.api import StepError  # noqa: E402
from listly.identify import STEP as IDENTIFY_STEP, cache_key, identify_item  # noqa: E402
from listly.images import image_hash, shrink_image  # noqa: E402
from listly.models import CONDITIONS, UNKNOWN, ListingDraft  # noqa: E402
from listly.pricing import suggest_price  # noqa: E402

HERE = Path(__file__).resolve().parent
PHOTOS = HERE / "photos"


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", text.lower()))


def item_match(expected: str, got: str) -> bool:
    # Lenient on purpose: "running shoes" vs "Nike running shoe" should count as right.
    return bool(words(expected) & words(got)) or expected.lower() in got.lower()


def brand_result(expected: str, got: str) -> str:
    if got == UNKNOWN:
        return "unknown"  # the model said it didn't know: not wrong, just unhelpful
    return "right" if expected.lower() in got.lower() or got.lower() in expected.lower() else "wrong"


def condition_steps(expected: str, got: str) -> int | None:
    """How many steps apart on the new..poor scale (0 = exact). None if either is unknown."""
    if expected not in CONDITIONS or got not in CONDITIONS:
        return None
    return abs(CONDITIONS.index(expected) - CONDITIONS.index(got))


def flaw_recall(expected: list[str], got: list[str]) -> float | None:
    if not expected:
        return None
    found = words(" ".join(got))
    return sum(1 for flaw in expected if words(flaw) & found) / len(expected)


def main() -> None:
    run, with_price = "--yes" in sys.argv, "--no-price" not in sys.argv
    rows = list(csv.DictReader(open(HERE / "items.csv", encoding="utf-8")))
    items = [(row, PHOTOS / row["photo"]) for row in rows]
    missing = [row["photo"] for row, path in items if not path.exists()]
    items = [(row, path) for row, path in items if path.exists()]
    if missing:
        print(f"Skipping {len(missing)} rows with no photo in eval/photos/: {', '.join(missing)}")
    if not items:
        print("No photos to evaluate. Add photos to eval/photos/ and rows to eval/items.csv.")
        return

    images = [shrink_image(path.read_bytes()) for _, path in items]
    new_identify = sum(1 for img in images if cache.load(IDENTIFY_STEP, cache_key(img)) is None)
    print(f"{len(items)} items: {new_identify} new identification calls" + (f", up to {len(items)} price searches" if with_price else ""))
    if not run:
        print("Nothing was sent. Re-run with --yes to make these calls (cached results cost nothing).")
        return

    results = []
    for (row, path), img in zip(items, images):
        result = {"photo": row["photo"]}
        try:
            info = identify_item(img)
        except StepError as e:
            print(f"{row['photo']}: identification failed ({e})")
            continue
        result.update(
            item_ok=item_match(row["item"], info.item),
            brand=brand_result(row["brand"], info.brand),
            condition_steps=condition_steps(row["condition"].lower(), info.condition),
            flaw_recall=flaw_recall([f for f in row["flaws"].split(";") if f.strip()], info.flaws),
            confidence=info.confidence,
        )
        if with_price and row.get("price_low") and row.get("price_high"):
            low, high = int(row["price_low"]), int(row["price_high"])
            try:
                price = suggest_price(ListingDraft(photo_id=image_hash(img), info=info))
                # A hit if the two ranges overlap at all; a seller would see a sensible starting point.
                result["price_hit"] = price.price_low <= high and price.price_high >= low
                result["price_got"] = f"{price.price_low}-{price.price_high}"
            except StepError as e:
                print(f"{row['photo']}: price failed ({e})")
        results.append(result)
        print(f"{row['photo']}: item {'✓' if result['item_ok'] else '✗'}, brand {result['brand']}, "
              f"condition off by {result['condition_steps']}, flaw recall {result['flaw_recall']}, "
              f"price {result.get('price_got', '-')} {'✓' if result.get('price_hit') else ''}")

    def share(values) -> str:
        values = [v for v in values if v is not None]
        return f"{sum(values) / len(values):.0%} (n={len(values)})" if values else "n/a"

    print("\nSummary")
    print("  Item identified:      ", share([r["item_ok"] for r in results]))
    print("  Brand right:          ", share([r["brand"] == "right" for r in results]))
    print("  Brand wrong (guessed):", share([r["brand"] == "wrong" for r in results]))
    print("  Condition exact:      ", share([r["condition_steps"] == 0 if r["condition_steps"] is not None else None for r in results]))
    print("  Flaw recall:          ", share([r["flaw_recall"] for r in results]))
    print("  Price range overlaps: ", share([r.get("price_hit") for r in results]))

    with open(HERE / "results.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=sorted({k for r in results for k in r}))
        writer.writeheader()
        writer.writerows(results)
    print("\nPer-item results saved to eval/results.csv")


if __name__ == "__main__":
    main()
