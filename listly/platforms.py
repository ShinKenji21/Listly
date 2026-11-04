"""One small profile per selling platform. Adding a site = adding a profile here.

The writer sends the profile to Muse Spark, and the checker validates the result against it.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Platform:
    key: str
    name: str
    tone: str
    max_title: int  # characters; TODO: double-check each limit on the site's create-listing page
    hashtags: bool  # whether hashtags belong in the description
    description_tips: str
    create_url: str  # the site's own "create listing" page; Listly never posts for the seller
    min_tags: int = 3
    max_tags: int = 10


PLATFORMS = {
    p.key: p
    for p in [
        Platform(
            key="facebook",
            name="Facebook Marketplace",
            tone="friendly but straightforward, like a normal seller on Facebook Marketplace",
            max_title=100,
            hashtags=False,
            description_tips="Short paragraphs. Start with the key facts (condition, size/specs), then flaws, "
            "then how to buy: meet-up or delivery, and that the item is available. Emojis are fine but use few.",
            create_url="https://www.facebook.com/marketplace/create/item",
        ),
        Platform(
            key="shopee",
            name="Shopee",
            tone="clear and professional, like a trusted shop",
            max_title=120,
            hashtags=True,
            description_tips="Start with a one-line summary, then a bullet list of specs and condition, "
            "then flaws, then what's included. Put the main search keywords in the title.",
            create_url="https://seller.shopee.ph/portal/product/new",
        ),
        Platform(
            key="carousell",
            name="Carousell",
            tone="casual and to the point",
            max_title=80,
            hashtags=False,
            description_tips="Short and scannable: condition, key details, flaws, reason for selling if known, "
            "and meet-up or delivery options.",
            create_url="https://www.carousell.ph/sell",
        ),
    ]
}
