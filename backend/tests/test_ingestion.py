import json
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from backend.app import main
from backend.app.database import get_session
from backend.app.models import MarketplaceSource, PriceObservation

INGEST_TOKEN = "test-ingestion-token-" + ("x" * 32)
ADMIN_TOKEN = "test-admin-token-" + ("y" * 32)


class IngestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            session.add(
                MarketplaceSource(
                    source_key="jiji",
                    name="Jiji Nigeria",
                    access_method="feed",
                    permission_status="approved",
                    enabled=True,
                    permission_reference="test-only authorization reference",
                    permitted_categories_json=json.dumps(["Phones"]),
                    permitted_fields_json=json.dumps(
                        [
                            "title",
                            "category",
                            "asking_price",
                            "location",
                            "source_listing_id",
                            "source_url",
                        ]
                    ),
                )
            )
            session.commit()

        def override_session():
            with Session(self.engine) as session:
                yield session

        self.previous_override = main.app.dependency_overrides.get(get_session)
        main.app.dependency_overrides[get_session] = override_session
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        if self.previous_override is None:
            main.app.dependency_overrides.pop(get_session, None)
        else:
            main.app.dependency_overrides[get_session] = self.previous_override
        self.engine.dispose()

    def test_ingestion_requires_configured_secret_and_rejects_bad_secret(self) -> None:
        with patch.object(main, "INGESTION_TOKEN", ""):
            with self.assertRaises(HTTPException) as missing:
                main.require_ingestion_token("anything")
        self.assertEqual(missing.exception.status_code, 503)

        with patch.object(main, "INGESTION_TOKEN", INGEST_TOKEN):
            with self.assertRaises(HTTPException) as invalid:
                main.require_ingestion_token("wrong-token")
        self.assertEqual(invalid.exception.status_code, 401)

    def test_public_source_catalog_exposes_status_but_not_permission_reference(self) -> None:
        response = self.client.get("/api/sources")

        self.assertEqual(response.status_code, 200, response.text)
        source = next(item for item in response.json() if item["source_key"] == "jiji")
        self.assertTrue(source["permission_reference_present"])
        self.assertTrue(source["enabled"])
        self.assertTrue(source["connector_available"])
        self.assertNotIn("test-only authorization reference", response.text)

    def test_read_token_protects_read_endpoints_when_configured(self) -> None:
        with patch.object(main, "READ_TOKEN", "read-token-" + ("z" * 32)):
            unauthorized = self.client.get("/api/sources")
            authorized = self.client.get(
                "/api/sources",
                headers={"Authorization": "Bearer read-token-" + ("z" * 32)},
            )
        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(authorized.status_code, 200, authorized.text)

    def test_source_configuration_requires_admin_and_explicit_permission(self) -> None:
        payload = {
            "access_method": "authorized_web",
            "permission_status": "approved",
            "enabled": False,
            "minimum_interval_seconds": 300,
            "permitted_categories": ["Phones"],
            "permitted_fields": [
                "title",
                "category",
                "asking_price",
                "location",
                "source_listing_id",
            ],
            "permission_reference": "Partner agreement reference",
            "retention_days": 90,
        }
        with patch.object(main, "ADMIN_TOKEN", ADMIN_TOKEN):
            unauthorized = self.client.put("/api/admin/sources/jiji", json=payload)
            self.assertEqual(unauthorized.status_code, 401)

            approved = self.client.put(
                "/api/admin/sources/jiji",
                json=payload,
                headers={"X-Admin-Token": ADMIN_TOKEN},
            )
            self.assertEqual(approved.status_code, 200, approved.text)
            self.assertEqual(approved.json()["permission_status"], "approved")
            self.assertTrue(approved.json()["permission_reference_present"])
            self.assertFalse(approved.json()["enabled"])

            audit = self.client.get(
                "/api/admin/audit",
                headers={"X-Admin-Token": ADMIN_TOKEN},
            )
            self.assertEqual(audit.status_code, 200, audit.text)
            self.assertEqual(audit.json()[0]["action"], "update_marketplace_source")
            self.assertNotIn("Partner agreement reference", audit.text)

            unsupported_method = self.client.put(
                "/api/admin/sources/jiji",
                json={**payload, "access_method": "api", "enabled": True},
                headers={"X-Admin-Token": ADMIN_TOKEN},
            )
            self.assertEqual(unsupported_method.status_code, 409)

            enabled = self.client.put(
                "/api/admin/sources/jiji",
                json={**payload, "enabled": True},
                headers={"X-Admin-Token": ADMIN_TOKEN},
            )
            self.assertEqual(enabled.status_code, 200, enabled.text)
            self.assertTrue(enabled.json()["enabled"])

            missing_reference = self.client.put(
                "/api/admin/sources/jiji",
                json={**payload, "permission_reference": None},
                headers={"X-Admin-Token": ADMIN_TOKEN},
            )
            self.assertEqual(missing_reference.status_code, 422)

    def test_ingestion_requires_approved_source_and_field_scope(self) -> None:
        payload = {
            "source_id": "jiji",
            "title": "Phone",
            "category": "Phones",
            "asking_price": 100000,
            "location": "Lagos",
            "source_listing_id": "item-1",
        }
        with patch.object(main, "INGESTION_TOKEN", INGEST_TOKEN):
            with Session(self.engine) as session:
                source = session.get(MarketplaceSource, 1)
                assert source is not None
                source.permission_status = "unknown"
                session.add(source)
                session.commit()

            denied = self.client.post(
                "/api/listings",
                json=payload,
                headers={"X-Ingestion-Token": INGEST_TOKEN},
            )
            self.assertEqual(denied.status_code, 403)

            with Session(self.engine) as session:
                source = session.get(MarketplaceSource, 1)
                assert source is not None
                source.permission_status = "approved"
                source.permitted_fields_json = json.dumps(["title", "category"])
                session.add(source)
                session.commit()

            denied_fields = self.client.post(
                "/api/listings",
                json=payload,
                headers={"X-Ingestion-Token": INGEST_TOKEN},
            )
            self.assertEqual(denied_fields.status_code, 403)

    def test_ingestion_requires_stable_listing_identity(self) -> None:
        payload = {
            "source_id": "jiji",
            "title": "Phone without identity",
            "category": "Phones",
            "asking_price": 100000,
            "location": "Lagos",
        }
        with patch.object(main, "INGESTION_TOKEN", INGEST_TOKEN):
            response = self.client.post(
                "/api/listings",
                json=payload,
                headers={"X-Ingestion-Token": INGEST_TOKEN},
            )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("source_listing_id or source_url", response.text)

    def test_ingestion_records_source_and_initial_price_observation(self) -> None:
        payload = {
            "source_id": "jiji",
            "title": "  iPhone 13 Pro ",
            "category": "Phones",
            "asking_price": 450000,
            "location": "Lagos",
            "source_listing_id": "item-1",
        }
        with patch.object(main, "INGESTION_TOKEN", INGEST_TOKEN):
            response = self.client.post(
                "/api/listings",
                json=payload,
                headers={"X-Ingestion-Token": INGEST_TOKEN},
            )
            self.assertEqual(response.status_code, 201, response.text)
            self.assertEqual(response.json()["source_id"], "jiji")
            self.assertEqual(response.json()["source_name"], "Jiji Nigeria")
            self.assertEqual(response.json()["normalized_title"], "iphone 13 pro")

            duplicate = self.client.post(
                "/api/listings",
                json=payload,
                headers={"X-Ingestion-Token": INGEST_TOKEN},
            )
            self.assertEqual(duplicate.status_code, 200)

            changed_price = {**payload, "asking_price": 430000}
            updated = self.client.post(
                "/api/listings",
                json=changed_price,
                headers={"X-Ingestion-Token": INGEST_TOKEN},
            )
            self.assertEqual(updated.status_code, 200)
            self.assertEqual(updated.json()["asking_price"], 430000)
            self.assertIsNotNone(updated.json()["last_price_update_at"])

        with Session(self.engine) as session:
            observations = session.exec(select(PriceObservation)).all()
            self.assertEqual(len(observations), 3)
            self.assertEqual(observations[-1].asking_price, 430000)

        listing_page = self.client.get("/api/listings?limit=10")
        self.assertEqual(listing_page.status_code, 200)
        self.assertEqual(listing_page.json()["total"], 1)
        history = self.client.get(
            f"/api/listings/{response.json()['id']}/price-history"
        )
        self.assertEqual(history.status_code, 200)
        self.assertEqual(
            [item["asking_price"] for item in history.json()],
            [450000, 450000, 430000],
        )
        self.assertEqual(history.json()[-1]["change_amount_ngn"], -20000)

    def test_canonical_url_deduplicates_tracking_variants_within_a_source(self) -> None:
        payload = {
            "source_id": "jiji",
            "title": "Phone",
            "category": "Phones",
            "asking_price": 100000,
            "location": "Lagos",
            "source_url": "https://JIJI.NG/ad/phone-1/?utm_source=feed&fbclid=track",
        }
        with patch.object(main, "INGESTION_TOKEN", INGEST_TOKEN):
            first = self.client.post(
                "/api/listings",
                json=payload,
                headers={"X-Ingestion-Token": INGEST_TOKEN},
            )
            second = self.client.post(
                "/api/listings",
                json={
                    **payload,
                    "asking_price": 95000,
                    "source_url": "https://jiji.ng/ad/phone-1",
                },
                headers={"X-Ingestion-Token": INGEST_TOKEN},
            )

        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(
            second.json()["canonical_url"],
            "https://jiji.ng/ad/phone-1",
        )
        with Session(self.engine) as session:
            listings = session.exec(select(main.Listing)).all()
            observations = session.exec(select(PriceObservation)).all()
        self.assertEqual(len(listings), 1)
        self.assertEqual(len(observations), 2)
