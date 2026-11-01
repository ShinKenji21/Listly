"""Listly - Streamlit UI only. All model/image/cache logic lives in the listly/ package."""

import copy
from dataclasses import replace

import streamlit as st
from PIL import UnidentifiedImageError

from listly.api import StepError
from listly.clean_photo import make_clean_photo
from listly.config import DEMO_MODE, has_api_key
from listly.cutout import cut_out
from listly.identify import identify_item
from listly.pricing import suggest_price
from listly.images import image_hash, shrink_image
from listly.models import CONDITIONS, UNKNOWN, ListingDraft

st.set_page_config(page_title="Listly", page_icon="🏷️")
st.title("🏷️ Listly")
st.caption("Snap a photo of something you want to sell.")

if DEMO_MODE:
    st.info("Demo mode: showing a sample answer. No API calls, no credits used.")
elif not has_api_key():
    # Someone who downloaded the repo without a key should still be able to see the app working.
    st.error(
        "No API key found. Copy .env.example to .env and add your own META_API_KEY.\n\n"
        "No key? Set LISTLY_DEMO=1 in .env to try Listly with sample results."
    )
    st.stop()

source = st.radio("Photo from", ["Upload", "Camera"], horizontal=True)
photo = (
    st.file_uploader("Upload a photo", type=["jpg", "jpeg", "png", "webp"])
    if source == "Upload"
    else st.camera_input("Take a photo")
)

if not photo:
    st.stop()

try:
    image_bytes = shrink_image(photo.getvalue())
except UnidentifiedImageError:
    st.error("That file doesn't look like a photo. Try a JPG or PNG.")
    st.stop()

# Streamlit reruns the whole script on every click, so keep the result in session_state
# (tied to this photo) or it disappears as soon as the seller touches anything else.
photo_id = image_hash(image_bytes)
if st.session_state.get("photo_id") != photo_id:
    st.session_state.photo_id = photo_id
    st.session_state.info = None  # Muse Spark's raw answer
    st.session_state.draft = None  # the seller's edited version
    st.session_state.identify_error = None
    st.session_state.clean_photo = None
    st.session_state.photo_notes = []
    st.session_state.price = None
    st.session_state.price_error = None

if st.session_state.info is None:
    st.image(image_bytes, width=300)  # preview; after identifying, the Photo section shows it

label = "Try again" if st.session_state.identify_error else "Identify item"
if st.session_state.info is None and st.button(label, type="primary"):
    with st.spinner("Looking at your item..."):
        try:
            info = identify_item(image_bytes)
            st.session_state.info = info
            # Copy so the seller's edits never change the model's original answer.
            st.session_state.draft = ListingDraft(photo_id=photo_id, info=copy.deepcopy(info))
            st.session_state.identify_error = None
        except StepError as e:
            st.session_state.identify_error = str(e)
    st.rerun()  # redraw so the button label/result match the new state

if st.session_state.identify_error:
    st.error(st.session_state.identify_error)

info = st.session_state.info
if info is None:
    st.stop()

if info.prohibited:
    st.error(
        "Listly can't help list this item"
        + (f": {info.prohibited_reason}" if info.prohibited_reason != UNKNOWN else ".")
    )
    st.stop()

draft = st.session_state.draft


def as_input(value: str) -> str:
    # Show an empty box (with an "Unknown" placeholder) so the seller sees what's missing.
    return "" if value == UNKNOWN else value


def from_input(text: str) -> str:
    return text.strip() or UNKNOWN


st.subheader("Item details")
st.caption(f"Muse Spark's confidence: **{info.confidence}**. Fix anything it got wrong.")

# Shown above the form so flaws can't be missed: honest listings get fewer returns and disputes.
if draft.info.flaws:
    st.warning("**Flaws to mention in the listing:**\n- " + "\n- ".join(draft.info.flaws))

# A form only reruns the app when Save is pressed, not on every keystroke.
with st.form("details"):
    item = st.text_input("Item", draft.info.item)
    col1, col2 = st.columns(2)
    brand = col1.text_input("Brand", as_input(draft.info.brand), placeholder="Unknown")
    model = col2.text_input("Model", as_input(draft.info.model), placeholder="Unknown")
    category = col1.text_input("Category", as_input(draft.info.category), placeholder="Unknown")
    color = col2.text_input("Color", as_input(draft.info.color), placeholder="Unknown")

    condition_options = [UNKNOWN] + CONDITIONS
    condition = st.selectbox(
        "Condition",
        condition_options,
        index=condition_options.index(draft.info.condition),
        format_func=str.capitalize,
    )
    flaws_text = st.text_area(
        "Flaws (one per line)",
        "\n".join(draft.info.flaws),
        placeholder="No flaws",
    )

    answers = {}
    if draft.info.questions_for_seller:
        st.markdown("**A few questions the photo can't answer**")
        for question in draft.info.questions_for_seller:
            answers[question] = st.text_input(question, draft.answers.get(question, ""))

    saved = st.form_submit_button("Save details", type="primary", width="stretch")

if saved:
    if not item.strip():
        st.error("Please say what the item is.")
    else:
        draft.info = replace(
            draft.info,
            item=item.strip(),
            brand=from_input(brand),
            model=from_input(model),
            category=from_input(category),
            color=from_input(color),
            condition=condition,
            flaws=[line.strip() for line in flaws_text.splitlines() if line.strip()],
        )
        # Skip blank answers so later steps don't treat "" as something the seller said.
        draft.answers = {q: a.strip() for q, a in answers.items() if a.strip()}
        st.session_state.price = None  # new details can change the price (unchanged ones hit the cache)
        st.session_state.just_saved = True
        st.rerun()  # redraw so the flaws box above shows the edited list

if st.session_state.pop("just_saved", False):
    st.success("Details saved.")

st.subheader("Photo")
photo_label = "Try again" if st.session_state.photo_notes else "Make clean photo"
if st.session_state.clean_photo is None and st.button(photo_label, width="stretch"):
    notes = []
    with st.spinner("Cutting out your item and cleaning up the photo..."):
        # Each step can fail on its own; a failed step falls back instead of stopping everything.
        source = image_bytes
        try:
            cut = cut_out(image_bytes, draft.info)
            source = cut.png
            if not cut.exact:
                notes.append("Couldn't trace the item's exact outline, so it was cropped instead.")
        except StepError as e:
            notes.append(f"Cut-out skipped: {e} Using the full photo instead.")
        try:
            st.session_state.clean_photo = make_clean_photo(source)
        except StepError as e:
            notes.append(f"Couldn't make a clean photo: {e} Your original photo is still fine to use.")
    st.session_state.photo_notes = notes
    st.rerun()

for note in st.session_state.photo_notes:
    st.info(note)

col1, col2 = st.columns(2)
col1.image(image_bytes, caption="Original")
# Download the seller's full-size photo, not the shrunk copy we send to the model.
col1.download_button("Download original", photo.getvalue(), photo.name, photo.type, width="stretch")
if st.session_state.clean_photo:
    col2.image(st.session_state.clean_photo, caption="Clean photo")
    col2.download_button(
        "Download clean photo", st.session_state.clean_photo, "listly-clean.jpg", "image/jpeg", width="stretch"
    )

st.subheader("Price")
price_label = "Try again" if st.session_state.price_error else "Find a price"
if st.session_state.price is None and st.button(price_label, width="stretch"):
    with st.spinner("Searching for similar listings..."):
        try:
            st.session_state.price = suggest_price(draft)
            st.session_state.price_error = None
        except StepError as e:
            st.session_state.price_error = str(e)
    st.rerun()

if st.session_state.price_error:
    st.error(st.session_state.price_error)

price = st.session_state.price
if price:
    st.metric("Suggested price", f"₱{price.price_low:,} – ₱{price.price_high:,}")
    if price.new_price:
        st.caption(f"Brand new: about ₱{price.new_price:,}")
    st.caption(f"{price.summary} (confidence: {price.confidence})")
    if price.comparables:
        st.markdown("**Similar listings found**")
        for comp in price.comparables:
            # Brackets in a web page title would break the markdown link, so drop them.
            title = comp.title.replace("[", "").replace("]", "")
            url = comp.url.replace(")", "%29")
            st.markdown(f"- [{title}]({url})" + (f" — ₱{comp.price:,}" if comp.price else ""))
    else:
        st.warning("No source links could be checked, so treat this range as a rough guess.")

with st.expander("Saved draft (what the next steps will use)"):
    st.json(draft.to_dict())
with st.expander("Raw model output (validated)"):
    st.json(info.to_dict())
