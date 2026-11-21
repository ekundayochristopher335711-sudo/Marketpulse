from __future__ import annotations

from datetime import datetime
import re
from typing import AsyncIterator

from .base import ConnectorConfig, MarketplaceConnector
from .utils import (
    EnytinCardParser,
    canonical_source_url,
    parse_ngn_price,
    robots_allows,
    scoped_listing,
    split_location,
)
from ..schemas import ListingCreate

ENYTIN_ROOT = "https://nigeria.enytinplus.com"
ENYTIN_SHOP_URL = f"{ENYTIN_ROOT}/shop/"

ENYTIN_CATEGORY_MAP = {
    "vehicles": "Vehicles",
    "phones & electronics": "Electronics",
    "fashion": "Fashion & Beauty",
    "home & furniture": "Home & Garden",
    "health & beauty": "Health & Beauty",
    "equipment & tools": "Commercial Equipment & Tools",
    "property": "Property",
    "agriculture & food": "Agriculture & Foodstuff",
    "jobs & services": "Services",
    "babies & kids": "Babies & Kids",
    "animals & pets": "Animals & Pets",
    "sports & outdoors": "Leisure & Activities",
}


def _listing_id(card: dict[str, str], source_url: str | None) -> str | None:
    if card.get("source_listing_id"):
        return card["source_listing_id"][:255]
    if source_url:
        value = source_url.rstrip("/").rsplit("/", 1)[-1]
        value = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-")
        return value[:255] or None
    return None


def parse_enytin_cards(
    html: str,
    observed_at: datetime | None = None,
) -> list[ListingCreate]:
    parser = EnytinCardParser()
    parser.feed(html)
    observed = observed_at or datetime.now().astimezone()
    listings: list[ListingCreate] = []
    for card in parser.cards:
        source_url = canonical_source_url(ENYTIN_ROOT, card.get("source_url", ""))
        source_listing_id = _listing_id(card, source_url)
        title = " ".join(card.get("title", "").split())
        asking_price = parse_ngn_price(card.get("asking_price"))
        raw_category = " ".join(card.get("category", "").split()).casefold()
        category = ENYTIN_CATEGORY_MAP.get(raw_category)
        raw_location = " ".join(card.get("location", "").split())
        if not source_listing_id or not title or not asking_price or not category or not raw_location:
            continue
        location, state, city = split_location(raw_location)
        listings.append(
            ListingCreate(
                source_id="enytinplus",
                source_listing_id=source_listing_id,
                title=title[:500],
                category=category,
                asking_price=asking_price,
                currency="NGN",
                location=location,
                state=state,
                city=city,
                source_url=source_url,
                condition=" ".join(card.get("condition", "").split())[:80] or None,
                observed_at=observed,
            )
        )
    return listings


class EnytinPlusConnector(MarketplaceConnector):
    source_key = "enytinplus"
    supported_access_methods = frozenset({"authorized_web"})

    def __init__(self, config: ConnectorConfig):
        if config.access_method != "authorized_web":
            raise ValueError("EnytinPlus collection requires authorized web access.")
        super().__init__(config)
        self._robots_checked = False
        self._robots_allowed = False

    async def healthcheck(self) -> bool:
        self._robots_allowed = await robots_allows(
            self,
            f"{ENYTIN_ROOT}/robots.txt",
            ENYTIN_SHOP_URL,
        )
        self._robots_checked = True
        return self._robots_allowed

    async def discover_listings(
        self, since: datetime | None
    ) -> AsyncIterator[ListingCreate]:
        if not self._robots_checked and not await self.healthcheck():
            raise RuntimeError("EnytinPlus robots.txt blocks the approved shop page.")
        if not self._robots_allowed:
            raise RuntimeError("EnytinPlus robots.txt blocks the approved shop page.")

        response = await self.request("GET", ENYTIN_SHOP_URL)
        for listing in parse_enytin_cards(response.text):
            if listing.category not in self.config.permitted_categories:
                continue
            if since and listing.observed_at and listing.observed_at < since:
                continue
            yield scoped_listing(listing, self.config)
