"""Listly - Streamlit UI only. All model/image/cache logic lives in the listly/ package.

Pages: home (Sell something new + My listings), new (4 steps), view (one saved listing).
Streamlit reruns this whole script on every click, so "where we are" lives in st.session_state.
The look lives in listly/ui (theme.py for styling, components.py for reusable pieces).
"""

import copy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from html import escape
from pathlib import Path

import streamlit as st
from PIL import UnidentifiedImageError

from listly import storage
from listly.api import StepError
from listly.buyer import draft_reply
from listly.clean_photo import make_clean_photo
from listly.config import DEMO_MODE, has_api_key
from listly.cutout import cut_out
from listly.identify import identify_item
from listly.images import image_hash, shrink_image
from listly.models import CONDITIONS, STATUSES, UNKNOWN, ListingDraft, PlatformListing, PriceEstimate
from listly.platforms import PLATFORMS
from listly.pricing import suggest_price
from listly.sample import SAMPLE_PREFIX, make_samples
from listly.ui.components import (
    empty_state,
    html,
    image_src,
    listing_card,
    peso,
    platform_chips,
    section_header,
    step_bar,
    title_of,
    top_bar,
)
from listly.ui.theme import apply_theme
from listly.writer import LANGUAGES, check, revise_listing, write_listing

st.set_page_config(page_title="Listly", page_icon=str(Path(__file__).parent / "listly-icon.svg"))
apply_theme()
state = st.session_state
state.setdefault("page", "home")
if "toast" in state:
    st.toast(state.pop("toast"))  # set before a rerun, shown after it

STEPS = ["Photo", "Details", "Photo & price", "Listings"]
SOURCES = ["Upload photo", "Take photo"]


# --- small helpers -------------------------------------------------------------------------------


def go(page: str, **values) -> None:
    """Switch page (and set any extra state, e.g. toast="Saved"), then redraw."""
    state.page = page
    for name, value in values.items():
        state[name] = value
    st.rerun()


def as_input(value: str) -> str:
    # Show an empty box (with an "Unknown" placeholder) so the seller sees what's missing.
    return "" if value == UNKNOWN else value


def from_input(text: str) -> str:
    return text.strip() or UNKNOWN


def tags_text(listing: PlatformListing, hashtags: bool) -> str:
    if hashtags:
        return " ".join("#" + tag.replace(" ", "") for tag in listing.tags)
    return ", ".join(listing.tags)


def copy_box(label: str, text: str) -> None:
    # st.code has a built-in copy button, which is the simplest reliable "Copy" in Streamlit.
    st.caption(label)
    st.code(text, language=None, wrap_lines=True)


def item_row(image_bytes: bytes, title: str, chips: list[tuple[str, str]]) -> None:
    """Thumbnail + name + small chips. chips = [(text, "good" | "warn" | "")]."""
    chip_html = "".join(f'<span class="chip {kind}">{escape(text)}</span>' for text, kind in chips)
    html(
        f'<div class="item-row"><img src="{image_src(image_bytes)}" alt="">'
        f'<div><div class="title">{escape(title)}</div><div class="chips">{chip_html}</div></div></div>'
    )


def show_price(price: PriceEstimate) -> None:
    chips = [f"{price.confidence.capitalize()} confidence", f"{len(price.comparables)} sources checked"]
    if price.new_price:
        chips.insert(0, f"Brand new ≈ ₱{price.new_price:,}")
    chip_html = "".join(f'<span class="chip">{escape(c)}</span>' for c in chips)
    summary = f'<p class="summary">{escape(price.summary)}</p>' if price.summary else ""
    html(
        f'<div class="price-card"><div class="label">Suggested price</div>'
        f'<div class="range">₱{price.price_low:,} – ₱{price.price_high:,}</div>'
        f'<div class="chips">{chip_html}</div>{summary}</div>'
    )
    if price.comparables:
        with st.expander(f"See the {len(price.comparables)} listings this is based on"):
            for comp in price.comparables:
                # Brackets in a web page title would break the markdown link, so drop them.
                title = comp.title.replace("[", "").replace("]", "")
                url = comp.url.replace(")", "%29")
                st.markdown(f"- [{title}]({url})" + (f" — **₱{comp.price:,}**" if comp.price else ""))
    else:
        st.warning("No source links could be checked, so treat this range as a rough guess.")


def listing_tabs(draft: ListingDraft, on_save=None) -> None:
    """One tab per platform: copy boxes, rewrite-by-request, an editor and an Open-site button."""
    keys = [k for k in draft.platforms if k in PLATFORMS]
    for key, tab in zip(keys, st.tabs([PLATFORMS[k].name for k in keys])):
        platform = PLATFORMS[key]
        with tab:
            listing = draft.listings.get(key)
            if listing is None:
                st.error(state.get("writer_errors", {}).get(key, "This listing isn't written yet."))
                if st.button("Try again", key=f"retry-{key}"):
                    state.writer_tried = False
                    st.rerun()
                continue

            for warning in listing.warnings:
                st.warning(warning)
            copy_box(f"Title · {len(listing.title)}/{platform.max_title} characters", listing.title)
            copy_box("Description", listing.description)
            copy_box("Tags", tags_text(listing, platform.hashtags))
            if draft.asking_price:
                copy_box("Price", str(draft.asking_price))
            st.caption("Tap a box, then its copy icon, and paste it into the site.")

            with st.expander("Copy everything at once"):
                everything = f"{listing.title}\n\n{listing.description}\n\n{tags_text(listing, platform.hashtags)}"
                st.code(everything, language=None, wrap_lines=True)

            with st.form(f"ask-{key}", border=False, clear_on_submit=True):
                request = st.text_input(
                    "Ask Listly to change it",
                    placeholder="e.g. make it shorter · add that it comes with the box",
                )
                if st.form_submit_button("Rewrite", width="stretch") and request.strip():
                    with st.spinner("Rewriting your listing…"):
                        try:
                            draft.listings[key] = revise_listing(draft, platform, listing, request)
                            if on_save:
                                on_save(draft)
                            st.rerun()
                        except StepError as e:
                            st.error(str(e))

            with st.expander("Edit it yourself"):
                with st.form(f"edit-{key}", border=False):
                    title = st.text_input("Title", listing.title)
                    description = st.text_area("Description", listing.description, height=220)
                    tags = st.text_input("Tags (comma-separated)", ", ".join(listing.tags))
                    if st.form_submit_button("Save changes", width="stretch"):
                        edited = PlatformListing(
                            title=title.strip(),
                            description=description.strip(),
                            tags=[t.strip().lstrip("#") for t in tags.split(",") if t.strip()],
                        )
                        # Re-check the seller's edit too, so they see if it breaks a platform rule.
                        draft.listings[key] = replace(edited, warnings=check(edited, platform, draft))
                        if on_save:
                            on_save(draft)
                        st.rerun()

            # Listly never posts: this just opens the site's own create-listing page in a new tab.
            st.link_button(f"Open {platform.name} ↗", platform.create_url, width="stretch")


# --- home ----------------------------------------------------------------------------------------


def begin_new(source: str) -> None:
    """Start a fresh listing at the Photo step."""
    go(
        "new",
        step=1,
        source=source,
        image=None,
        draft=None,
        clean=None,
        photo_notes=[],
        photo_tried=False,
        price_error=None,
        price_tried=False,
        writer_errors={},
        writer_tried=False,
    )


def add_samples() -> None:
    for draft, photo in make_samples():
        storage.save_listing(draft, photo)
    go("home", toast="Added 3 sample listings")


def sell_card() -> None:
    with st.container(key="card-sell"):
        html(
            '<div class="sell-title">Sell something new</div>'
            '<div class="sell-sub">Take one photo. Listly identifies the item, cleans up the photo, '
            "finds a fair price and writes your listings.</div>"
        )
        if not (DEMO_MODE or has_api_key()):
            # Someone who downloaded the repo without a key should still be able to see the app working.
            st.warning(
                "No API key found. Copy .env.example to .env and add your own META_API_KEY. "
                "No key? Set LISTLY_DEMO=1 in .env, or add the sample listings below."
            )
            return
        with st.container(key="pair_sell"):
            upload, take = st.columns(2)
            if upload.button("Upload photo", type="primary", icon=":material/upload:", width="stretch"):
                begin_new("Upload photo")
            if take.button("Take photo", icon=":material/photo_camera:", width="stretch"):
                begin_new("Take photo")


def my_listings() -> None:
    listings = storage.list_listings()
    section_header("My listings", len(listings))
    if not listings:
        empty_state("No listings yet", "Snap your first item and Listly does the rest.")
        with st.container(key="pair_empty"):
            first, samples = st.columns(2)
            if first.button("Snap your first item", type="primary", width="stretch"):
                begin_new("Take photo")
            if samples.button("Add sample listings", width="stretch"):
                add_samples()
        return

    query = st.text_input(
        "Search your listings",
        placeholder="Search by name or brand",
        icon=":material/search:",
        label_visibility="collapsed",
    )
    counts = {status: sum(d.status == status for d in listings) for status in STATUSES}
    choice = st.segmented_control(
        "Filter by status",
        ["all"] + STATUSES,
        default="all",
        format_func=lambda s: f"All {len(listings)}" if s == "all" else f"{s.capitalize()} {counts[s]}",
        label_visibility="collapsed",
    ) or "all"

    words = query.lower().split()
    shown = [
        d for d in listings
        if (choice == "all" or d.status == choice)
        and all(w in f"{title_of(d)} {d.info.item} {d.info.brand}".lower() for w in words)
    ]
    if not shown:
        st.caption("No listings match.")
    with st.container(key="grid"):
        for draft in shown:
            image = storage.load_photo(draft.photo_id, "clean") or storage.load_photo(draft.photo_id, "photo")
            if listing_card(draft, image):
                go("view", view_id=draft.photo_id)

    if not any(d.photo_id.startswith(SAMPLE_PREFIX) for d in listings):
        if st.button("Add sample listings", type="tertiary"):
            add_samples()


def home_page() -> None:
    top_bar(DEMO_MODE)
    sell_card()
    my_listings()
    html('<div class="footer">Listly never posts for you · Your listings stay on this computer</div>')


# --- new listing: 4 steps ------------------------------------------------------------------------


def nav_buttons(back_step: int | None, forward_label: str, disabled: bool = False) -> bool:
    """Back + forward side by side. back_step None = back to home. Returns True when forward is pressed."""
    with st.container(key="pair_nav"):
        back, forward = st.columns(2)
        if back.button("← Back" if back_step else "Cancel", width="stretch"):
            if back_step:
                go("new", step=back_step)
            go("home")
        return forward.button(forward_label, type="primary", width="stretch", disabled=disabled)


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
            "new",
            step=2,
            image=image_bytes,
            raw_info=info,  # Muse Spark's own answer, kept for its confidence score
            # Copy so the seller's edits never change the model's original answer.
            draft=ListingDraft(
                photo_id=image_hash(image_bytes), info=copy.deepcopy(info), platforms=[names[n] for n in chosen]
            ),
        )


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
        go("new", step=3, price_tried=False, price_error=None, writer_tried=False)
    if st.button("← Back to photo", type="tertiary"):
        go("new", step=1)


def details_form(draft: ListingDraft, submit_label: str) -> bool:
    """The editable item details. Updates draft and returns True when the seller saves valid details.

    Used in the new-listing flow and on a saved listing's Details tab.
    """
    # A form only reruns the app when the button is pressed, not on every keystroke.
    with st.container(key="card-details"), st.form(f"details-{draft.photo_id}", border=False):
        item = st.text_input("Item", draft.info.item)
        col1, col2 = st.columns(2)
        brand = col1.text_input("Brand", as_input(draft.info.brand), placeholder="Unknown")
        model = col2.text_input("Model", as_input(draft.info.model), placeholder="Unknown")
        category = col1.text_input("Category", as_input(draft.info.category), placeholder="Unknown")
        color = col2.text_input("Color", as_input(draft.info.color), placeholder="Unknown")
        condition_options = [UNKNOWN] + CONDITIONS
        condition = st.selectbox(
            "Condition",
            condition_options,
            index=condition_options.index(draft.info.condition),
            format_func=str.capitalize,
        )
        flaws_text = st.text_area("Flaws (one per line)", "\n".join(draft.info.flaws), placeholder="No flaws")
        features_text = st.text_area(
            "Highlights (one per line)",
            "\n".join(draft.info.features),
            placeholder="e.g. original box included",
            help="Selling points the listing should mention.",
        )

        answers = {}
        if draft.info.questions_for_seller:
            st.markdown("**A few questions the photo can't answer**")
            for question in draft.info.questions_for_seller:
                answers[question] = st.text_input(question, draft.answers.get(question, ""))

        saved = st.form_submit_button(submit_label, type="primary", width="stretch")

    if not saved:
        return False
    if not item.strip():
        st.error("Please say what the item is.")
        return False
    draft.info = replace(
        draft.info,
        item=item.strip(),
        brand=from_input(brand),
        model=from_input(model),
        category=from_input(category),
        color=from_input(color),
        condition=condition,
        flaws=[line.strip() for line in flaws_text.splitlines() if line.strip()],
        features=[line.strip() for line in features_text.splitlines() if line.strip()],
    )
    # Skip blank answers so later steps don't treat "" as something the seller said.
    draft.answers = {q: a.strip() for q, a in answers.items() if a.strip()}
    return True


def make_photos(image: bytes, info) -> tuple[bytes | None, list[str]]:
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


def photo_pair(original: bytes | None, clean: bytes | None, retry: bool = False) -> None:
    with st.container(key="pair_photos"):
        left, right = st.columns(2)
        if original:
            left.image(original, caption="Original")
            left.download_button("Download", original, "listly-original.jpg", "image/jpeg", width="stretch", key="dl-orig")
        if clean:
            right.image(clean, caption="Clean photo")
            right.download_button("Download", clean, "listly-clean.jpg", "image/jpeg", width="stretch", key="dl-clean")
        elif retry and right.button("Try the clean photo again", width="stretch"):
            state.photo_tried = False
            st.rerun()


def photo_price_step(draft: ListingDraft) -> None:
    run_photo_and_price(draft)

    st.subheader("Photo")
    for note in state.photo_notes:
        st.info(note)
    photo_pair(state.image, state.clean, retry=True)

    st.subheader("Price")
    if state.price_error:
        st.error(state.price_error)
        if st.button("Search again"):
            state.price_tried = False
            st.rerun()
    if draft.price:
        show_price(draft.price)

    suggested = round((draft.price.price_low + draft.price.price_high) / 2, -2) if draft.price else 0
    asking = st.number_input("Your listing price (₱)", min_value=0, value=int(draft.asking_price or suggested), step=100)

    if nav_buttons(2, "Next  →"):
        if draft.asking_price != (asking or None):
            draft.listings = {}  # the texts mention the price, so a new price means new texts
        draft.asking_price = int(asking) or None
        go("new", step=4, writer_tried=False)


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
        go("view", view_id=draft.photo_id, toast="Listing saved")


def new_page() -> None:
    if st.button("← My listings", type="tertiary"):
        go("home")
    step_bar(STEPS, state.step)
    if state.step == 1:
        photo_step()
    else:
        [details_step, photo_price_step, listings_step][state.step - 2](state.draft)


# --- one saved listing ---------------------------------------------------------------------------


def buyer_helper(draft: ListingDraft) -> None:
    with st.container(key="card-buyer"):
        st.caption("Paste what the buyer wrote. Listly drafts a polite reply and never goes below your lowest price.")
        with st.form("buyer", border=False):
            message = st.text_area("Buyer's message", placeholder="Hi! Last price? Can you do ₱1,200?")
            default_lowest = int(round(draft.asking_price * 0.9, -2)) if draft.asking_price else 0
            lowest = st.number_input(
                "Your lowest price (₱) — never shown to the buyer", min_value=0, value=default_lowest, step=100
            )
            sent = st.form_submit_button("Draft a reply", type="primary", width="stretch")
        replies = state.setdefault("replies", {})
        if sent:
            if not message.strip() or not lowest:
                st.error("Paste the buyer's message and set your lowest price.")
            else:
                with st.spinner("Writing a reply…"):
                    try:
                        replies[draft.photo_id] = draft_reply(draft, message, int(lowest))
                    except StepError as e:
                        st.error(str(e))
        if draft.photo_id in replies:
            copy_box("Suggested reply (check it before sending)", replies[draft.photo_id])


@st.dialog("Delete this listing?")
def confirm_delete(draft: ListingDraft) -> None:
    st.write(f"**{title_of(draft)}** and its photos will be removed from this computer. This can't be undone.")
    with st.container(key="pair_delete"):
        cancel, delete = st.columns(2)
        if cancel.button("Cancel", width="stretch"):
            st.rerun()
        if delete.button("Delete", type="primary", width="stretch"):
            storage.delete_listing(draft.photo_id)
            go("home", toast="Listing deleted")


def hero_photo(draft: ListingDraft) -> None:
    """One big photo (clean if there is one) with a switch to the original, plus a Download button."""
    original = storage.load_photo(draft.photo_id, "photo")
    clean = storage.load_photo(draft.photo_id, "clean")
    choice = "Clean photo" if clean else "Original"
    if clean and original:
        choice = st.segmented_control(
            "Photo", ["Clean photo", "Original"], default="Clean photo",
            key=f"photo-{draft.photo_id}", label_visibility="collapsed",
        ) or "Clean photo"
    shown = clean if (choice == "Clean photo" and clean) else original
    if shown:
        with st.container(key="hero_photo"):
            st.image(shown)
        name = "listly-clean.jpg" if shown is clean else "listly-original.jpg"
        st.download_button(f"Download {choice.lower()}", shown, name, "image/jpeg", icon=":material/download:")


def view_page() -> None:
    draft = storage.load_listing(state.get("view_id", ""))
    if st.button("← My listings", type="tertiary"):
        go("home")
    if draft is None:
        st.error("This listing couldn't be opened.")
        return

    hero_photo(draft)
    html(
        f'<div class="page-head"><h2>{escape(title_of(draft))}</h2>'
        f'<div class="big-price">{escape(peso(draft.asking_price))}</div>'
        f'<div class="chips">{platform_chips(draft.platforms)}'
        f'<span class="chip">Saved {escape(draft.created[:10])}</span></div></div>'
    )

    # Listly never posts and can't see the seller's accounts, so the seller sets the status themselves.
    status = st.segmented_control(
        "Status",
        STATUSES,
        default=draft.status,
        format_func=str.capitalize,
        key=f"status-{draft.photo_id}",
        help="Draft: not posted yet · Listed: you posted it · Sold: it's gone. Only you see this.",
    )
    if status and status != draft.status:
        storage.update_status(draft.photo_id, status)
        go("view", toast=f"Marked as {status.capitalize()}")

    details, listings, price, replies = st.tabs(["Details", "Listings", "Price", "Buyer replies"])
    with details:
        if details_form(draft, "Save details"):
            storage.save_listing(draft)
            go("view", toast="Details saved")
        st.caption(
            "Saving details doesn't change your listing texts. To update them, "
            'use "Ask Listly to change it" in the Listings tab.'
        )
    with listings:
        listing_tabs(draft, on_save=storage.save_listing)
    with price:
        with st.form(f"price-{draft.photo_id}", border=False):
            asking = st.number_input("Your listing price (₱)", min_value=0, value=int(draft.asking_price or 0), step=100)
            if st.form_submit_button("Save price", width="stretch"):
                draft.asking_price = int(asking) or None
                storage.save_listing(draft)
                go("view", toast="Price saved")
        if draft.price:
            show_price(draft.price)
        else:
            st.caption("No price research for this listing.")
    with replies:
        buyer_helper(draft)

    st.divider()
    if st.button("Delete listing", icon=":material/delete:", type="tertiary"):
        confirm_delete(draft)


# --- which page to show --------------------------------------------------------------------------

if state.page == "new" and (state.get("step", 1) > 1 and not state.get("draft")):
    state.page = "home"  # e.g. the browser tab was reloaded mid-listing
{"home": home_page, "new": new_page, "view": view_page}[state.page]()
