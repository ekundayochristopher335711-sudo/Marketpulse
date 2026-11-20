import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from backend.app.models import CollectionRun, Listing, MarketplaceSource, PriceObservation
from backend.app.services.analytics import build_market_overview


class AnalyticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(self.engine)
        self.now = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_empty_database_returns_zeroed_observed_metrics(self) -> None:
        with Session(self.engine) as session:
            result = build_market_overview(session, period_days=30, now=self.now)

        self.assertEqual(result.total_listings, 0)
        self.assertEqual(result.active_listings, 0)
        self.assertEqual(result.categories, [])
        self.assertEqual(result.price_reductions, 0)
        self.assertIsNone(result.collection_success_rate_percent)

    def test_overview_uses_listing_history_and_labels_momentum_as_supply(self) -> None:
        with Session(self.engine) as session:
            session.add(
                MarketplaceSource(
                    source_key="jiji",
                    name="Jiji Nigeria",
                    access_method="feed",
                    permission_status="approved",
                    enabled=True,
                )
            )
            phone = Listing(
                source_id="jiji",
                source_listing_id="phone-1",
                title="Phone 1",
                category="Phones",
                asking_price=100000,
                currency="NGN",
                location="Ikeja, Lagos",
                state="Lagos",
                city="Ikeja",
                source_name="Jiji Nigeria",
                first_discovered_at=self.now - timedelta(days=2),
                last_observed_at=self.now,
                observed_at=self.now,
            )
            phone_2 = Listing(
                source_id="jiji",
                source_listing_id="phone-2",
                title="Phone 2",
                category="Phones",
                asking_price=200000,
                currency="NGN",
                location="Abuja",
                state="FCT",
                city="Abuja",
                source_name="Jiji Nigeria",
                first_discovered_at=self.now - timedelta(days=10),
                last_observed_at=self.now,
                observed_at=self.now,
            )
            laptop = Listing(
                source_id="jiji",
                source_listing_id="laptop-1",
                title="Laptop",
                category="Computers",
                asking_price=300000,
                currency="NGN",
                location="Lagos",
                state="Lagos",
                city="Lagos",
                source_name="Jiji Nigeria",
                first_discovered_at=self.now - timedelta(days=1),
                last_observed_at=self.now,
                observed_at=self.now,
            )
            old_listing = Listing(
                source_id="jiji",
                source_listing_id="old-1",
                title="Old listing",
                category="Phones",
                asking_price=50000,
                currency="NGN",
                location="Kano",
                source_name="Jiji Nigeria",
                listing_status="expired",
                first_discovered_at=self.now - timedelta(days=40),
                last_observed_at=self.now - timedelta(days=40),
                observed_at=self.now - timedelta(days=40),
            )
            session.add_all([phone, phone_2, laptop, old_listing])
            session.flush()
            session.add_all(
                [
                    PriceObservation(
                        listing_id=phone.id,
                        asking_price=150000,
                        observed_at=self.now - timedelta(days=1),
                    ),
                    PriceObservation(
                        listing_id=phone.id,
                        asking_price=100000,
                        observed_at=self.now,
                    ),
                    PriceObservation(
                        listing_id=laptop.id,
                        asking_price=280000,
                        observed_at=self.now - timedelta(days=1),
                    ),
                    PriceObservation(
                        listing_id=laptop.id,
                        asking_price=300000,
                        observed_at=self.now,
                    ),
                    PriceObservation(
                        listing_id=old_listing.id,
                        asking_price=100000,
                        observed_at=self.now - timedelta(days=2),
                    ),
                    PriceObservation(
                        listing_id=old_listing.id,
                        asking_price=50000,
                        observed_at=self.now - timedelta(days=1),
                    ),
                ]
            )
            session.add_all(
                [
                    CollectionRun(
                        source_key="jiji",
                        status="completed",
                        completed_at=self.now,
                    ),
                    CollectionRun(
                        source_key="jiji",
                        status="failed",
                        completed_at=self.now,
                    ),
                ]
            )
            session.commit()

            result = build_market_overview(session, period_days=14, now=self.now)

        self.assertEqual(result.total_listings, 4)
        self.assertEqual(result.active_listings, 3)
        self.assertEqual(result.median_asking_price_ngn, 200000)
        self.assertEqual(result.newly_discovered_in_period, 3)
        self.assertEqual(result.enabled_sources, 1)
        self.assertEqual(result.price_reductions, 1)
        self.assertEqual(result.price_increases, 1)
        self.assertEqual(result.collection_success_rate_percent, 50)
        phones = next(item for item in result.categories if item.category == "Phones")
        self.assertEqual(phones.active_listings, 2)
        self.assertEqual(phones.median_asking_price_ngn, 150000)
        phone_momentum = next(
            item for item in result.listing_momentum if item.category == "Phones"
        )
        self.assertEqual(phone_momentum.signal, "stable_listing_activity")
        self.assertIn("Listing counts measure observed supply", result.limitations[0])

