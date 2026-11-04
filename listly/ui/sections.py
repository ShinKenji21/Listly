"""Screen sections used by more than one page (the new-listing flow and a saved listing)."""

from dataclasses import replace
from html import escape

import streamlit as st

from listly.ai.api import StepError
from listly.ai.writer import check, revise_listing
from listly.models import CONDITIONS, UNKNOWN, ListingDraft, PlatformListing, PriceEstimate
from listly.platforms import PLATFORMS
from listly.ui.components import copy_buttons, html, image_src, peso, text_field
from listly.ui.state import state

PRIVATE_NOTE = "🔒 Only you see this. It's never put in your listings."


def as_input(value: str) -> str:
    # Show an empty box (with an "Unknown" placeholder) so the seller sees what's missing.
    return "" if value == UNKNOWN else value


def from_input(text: str) -> str:
    return text.strip() or UNKNOWN


def lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def tags_text(listing: PlatformListing, hashtags: bool) -> str:
    if hashtags:
        return " ".join("#" + tag.replace(" ", "") for tag in listing.tags)
    return ", ".join(listing.tags)


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
    reason = price.reason or price.summary
    summary = f'<p class="summary">{escape(reason)}</p>' if reason else ""
    html(
        f'<div class="price-card"><div class="label">Fair price range</div>'
        f'<div class="range">₱{price.price_low:,} – ₱{price.price_high:,}</div>'
        f'<div class="chips">{chip_html}</div>{summary}</div>'
    )
    if price.comparables:
        with st.expander(f"See the {len(price.comparables)} listings this is based on"):
            if price.summary and price.reason:
                st.caption(price.summary)
            for comp in price.comparables:
                # Brackets in a web page title would break the markdown link, so drop them.
                title = comp.title.replace("[", "").replace("]", "")
                url = comp.url.replace(")", "%29")
                st.markdown(f"- [{title}]({url})" + (f" — **₱{comp.price:,}**" if comp.price else ""))
    else:
        st.warning("No source links could be checked, so treat this range as a rough guess.")


def price_inputs(draft: ListingDraft, key: str) -> tuple[int, int]:
    """Listing price + private lowest price, side by side. Defaults come from the price research."""
    suggested = draft.price.listing_price if draft.price else 0
    lowest_hint = draft.price.suggested_lowest if draft.price else 0
    asking_default = int(draft.asking_price or suggested or 0)
    lowest_default = int(draft.lowest_price or lowest_hint or round(asking_default * 0.9, -2))
    with st.container(key=f"pair_{key}"):
        left, right = st.columns(2)
        asking = left.number_input("Listing price (₱)", min_value=0, value=asking_default, step=100, key=f"ask-{key}")
        lowest = right.number_input("Lowest you'd accept (₱)", min_value=0, value=lowest_default, step=100, key=f"low-{key}")
    html(f'<div class="private">{escape(PRIVATE_NOTE)}</div>')
    return int(asking), int(lowest)


def details_form(draft: ListingDraft, submit_label: str) -> bool:
    """The editable item details. Updates draft and returns True when the seller saves valid details."""
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
        flaws=lines(flaws_text),
        features=lines(features_text),
    )
    # Skip blank answers so later steps don't treat "" as something the seller said.
    draft.answers = {q: a.strip() for q, a in answers.items() if a.strip()}
    return True


def listing_tabs(draft: ListingDraft, on_save=None) -> None:
    """One tab per platform: the texts, real Copy buttons, Open site, and ways to change it.

    on_save(draft) is called after a change, so a saved listing is written back to disk.
    """
    keys = [k for k in draft.platforms if k in PLATFORMS]
    for key, tab in zip(keys, st.tabs([PLATFORMS[k].name for k in keys]), strict=True):
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
            tags = tags_text(listing, platform.hashtags)
            text_field("Title", listing.title, f"{len(listing.title)}/{platform.max_title} characters")
            text_field("Description", listing.description)
            text_field("Tags", tags)
            if draft.asking_price:
                text_field("Price", peso(draft.asking_price))
            everything = f"{listing.title}\n\n{listing.description}\n\n{tags}"
            copy_buttons([("Copy title", listing.title), ("Copy description", listing.description), ("Copy all", everything)])
            # Listly never posts: this just opens the site's own create-listing page in a new tab.
            st.link_button(f"Open {platform.name} ↗", platform.create_url, width="stretch")

            with st.expander("✨ Change this listing"):
                _change_listing(draft, key, listing, on_save)


def _change_listing(draft: ListingDraft, key: str, listing: PlatformListing, on_save) -> None:
    platform = PLATFORMS[key]
    with st.form(f"ask-{key}", border=False, clear_on_submit=True):
        request = st.text_input(
            "Ask Listly to change it",
            placeholder="e.g. make it shorter · add that it comes with the box",
        )
        if st.form_submit_button("Rewrite with Muse Spark", type="primary", width="stretch") and request.strip():
            with st.spinner("Rewriting your listing…"):
                try:
                    draft.listings[key] = revise_listing(draft, platform, listing, request)
                    if on_save:
                        on_save(draft)
                    st.rerun()
                except StepError as e:
                    st.error(str(e))

    st.caption("Or edit it yourself:")
    with st.form(f"edit-{key}", border=False):
        title = st.text_input("Title", listing.title)
        description = st.text_area("Description", listing.description, height=220)
        tag_text = st.text_input("Tags (comma-separated)", ", ".join(listing.tags))
        if st.form_submit_button("Save changes", width="stretch"):
            edited = PlatformListing(
                title=title.strip(),
                description=description.strip(),
                tags=[t.strip().lstrip("#") for t in tag_text.split(",") if t.strip()],
            )
            # Re-check the seller's edit too, so they see if it breaks a platform rule.
            draft.listings[key] = replace(edited, warnings=check(edited, platform, draft))
            if on_save:
                on_save(draft)
            st.rerun()
