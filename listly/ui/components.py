"""Reusable UI pieces, so every screen looks the same. Styles are in theme.py.

Everything that comes from the model or the seller goes through escape(), so it can't inject HTML.
"""

import base64
import json
from datetime import datetime
from functools import lru_cache
from html import escape
from pathlib import Path

import streamlit as st

from listly.images import thumbnail, to_data_url
from listly.models import ListingDraft
from listly.platforms import PLATFORMS

SHORT_NAMES = {"facebook": "FB", "shopee": "Shopee", "carousell": "Carousell"}
ICON_PATH = Path(__file__).resolve().parents[2] / "listly-icon.svg"  # the app icon in the repo root


@lru_cache(maxsize=1)
def icon_src() -> str:
    """The Listly icon as a data URL, so it can be shown inside our own HTML."""
    return "data:image/svg+xml;base64," + base64.b64encode(ICON_PATH.read_bytes()).decode()


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


def top_bar() -> None:
    # The wordmark is text (not the logo image) so it stays readable in dark mode.
    html(
        f"""<div class="topbar"><img class="mark" src="{icon_src()}" alt="Listly logo">
        <div><div class="name">listly</div><div class="tagline">One photo. Every marketplace.</div></div></div>"""
    )


def demo_badge() -> None:
    html('<span class="demo">Demo mode · sample answers, no credits used</span>')


def section_header(title: str, count: int | None = None) -> None:
    extra = f'<span class="count">{count}</span>' if count is not None else ""
    html(f'<div class="section-header"><h3>{escape(title)}</h3>{extra}</div>')


def empty_state(title: str, message: str) -> None:
    html(
        f'<div class="empty"><img src="{icon_src()}" alt="">'
        f"<b>{escape(title)}</b><br>{escape(message)}</div>"
    )


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


def text_field(label: str, text: str, note: str = "") -> None:
    """A read-only block of listing text with a small label (newlines kept)."""
    body = escape(text).replace("\n", "<br>")  # html() joins lines, so keep line breaks as <br>
    html(
        f'<div class="field"><div class="field-label"><span>{escape(label)}</span><span>{escape(note)}</span></div>'
        f'<div class="field-text">{body}</div></div>'
    )


COPY_CSS = """
body { margin: 0; font-family: Inter, system-ui, -apple-system, "Segoe UI", sans-serif; }
.row { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
button { height: 44px; border-radius: 12px; border: 1px solid #E2E6EA; background: #fff; color: #1C2430;
         font: 600 14px Inter, system-ui, sans-serif; cursor: pointer; }
button.primary { background: #0F766E; border-color: #0F766E; color: #fff; }
button.wide { grid-column: 1 / -1; }
@media (prefers-color-scheme: dark) {
  button { background: #161D24; border-color: #2A333D; color: #E7ECF1; }
  button.primary { background: #2DB3A3; border-color: #2DB3A3; color: #06231F; }
}
"""


def copy_buttons(items: list[tuple[str, str]]) -> None:
    """Real "Copy" buttons. They live in a tiny iframe because only JavaScript can write to the clipboard.

    items = [(button label, text to copy)]. Two per row; the last one is the main (wide, coloured) button.
    """
    buttons = []
    for i, (label, _) in enumerate(items):
        last = i == len(items) - 1
        kind = "primary" + (" wide" if len(items) % 2 == 1 else "") if last else ""
        buttons.append(f'<button class="{kind}">{escape(label)}</button>')
    # The texts come from the model or the seller, so they only ever appear as JSON data, with every "<"
    # encoded: nothing inside them can end the script or add HTML. Labels are escaped above.
    texts = json.dumps([text for _, text in items]).replace("<", "\\u003c")
    rows = (len(items) + 1) // 2
    st.iframe(
        f"""<style>{COPY_CSS}</style><div class="row">{"".join(buttons)}</div>
        <script>
        const texts = {texts};
        document.querySelectorAll("button").forEach((button, i) => button.addEventListener("click", async () => {{
          const label = button.textContent;
          try {{ await navigator.clipboard.writeText(texts[i]); }}
          catch (e) {{  // older browsers: copy through a hidden text box instead
            const box = document.createElement("textarea"); box.value = texts[i];
            document.body.appendChild(box); box.select(); document.execCommand("copy"); box.remove();
          }}
          button.textContent = "✓ Copied"; setTimeout(() => button.textContent = label, 1500);
        }}));
        </script>""",
        height=rows * 52,
    )


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
