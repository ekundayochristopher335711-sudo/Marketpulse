from __future__ import annotations

from datetime import datetime
import re
from typing import AsyncIterator, Iterable

from .base import ConnectorConfig, MarketplaceConnector
from .utils import NaijaCardParser, parse_ngn_price, robots_allows, scoped_listing, split_location
from ..schemas import ListingCreate

NAIJA_ROOT = "https://naijabargains.com"


def classify_naija_title(title: str) -> str:
    value = title.casefold()
    if any(term in value for term in ("iphone", "phone", "samsung", "tecno", "infinix", "laptop", "router", "television")):
        return "Phones & Tablets"
    if any(term in value for term in ("toyota", "honda", "lexus", "mercedes", "car", "vehicle", "suv", "bike", "motorcycle")):
        return "Vehicles"
    if any(term in value for term in ("dog", "cat", "puppy", "kitten", "pet")):
        return "Animals & Pets"
    if any(term in value for term in ("sofa", "chair", "table", "fridge", "refrigerator", "fan", "solar", "furniture")):
        return "Home & Garden"
    if any(term in value for term in ("dress", "shoe", "bag", "ankara", "fashion")):
        return "Fashion & Beauty"
    if any(term in value for term in ("rice", "food", "farm", "poultry", "feed", "fish", "agro")):
        return "Agriculture & Foodstuff"
    return "Electronics"


def _clean_naija_location(value: str) -> str:
    value = re.split(r"\s+Escrow\b", value, maxsplit=1, flags=re.IGNORECASE)[0]
    value = re.split(r"\s+\d{1,2}\s+[A-Za-z]{3,}\b", value, maxsplit=1)[0]
    return re.sub(r"\s*(?:\||\u00b7|-)+\s*$", "", value).strip()


def normalize_naija_records(
    records: Iterable[dict[str, str]],
    observed_at: datetime | None = None,
) -> list[ListingCreate]:
    observed = observed_at or datetime.now().astimezone()
    listings: list[ListingCreate] = []
    seen_ids: set[str] = set()
    for card in records:
        title = " ".join(card.get("title", "").split())
        asking_price = parse_ngn_price(card.get("asking_price"))
        raw_location = _clean_naija_location(" ".join(card.get("location", "").split()))
        source_listing_id = card.get("source_listing_id", "").strip()[:255]
        if not title or not asking_price or not raw_location or not source_listing_id:
            continue
        if source_listing_id in seen_ids:
            continue
        seen_ids.add(source_listing_id)
        location, state, city = split_location(raw_location)
        listings.append(
            ListingCreate(
                source_id="naijabargains",
                source_listing_id=source_listing_id,
                title=title[:500],
                category=classify_naija_title(title),
                asking_price=asking_price,
                currency="NGN",
                location=location,
                state=state,
                city=city,
                observed_at=observed,
            )
        )
    return listings


def parse_naija_cards(
    html: str,
    observed_at: datetime | None = None,
) -> list[ListingCreate]:
    parser = NaijaCardParser()
    parser.feed(html)
    return normalize_naija_records(parser.cards, observed_at)


class NaijaBargainsConnector(MarketplaceConnector):
    source_key = "naijabargains"
    supported_access_methods = frozenset({"authorized_web"})

    def __init__(self, config: ConnectorConfig):
        if config.access_method != "authorized_web":
            raise ValueError("NaijaBargains collection requires authorized web access.")
        super().__init__(config)
        self._robots_checked = False
        self._robots_allowed = False

    async def healthcheck(self) -> bool:
        self._robots_allowed = await robots_allows(
            self,
            f"{NAIJA_ROOT}/robots.txt",
            f"{NAIJA_ROOT}/",
        )
        self._robots_checked = True
        return self._robots_allowed

    async def discover_listings(
        self, since: datetime | None
    ) -> AsyncIterator[ListingCreate]:
        if not self._robots_checked and not await self.healthcheck():
            raise RuntimeError("NaijaBargains robots.txt blocks the public listing page.")
        if not self._robots_allowed:
            raise RuntimeError("NaijaBargains robots.txt blocks the public listing page.")

        # The public homepage is rendered by the site's own client. Use that
        # public page in an authorized browser session instead of calling the
        # site's /api/ path, which its robots file disallows for crawlers.
        try:
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError
            from playwright.async_api import async_playwright
        except ImportError as error:
            raise RuntimeError(
                "NaijaBargains browser collection requires the Python Playwright package."
            ) from error

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context(ignore_https_errors=False)
                try:
                    page = await context.new_page()
                    await self.rate_limiter.wait()
                    try:
                        response = await page.goto(
                            f"{NAIJA_ROOT}/",
                            wait_until="domcontentloaded",
                            timeout=30_000,
                        )
                        if response is None or response.status >= 300 or page.url != f"{NAIJA_ROOT}/":
                            raise RuntimeError("NaijaBargains returned an unexpected browser response.")
                        cards = page.locator(".lcard:not(.lcard-sample)")
                        try:
                            await cards.first.wait_for(state="attached", timeout=15_000)
                        except PlaywrightTimeoutError:
                            records: list[dict[str, str]] = []
                            cards = None
                        records: list[dict[str, str]] = []
                        if cards is not None:
                            for index in range(await cards.count()):
                                card = cards.nth(index)
                                onclick = await card.get_attribute("onclick") or ""
                                match = re.search(r"openLst\(['\"]([^'\"]+)['\"]\)", onclick)
                                if not match:
                                    continue
                                records.append(
                                    {
                                        "source_listing_id": match.group(1),
                                        "title": (await card.locator(".l-title").inner_text()).strip(),
                                        "asking_price": (await card.locator(".l-price").inner_text()).strip(),
                                        "location": (await card.locator(".l-meta").inner_text()).strip(),
                                    }
                                )
                    except PlaywrightTimeoutError as error:
                        raise RuntimeError("NaijaBargains browser request timed out.") from error
                finally:
                    await context.close()
            finally:
                await browser.close()

        for listing in normalize_naija_records(records):
            if listing.category not in self.config.permitted_categories:
                continue
            yield scoped_listing(listing, self.config)
