import unittest

from backend.app.connectors.aae import parse_aae_vehicles
from backend.app.connectors.enytinplus import parse_enytin_cards
from backend.app.connectors.facebook_marketplace import parse_facebook_listings
from backend.app.connectors.jax import parse_jax_cards
from backend.app.connectors.naijabargains import parse_naija_cards
from backend.app.connectors.registry import connector_registry


class MarketplaceConnectorParserTests(unittest.TestCase):
    def test_registry_has_every_approved_source(self) -> None:
        for source_key in (
            "aae",
            "enytinplus",
            "facebook_marketplace",
            "jax",
            "jiji",
            "naijabargains",
        ):
            self.assertTrue(connector_registry.available(source_key), source_key)

    def test_aae_parser_skips_poa_and_normalizes_vehicles(self) -> None:
        listings = parse_aae_vehicles(
            {
                "vehicles": [
                    {
                        "id": "veh-1",
                        "slug": "2023-toyota-corolla-asaba-C4MTUJ",
                        "price": 22500000,
                        "condition": "foreign_used",
                        "status": "active",
                        "description": "Location: Asaba, Delta State, Nigeria.",
                    },
                    {
                        "id": "veh-poa",
                        "slug": "2024-lexus-lx600-ajah-POA123",
                        "price": None,
                        "status": "active",
                    },
                ]
            }
        )

        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0].source_listing_id, "veh-1")
        self.assertEqual(listings[0].category, "Vehicles")
        self.assertEqual(listings[0].asking_price, 22500000)
        self.assertEqual(listings[0].location, "Asaba, Delta State, Nigeria")
        self.assertEqual(listings[0].source_url, "https://aae.ng/vehicle/2023-toyota-corolla-asaba-C4MTUJ")

    def test_enytin_parser_reads_public_card_fields(self) -> None:
        html = """
        <article class="enp-card">
          <a class="enp-card__media" href="https://nigeria.enytinplus.com/product/honda-pilot/"><span class="enp-card__badge">Used</span></a>
          <button data-product-id="37012"></button>
          <div class="enp-card__body">
            <span class="enp-card__cat">Vehicles</span>
            <h3 class="enp-card__title"><a href="/product/honda-pilot/">Honda pilot Ex</a></h3>
            <div class="enp-card__price">₦5,500,000</div>
            <div class="enp-card__meta"><span class="enp-card__where">Lagos</span></div>
          </div>
        </article>
        """

        listings = parse_enytin_cards(html)

        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0].source_listing_id, "37012")
        self.assertEqual(listings[0].title, "Honda pilot Ex")
        self.assertEqual(listings[0].category, "Vehicles")
        self.assertEqual(listings[0].asking_price, 5500000)
        self.assertEqual(listings[0].source_url, "https://nigeria.enytinplus.com/product/honda-pilot")

    def test_jax_parser_reads_stable_ad_url_and_id(self) -> None:
        html = """
        <a class="group border" href="/ad-details/iphone-13-pro">
          <p># 355,000</p>
          <p>iPhone 13 Pro</p>
          <p>Abuja, Abuja Federal Capital Territory, Nigeria</p>
        </a>
        """

        listings = parse_jax_cards(html)

        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0].source_listing_id, "iphone-13-pro")
        self.assertEqual(listings[0].category, "Phones & Tablets")
        self.assertEqual(listings[0].asking_price, 355000)
        self.assertEqual(listings[0].source_url, "https://jax.ng/ad-details/iphone-13-pro")

    def test_naija_parser_ignores_sample_card_and_keeps_real_id(self) -> None:
        html = """
        <article class="lcard lcard-sample"><div class="l-title">Example: Smartphone</div></article>
        <article class="lcard" onclick="openLst('l_93cb2fd2cd10')">
          <div class="lcard-body">
            <div class="l-title">Solar panels</div>
            <div class="l-price">₦25,000</div>
            <div class="l-meta">Lagos · 30 Oct Escrow</div>
          </div>
        </article>
        """

        listings = parse_naija_cards(html)

        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0].source_listing_id, "l_93cb2fd2cd10")
        self.assertEqual(listings[0].category, "Home & Garden")
        self.assertEqual(listings[0].asking_price, 25000)
        self.assertEqual(listings[0].location, "Lagos")

    def test_facebook_parser_accepts_meta_content_library_shape(self) -> None:
        listings = parse_facebook_listings(
            {
                "data": [
                    {
                        "id": "fb-1",
                        "listing_details": {
                            "title": "Used iPhone 13",
                            "location": "Lagos",
                            "category": "Phones",
                            "price": {"amount": 450000, "currency": "NGN"},
                            "condition": "used",
                        },
                    }
                ]
            }
        )

        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0].source_listing_id, "fb-1")
        self.assertEqual(listings[0].category, "Phones & Tablets")
        self.assertEqual(listings[0].asking_price, 450000)
        self.assertEqual(listings[0].location, "Lagos")


if __name__ == "__main__":
    unittest.main()
