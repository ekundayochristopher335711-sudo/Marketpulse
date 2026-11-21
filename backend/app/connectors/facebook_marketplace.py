from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any, AsyncIterator

import httpx

from .base import ConnectorConfig, MarketplaceConnector
from .utils import parse_ngn_price, scoped_listing, split_location
from ..schemas import ListingCreate

FACEBOOK_API_ROOT = "https://graph.facebook.com"
FACEBOOK_DEFAULT_VERSION = "v24.0"
FACEBOOK_FIELDS = ",".join(
    (
        "id",
        "listing_details.title",
        "listing_details.location",
        "listing_details.category",
        "listing_details.price.amount",
        "listing_details.price.currency",
        "listing_details.condition",
        "modified_time",
    )
)


def _nested(value: Any, *keys: str) -> Any:
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _facebook_category(value: object) -> str:
    category = str(value or "").casefold()
    if "vehicle" in category or "car" in category:
        return "Vehicles"
    if "phone" in category or "tablet" in category:
        return "Phones & Tablets"
    if "electronic" in category or "computer" in category:
        return "Electronics"
    if "home" in category or "garden" in category or "furniture" in category:
        return "Home & Garden"
    if "fashion" in category or "beauty" in category or "clothing" in category:
        return "Fashion & Beauty"
    if "property" in category or "real estate" in category:
        return "Property"
    if "job" in category:
        return "Jobs"
    if "service" in category:
        return "Services"
    if "sport" in category or "hobby" in category:
        return "Leisure & Activities"
    return "Electronics"


def _facebook_location(value: object) -> str:
    if isinstance(value, str):
        return value.strip()[:200] or "Nigeria"
    if isinstance(value, dict):
        parts = [str(value.get(key) or "").strip() for key in ("city", "state", "country")]
        return ", ".join(part for part in parts if part)[:200] or "Nigeria"
    return "Nigeria"


def parse_facebook_listings(
    payload: dict[str, Any],
    observed_at: datetime | None = None,
    since: datetime | None = None,
) -> list[ListingCreate]:
    observed = observed_at or datetime.now(timezone.utc)
    listings: list[ListingCreate] = []
    for item in payload.get("data", []):
        if not isinstance(item, dict):
            continue
        details = item.get("listing_details") if isinstance(item.get("listing_details"), dict) else item
        title = str(_nested(details, "title") or "").strip()
        price = _nested(details, "price", "amount")
        currency = str(_nested(details, "price", "currency") or "NGN").upper()
        if currency != "NGN":
            continue
        asking_price = parse_ngn_price(price)
        source_id = str(item.get("id") or "").strip()
        modified_value = item.get("modified_time")
        modified_at: datetime | None = None
        if isinstance(modified_value, str):
            try:
                modified_at = datetime.fromisoformat(modified_value.replace("Z", "+00:00"))
            except ValueError:
                modified_at = None
        if since and modified_at and modified_at < since:
            continue
        if not title or not asking_price or not source_id:
            continue
        raw_location = _facebook_location(_nested(details, "location"))
        location, state, city = split_location(raw_location)
        listings.append(
            ListingCreate(
                source_id="facebook_marketplace",
                source_listing_id=source_id[:255],
                title=title[:500],
                category=_facebook_category(_nested(details, "category")),
                asking_price=asking_price,
                currency="NGN",
                location=location,
                state=state,
                city=city,
                condition=str(_nested(details, "condition") or "")[:80] or None,
                observed_at=observed,
            )
        )
    return listings


class FacebookMarketplaceConnector(MarketplaceConnector):
    source_key = "facebook_marketplace"
    supported_access_methods = frozenset({"api", "authorized_web"})

    def __init__(self, config: ConnectorConfig):
        if config.access_method not in self.supported_access_methods:
            raise ValueError("Facebook Marketplace collection requires Meta Content Library API access.")
        super().__init__(config)
        self._token = os.getenv("MARKETPULSE_FACEBOOK_ACCESS_TOKEN", "").strip()
        version = os.getenv("MARKETPULSE_FACEBOOK_API_VERSION", FACEBOOK_DEFAULT_VERSION).strip()
        api_root = os.getenv("MARKETPULSE_FACEBOOK_API_ROOT", FACEBOOK_API_ROOT).rstrip("/")
        self._endpoint = f"{api_root}/{version}/facebook/marketplace-listings/preview"

    async def healthcheck(self) -> bool:
        if not self._token:
            return False
        try:
            await self.request(
                "GET",
                self._endpoint,
                params={
                    "access_token": self._token,
                    "fields": "id",
                    "listing_countries": "NG",
                    "limit": "1",
                },
            )
        except httpx.HTTPError:
            return False
        return True

    async def discover_listings(
        self, since: datetime | None
    ) -> AsyncIterator[ListingCreate]:
        if not self._token:
            raise RuntimeError(
                "Facebook Marketplace needs MARKETPULSE_FACEBOOK_ACCESS_TOKEN from Meta Content Library."
            )
        params: dict[str, str] = {
            "access_token": self._token,
            "fields": FACEBOOK_FIELDS,
            "listing_countries": "NG",
            "sort": "newest_to_oldest",
            "limit": "50",
        }
        if since:
            params["since"] = str(int(since.timestamp()))
        response = await self.request("GET", self._endpoint, params=params)
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Facebook Marketplace response was not an object.")
        for listing in parse_facebook_listings(payload, since=since):
            if listing.category not in self.config.permitted_categories:
                continue
            yield scoped_listing(listing, self.config)
