"""Listly - Streamlit UI only. All model/image/cache logic lives in the listly/ package.

Three pages: home (new photo + My listings), new (3 steps), view (one saved listing).
Streamlit reruns this whole script on every click, so "where we are" lives in st.session_state.
Styling is in style.css; small HTML pieces below use its classes.
"""

import copy
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
from listly.images import image_hash, shrink_image, thumbnail, to_data_url
from listly.models import CONDITIONS, UNKNOWN, ListingDraft, PlatformListing, PriceEstimate
from listly.platforms import PLATFORMS
from listly.pricing import suggest_price
from listly.sample import SAMPLE_ID, make_sample
from listly.writer import LANGUAGES, check, revise_listing, write_listing


def html(markup: str) -> None:
    """Show our own HTML. st.markdown (not st.html) because st.html is isolated from style.css.

    Lines are joined first: Markdown would turn indented lines into a code block.
    """
    st.markdown("".join(line.strip() for line in markup.splitlines()), unsafe_allow_html=True)


st.set_page_config(page_title="Listly", page_icon="🏷️")
st.markdown(f"<style>{(Path(__file__).parent / 'style.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
state = st.session_state
state.setdefault("page", "home")

STEPS = ["Details", "Photo & price", "Listings"]


# --- small helpers -------------------------------------------------------------------------------


def go(page: str, **values) -> None:
    """Switch page (and set any extra state), then redraw."""
    state.page = page
    for name, value in values.items():
        state[name] = value
    st.rerun()


def peso(amount: int | None) -> str:
    return f"₱{amount:,}" if amount else "No price set"


def title_of(draft: ListingDraft) -> str:
    first = next(iter(draft.listings.values()), None)
    return first.title if first else draft.info.item.capitalize()


def sites_of(draft: ListingDraft) -> str:
    return " · ".join(PLATFORMS[k].name.split()[0] for k in draft.platforms if k in PLATFORMS)


def thumb_src(image_bytes: bytes | None) -> str:
    return to_data_url(thumbnail(image_bytes)) if image_bytes else ""


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


def section_title(text: str, count: int | None = None) -> None:
    extra = f'<span class="count">{count}</span>' if count else ""
    html(f'<div class="section-title"><h3>{escape(text)}</h3>{extra}</div>')


# Everything that came from the model or the seller goes through escape(), so it can't inject HTML.


def hero() -> None:
    badge = '<span class="badge">Demo mode · no credits used</span>' if DEMO_MODE else ""
    html(
        f"""<div class="hero">
          <div class="brand"><span class="logo">🏷️</span><span class="name">Listly</span>{badge}</div>
          <p class="tagline">One photo in. A ready-to-post listing out.</p>
          <div class="how"><span>📸 Identify</span><span>✂️ Clean photo</span><span>💸 Fair price</span>
          <span>📝 3 platforms</span><span>💬 Buyer replies</span></div>
        </div>"""
    )


def step_bar(step: int) -> None:
    parts = []
    for number, name in enumerate(STEPS, start=1):
        status = "done" if number < step else "current" if number == step else ""
        dot = "✓" if number < step else str(number)
        if number > 1:
            parts.append(f'<div class="bar {"done" if number <= step else ""}"></div>')
        parts.append(f'<div class="step {status}"><span class="dot">{dot}</span><span class="label">{escape(name)}</span></div>')
    html(f'<div class="stepper">{"".join(parts)}</div>')


def item_row(image_bytes: bytes, title: str, chips: list[tuple[str, str]]) -> None:
    """Thumbnail + name + small coloured chips. chips = [(text, "good" | "warn" | "")]."""
    chip_html = "".join(f'<span class="chip {kind}">{escape(text)}</span>' for text, kind in chips)
    html(
        f'<div class="item-row"><img src="{thumb_src(image_bytes)}" alt="">'
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
    """One tab per platform: copy boxes, an editor and an Open-site button."""
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
                    "✨ Ask Listly to change it",
                    placeholder="e.g. make it shorter · add that it comes with the box",
                )
                if st.form_submit_button("Rewrite", width="stretch") and request.strip():
                    with st.spinner("Rewriting..."):
                        try:
                            draft.listings[key] = revise_listing(draft, platform, listing, request)
                            if on_save:
                                on_save(draft)
                            st.rerun()
                        except StepError as e:
                            st.error(str(e))

            with st.expander("✏️ Edit it yourself"):
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


def start_listing(image_bytes: bytes, info, platforms: list[str]) -> None:
    go(
        "new",
        step=1,
        image=image_bytes,
        raw_info=info,  # Muse Spark's own answer, kept for its confidence score
        # Copy so the seller's edits never change the model's original answer.
        draft=ListingDraft(photo_id=image_hash(image_bytes), info=copy.deepcopy(info), platforms=platforms),
        clean=None,
        photo_notes=[],
        photo_tried=False,
        price_error=None,
        price_tried=False,
        writer_errors={},
        writer_tried=False,
    )


def new_listing_form() -> None:
    source = st.segmented_control("Photo from", ["Upload", "Camera"], default="Upload") or "Upload"
    photo = (
        st.file_uploader("Upload a photo of the item", type=["jpg", "jpeg", "png", "webp"])
        if source == "Upload"
        else st.camera_input("Take a photo of the item")
    )
    names = {p.name: key for key, p in PLATFORMS.items()}
    chosen = st.pills("Sell on", list(names), selection_mode="multi", default=list(names))
    if not photo:
        return

    try:
        image_bytes = shrink_image(photo.getvalue())
    except UnidentifiedImageError:
        st.error("That file doesn't look like a photo. Try a JPG or PNG.")
        return
    st.image(image_bytes, width=220)
    if not chosen:
        st.caption("Pick at least one place to sell.")
        return

    if st.button("Identify item  →", type="primary", width="stretch"):
        with st.spinner("Looking at your item..."):
            try:
                info = identify_item(image_bytes)
            except StepError as e:
                st.error(str(e))  # the seller can press the button again to retry
                return
        if info.prohibited:
            reason = f": {info.prohibited_reason}" if info.prohibited_reason != UNKNOWN else "."
            st.error("Listly can't help list this item" + reason)
            return
        start_listing(image_bytes, info, [names[n] for n in chosen])


def listing_card(draft: ListingDraft) -> None:
    image = storage.photo(draft.photo_id, "clean") or storage.photo(draft.photo_id, "photo")
    with st.container(key=f"card-{draft.photo_id}"):
        html(
            f'<div class="lcard"><img src="{thumb_src(image)}" alt="">'
            f'<div><div class="ltitle">{escape(title_of(draft))}</div>'
            f'<div class="lmeta"><span class="lprice">{escape(peso(draft.asking_price))}</span>'
            f" · {escape(sites_of(draft))}</div>"
            f'<div class="lmeta">{escape(draft.created)}</div></div></div>'
        )
        if st.button("Open listing", key=f"open-{draft.photo_id}", width="stretch"):
            go("view", view_id=draft.photo_id)


def home_page() -> None:
    hero()
    with st.container(key="card-new"):
        st.subheader("New listing")
        if DEMO_MODE or has_api_key():
            new_listing_form()
        else:
            # Someone who downloaded the repo without a key should still be able to see the app working.
            st.warning(
                "No API key found. Copy .env.example to .env and add your own META_API_KEY.\n\n"
                "No key? Set LISTLY_DEMO=1 in .env to try it with sample results, or open the sample below."
            )

    saved = storage.load_all()
    section_title("My listings", len(saved))
    if not saved:
        html('<div class="empty">No listings yet.<br>Add a photo above to make your first one.</div>')
    for draft in saved:
        listing_card(draft)
    if all(d.photo_id != SAMPLE_ID for d in saved) and st.button("✨ Try a sample listing", width="stretch"):
        draft, photo = make_sample()
        storage.save(draft, photo)
        go("view", view_id=draft.photo_id)
    html('<div class="footer">Listly never posts for you · Your listings stay on this computer</div>')


# --- new listing: 3 steps ------------------------------------------------------------------------


def nav_buttons(back_step: int | None, forward_label: str, disabled: bool = False) -> bool:
    """Back + forward buttons side by side. Returns True when forward is pressed."""
    with st.container(key="pair_nav"):
        back, forward = st.columns(2)
        if back_step and back.button("← Back", width="stretch"):
            go("new", step=back_step)
        return forward.button(forward_label, type="primary", width="stretch", disabled=disabled)


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

    # A form only reruns the app when the button is pressed, not on every keystroke.
    with st.container(key="card-details"), st.form("details", border=False):
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

        saved = st.form_submit_button("Save and continue  →", type="primary", width="stretch")

    if saved:
        if not item.strip():
            st.error("Please say what the item is.")
            return
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
        # New details can change the price and the texts; unchanged details come from the cache for free.
        draft.price, draft.listings = None, {}
        go("new", step=2, price_tried=False, price_error=None, writer_tried=False)


def run_photo_steps(draft: ListingDraft) -> None:
    """Cut-out then clean photo. Each step can fail on its own and falls back instead of stopping."""
    state.photo_tried = True
    notes, source = [], state.image
    with st.spinner("Cutting out your item and cleaning up the photo..."):
        try:
            cut = cut_out(state.image, draft.info)
            source = cut.png
            if not cut.exact:
                notes.append("Couldn't trace the item's exact outline, so it was cropped instead.")
        except StepError as e:
            notes.append(f"Cut-out skipped: {e} Using the full photo instead.")
        try:
            state.clean = make_clean_photo(source)
        except StepError as e:
            notes.append(f"Couldn't make a clean photo: {e} Your original photo is still fine to use.")
    state.photo_notes = notes


def photo_pair(original: bytes | None, clean: bytes | None, retry: bool = False) -> None:
    with st.container(key="pair_photos"):
        left, right = st.columns(2)
        if original:
            left.image(original, caption="Original")
            left.download_button("Download", original, "listly-original.jpg", "image/jpeg", width="stretch", key="dl-orig")
        if clean:
            right.image(clean, caption="Clean photo ✨")
            right.download_button("Download", clean, "listly-clean.jpg", "image/jpeg", width="stretch", key="dl-clean")
        elif retry and right.button("Try the clean photo again", width="stretch"):
            state.photo_tried = False
            st.rerun()


def photo_price_step(draft: ListingDraft) -> None:
    st.subheader("Photo")
    if state.clean is None and not state.photo_tried:
        run_photo_steps(draft)
    for note in state.photo_notes:
        st.info(note)
    photo_pair(state.image, state.clean, retry=True)

    st.subheader("Price")
    if draft.price is None and not state.price_tried:
        state.price_tried = True
        with st.spinner("Searching the web for similar listings..."):
            try:
                draft.price = suggest_price(draft)
                state.price_error = None
            except StepError as e:
                state.price_error = str(e)
    if state.price_error:
        st.error(state.price_error)
        if st.button("Search again"):
            state.price_tried = False
            st.rerun()
    if draft.price:
        show_price(draft.price)

    suggested = round((draft.price.price_low + draft.price.price_high) / 2, -2) if draft.price else 0
    asking = st.number_input("Your asking price (₱)", min_value=0, value=int(draft.asking_price or suggested), step=100)

    if nav_buttons(1, "Continue  →"):
        if draft.asking_price != (asking or None):
            draft.listings = {}  # the texts mention the price, so a new price means new texts
        draft.asking_price = int(asking) or None
        go("new", step=3, writer_tried=False)


def listings_step(draft: ListingDraft) -> None:
    language = st.segmented_control("Language", list(LANGUAGES), default=draft.language) or draft.language
    if language != draft.language:
        draft.language, draft.listings = language, {}
        state.writer_tried = False

    missing = [k for k in draft.platforms if k not in draft.listings]
    if missing and not state.writer_tried:
        state.writer_tried, state.writer_errors = True, {}
        with st.spinner("Writing your listings..."):
            for key in missing:
                try:
                    draft.listings[key] = write_listing(draft, PLATFORMS[key])
                except StepError as e:
                    state.writer_errors[key] = str(e)

    listing_tabs(draft)

    if nav_buttons(2, "Save listing ✓", disabled=not draft.listings):
        storage.save(draft, state.image, state.clean)
        go("view", view_id=draft.photo_id, just_saved=True)


def new_page() -> None:
    if st.button("← Home", type="tertiary"):
        go("home")
    step_bar(state.step)
    [details_step, photo_price_step, listings_step][state.step - 1](state.draft)


# --- one saved listing ---------------------------------------------------------------------------


def buyer_helper(draft: ListingDraft) -> None:
    with st.container(key="card-buyer"):
        st.subheader("💬 Reply to a buyer")
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
                with st.spinner("Writing a reply..."):
                    try:
                        replies[draft.photo_id] = draft_reply(draft, message, int(lowest))
                    except StepError as e:
                        st.error(str(e))
        if draft.photo_id in replies:
            copy_box("Suggested reply (check it before sending)", replies[draft.photo_id])


def view_page() -> None:
    draft = storage.load(state.get("view_id", ""))
    if st.button("← Home", type="tertiary"):
        go("home")
    if draft is None:
        st.error("This listing couldn't be opened.")
        return
    if state.pop("just_saved", False):
        st.success("Saved to My listings.")

    chips = f'<span class="chip good">{escape(peso(draft.asking_price))}</span>'
    chips += f'<span class="chip">{escape(sites_of(draft))}</span><span class="chip">{escape(draft.created)}</span>'
    html(f'<div class="page-head"><h2>{escape(title_of(draft))}</h2><div class="chips">{chips}</div></div>')

    photo_pair(storage.photo(draft.photo_id, "photo"), storage.photo(draft.photo_id, "clean"))
    if draft.price:
        with st.expander("💸 Price research"):
            show_price(draft.price)

    section_title("Your listings")
    listing_tabs(draft, on_save=storage.save)
    buyer_helper(draft)

    with st.expander("Delete this listing"):
        if st.button("Delete for good", type="primary"):
            storage.delete(draft.photo_id)
            go("home")


# --- which page to show --------------------------------------------------------------------------

if state.page == "new" and "draft" not in state:
    state.page = "home"  # e.g. the browser tab was reloaded mid-listing
{"home": home_page, "new": new_page, "view": view_page}[state.page]()
