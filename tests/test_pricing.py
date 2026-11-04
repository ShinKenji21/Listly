"""Price research: only links the web search really found are kept, and results are cached."""

import json

from listly.ai.pricing import suggest_price
from listly.models import ItemInfo, ListingDraft

ANSWER = {
    "price_low": 1500, "price_high": 2200, "listing_price": 1900, "suggested_lowest": 1600,
    "summary": "Based on 3 listings.", "confidence": "medium",
    "comparables": [
        {"title": "Nike Pegasus", "price": "₱1,800", "url": "https://www.carousell.ph/p/nike-123/"},
        {"title": "Nike shoes", "price": 2000, "url": "https://shopee.ph/nike-456"},
        {"title": "Invented listing", "price": 999, "url": "https://fake.example/made-up"},
    ],
}


def search_reply():
    """A web search result for the Shopee link and a citation for the Carousell link (not the made-up one)."""
    return [
        {"id": "ws", "type": "web_search_call", "status": "completed",
         "results": [{"type": "text_result", "title": "Shopee", "url": "https://shopee.ph/nike-456", "snippet": "..."}]},
        {"id": "m", "type": "message", "status": "completed", "role": "assistant", "content": [{
            "type": "output_text", "text": json.dumps(ANSWER),
            "annotations": [{"type": "url_citation", "url": "https://www.carousell.ph/p/nike-123", "title": "t", "start_index": 0, "end_index": 5}],
        }]},
    ]


def test_made_up_links_are_dropped_and_real_ones_kept(fake_api):
    fake_api.reply_output(search_reply())
    draft = ListingDraft("shoes-1", ItemInfo.from_dict({"item": "running shoes", "brand": "Nike", "condition": "good"}))
    price = suggest_price(draft)
    assert [c.url for c in price.comparables] == ["https://www.carousell.ph/p/nike-123/", "https://shopee.ph/nike-456"]
    assert (price.listing_price, price.suggested_lowest) == (1900, 1600)

    request = fake_api.requests[0]
    assert request["tools"][0]["type"] == "web_search"
    assert request["tools"][0]["user_location"]["country"] == "PH"
    assert request["include"] == ["web_search_call.results"]

    suggest_price(draft)
    assert len(fake_api.requests) == 1  # cached
