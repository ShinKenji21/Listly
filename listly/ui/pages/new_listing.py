"""New listing, in 4 steps: Photo → Details → Photo & price → Listings → Save."""

import copy
from concurrent.futures import ThreadPoolExecutor

import streamlit as st
from PIL import UnidentifiedImageError

from listly import storage
from listly.ai.api import StepError
from listly.ai.clean_photo import make_clean_photo
from listly.ai.cutout import cut_out
from listly.ai.identify import identify_item
from listly.ai.pricing import suggest_price
from listly.ai.writer import LANGUAGES, write_listing
from listly.images import image_hash, shrink_image
from listly.models import UNKNOWN, ItemInfo, ListingDraft
from listly.platforms import PLATFORMS
from listly.ui.components import step_bar
from listly.ui.sections import details_form, item_row, listing_tabs, price_inputs, show_price
from listly.ui.state import HOME, NEW, VIEW, go, state

STEPS = ["Photo", "Details", "Photo & price", "Listings"]
SOURCES = ["Upload photo", "Take photo"]


def nav_buttons(back_step: int | None, forward_label: str, disabled: bool = False) -> bool:
    """Back + forward side by side. back_step None = back to home. Returns True when forward is pressed."""
    with st.container(key="pair_nav"):
        back, forward = st.columns(2)
        if back.button("← Back" if back_step else "Cancel", width="stretch"):
            if back_step:
                go(NEW, step=back_step)
            go(HOME)
        return forward.button(forward_label, type="primary", width="stretch", disabled=disabled)


# --- step 1: photo -------------------------------------------------------------------------------


def photo_step() -> None:
    default = state.get("source", SOURCES[0])
    source = st.segmented_control("Photo from", SOURCES, default=default, label_visibility="collapsed") or default
    photo = (
        st.file_uploader("Upload a photo of the item", type=["jpg", "jpeg", "png", "webp"])
        if source == "Upload photo"
        else st.camera_input("Take a photo of the item")
    )
    names = {p.name: key for key, p in PLATFORMS.items()}
    chosen = st.pills("Sell on", list(names), selection_mode="multi", default=list(names))

    image_bytes = None
    if photo:
        try:
            image_bytes = shrink_image(photo.getvalue())
            st.image(image_bytes, width=240)
        except UnidentifiedImageError:
            st.error("That file doesn't look like a photo. Try a JPG or PNG.")
    if image_bytes and not chosen:
        st.caption("Pick at least one place to sell.")

    if nav_buttons(None, "Next  →", disabled=not (image_bytes and chosen)):
        with st.spinner("Looking at your item…"):
            try:
                info = identify_item(image_bytes)
            except StepError as e:
                st.error(str(e))  # the seller can press Next again to retry
                return
        if info.prohibited:
            reason = f": {info.prohibited_reason}" if info.prohibited_reason != UNKNOWN else "."
            st.error("Listly can't help list this item" + reason)
            return
        go(
            NEW,
            step=2,
            image=image_bytes,
            raw_info=info,  # Muse Spark's own answer, kept for its confidence score
            # Copy so the seller's edits never change the model's original answer.
            draft=ListingDraft(
                photo_id=image_hash(image_bytes), info=copy.deepcopy(info), platforms=[names[n] for n in chosen]
            ),
        )


# --- step 2: details -----------------------------------------------------------------------------


def details_step(draft: ListingDraft) -> None:
    confidence = state.raw_info.confidence
    chips = [
        (f"{confidence.capitalize()} confidence", "good" if confidence == "high" else "warn" if confidence == "low" else ""),
        (draft.info.condition.capitalize(), ""),
    ]
    if draft.info.flaws:
        chips.append((f"{len(draft.info.flaws)} flaw{'s' if len(draft.info.flaws) > 1 else ''} found", "warn"))
    item_row(state.image, draft.info.item.capitalize(), chips)
    st.caption("Check what Muse Spark found and fix anything it got wrong. Your answers make the listing better.")

    # Shown above the form so flaws can't be missed: honest listings get fewer returns and disputes.
    if draft.info.flaws:
        st.warning("**Flaws to mention in the listing:**\n- " + "\n- ".join(draft.info.flaws))

    if details_form(draft, "Save and continue  →"):
        # New details can change the price and the texts; unchanged details come from the cache for free.
        draft.price, draft.listings = None, {}
        go(NEW, step=3, price_tried=False, price_error=None, writer_tried=False)
    if st.button("← Back to photo", type="tertiary"):
        go(NEW, step=1)


# --- step 3: photo & price -----------------------------------------------------------------------


def make_photos(image: bytes, info: ItemInfo) -> tuple[bytes | None, list[str]]:
    """Cut-out then clean photo. Each step can fail on its own and falls back instead of stopping.

    No st.* calls in here, because it runs in a background thread next to the price search.
    """
    notes, source, clean = [], image, None
    try:
        cut = cut_out(image, info)
        source = cut.png
        if not cut.exact:
            notes.append("Couldn't trace the item's exact outline, so it was cropped instead.")
    except StepError as e:
        notes.append(f"Cut-out skipped: {e} Using the full photo instead.")
    try:
        clean = make_clean_photo(source)
    except StepError as e:
        notes.append(f"Couldn't make a clean photo: {e} Your original photo is still fine to use.")
    return clean, notes


def run_photo_and_price(draft: ListingDraft) -> None:
    """The photo cleanup and the price search don't depend on each other, so run them at the same time.

    Each is several seconds of waiting for Meta's servers; side by side, the seller waits for the
    slower one instead of both added together.
    """
    need_photo = state.clean is None and not state.photo_tried
    need_price = draft.price is None and not state.price_tried
    if not (need_photo or need_price):
        return
    state.photo_tried = state.photo_tried or need_photo
    state.price_tried = state.price_tried or need_price
    message = "Cleaning up your photo and checking prices…" if need_photo and need_price else (
        "Cleaning up your photo…" if need_photo else "Checking prices of similar items…"
    )
    with st.spinner(message), ThreadPoolExecutor(max_workers=2) as pool:
        photo_job = pool.submit(make_photos, state.image, draft.info) if need_photo else None
        price_job = pool.submit(suggest_price, draft) if need_price else None
        if photo_job:
            state.clean, state.photo_notes = photo_job.result()
        if price_job:
            try:
                draft.price, state.price_error = price_job.result(), None
            except StepError as e:
                state.price_error = str(e)


def photo_pair(original: bytes | None, clean: bytes | None) -> None:
    with st.container(key="pair_photos"):
        left, right = st.columns(2)
        if original:
            left.image(original, caption="Original")
            left.download_button("Download", original, "listly-original.jpg", "image/jpeg", width="stretch", key="dl-orig")
        if clean:
            right.image(clean, caption="Clean photo")
            right.download_button("Download", clean, "listly-clean.jpg", "image/jpeg", width="stretch", key="dl-clean")
        elif right.button("Try the clean photo again", width="stretch"):
            state.photo_tried = False
            st.rerun()


def photo_price_step(draft: ListingDraft) -> None:
    run_photo_and_price(draft)

    st.subheader("Photo")
    for note in state.photo_notes:
        st.info(note)
    photo_pair(state.image, state.clean)

    st.subheader("Price")
    if state.price_error:
        st.error(state.price_error)
        if st.button("Search again"):
            state.price_tried = False
            st.rerun()
    if draft.price:
        show_price(draft.price)
    asking, lowest = price_inputs(draft, "step")

    if nav_buttons(2, "Next  →"):
        if draft.asking_price != (asking or None):
            draft.listings = {}  # the texts mention the price, so a new price means new texts
        draft.asking_price = asking or None
        draft.lowest_price = min(lowest, asking) if asking and lowest else (lowest or None)
        go(NEW, step=4, writer_tried=False)


# --- step 4: listings ----------------------------------------------------------------------------


def listings_step(draft: ListingDraft) -> None:
    language = st.segmented_control("Language", list(LANGUAGES), default=draft.language) or draft.language
    if language != draft.language:
        draft.language, draft.listings = language, {}
        state.writer_tried = False

    missing = [k for k in draft.platforms if k not in draft.listings]
    if missing and not state.writer_tried:
        state.writer_tried, state.writer_errors = True, {}
        # One call per platform, all at the same time: the seller waits for the slowest, not all three in a row.
        with st.spinner("Writing your listings…"), ThreadPoolExecutor(max_workers=len(missing)) as pool:
            jobs = {key: pool.submit(write_listing, draft, PLATFORMS[key]) for key in missing}
            for key, job in jobs.items():
                try:
                    draft.listings[key] = job.result()
                except StepError as e:
                    state.writer_errors[key] = str(e)

    listing_tabs(draft)

    if nav_buttons(3, "Save listing ✓", disabled=not draft.listings):
        storage.save_listing(draft, state.image, state.clean)
        go(VIEW, view_id=draft.photo_id, toast="Listing saved")


def render() -> None:
    if st.button("← My listings", type="tertiary"):
        go(HOME)
    step_bar(STEPS, state.step)
    if state.step == 1:
        photo_step()
    else:
        [details_step, photo_price_step, listings_step][state.step - 2](state.draft)
