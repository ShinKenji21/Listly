"""Where the seller is in the app.

Streamlit reruns the whole script on every click, so the current page (and anything a page needs
to remember, like the listing being made) lives in st.session_state.
"""

import streamlit as st

state = st.session_state

HOME, NEW, VIEW, SETTINGS = "home", "new", "view", "settings"


def go(page: str, **values) -> None:
    """Switch page (and set any extra state, e.g. toast="Saved"), then redraw."""
    state.page = page
    for name, value in values.items():
        state[name] = value
    st.rerun()
