"""Listly: one photo in, ready-to-post listings out. Run with:  streamlit run app.py

This file only sets up the page and picks which screen to show. Everything else lives in listly/:
    listly/ai/        calls to Meta's models (identify, cut-out, clean photo, price, writer, replies)
    listly/ui/pages/  one module per screen
    listly/           data models, storage, cache and helpers
"""

from pathlib import Path

import streamlit as st

from listly.ui.pages import home, listing, new_listing, settings
from listly.ui.state import HOME, NEW, SETTINGS, VIEW, state
from listly.ui.theme import apply_theme

st.set_page_config(page_title="Listly", page_icon=str(Path(__file__).parent / "assets" / "listly-icon.svg"))
apply_theme()

PAGES = {HOME: home.render, NEW: new_listing.render, VIEW: listing.render, SETTINGS: settings.render}

state.setdefault("page", HOME)
if "toast" in state:
    st.toast(state.pop("toast"))  # set before a rerun, shown after it
if state.page == NEW and state.get("step", 1) > 1 and not state.get("draft"):
    state.page = HOME  # e.g. the browser tab was reloaded in the middle of a new listing

PAGES[state.page]()
