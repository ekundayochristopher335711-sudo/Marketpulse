from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser
import re
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from ..schemas import ListingCreate
from .base import COLLECTOR_USER_AGENT, ConnectorConfig, MarketplaceConnector

MAX_LISTING_PRICE_NGN = 10_000_000_000


def parse_ngn_price(value: object) -> int | None:
    """Parse a displayed naira amount while rejecting contact/POA prices."""
    if value is None:
        return None
    # A price range such as "₦80,000 - ₦100,000" is not one asking price.
    # Parse one grouped number and skip ambiguous text instead of concatenating
    # both amounts into an unrealistic value.
    matches = re.findall(r"(?<!\d)(?:\d{1,3}(?:[ ,]\d{3})+|\d+)(?!\d)", str(value))
    if len(matches) != 1:
        return None
    amount = int(re.sub(r"\D", "", matches[0]))
    if amount <= 0 or amount > MAX_LISTING_PRICE_NGN:
        return None
    return amount


def split_location(value: str) -> tuple[str, str | None, str | None]:
    parts = [part.strip() for part in value.split(",") if part.strip()]
    location = ", ".join(parts)[:200] or "Nigeria"
    if len(parts) == 1:
        return location, parts[0][:100], None
    return location, parts[-1][:100], parts[0][:100]


def canonical_source_url(root: str, href: str) -> str | None:
    parsed = urlsplit(urljoin(root, href))
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit(("https", parsed.hostname.casefold(), path, "", ""))


def scoped_listing(listing: ListingCreate, config: ConnectorConfig) -> ListingCreate:
    """Apply the source's approved field scope before handing data to ingestion."""
    values: dict[str, Any] = {}
    for field in config.permitted_fields:
        if field in listing.model_fields_set:
            values[field] = getattr(listing, field)
    return ListingCreate(source_id=listing.source_id, **values)


async def robots_allows(
    connector: MarketplaceConnector,
    robots_url: str,
    target_url: str,
) -> bool:
    response = await connector.request("GET", robots_url)
    if len(response.content) > 256_000:
        return False
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(response.text.splitlines())
    return parser.can_fetch(COLLECTOR_USER_AGENT, target_url)


class EnytinCardParser(HTMLParser):
    """Parser for the public EnytinPlus shop cards (no seller/contact fields)."""

    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

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
            if tag == "article" and "enp-card" in classes:
                self.card = {}
                self.depth = 1
            return

        if tag not in self.VOID:
            self.depth += 1
        if attributes.get("data-product-id"):
            self.card.setdefault("source_listing_id", attributes["data-product-id"] or "")
        href = attributes.get("href") or ""
        if href and "/product/" in href:
            self.card.setdefault("source_url", href)

        targets = (
            ("enp-card__cat", "category"),
            ("enp-card__price", "asking_price"),
            ("enp-card__where", "location"),
            ("enp-card__title", "title"),
            ("enp-card__badge", "condition"),
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
        if tag == "article" and self.depth == 1:
            self.cards.append(self.card)
            self.card = None
            self.depth = 0
            return
        if tag not in self.VOID:
            self.depth = max(1, self.depth - 1)


class JaxCardParser(HTMLParser):
    """Parser for public Jax ad cards on /ads and /ads/{category}."""

    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[dict[str, str]] = []
        self.card: dict[str, str] | None = None
        self.depth = 0
        self.paragraph_index = 0
        self.capture_depth: int | None = None
        self.capture_field: str | None = None
        self.capture_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if self.card is None:
            href = attributes.get("href") or ""
            if tag == "a" and href.startswith("/ad-details/"):
                self.card = {"source_url": href}
                self.depth = 1
                self.paragraph_index = 0
            return
        if tag not in self.VOID:
            self.depth += 1
        if tag == "p":
            self.capture_depth = self.depth
            self.capture_field = f"p{self.paragraph_index}"
            self.paragraph_index += 1
            self.capture_parts = []

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
        if tag not in self.VOID:
            self.depth = max(1, self.depth - 1)


class NaijaCardParser(HTMLParser):
    """Parser for the public listing cards on the NaijaBargains homepage."""

    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

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
        onclick = attributes.get("onclick") or ""
        if self.card is None:
            if tag == "article" and "lcard" in classes and "lcard-sample" not in classes:
                match = re.search(r"openLst\(['\"]([^'\"]+)['\"]\)", onclick)
                if match:
                    self.card = {"source_listing_id": match.group(1)}
                    self.depth = 1
            return
        if tag not in self.VOID:
            self.depth += 1
        targets = (("l-title", "title"), ("l-price", "asking_price"), ("l-meta", "location"))
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
        if tag == "article" and self.depth == 1:
            self.cards.append(self.card)
            self.card = None
            self.depth = 0
            return
        if tag not in self.VOID:
            self.depth = max(1, self.depth - 1)


def observed_now() -> datetime:
    return datetime.now(timezone.utc)
