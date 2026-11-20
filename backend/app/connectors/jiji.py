from datetime import datetime, timezone
from html.parser import HTMLParser
import os
import re
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser
from typing import AsyncIterator

from .base import COLLECTOR_USER_AGENT, ConnectorConfig, MarketplaceConnector
from ..schemas import ListingCreate

JIJI_ROOT = "https://jiji.ng"
MAX_RESPONSE_BYTES = 2_000_000

CATEGORY_PATHS = {
    "Vehicles": "/vehicles",
    "Property": "/real-estate",
    "Phones & Tablets": "/mobile-phones-tablets",
    "Electronics": "/electronics",
    "Home & Garden": "/home-garden",
    "Fashion & Beauty": "/fashion-and-beauty",
    "Health & Beauty": "/health-and-beauty",
    "Services": "/services",
    "Repair & Construction": "/repair-and-construction",
    "Commercial Equipment & Tools": "/office-and-commercial-equipment-tools",
    "Leisure & Activities": "/hobbies-art-sport",
    "Babies & Kids": "/babies-and-kids",
    "Agriculture & Foodstuff": "/agriculture-and-foodstuff",
    "Animals & Pets": "/animals-and-pets",
    "Jobs": "/jobs",
    "Seeking Work - CVs": "/seeking-work-cvs",
    "Business & Industry": "/business-and-industry",
}


class _ListingCardParser(HTMLParser):
    VOID_ELEMENTS = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[dict[str, str]] = []
        self.card: dict[str, str] | None = None
        self.depth = 0
        self.capture_depth: int | None = None
        self.capture_field: str | None = None
        self.capture_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if self.card is None:
            if tag == "a" and "b-list-advert-base" in classes:
                self.card = {"href": attributes.get("href") or ""}
                self.depth = 1
            return

        if tag not in self.VOID_ELEMENTS:
            self.depth += 1
        if tag == "img" and attributes.get("alt"):
            self.card.setdefault("image_alt", attributes["alt"] or "")
        targets = (
            ("qa-advert-price", "asking_price"),
            ("qa-advert-title", "title"),
            ("b-advert-title-inner", "title"),
            ("b-list-advert-base__item-attr", "condition"),
            ("b-list-advert__region__text", "location"),
        )
        for class_name, field in targets:
            if class_name in classes and field not in self.card:
                self.capture_depth = self.depth
                self.capture_field = field
                self.capture_parts = []
                break

    def handle_data(self, data: str) -> None:
        if self.capture_field is not None:
            self.capture_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.card is None:
            return
        if self.capture_depth == self.depth and self.capture_field is not None:
            value = " ".join(" ".join(self.capture_parts).split())
            if value:
                self.card[self.capture_field] = value
            self.capture_depth = None
            self.capture_field = None
            self.capture_parts = []
        if tag == "a" and self.depth == 1:
            self.cards.append(self.card)
            self.card = None
            self.depth = 0
            return
        if tag not in self.VOID_ELEMENTS:
            self.depth = max(1, self.depth - 1)


def parse_listing_cards(
    html: str,
    category: str,
    observed_at: datetime | None = None,
) -> list[ListingCreate]:
    if category not in CATEGORY_PATHS:
        raise ValueError(f"Unsupported Jiji category: {category}")

    parser = _ListingCardParser()
    parser.feed(html)
    observed_time = observed_at or datetime.now(timezone.utc)
    listings: list[ListingCreate] = []
    for card in parser.cards:
        href = card.get("href", "")
        parsed = urlsplit(urljoin(JIJI_ROOT, href))
        if parsed.scheme != "https" or parsed.hostname not in {"jiji.ng", "www.jiji.ng"}:
            continue
        path = parsed.path
        listing_id = path.rsplit("/", 1)[-1]
        if not listing_id or len(listing_id) > 255:
            continue

        title = card.get("title") or card.get("image_alt", "")
        price_digits = re.sub(r"\D", "", card.get("asking_price", ""))
        location = card.get("location", "")
        if not title.strip() or not price_digits or not location:
            continue

        location_parts = [part.strip() for part in location.split(",") if part.strip()]
        source_url = urlunsplit(("https", parsed.netloc, path, "", ""))
        listings.append(
            ListingCreate(
                source_id="jiji",
                source_listing_id=listing_id,
                title=title[:500],
                category=category,
                asking_price=int(price_digits),
                currency="NGN",
                location=location[:200],
                state=location_parts[0][:100] if location_parts else None,
                city=location_parts[-1][:100] if len(location_parts) > 1 else None,
                source_url=source_url,
                condition=card.get("condition", "")[:80] or None,
                observed_at=observed_time,
            )
        )
    return listings


class JijiConnector(MarketplaceConnector):
    source_key = "jiji"
    supported_access_methods = frozenset({"authorized_web"})

    def __init__(self, config: ConnectorConfig):
        if config.access_method != "authorized_web":
            raise ValueError("Jiji collection requires explicitly authorized web access.")
        super().__init__(config)
        self._robots: RobotFileParser | None = None
        self._playwright_enabled = os.getenv("MARKETPULSE_JIJI_PLAYWRIGHT", "0").strip() == "1"
        self._storage_state = os.getenv("MARKETPULSE_PLAYWRIGHT_STORAGE_STATE", "").strip() or None

    async def healthcheck(self) -> bool:
        response = await self.request("GET", f"{JIJI_ROOT}/robots.txt")
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise RuntimeError("Jiji robots.txt exceeded the configured size limit.")
        lines = response.text.splitlines()
        if not any(line.strip().casefold().startswith("user-agent:") for line in lines):
            return False

        categories = tuple(dict.fromkeys(self.config.permitted_categories))
        if not categories:
            return False
        paths = []
        for category in categories:
            path = CATEGORY_PATHS.get(category)
            if path is None:
                raise ValueError(f"Unsupported approved Jiji category: {category}")
            paths.append(path)

        robots = RobotFileParser()
        robots.set_url(f"{JIJI_ROOT}/robots.txt")
        robots.parse(lines)
        self._robots = robots
        return any(
            robots.can_fetch(COLLECTOR_USER_AGENT, f"{JIJI_ROOT}{path}")
            for path in paths
        )

    async def discover_listings(
        self, since: datetime | None
    ) -> AsyncIterator[ListingCreate]:
        if self._robots is None and not await self.healthcheck():
            raise RuntimeError("Jiji robots.txt is unavailable or blocks all category pages.")

        categories = tuple(dict.fromkeys(self.config.permitted_categories))
        if not categories:
            raise ValueError("No Jiji categories are approved for collection.")

        if self._playwright_enabled:
            async for listing in self._discover_with_playwright(categories):
                yield listing
            return

        for category in categories:
            path = CATEGORY_PATHS.get(category)
            if path is None:
                raise ValueError(f"Unsupported approved Jiji category: {category}")
            if not self._robots or not self._robots.can_fetch(
                COLLECTOR_USER_AGENT, f"{JIJI_ROOT}{path}"
            ):
                continue

            response = await self.request("GET", f"{JIJI_ROOT}{path}")
            if 300 <= response.status_code < 400:
                raise RuntimeError(
                    "Jiji redirected a collection request; redirects are not followed."
                )
            if len(response.content) > MAX_RESPONSE_BYTES:
                raise RuntimeError("Jiji category response exceeded the configured size limit.")
            for listing in parse_listing_cards(response.text, category):
                authorized_fields = {
                    field: getattr(listing, field)
                    for field in self.config.permitted_fields
                    if field in listing.model_fields_set
                }
                yield ListingCreate(source_id=self.source_key, **authorized_fields)

    async def _discover_with_playwright(
        self, categories: tuple[str, ...]
    ) -> AsyncIterator[ListingCreate]:
        """Collect approved first-page results using a real browser."""
        try:
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError
            from playwright.async_api import async_playwright
        except ImportError as error:
            raise RuntimeError(
                "Playwright mode is enabled but the Python Playwright package is not installed."
            ) from error

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context_kwargs = {
                    "user_agent": COLLECTOR_USER_AGENT,
                    "ignore_https_errors": False,
                }
                if self._storage_state:
                    context_kwargs["storage_state"] = self._storage_state
                context = await browser.new_context(**context_kwargs)
                try:
                    page = await context.new_page()
                    for category in categories:
                        path = CATEGORY_PATHS.get(category)
                        if path is None:
                            raise ValueError(f"Unsupported Jiji category: {category}")
                        url = f"{JIJI_ROOT}{path}"
                        if not self._robots or not self._robots.can_fetch(COLLECTOR_USER_AGENT, url):
                            continue

                        await self.rate_limiter.wait()
                        try:
                            response = await page.goto(
                                url,
                                wait_until="domcontentloaded",
                                timeout=30_000,
                            )
                            if response is None:
                                raise RuntimeError("Jiji returned no browser response.")
                            if response.status >= 300:
                                raise RuntimeError(
                                    f"Jiji browser request returned HTTP {response.status}."
                                )
                            try:
                                await page.locator("a.b-list-advert-base").first.wait_for(
                                    state="attached", timeout=10_000
                                )
                            except PlaywrightTimeoutError:
                                pass
                            html = await page.content()
                        except PlaywrightTimeoutError as error:
                            raise RuntimeError(
                                f"Jiji browser request timed out for {category}."
                            ) from error

                        for listing in parse_listing_cards(html, category):
                            authorized_fields = {
                                field: getattr(listing, field)
                                for field in self.config.permitted_fields
                                if field in listing.model_fields_set
                            }
                            yield ListingCreate(source_id=self.source_key, **authorized_fields)
                finally:
                    await context.close()
            finally:
                await browser.close()
