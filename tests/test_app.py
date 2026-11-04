"""The whole app, clicked through with Streamlit's test runner, in demo mode (no API calls)."""

import io
import json
import sys
from pathlib import Path

import pytest
import streamlit as st
from PIL import Image
from streamlit.testing.v1 import AppTest

from listly import storage

APP = str(Path(__file__).parent.parent / "app.py")


@pytest.fixture
def app(monkeypatch):
    # Demo mode everywhere: every module that reads DEMO_MODE gets True.
    for name, module in list(sys.modules.items()):
        if name.startswith("listly") and hasattr(module, "DEMO_MODE"):
            monkeypatch.setattr(module, "DEMO_MODE", True)

    class UploadedPhoto:  # AppTest can't use a real file picker, so hand it a photo directly
        name, type = "item.png", "image/png"

        def getvalue(self):
            buf = io.BytesIO()
            Image.new("RGB", (1200, 900), "white").save(buf, "PNG")
            return buf.getvalue()

    monkeypatch.setattr(st, "file_uploader", lambda *a, **k: UploadedPhoto())
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    return at


def click(at, label):
    [b for b in at.button if label in b.label][0].click().run()
    assert not at.exception, at.exception


def test_home_starts_empty_and_can_add_samples(app):
    assert [b.label for b in app.button][:2] == ["Settings", "Upload photo"]
    click(app, "Add sample listings")
    assert len([b for b in app.button if b.label.startswith("Open ")]) == 3


def test_new_listing_from_photo_to_saved(app):
    click(app, "Upload photo")
    click(app, "Next")  # identify
    assert app.session_state["step"] == 2
    click(app, "Save and continue")  # details
    assert {n.label: n.value for n in app.number_input} == {"Listing price (₱)": 1900, "Lowest you'd accept (₱)": 1600}
    click(app, "Next")  # photo & price
    click(app, "Save listing")  # listings
    saved = storage.load_listing(app.session_state["view_id"])
    assert (saved.asking_price, saved.lowest_price, len(saved.listings)) == (1900, 1600, 3)


def test_status_buyer_reply_and_settings(app):
    click(app, "Add sample listings")
    click(app, "Open iPhone")
    app.session_state["status-sample-phone"] = "listed"
    app.run()
    assert storage.load_listing("sample-phone").status == "listed"

    [t for t in app.text_area if "buyer's message" in t.label][0].input("Paid na, here is the GCash screenshot")
    click(app, "Draft reply")
    assert any("Possible scam" in e.value for e in app.error)
    assert len(storage.load_listing("sample-phone").reply_history) == 1

    click(app, "My listings")
    click(app, "Settings")
    [t for t in app.text_input if t.label == "Meet-up spots"][0].input("Trinoma")
    click(app, "Save settings")
    assert json.loads((storage.DATA_DIR / "settings.json").read_text(encoding="utf-8"))["meetup_spots"] == "Trinoma"
