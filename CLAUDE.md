# Listly — project guide for Claude Code

## What we're building
Listly is a web app that turns one photo of an item into a ready-to-post online listing.
Built for the Meta Global AI Developer Hackathon 2026 (Indie Developer track).
Submission deadline: 5 November 2026, 9:00 AM (UTC+8). Keep scope tight.

User flow:
1. Seller uploads a photo or takes one with the camera.
2. Muse Spark identifies the item (item, brand, model, category, color, condition, flaws,
   confidence) and asks follow-up questions for things the photo can't show.
3. SAM 3.1 cuts the item out of the background.
4. Muse Image makes a clean product photo from the cut-out. Always keep the original photo too.
5. Muse Spark uses web search to find comparable listings and suggests a price range in PHP,
   with source links.
6. Muse Spark writes a title, description and tags per platform
   (Facebook Marketplace, Shopee, Carousell), in English, Filipino or Taglish.
7. Seller edits and approves everything, then copies each version. Listly never posts anything.

## Tech stack
- Python 3.10+, Streamlit for the UI (must work in a phone browser)
- Meta Model API through the `openai` Python SDK with a custom base URL
- Pillow for resizing, python-dotenv for config
- JSON file cache in `cache/`

## Meta Model API
- Base URL: `https://api.meta.ai/v1` (OpenAI-compatible)
- Text/vision model: `muse-spark-1.3` (read from env var `META_MODEL`)
- Web search, SAM 3.1 and Muse Image: **exact request formats and model IDs are not confirmed.**
  Do NOT invent endpoints or parameters. Put each one behind a small function in its own module
  with a clear `TODO: confirm in Meta Model API docs` and ask me for the docs before implementing.

## Rules
- Never hardcode or print the API key. It lives only in `.env`. `.env` and `cache/` must be in
  `.gitignore`. The repo is public.
- Save API credits ($150 total for the whole hackathon):
  - Resize images to max 1024px JPEG before sending.
  - Cache every model result by image hash (and step name) so re-runs cost nothing.
  - Never call the API in loops or tests without asking me first.
- Ask Muse Spark for JSON and validate it. If parsing fails, show a friendly error and let the
  seller retry that one step, not the whole flow.
- Model must say "unknown" and lower its confidence rather than guess a brand or model.
- Refuse to create listings for prohibited items (weapons, drugs, counterfeit goods, animals).
- Keep code simple and readable — I'm a student and need to understand and explain it to judges.
  Add short comments explaining *why*, not *what*.
- Make small changes, one step at a time. After each step, tell me how to run and test it.

## Suggested structure
```
app.py                 # Streamlit UI only
listly/
  __init__.py
  config.py            # env vars, client setup
  images.py            # resize, hashing
  cache.py             # disk cache helpers
  identify.py          # Muse Spark: item + flaws + questions
  cutout.py            # SAM 3.1 (TODO until docs confirmed)
  clean_photo.py       # Muse Image (TODO until docs confirmed)
  pricing.py           # Muse Spark + web search
  writer.py            # per-platform listings
  models.py            # dataclasses: Photo, ItemInfo, PriceEstimate, Comparable, PlatformListing, ListingDraft
eval/
  items.csv            # 30 test items with known answers
  run_eval.py          # scores identification, flaws, price range
```

## Screens (phone-first, step bar at the top)
1. Add photo — Upload / Camera, platform checkboxes (Facebook Marketplace, Shopee, Carousell).
2. Item details — editable fields, flaws highlighted, follow-up questions as quick inputs.
3. Photo and price — original + clean photo side by side with Download buttons; price range with
   links to comparable listings.
4. Listings — one tab per platform: title, description, tags, each with a Copy button, plus
   Copy all and an "Open site" button (opens the site's create-listing page in a new tab).
Listly never posts for the seller and never asks for their passwords.

## Platform profiles
Each platform is a small profile (tone, max title length, required fields, hashtags yes/no) in
`listly/platforms.py`. The writer sends the profile to Muse Spark; a checker validates the result
against the profile and asks Muse Spark to rewrite it if it doesn't fit. Adding a site = adding a profile.

## Build order (feature complete by Monday 2 Nov)
1. Sat 31 Oct: refactor `app.py` into `listly/`; identification, flaws, follow-up questions; cache.
2. Sun 1 Nov: SAM 3.1 cut-out, Muse Image clean photo, price research with sources.
3. Mon 2 Nov: platform profiles, writer + checker, 4-screen UI with step bar, copy/download/open buttons.
4. Tue 3 Nov: extras if time (language choice, buyer reply helper, edit by chat), error handling, deploy.
5. Wed 4 Nov: 30-item eval, README, demo video. Submit by Thu 5 Nov, 9:00 AM (UTC+8).
