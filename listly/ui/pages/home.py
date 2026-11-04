"""Home: "Sell something new" and the My listings grid."""

import streamlit as st

from listly import storage
from listly.config import DEMO_MODE, has_api_key
from listly.models import STATUSES
from listly.sample import SAMPLE_PREFIX, make_samples
from listly.ui.components import demo_badge, empty_state, html, listing_card, section_header, title_of, top_bar
from listly.ui.state import HOME, NEW, SETTINGS, VIEW, go


def begin_new(source: str) -> None:
    """Start a fresh listing at the Photo step."""
    go(
        NEW,
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
    go(HOME, toast="Added 3 sample listings")


def sell_card() -> None:
    with st.container(key="card-sell"):
        html(
            '<div class="sell-title">Sell something new</div>'
            '<div class="sell-sub">Take one photo. Listly identifies the item, cleans up the photo, '
            "finds a fair price and writes your listings.</div>"
        )
        if DEMO_MODE:
            demo_badge()
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
                go(VIEW, view_id=draft.photo_id)

    if not any(d.photo_id.startswith(SAMPLE_PREFIX) for d in listings):
        if st.button("Add sample listings", type="tertiary"):
            add_samples()


def render() -> None:
    with st.container(key="toprow"):
        brand, settings = st.columns([5, 1])
        with brand:
            top_bar()
        if settings.button("Settings", icon=":material/settings:", type="tertiary"):
            go(SETTINGS, back_to=HOME)
    sell_card()
    my_listings()
    html('<div class="footer">Listly never posts for you · Your listings stay on this computer</div>')
