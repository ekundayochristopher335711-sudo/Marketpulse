import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import logging
import os

from sqlmodel import Session, or_, select

from .connectors.base import ConnectorConfig
from .connectors.registry import connector_registry
from .database import engine
from .models import CollectionRun, MarketplaceSource
from .services.ingestion import (
    SourceFieldNotPermittedError,
    SourceNotApprovedError,
    ingest_listing,
)

logger = logging.getLogger("marketpulse.worker")
POLL_INTERVAL_SECONDS = max(1, int(os.getenv("MARKETPULSE_WORKER_POLL_SECONDS", "10")))
STALE_RUN_SECONDS = 24 * 3600


@dataclass(frozen=True)
class CollectionJob:
    source_key: str
    run_id: int
    connector_config: ConnectorConfig
    since: datetime | None


def _connector_config(source: MarketplaceSource) -> ConnectorConfig:
    return ConnectorConfig(
        source_key=source.source_key,
        enabled=source.enabled,
        permission_status=source.permission_status,
        access_method=source.access_method,
        minimum_interval_seconds=source.minimum_interval_seconds,
        permitted_categories=tuple(json.loads(source.permitted_categories_json)),
        permitted_fields=frozenset(json.loads(source.permitted_fields_json)),
        permission_reference=source.permission_reference,
    )


def recover_interrupted_runs() -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=STALE_RUN_SECONDS)
    with Session(engine) as session:
        stale_runs = session.exec(
            select(CollectionRun).where(
                CollectionRun.status == "running",
                CollectionRun.started_at < cutoff,
            )
        ).all()
        for run in stale_runs:
            run.status = "failed"
            run.completed_at = datetime.now(timezone.utc)
            run.error_count += 1
            run.error_summary = "Worker restarted before the collection run completed."
            session.add(run)
            source = session.exec(
                select(MarketplaceSource).where(
                    MarketplaceSource.source_key == run.source_key
                )
            ).first()
            if source is not None:
                source.next_run_at = run.completed_at + timedelta(
                    seconds=source.minimum_interval_seconds
                )
                session.add(source)
        session.commit()
        return len(stale_runs)


def claim_due_jobs(now: datetime | None = None) -> list[CollectionJob]:
    current_time = now or datetime.now(timezone.utc)
    jobs: list[CollectionJob] = []
    with Session(engine) as session:
        sources = session.exec(
            select(MarketplaceSource)
            .where(
                MarketplaceSource.enabled.is_(True),
                MarketplaceSource.permission_status == "approved",
                or_(
                    MarketplaceSource.next_run_at.is_(None),
                    MarketplaceSource.next_run_at <= current_time,
                ),
                ~MarketplaceSource.source_key.in_(
                    select(CollectionRun.source_key).where(
                        CollectionRun.status == "running"
                    )
                ),
            )
            .with_for_update(skip_locked=True)
        ).all()

        for source in sources:
            connector_type = connector_registry.get(source.source_key)
            if connector_type is None:
                logger.error(
                    "Enabled source %s has no registered connector; no requests were made.",
                    source.source_key,
                )
                continue

            run = CollectionRun(
                source_key=source.source_key,
                status="running",
                started_at=current_time,
            )
            source.next_run_at = current_time + timedelta(
                seconds=source.minimum_interval_seconds
            )
            session.add(source)
            session.add(run)
            session.flush()
            jobs.append(
                CollectionJob(
                    source_key=source.source_key,
                    run_id=run.id,
                    connector_config=_connector_config(source),
                    since=source.last_success_at,
                )
            )
            session.commit()
    return jobs


async def execute_job(job: CollectionJob) -> None:
    discovered = 0
    updated = 0
    duplicates = 0
    errors = 0
    error_messages: list[str] = []

    try:
        connector_type = connector_registry.get(job.source_key)
        if connector_type is None:
            raise RuntimeError("No connector is registered for this source.")
        connector = connector_type(job.connector_config)
        async with connector:
            if not await connector.healthcheck():
                raise RuntimeError("The source health check failed.")

            async for payload in connector.discover_listings(job.since):
                try:
                    with Session(engine) as session:
                        source = session.exec(
                            select(MarketplaceSource).where(
                                MarketplaceSource.source_key == job.source_key
                            )
                        ).first()
                        if source is None:
                            raise RuntimeError("Source configuration was removed during collection.")
                        outcome = ingest_listing(session, source, payload)
                    if outcome.created:
                        discovered += 1
                    else:
                        updated += 1
                        duplicates += 1
                except (SourceNotApprovedError, SourceFieldNotPermittedError) as error:
                    errors += 1
                    error_messages.append(str(error))
                    logger.warning(
                        "Rejected listing from %s because it exceeded the approved scope: %s",
                        job.source_key,
                        error,
                    )
                except Exception as error:
                    errors += 1
                    error_messages.append(type(error).__name__)
                    logger.exception("Could not ingest one listing from %s.", job.source_key)

        status = "completed_with_errors" if errors else "completed"
        with Session(engine) as session:
            run = session.get(CollectionRun, job.run_id)
            source = session.exec(
                select(MarketplaceSource).where(
                    MarketplaceSource.source_key == job.source_key
                )
            ).first()
            if run is None or source is None:
                raise RuntimeError("Collection run or source disappeared before completion.")
            run.status = status
            run.completed_at = datetime.now(timezone.utc)
            run.discovered_count = discovered
            run.updated_count = updated
            run.duplicate_count = duplicates
            run.error_count = errors
            run.error_summary = "; ".join(dict.fromkeys(error_messages))[:2000] or None
            source.next_run_at = run.completed_at + timedelta(
                seconds=source.minimum_interval_seconds
            )
            if errors == 0:
                source.last_success_at = run.completed_at
            session.add(run)
            session.add(source)
            session.commit()
    except Exception as error:
        logger.exception("Collection run %s for %s failed.", job.run_id, job.source_key)
        with Session(engine) as session:
            run = session.get(CollectionRun, job.run_id)
            if run is not None:
                run.status = "failed"
                run.completed_at = datetime.now(timezone.utc)
                run.error_count = max(1, errors)
                run.error_summary = str(error)[:2000]
                session.add(run)
                source = session.exec(
                    select(MarketplaceSource).where(
                        MarketplaceSource.source_key == job.source_key
                    )
                ).first()
                if source is not None:
                    source.next_run_at = run.completed_at + timedelta(
                        seconds=source.minimum_interval_seconds
                    )
                    session.add(source)
                session.commit()


async def run_due_jobs_once() -> int:
    jobs = claim_due_jobs()
    for job in jobs:
        await execute_job(job)
    return len(jobs)


async def run_worker() -> None:
    recovered = recover_interrupted_runs()
    if recovered:
        logger.warning("Marked %s interrupted collection runs as failed.", recovered)
    logger.info("MarketPulse collection worker started.")
    while True:
        try:
            await run_due_jobs_once()
        except Exception:
            logger.exception("Worker polling cycle failed; it will retry after the poll interval.")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run_worker())
