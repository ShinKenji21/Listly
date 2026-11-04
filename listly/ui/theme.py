"""All of Listly's custom styling in one place.

Colours, font and corner radius for Streamlit's own widgets are in .streamlit/config.toml
([theme.light] and [theme.dark]); this CSS styles our own pieces to match, in both modes.
Streamlit elements are targeted by data-testid, our containers by their key (".st-key-<key>").
"""

import streamlit as st

CSS = """
/* Design tokens: one brand colour, neutral greys, 8px spacing, 12px corners. */
:root {
  --brand: #0F766E; --brand-ink: #FFFFFF; --brand-soft: #E3F2EF;
  --ink: #1C2430; --muted: #5F6B78; --line: #E2E6EA;
  --surface: #FFFFFF; --surface-2: #F1F3F5;
  --ok: #15803D; --ok-soft: #E3F5E9; --warn: #8A5300; --warn-soft: #FFF3D9;
  --radius: 12px; --shadow: 0 1px 2px rgba(16,24,40,.05), 0 2px 8px rgba(16,24,40,.06);
  --shadow-hover: 0 4px 14px rgba(16,24,40,.12);
}
@media (prefers-color-scheme: dark) {
  :root {
    --brand: #2DB3A3; --brand-ink: #06231F; --brand-soft: #143A36;
    --ink: #E7ECF1; --muted: #9AA6B2; --line: #2A333D;
    --surface: #161D24; --surface-2: #1E262E;
    --ok: #4ADE80; --ok-soft: #153020; --warn: #F5C26B; --warn-soft: #3A2C10;
    --shadow: 0 1px 2px rgba(0,0,0,.4); --shadow-hover: 0 4px 14px rgba(0,0,0,.5);
  }
}

/* Page: narrow, phone-first column; hide Streamlit's header bar, menu and footer. */
[data-testid="stMainBlockContainer"] { max-width: 760px; padding: 16px 16px 64px; }
header[data-testid="stHeader"], #MainMenu, footer { display: none !important; }
[data-testid="stHeaderActionElements"] { display: none; }

/* Big, easy tap targets. */
.stButton button, .stDownloadButton button, .stLinkButton a, [data-testid="stFormSubmitButton"] button {
  min-height: 44px; font-weight: 600;
}

/* Cards: our containers whose key starts with "card". */
[class*="st-key-card"] {
  background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius);
  box-shadow: var(--shadow); padding: 16px;
}

/* Two things side by side even on a phone (two photos, two buttons). */
[class*="st-key-pair"] [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 8px; }
[class*="st-key-pair"] [data-testid="stColumn"] { min-width: 0 !important; width: auto !important; flex: 1 1 0 !important; }
.st-key-pair_photos img {
  aspect-ratio: 1 / 1; object-fit: contain; background: var(--surface);
  border: 1px solid var(--line); border-radius: var(--radius);
}

/* Copy boxes hold listing text, so they look like text, not code. */
[data-testid="stCode"] pre { background: var(--surface) !important; border: 1px solid var(--line); border-radius: var(--radius); }
[data-testid="stCode"] code { font-size: .95rem !important; line-height: 1.55 !important; }

/* --- Top bar ------------------------------------------------------------------------------ */
.topbar { display: flex; align-items: center; gap: 10px; padding: 8px 0 16px; }
.topbar .mark {
  width: 36px; height: 36px; border-radius: 10px; background: var(--brand); color: var(--brand-ink);
  display: grid; place-items: center; font-weight: 800; font-size: 1.1rem;
}
.topbar .name { font-size: 1.35rem; font-weight: 800; letter-spacing: -.02em; color: var(--ink); line-height: 1.1; }
.topbar .tagline { font-size: .85rem; color: var(--muted); }
.topbar .demo {
  margin-left: auto; font-size: .75rem; font-weight: 600; color: var(--warn); white-space: nowrap;
  background: var(--warn-soft); border-radius: 999px; padding: 4px 10px;
}

/* "Sell something new" card */
.sell-title { font-size: 1.15rem; font-weight: 700; color: var(--ink); }
.sell-sub { font-size: .9rem; color: var(--muted); margin: 4px 0 8px; line-height: 1.45; }

/* Section header: title + count */
.section-header { display: flex; align-items: baseline; gap: 8px; margin: 24px 0 8px; }
.section-header h3 { margin: 0; font-size: 1.1rem; font-weight: 700; color: var(--ink); }
.section-header .count { color: var(--muted); font-size: .9rem; }

/* --- Listing grid: 2 columns on a phone, 3 on wider screens --------------------------------- */
.st-key-grid {
  display: grid !important; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; align-items: stretch !important;
}
@media (min-width: 640px) { .st-key-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
.st-key-grid > div { width: auto !important; min-width: 0; display: flex; align-self: stretch !important; height: auto !important; }
.st-key-grid > div > div { flex: 1; }  /* cards in the same row get the same height */

[class*="st-key-lcard-"] {
  position: relative; gap: 0 !important; overflow: hidden;
  background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius);
  box-shadow: var(--shadow); transition: box-shadow .15s, transform .15s;
}
@media (hover: hover) {
  [class*="st-key-lcard-"]:hover { box-shadow: var(--shadow-hover); transform: translateY(-2px); }
}
/* The whole card is one invisible button laid over it, so a tap anywhere opens the listing. */
[class*="st-key-lcard-"] [data-testid="stElementContainer"]:has(.stButton) { position: absolute; inset: 0; z-index: 2; }
[class*="st-key-lcard-"] .stButton, [class*="st-key-lcard-"] .stButton button { width: 100%; height: 100%; }
[class*="st-key-lcard-"] .stButton button { opacity: 0; }
[class*="st-key-lcard-"] .stButton button:focus-visible { opacity: 1; background: transparent; outline: 3px solid var(--brand); }

/* Streamlit gives Markdown blocks a negative bottom margin, which would clip the bottom of the card. */
[class*="st-key-lcard-"] [data-testid="stMarkdown"], [class*="st-key-lcard-"] [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
.lcard .thumb { position: relative; aspect-ratio: 1 / 1; background: var(--surface-2); }
.lcard .thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.lcard .thumb .badge { position: absolute; top: 8px; left: 8px; }
.lcard .body { padding: 8px 12px 12px; }
.lcard .title {
  font-weight: 600; font-size: .92rem; color: var(--ink); line-height: 1.3;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; min-height: 2.6em;
}
.lcard .price { font-weight: 800; font-size: 1.05rem; color: var(--ink); margin: 4px 0; }
.lcard .meta { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.lcard .date { font-size: .75rem; color: var(--muted); margin-top: 6px; }

/* Status badges (text + colour, so they never rely on colour alone) */
.badge {
  display: inline-block; font-size: .72rem; font-weight: 700; letter-spacing: .02em;
  border-radius: 999px; padding: 3px 9px; text-transform: uppercase;
}
.badge.draft { background: var(--surface-2); color: var(--muted); border: 1px solid var(--line); }
.badge.listed { background: var(--brand); color: var(--brand-ink); }
.badge.sold { background: var(--ok-soft); color: var(--ok); border: 1px solid var(--ok); }

/* Small chips: platforms, confidence, etc. */
.chips { display: flex; flex-wrap: wrap; gap: 4px; }
.chip {
  font-size: .72rem; font-weight: 600; border-radius: 6px; padding: 2px 7px;
  background: var(--surface-2); color: var(--muted);
}
.chip.good { background: var(--brand-soft); color: var(--brand); }
.chip.warn { background: var(--warn-soft); color: var(--warn); }

/* Empty state */
.empty {
  text-align: center; color: var(--muted); padding: 32px 16px; line-height: 1.5;
  border: 1.5px dashed var(--line); border-radius: var(--radius); background: var(--surface);
}
.empty b { color: var(--ink); font-size: 1.05rem; }

/* --- New-listing flow ------------------------------------------------------------------------ */
.stepper { display: flex; align-items: center; gap: 6px; margin: 4px 0 16px; }
.stepper .step { display: flex; align-items: center; gap: 6px; white-space: nowrap; }
.stepper .dot {
  display: inline-grid; place-items: center; width: 26px; height: 26px; border-radius: 50%;
  font-size: .8rem; font-weight: 700; border: 2px solid var(--line); color: var(--muted); background: var(--surface);
}
.stepper .label { font-size: .85rem; color: var(--muted); }
.stepper .bar { flex: 1; height: 2px; background: var(--line); min-width: 12px; }
.stepper .done .dot { background: var(--brand); border-color: var(--brand); color: var(--brand-ink); }
.stepper .bar.done { background: var(--brand); }
.stepper .current .dot { border-color: var(--brand); color: var(--brand); }
.stepper .current .label { color: var(--ink); font-weight: 700; }
@media (max-width: 520px) { .stepper .step:not(.current) .label { display: none; } }

.item-row { display: flex; gap: 12px; align-items: center; margin-bottom: 8px; }
.item-row img { width: 72px; height: 72px; border-radius: var(--radius); object-fit: cover; border: 1px solid var(--line); }
.item-row .title { font-size: 1.1rem; font-weight: 700; color: var(--ink); line-height: 1.25; margin-bottom: 4px; }

.price-card {
  background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius);
  box-shadow: var(--shadow); padding: 16px; margin: 4px 0 8px;
}
.price-card .label { font-size: .8rem; color: var(--muted); font-weight: 600; text-transform: uppercase; letter-spacing: .04em; }
.price-card .range { font-size: 1.9rem; font-weight: 800; letter-spacing: -.02em; color: var(--ink); margin: 2px 0 8px; }
.price-card .summary { font-size: .9rem; color: var(--muted); margin: 8px 0 0; line-height: 1.45; }

.page-head { margin-bottom: 12px; }
.page-head h2 { font-size: 1.3rem; font-weight: 800; margin: 4px 0 6px; color: var(--ink); line-height: 1.3; }

.footer { text-align: center; color: var(--muted); font-size: .78rem; margin-top: 40px; }
"""


def apply_theme() -> None:
    # st.markdown (not st.html): st.html is isolated from the rest of the page, so its CSS wouldn't apply.
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)
