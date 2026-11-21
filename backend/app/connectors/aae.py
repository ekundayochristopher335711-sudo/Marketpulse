from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import AsyncIterator, Any

from .base import ConnectorConfig, MarketplaceConnector
from .utils import canonical_source_url, parse_ngn_price, robots_allows, scoped_listing, split_location
from ..schemas import ListingCreate

AAE_ROOT = "https://aae.ng"
AAE_APP_ID = "6a7e48a71213701f105400b3"
AAE_PUBLIC_VEHICLES_URL = f"{AAE_ROOT}/api/apps/{AAE_APP_ID}/functions/getPublicVehicles"


def _title_from_slug(slug: str) -> str:
    value = re.sub(r"-[A-Z0-9]{5,}$", "", slug)
    return " ".join(part.capitalize() for part in value.split("-") if part)


def _aae_location(item: dict[str, Any]) -> str:
    description = str(item.get("description") or "")
    match = re.search(r"\bLocation:\s*([^\n.]+)", description, re.IGNORECASE)
    if match:
        value = match.group(1).strip(" ,")
        if value:
            return value[:200]
    return "Nigeria"


def _parse_source_time(item: dict[str, Any]) -> datetime | None:
    value = item.get("published_at") or item.get("created_date")
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_aae_vehicles(
    payload: dict[str, Any],
    observed_at: datetime | None = None,
    since: datetime | None = None,
) -> list[ListingCreate]:
    observed = observed_at or datetime.now(timezone.utc)
    listings: list[ListingCreate] = []
    for item in payload.get("vehicles", []):
        if not isinstance(item, dict):
            continue
        if item.get("status") not in {None, "active"} or item.get("sold_at") or item.get("demo"):
            continue
        published_at = _parse_source_time(item)
        if since and published_at and published_at < since:
            continue
        price = parse_ngn_price(item.get("price"))
        slug = str(item.get("slug") or "").strip()
        source_id = str(item.get("id") or "").strip()
        if not price or not slug or not source_id:
            continue
        source_url = canonical_source_url(AAE_ROOT, f"/vehicle/{slug}")
        raw_location = _aae_location(item)
        location, state, city = split_location(raw_location)
        condition = str(item.get("condition") or "").replace("_", " ").title()[:80] or None
        listings.append(
            ListingCreate(
                source_id="aae",
                source_listing_id=source_id[:255],
                title=_title_from_slug(slug)[:500],
                category="Vehicles",
                asking_price=price,
                currency="NGN",
                location=location,
                state=state,
                city=city,
                source_url=source_url,
                condition=condition,
                observed_at=observed,
            )
        )
    return listings


class AaeConnector(MarketplaceConnector):
    source_key = "aae"
    supported_access_methods = frozenset({"authorized_web"})

    def __init__(self, config: ConnectorConfig):
        if config.access_method != "authorized_web":
            raise ValueError("AAE.NG collection requires authorized web access.")
        super().__init__(config)
        self._robots_checked = False
        self._robots_allowed = False

    async def healthcheck(self) -> bool:
        self._robots_allowed = await robots_allows(
            self,
            f"{AAE_ROOT}/robots.txt",
            f"{AAE_ROOT}/cars",
        )
        self._robots_checked = True
        return self._robots_allowed

    async def discover_listings(
        self, since: datetime | None
    ) -> AsyncIterator[ListingCreate]:
        if not self._robots_checked and not await self.healthcheck():
            raise RuntimeError("AAE.NG robots.txt blocks the public vehicle page.")
        if not self._robots_allowed:
            raise RuntimeError("AAE.NG robots.txt blocks the public vehicle page.")

        response = await self.request(
            "POST",
            AAE_PUBLIC_VEHICLES_URL,
            json={"sort": "-created_date", "paginate": True, "page": 1, "page_size": 24},
        )
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("AAE.NG public vehicle response was not an object.")
        for listing in parse_aae_vehicles(payload, since=since):
            if listing.category not in self.config.permitted_categories:
                continue
            yield scoped_listing(listing, self.config)
