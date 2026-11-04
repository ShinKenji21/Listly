"""Reusable UI pieces, so every screen looks the same. Styles are in theme.py.

Everything that comes from the model or the seller goes through escape(), so it can't inject HTML.
"""

from datetime import datetime
from html import escape

import streamlit as st

from listly.images import thumbnail, to_data_url
from listly.models import ListingDraft
from listly.platforms import PLATFORMS

SHORT_NAMES = {"facebook": "FB", "shopee": "Shopee", "carousell": "Carousell"}


def html(markup: str) -> None:
    """Show our own HTML. Lines are joined first: Markdown would turn indented lines into a code block."""
    st.markdown("".join(line.strip() for line in markup.splitlines()), unsafe_allow_html=True)


def peso(amount: int | None) -> str:
    return f"₱{amount:,}" if amount else "No price yet"


def short_date(created: str) -> str:
    try:
        return datetime.strptime(created, "%Y-%m-%d %H:%M").strftime("%b %d").replace(" 0", " ")
    except ValueError:
        return created


def image_src(image_bytes: bytes | None, size: int = 160) -> str:
    return to_data_url(thumbnail(image_bytes, size)) if image_bytes else ""


def title_of(draft: ListingDraft) -> str:
    first = next(iter(draft.listings.values()), None)
    return first.title if first else draft.info.item.capitalize()


# --- small HTML snippets -------------------------------------------------------------------------


def status_badge(status: str) -> str:
    return f'<span class="badge {escape(status)}">{escape(status.capitalize())}</span>'


def platform_chips(keys: list[str]) -> str:
    return "".join(f'<span class="chip">{SHORT_NAMES.get(k, k)}</span>' for k in keys if k in PLATFORMS)


def price_tag(amount: int | None) -> str:
    return f'<div class="price">{escape(peso(amount))}</div>'


# --- whole pieces --------------------------------------------------------------------------------


def top_bar(demo: bool) -> None:
    demo_badge = '<span class="demo" title="Sample answers, no API calls, no credits used">Demo mode</span>' if demo else ""
    html(
        f"""<div class="topbar"><div class="mark">L</div>
        <div><div class="name">Listly</div><div class="tagline">One photo. Every marketplace.</div></div>
        {demo_badge}</div>"""
    )


def section_header(title: str, count: int | None = None) -> None:
    extra = f'<span class="count">{count}</span>' if count is not None else ""
    html(f'<div class="section-header"><h3>{escape(title)}</h3>{extra}</div>')


def empty_state(title: str, message: str) -> None:
    html(f'<div class="empty"><b>{escape(title)}</b><br>{escape(message)}</div>')


def step_bar(steps: list[str], current: int) -> None:
    """current is 1-based. Done steps get a tick; only the current label shows on narrow phones."""
    parts = []
    for number, name in enumerate(steps, start=1):
        status = "done" if number < current else "current" if number == current else ""
        if number > 1:
            parts.append(f'<div class="bar {"done" if number <= current else ""}"></div>')
        dot = "✓" if number < current else str(number)
        parts.append(f'<div class="step {status}"><span class="dot">{dot}</span><span class="label">{escape(name)}</span></div>')
    html(f'<div class="stepper" aria-label="Step {current} of {len(steps)}">{"".join(parts)}</div>')


def listing_card(draft: ListingDraft, image: bytes | None) -> bool:
    """One card in the My listings grid. Returns True when it's tapped."""
    with st.container(key=f"lcard-{draft.photo_id}"):
        html(
            f"""<div class="lcard">
            <div class="thumb"><img src="{image_src(image, 360)}" alt="">{status_badge(draft.status)}</div>
            <div class="body"><div class="title">{escape(title_of(draft))}</div>
            {price_tag(draft.asking_price)}
            <div class="meta">{platform_chips(draft.platforms)}</div>
            <div class="date">{escape(short_date(draft.created))}</div></div></div>"""
        )
        # Invisible button over the whole card (see theme.py), labelled for screen readers.
        return st.button(f"Open {title_of(draft)}", key=f"open-{draft.photo_id}")
