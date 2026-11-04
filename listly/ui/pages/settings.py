"""Selling settings: meet-up spots, times, shipping, payment and swaps, used by buyer replies."""

import streamlit as st

from listly import storage
from listly.models import SellerSettings
from listly.ui.components import html
from listly.ui.state import HOME, go, state


def render() -> None:
    if st.button("← Back", type="tertiary"):
        go(state.get("back_to", HOME))
    html(
        '<div class="page-head"><h2>Selling settings</h2>'
        "<div class=\"sell-sub\">Listly uses this to answer buyers' questions about meet-ups, shipping and payment. "
        "It's saved only on this computer.</div></div>"
    )
    current = storage.load_settings()
    with st.container(key="card-settings"), st.form("settings", border=False):
        meetup = st.text_input("Meet-up spots", current.meetup_spots, placeholder="e.g. SM North EDSA, Trinoma, MRT Quezon Ave")
        times = st.text_input("Available times", current.available_times, placeholder="e.g. Weekdays after 6 PM, weekends")
        shipping = st.text_input("Shipping options", current.shipping, placeholder="e.g. Lalamove or J&T, buyer pays shipping")
        payment = st.text_input("Payment methods", current.payment, placeholder="e.g. Cash on meet-up, GCash")
        swaps = st.toggle("Open to swaps", current.swaps)
        if st.form_submit_button("Save settings", type="primary", width="stretch"):
            storage.save_settings(SellerSettings(meetup.strip(), times.strip(), shipping.strip(), payment.strip(), swaps))
            go(state.get("back_to", HOME), toast="Settings saved")
