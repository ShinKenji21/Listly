"""One saved listing: photo, status, and tabs for Listings, Buyer replies, Price and Details."""

from datetime import datetime
from html import escape

import streamlit as st

from listly import storage
from listly.ai.api import StepError
from listly.ai.replies import draft_reply
from listly.ai.writer import LANGUAGES
from listly.images import image_hash
from listly.models import STATUSES, ListingDraft
from listly.platforms import PLATFORMS
from listly.ui.components import copy_buttons, html, peso, platform_chips, title_of
from listly.ui.sections import PRIVATE_NOTE, details_form, listing_tabs, price_inputs, show_price
from listly.ui.state import HOME, SETTINGS, VIEW, go, state

HISTORY_SIZE = 5  # past buyer replies kept per listing


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


def status_switch(draft: ListingDraft) -> None:
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
        go(VIEW, toast=f"Marked as {status.capitalize()}")


def buyer_replies(draft: ListingDraft) -> None:
    settings = storage.load_settings()
    if settings.is_empty():
        st.info("Add your meet-up spots, shipping and payment methods so Listly can answer more buyer questions.")
        if st.button("Open selling settings", icon=":material/settings:"):
            go(SETTINGS, back_to=VIEW)

    names = {PLATFORMS[k].name: k for k in draft.platforms if k in PLATFORMS}
    with st.container(key="card-buyer"):
        with st.form(f"buyer-{draft.photo_id}", border=False):
            message = st.text_area("Paste the buyer's message", placeholder="Hi! Available pa? Last price? Pwede meet-up sa Trinoma?")
            col1, col2 = st.columns(2)
            platform_name = col1.selectbox("Where they messaged you", list(names) or ["Other"])
            language = col2.selectbox("Reply in", list(LANGUAGES), index=list(LANGUAGES).index(draft.language))
            default_lowest = int(draft.lowest_price or round((draft.asking_price or 0) * 0.9, -2))
            lowest = st.number_input("Lowest you'd accept (₱)", min_value=0, value=default_lowest, step=100)
            html(f'<div class="private">{escape(PRIVATE_NOTE)} The buyer never sees it either.</div>')
            sent = st.form_submit_button("Draft reply", type="primary", width="stretch")

        replies = state.setdefault("replies", {})
        if sent:
            if not message.strip() or not lowest:
                st.error("Paste the buyer's message and set your lowest price.")
            else:
                with st.spinner("Writing a reply…"):
                    try:
                        result = draft_reply(draft, message, int(lowest), settings, names.get(platform_name, ""), language)
                        replies[draft.photo_id] = result
                        _remember(draft, int(lowest), platform_name, message, result.reply)
                    except StepError as e:
                        st.error(str(e))

        result = replies.get(draft.photo_id)
        if result:
            if result.scam_warning:
                st.error(f"**⚠️ Possible scam.** {result.scam_warning}")
            if result.needs_seller_input:
                st.info("**Listly needs your answer to:**\n- " + "\n- ".join(result.needs_seller_input))
            edited = st.text_area(
                "Your reply (edit it before sending)",
                result.reply,
                height=130,
                key=f"reply-{draft.photo_id}-{image_hash(result.reply.encode())}",
            )
            copy_buttons([("Copy reply", edited)])

    if draft.reply_history:
        with st.expander(f"Past replies ({len(draft.reply_history)})"):
            for entry in draft.reply_history:
                st.caption(f"{entry.get('date', '')} · {entry.get('platform', '')}")
                st.text(f"Buyer: {entry.get('message', '')}")
                st.text(f"You: {entry.get('reply', '')}")
                st.divider()


def _remember(draft: ListingDraft, lowest: int, platform_name: str, message: str, reply: str) -> None:
    """Keep the lowest price and a short history of replies for this item."""
    draft.lowest_price = lowest
    entry = {"date": datetime.now().strftime("%b %d, %H:%M"), "platform": platform_name, "message": message.strip(), "reply": reply}
    draft.reply_history = ([entry] + draft.reply_history)[:HISTORY_SIZE]
    storage.save_listing(draft)


def price_tab(draft: ListingDraft) -> None:
    with st.form(f"price-{draft.photo_id}", border=False):
        asking, lowest = price_inputs(draft, f"view_{draft.photo_id}")  # per listing, so values don't carry over
        if st.form_submit_button("Save prices", width="stretch"):
            draft.asking_price = asking or None
            draft.lowest_price = lowest or None
            storage.save_listing(draft)
            go(VIEW, toast="Prices saved")
    if draft.price:
        show_price(draft.price)
    else:
        st.caption("No price research for this listing.")


@st.dialog("Delete this listing?")
def confirm_delete(draft: ListingDraft) -> None:
    st.write(f"**{title_of(draft)}** and its photos will be removed from this computer. This can't be undone.")
    with st.container(key="pair_delete"):
        cancel, delete = st.columns(2)
        if cancel.button("Cancel", width="stretch"):
            st.rerun()
        if delete.button("Delete", type="primary", width="stretch"):
            storage.delete_listing(draft.photo_id)
            go(HOME, toast="Listing deleted")


def render() -> None:
    draft = storage.load_listing(state.get("view_id", ""))
    if st.button("← My listings", type="tertiary"):
        go(HOME)
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
    status_switch(draft)

    listings, replies, price, details = st.tabs(["Listings", "Buyer replies", "Price", "Details"])
    with listings:
        listing_tabs(draft, on_save=storage.save_listing)
    with replies:
        buyer_replies(draft)
    with price:
        price_tab(draft)
    with details:
        if details_form(draft, "Save details"):
            storage.save_listing(draft)
            go(VIEW, toast="Details saved")
        st.caption(
            "Saving details doesn't change your listing texts. To update them, "
            'use "Change this listing" in the Listings tab.'
        )

    st.divider()
    if st.button("Delete listing", icon=":material/delete:", type="tertiary"):
        confirm_delete(draft)
