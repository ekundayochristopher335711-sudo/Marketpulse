import asyncio
from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import patch

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from backend.app import worker
from backend.app.connectors.base import ConnectorConfig, MarketplaceConnector, RequestRateLimiter
from backend.app.models import CollectionRun, Listing, MarketplaceSource, PriceObservation
from backend.app.schemas import ListingCreate


class FakeConnector(MarketplaceConnector):
    source_key = "test_source"

    async def healthcheck(self) -> bool:
        return True

    async def discover_listings(self, since: datetime | None):
        yield ListingCreate(
            source_id="test_source",
            source_listing_id="one",
            title="Test phone",
            category="Phones",
            asking_price=200000,
            location="Lagos",
        )


class WorkerTests(unittest.TestCase):
    def test_slow_source_does_not_block_other_sources(self) -> None:
        async def scenario():
            other_started = asyncio.Event()

            async def execute(job):
                if job == 'slow':
                    await asyncio.wait_for(other_started.wait(), timeout=1)
                else:
                    other_started.set()

            with patch.object(worker, 'claim_due_jobs', return_value=['slow', 'fast']), patch.object(worker, 'execute_job', side_effect=execute):
                return await worker.run_due_jobs_once()

        self.assertEqual(asyncio.run(scenario()), 2)

    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(self.engine)
        now = datetime.now(timezone.utc)
        with Session(self.engine) as session:
            session.add(
                MarketplaceSource(
                    source_key="test_source",
                    name="Test source",
                    access_method="feed",
                    permission_status="approved",
                    enabled=True,
                    minimum_interval_seconds=300,
                    permitted_categories_json=json.dumps(["Phones"]),
                    permitted_fields_json=json.dumps(
                        ["source_listing_id", "title", "category", "asking_price", "location"]
                    ),
                    permission_reference="Fixture authorization",
                    next_run_at=now - timedelta(seconds=1),
                )
            )
            session.commit()

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_request_limiter_enforces_configured_spacing(self) -> None:
        limiter = RequestRateLimiter(0.03)

        async def make_two_requests() -> float:
            await limiter.wait()
            started = asyncio.get_running_loop().time()
            await limiter.wait()
            return asyncio.get_running_loop().time() - started

        elapsed = asyncio.run(make_two_requests())
        self.assertGreaterEqual(elapsed, 0.02)

    def test_worker_claims_due_job_and_persists_listing_history(self) -> None:
        now = datetime.now(timezone.utc)
        with (
            patch.object(worker, "engine", self.engine),
            patch.object(worker.connector_registry, "get", return_value=FakeConnector),
        ):
            jobs = worker.claim_due_jobs(now)
            self.assertEqual(len(jobs), 1)
            asyncio.run(worker.execute_job(jobs[0]))

        with Session(self.engine) as session:
            listing = session.exec(select(Listing)).one()
            observation = session.exec(select(PriceObservation)).one()
            run = session.get(CollectionRun, jobs[0].run_id)
            source = session.get(MarketplaceSource, 1)

        self.assertEqual(listing.source_id, "test_source")
        self.assertEqual(listing.asking_price, 200000)
        self.assertEqual(observation.asking_price, 200000)
        self.assertIsNotNone(run)
        self.assertEqual(run.status, "completed")
        self.assertEqual(run.discovered_count, 1)
        self.assertIsNotNone(source)
        self.assertIsNotNone(source.next_run_at)
        self.assertGreater(source.next_run_at, run.completed_at)

    def test_worker_does_not_claim_a_source_with_an_active_run(self) -> None:
        now = datetime.now(timezone.utc)
        with Session(self.engine) as session:
            session.add(CollectionRun(source_key="test_source", status="running", started_at=now))
            session.commit()

        with patch.object(worker, "engine", self.engine):
            jobs = worker.claim_due_jobs(now)

        self.assertEqual(jobs, [])

    def test_worker_skips_enabled_source_without_connector(self) -> None:
        now = datetime.now(timezone.utc)

        with patch.object(worker, "engine", self.engine), patch.object(
            worker.connector_registry, "get", return_value=None
        ):
            jobs = worker.claim_due_jobs(now)

        self.assertEqual(jobs, [])
        with Session(self.engine) as session:
            source = session.get(MarketplaceSource, 1)
            runs = session.exec(select(CollectionRun)).all()

        self.assertIsNotNone(source)
        assert source is not None
        next_run_at = source.next_run_at
        if next_run_at.tzinfo is None:
            next_run_at = next_run_at.replace(tzinfo=timezone.utc)
        self.assertGreater(next_run_at, now)
        self.assertEqual(runs, [])
