<p align="center"><img src="assets/listly-logo.svg" alt="Listly: One photo. Every marketplace." width="420"></p>

# Listly

**One photo in, a ready-to-post listing out.** Listly helps second-hand sellers in the Philippines turn a single
photo of an item into honest, ready-to-copy listings for **Facebook Marketplace, Shopee and Carousell**, with a
clean product photo and a price backed by real comparable listings.

Built for the Meta Global AI Developer Hackathon 2026 (Indie Developer track, "Build for Your World").

## Why

Selling preloved items online is a side income for many Filipinos, but every listing means taking a decent photo,
figuring out a fair price, and writing a description three times, once per platform, often in Taglish. Listly does
the busywork. The seller stays in control: they check and edit everything, and **Listly never posts anything**.

## What it does

1. **Identify:** Muse Spark reads any visible logos and labels first, then returns the item, brand, model,
   condition, visible flaws (with where they are), highlights worth mentioning, and a confidence level. It says
   "unknown" rather than guessing a brand, and asks follow-up questions that fit the kind of item (size for shoes,
   battery and charger for gadgets, mileage and OR/CR for vehicles). It refuses prohibited items (weapons, drugs,
   counterfeits, animals).
2. **Cut out:** SAM 3.1 finds the item in the photo and cuts it out of the background.
3. **Clean photo:** Muse Image 1.0 places the cut-out on a clean white background, and is told never to change the
   item or hide its flaws. The original photo is always kept too.
4. **Price:** Muse Spark uses its built-in web search (biased to the Philippines) to find comparable listings and the
   brand-new price, then suggests a range in pesos, a listing price, and a private lowest price to accept.
   **Every source link is checked against the pages the search actually returned**, so made-up links are dropped.
5. **Write:** Muse Spark writes a title, description and tags for each platform, in English, Filipino or Taglish,
   following that platform's profile (tone, title length, hashtags). A checker validates each listing in code,
   including that **every flaw is mentioned**, and asks the model to fix it once if needed. The seller can edit by
   hand or just ask: "make it shorter", "add that it comes with the box". Rewrites go through the same checker, so a
   request can't quietly drop a flaw.
6. **Reply to buyers:** paste a buyer's message from any platform. Muse Spark drafts a reply using the item details
   and your selling settings (meet-up spots, times, shipping, payment, swaps), in your language and the platform's
   tone. It never makes up answers: anything it can't answer comes back to you as a question. Listly checks the
   reply in code so it **never offers less than your lowest price**, and **flags likely scams** (fake payment
   screenshots, "courier" links, OTP requests, overpay-and-refund, moving off the platform) even if the model misses them.

Saved listings live in "My listings" on your own computer (the `data/` folder), with a status (Draft, Listed, Sold)
so you can keep track. Each listing has real Copy buttons (title, description, everything) and an Open-site button.

## Meta models used

| Model | Used for |
|---|---|
| `muse-spark-1.3` | Identifying the item, price research with built-in `web_search`, writing listings, buyer replies |
| `sam-3.1` | Segmenting the item (one_bit masks, decoded in Python) |
| `muse-image-1.0` | Image-to-image clean product photo |

All calls go through the Meta Model API's Responses endpoint using the `openai` Python SDK.

## Run it yourself

You need Python 3.10+ and your own Meta Model API key. No key? Use demo mode (step 4) or tap **Try a sample listing**.

```bash
git clone <this repo>
cd Listly
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then put your own key in .env: META_API_KEY=...
streamlit run app.py
```

Open the link Streamlit prints (usually http://localhost:8501). On a phone on the same Wi-Fi, use the "Network URL".

**Demo mode:** set `LISTLY_DEMO=1` in `.env` to see the whole flow with sample answers. No key, no API calls, no cost.

## Design choices

- **Saves credits:** photos are shrunk to 1024px before sending, and every model result is cached on disk by image
  hash and step (`cache/`), so re-running the same photo costs nothing.
- **Fails gracefully:** each step can fail on its own. If the cut-out fails, the clean photo uses the full photo; if
  the clean photo fails, the original is still there. Every step has its own "Try again".
- **Model output is validated:** all model replies are JSON, checked into dataclasses (`listly/models.py`); bad
  replies show a friendly error instead of crashing.
- **Private by default:** your API key stays in `.env`, your listings stay in `data/` on your computer, and
  nothing is posted anywhere.

## Project structure

```
app.py                    entry point: page setup and which screen to show
listly/
  ai/                     everything that calls Meta's models
    api.py                one shared API call: errors, timing, JSON parsing
    identify.py           Muse Spark: item, flaws, highlights, follow-up questions
    cutout.py             SAM 3.1 cut-out + one_bit mask decoder
    clean_photo.py        Muse Image clean product photo
    pricing.py            Muse Spark + web search: price range, listing and lowest price, checked sources
    writer.py             per-platform listings + checker + rewrite on request
    replies.py            buyer replies: seller questions, scam warnings, lowest-price guard
  ui/                     the Streamlit interface
    pages/                one module per screen: home, new_listing, listing, settings
    sections.py           sections shared by screens (listing tabs, price, details form)
    components.py         small reusable pieces: listing card, badges, step bar, copy buttons
    theme.py              all custom styling (light and dark)
    state.py              page navigation
  models.py               dataclasses + validation of everything the model returns
  platforms.py            platform profiles (adding a site = adding a profile)
  storage.py              saved listings and settings in data/
  cache.py, config.py, images.py, sample.py
tests/                    57 automated tests, using a fake Meta API (no key, no credits)
eval/                     scores Listly on real photos with known answers (uses real API calls)
assets/                   logo and app icon
.streamlit/config.toml    light and dark theme colours, Inter font
.github/workflows/        runs the linter and tests on every push
```

## Development

```bash
pip install -r requirements-dev.txt
pytest          # 57 tests, about 5 seconds; never calls the real API
ruff check .    # lint: unused imports, likely bugs, import order
```

The tests swap in a fake Meta API (see `tests/conftest.py`) that returns queued replies and records every
request, so they check the exact requests Listly sends and how it handles the replies, including bad JSON,
broken listings, made-up links, scams and replies that try to go below the seller's lowest price. The app
tests click through every screen with Streamlit's test runner in demo mode.

## Evaluation

`python eval/run_eval.py` shows how many API calls it would make; add `--yes` to run it. It reports how often the
item is identified, the brand is right (or honestly "unknown" instead of guessed), the condition matches, the known
flaws are found, and the price range overlaps the real one.

## Known limitations

- Facebook Marketplace listings need a login, so web search can't see them; comparables mostly come from public sites
  such as Carousell.
- Platform title limits in `listly/platforms.py` are best-known values and may change.
- Listly runs locally; it isn't hosted.

## Built during the hackathon

Everything in this repository was written during the hackathon building period (from 30 October 2026); see the
commit history.

## Credits

- The SAM 3.1 `one_bit` mask decoder in `listly/cutout.py` is a Python port of Meta's
  [`@meta-sam/parser`](https://www.npmjs.com/package/@meta-sam/parser) (`dist/mask-codec.js`), used under the SAM
  License: see [`third_party/SAM-LICENSE.txt`](third_party/SAM-LICENSE.txt).
- Listly's own code is MIT licensed: see [`LICENSE`](LICENSE).
