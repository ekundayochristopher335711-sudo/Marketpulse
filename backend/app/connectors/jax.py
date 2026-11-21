from __future__ import annotations

from datetime import datetime
import os
from typing import AsyncIterator

from .base import ConnectorConfig, MarketplaceConnector
from .utils import JaxCardParser, canonical_source_url, parse_ngn_price, robots_allows, scoped_listing, split_location
from ..schemas import ListingCreate

JAX_ROOT = "https://jax.ng"

JAX_CATEGORY_MAP = {
    "home-appliances-1": "Home & Garden",
    "furniture-home-garden": "Home & Garden",
    "clothing-accessories": "Fashion & Beauty",
    "pets": "Animals & Pets",
    "cars-vehicles": "Vehicles",
    "electronics-1": "Electronics",
    "cameras-imaging": "Electronics",
    "jewelry-watches": "Fashion & Beauty",
    "property-1": "Property",
    "mobile-phones-tablets": "Phones & Tablets",
    "consoles-and-video-games": "Leisure & Activities",
    "jobs": "Jobs",
    "musical-instruments": "Leisure & Activities",
    "sports-equipment": "Leisure & Activities",
    "computers-networking": "Electronics",
}


def classify_jax_title(title: str) -> str:
    value = title.casefold()
    if any(term in value for term in ("iphone", "phone", "samsung", "tecno", "infinix", "redmi", "oppo", "router", "laptop")):
        return "Phones & Tablets"
    if any(term in value for term in ("toyota", "honda", "lexus", "mercedes", "car", "vehicle", "suv", "bike", "motorcycle", "hijet")):
        return "Vehicles"
    if any(term in value for term in ("dog", "cat", "puppy", "kitten", "pet")):
        return "Animals & Pets"
    if any(term in value for term in ("sofa", "chair", "table", "fridge", "refrigerator", "fan", "solar", "furniture")):
        return "Home & Garden"
    if any(term in value for term in ("dress", "shoe", "bag", "ankara", "fashion")):
        return "Fashion & Beauty"
    return "Electronics"


def parse_jax_cards(
    html: str,
    category: str | None = None,
    observed_at: datetime | None = None,
) -> list[ListingCreate]:
    parser = JaxCardParser()
    parser.feed(html)
    observed = observed_at or datetime.now().astimezone()
    listings: list[ListingCreate] = []
    for card in parser.cards:
        title = " ".join(card.get("p1", "").split())
        asking_price = parse_ngn_price(card.get("p0"))
        raw_location = " ".join(card.get("p2", "").split())
        source_url = canonical_source_url(JAX_ROOT, card.get("source_url", ""))
        if not title or not asking_price or not raw_location or not source_url:
            continue
        location, state, city = split_location(raw_location)
        listings.append(
            ListingCreate(
                source_id="jax",
                source_listing_id=source_url.rstrip("/").rsplit("/", 1)[-1][:255],
                title=title[:500],
                category=category or classify_jax_title(title),
                asking_price=asking_price,
                currency="NGN",
                location=location,
                state=state,
                city=city,
                source_url=source_url,
                observed_at=observed,
            )
        )
    return listings


class JaxConnector(MarketplaceConnector):
    source_key = "jax"
    supported_access_methods = frozenset({"authorized_web"})

    def __init__(self, config: ConnectorConfig):
        if config.access_method != "authorized_web":
            raise ValueError("Jax.ng collection requires authorized web access.")
        super().__init__(config)
        configured_page = os.getenv("MARKETPULSE_JAX_CATEGORY_PAGE", "").strip().strip("/")
        self._category_page = configured_page
        self._page_url = f"{JAX_ROOT}/ads/{configured_page}" if configured_page else f"{JAX_ROOT}/ads"
        self._category = JAX_CATEGORY_MAP.get(configured_page)
        self._robots_checked = False
        self._robots_allowed = False

    async def healthcheck(self) -> bool:
        self._robots_allowed = await robots_allows(
            self,
            f"{JAX_ROOT}/robots.txt",
            self._page_url,
        )
        self._robots_checked = True
        return self._robots_allowed

    async def discover_listings(
        self, since: datetime | None
    ) -> AsyncIterator[ListingCreate]:
        if not self._robots_checked and not await self.healthcheck():
            raise RuntimeError("Jax.ng robots.txt blocks the approved ads page.")
        if not self._robots_allowed:
            raise RuntimeError("Jax.ng robots.txt blocks the approved ads page.")

        response = await self.request("GET", self._page_url)
        for listing in parse_jax_cards(response.text, self._category):
            if listing.category not in self.config.permitted_categories:
                continue
            yield scoped_listing(listing, self.config)
