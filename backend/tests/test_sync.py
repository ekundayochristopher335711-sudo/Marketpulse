from datetime import datetime, timezone
import json
import unittest

import httpx
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from backend.app.models import Listing
from backend.app.sync import sync_once


class HostedSyncTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(self.engine)
        self.stamp = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)
        with Session(self.engine) as session:
            for key, is_demo, category in [("real", False, "Phones"), ("demo", True, "Phones"), ("outside-scope", False, "Vehicles")]:
                session.add(Listing(
                    source_id="jiji", source_listing_id=key, title=key,
                    category=category, asking_price=100000, location="Lagos",
                    source_name="Jiji Nigeria", observed_at=self.stamp,
                    last_observed_at=self.stamp, is_demo=is_demo,
                    description="Not included in this source's field scope",
                ))
            session.commit()
        self.posts = []
        self.remote = []
        self.ingest_status = 201
        self.enabled = True

    def tearDown(self):
        self.engine.dispose()

    def handler(self, request):
        if request.url.path == "/api/sources":
            return httpx.Response(200, json=[{
                "source_key": "jiji", "name": "Jiji Nigeria", "enabled": self.enabled,
                "permission_status": "approved", "permitted_categories": ["Phones"],
                "permitted_fields": ["title", "category", "asking_price", "location", "source_listing_id", "observed_at"],
            }])
        if request.method == "GET" and request.url.path == "/api/listings":
            return httpx.Response(200, json={"items": self.remote, "total": len(self.remote)})
        if request.method == "POST" and request.url.path == "/api/listings":
            self.posts.append(json.loads(request.content))
            return httpx.Response(self.ingest_status, json={})
        raise AssertionError(f"Unexpected request: {request.method} {request.url.path}")

    def run_sync(self):
        with httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(self.handler)) as client:
            return sync_once(client, self.engine)

    def test_uploads_only_real_approved_fields_and_preserves_observation_time(self):
        result = self.run_sync()
        self.assertEqual(result["created"], 1)
        self.assertEqual(len(self.posts), 1)
        payload = self.posts[0]
        self.assertEqual(payload["source_listing_id"], "real")
        self.assertNotIn("description", payload)
        self.assertEqual(datetime.fromisoformat(payload["observed_at"].replace("Z", "+00:00")).replace(tzinfo=timezone.utc), self.stamp)

    def test_does_not_create_duplicate_observations_when_record_is_unchanged(self):
        self.remote = [{"source_id": "jiji", "source_listing_id": "real", "source_url": None, "asking_price": 100000, "last_observed_at": "2026-11-23T10:00:00Z"}]
        result = self.run_sync()
        self.assertEqual(result["unchanged"], 1)
        self.assertEqual(self.posts, [])

    def test_disabled_hosted_source_is_not_uploaded(self):
        self.enabled = False
        self.assertEqual(self.run_sync()["created"], 0)
        self.assertEqual(self.posts, [])

    def test_invalid_ingestion_token_stops_the_batch(self):
        self.ingest_status = 401
        with self.assertRaisesRegex(RuntimeError, "ingestion token"):
            self.run_sync()


if __name__ == "__main__":
    unittest.main()
