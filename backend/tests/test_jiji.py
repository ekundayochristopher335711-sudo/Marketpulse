import asyncio
import os
import unittest
from unittest.mock import AsyncMock

os.environ["MARKETPULSE_JIJI_PLAYWRIGHT"] = "0"

from backend.app.connectors.base import ConnectorConfig
from backend.app.connectors.jiji import JijiConnector, parse_listing_cards

LISTING_HTML = """
<a class="b-list-advert-base qa-advert-list-item"
   href="/ikeja/mobile-phones/iphone-13-128-gb-black-AbCdEf0123456789.html?indexPosition=0">
  <div><img alt="Apple iPhone 13 128 GB Black"></div>
  <div class="qa-advert-price">₦ 450,000</div>
  <div class="b-advert-title-inner qa-advert-title">Apple iPhone 13 128 GB Black</div>
  <div class="b-list-advert-base__item-attr">Used</div>
  <span class="b-list-advert__region__text">Lagos, Ikeja</span>
  <div class="b-list-advert-base__description-text">Call 08000000000 for details</div>
</a>
"""

ROBOTS_TEXT = """User-agent: *
Disallow: /admin/
"""


def connector_config(fields: set[str] | None = None) -> ConnectorConfig:
    return ConnectorConfig(
        source_key="jiji",
        enabled=True,
        permission_status="approved",
        access_method="authorized_web",
        minimum_interval_seconds=30,
        permitted_categories=("Phones & Tablets",),
        permitted_fields=frozenset(
            fields
            or {
                "source_listing_id",
                "title",
                "category",
                "asking_price",
                "location",
                "source_url",
                "condition",
                "city",
                "state",
                "observed_at",
            }
        ),
        permission_reference="Fixture authorization",
    )


class JijiConnectorTests(unittest.TestCase):
    def test_parser_normalizes_public_listing_fields_and_removes_position_query(self) -> None:
        listings = parse_listing_cards(LISTING_HTML, "Phones & Tablets")

        self.assertEqual(len(listings), 1)
        listing = listings[0]
        self.assertEqual(listing.source_listing_id, "iphone-13-128-gb-black-AbCdEf0123456789.html")
        self.assertEqual(listing.title, "Apple iPhone 13 128 GB Black")
        self.assertEqual(listing.asking_price, 450000)
        self.assertEqual(listing.category, "Phones & Tablets")
        self.assertEqual(listing.state, "Lagos")
        self.assertEqual(listing.city, "Ikeja")
        self.assertEqual(
            listing.source_url,
            "https://jiji.ng/ikeja/mobile-phones/iphone-13-128-gb-black-AbCdEf0123456789.html",
        )
        self.assertNotIn("description", listing.model_fields_set)

    def test_discovery_checks_robots_and_only_emits_permitted_fields(self) -> None:
        connector = JijiConnector(
            connector_config(
                {
                    "source_listing_id",
                    "title",
                    "category",
                    "asking_price",
                    "location",
                }
            )
        )

        async def fake_request(method: str, url: str, **_: object):
            self.assertEqual(method, "GET")
            return type(
                "Response",
                (),
                {
                    "text": ROBOTS_TEXT if url.endswith("robots.txt") else LISTING_HTML,
                    "content": b"fixture",
                    "status_code": 200,
                },
            )()

        async def collect():
            async with connector:
                connector.request = AsyncMock(side_effect=fake_request)
                self.assertTrue(await connector.healthcheck())
                return [item async for item in connector.discover_listings(None)]

        listings = asyncio.run(collect())

        self.assertEqual(len(listings), 1)
        self.assertEqual(
            listings[0].model_fields_set,
            {"source_id", "source_listing_id", "title", "category", "asking_price", "location"},
        )

    def test_discovery_does_not_fetch_a_category_blocked_by_robots(self) -> None:
        connector = JijiConnector(connector_config())
        blocked_robots = "User-agent: *\nDisallow: /mobile-phones-tablets\n"

        async def fake_request(method: str, url: str, **_: object):
            return type(
                "Response",
                (),
                {"text": blocked_robots, "content": b"fixture", "status_code": 200},
            )()

        async def check():
            async with connector:
                connector.request = AsyncMock(side_effect=fake_request)
                return await connector.healthcheck()

        self.assertFalse(asyncio.run(check()))


if __name__ == "__main__":
    unittest.main()
