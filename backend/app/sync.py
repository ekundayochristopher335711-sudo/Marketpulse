"""Send locally collected, non-demo listings to the hosted API."""

import argparse
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import time
from urllib.parse import urlsplit

from dotenv import dotenv_values
import httpx
from sqlmodel import Session, select

from .database import engine
from .models import Listing
from .schemas import ListingCreate

logger = logging.getLogger("marketpulse.sync")


def _time(value: str | datetime | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def remote_credentials() -> dict[str, str]:
    # The root .env holds the hosted credentials; the backend .env holds local
    # database/worker settings. Do not replace the local database URL.
    root = Path(__file__).resolve().parents[2]
    values = {}
    for path in (root / "backend" / ".env", root / ".env"):
        for name, value in dotenv_values(path).items():
            if value and name in {"MARKETPULSE_READ_TOKEN", "MARKETPULSE_INGEST_TOKEN"}:
                values[name] = value.strip()
    return values


def listing_payload(listing: Listing, permitted_fields: list[str]) -> dict:
    values = listing.model_dump()
    values["observed_at"] = listing.last_observed_at or listing.observed_at
    fields = set(permitted_fields).intersection(ListingCreate.model_fields)
    payload = {name: values[name] for name in fields if name in values}
    payload["source_id"] = listing.source_id
    return ListingCreate.model_validate(payload).model_dump(mode="json", exclude_unset=True)


def sync_once(client: httpx.Client, database_engine=engine, limit: int = 100) -> dict[str, int]:
    sources_response = client.get("/api/sources")
    sources_response.raise_for_status()
    sources = [source for source in sources_response.json() if source["enabled"] and source["permission_status"] == "approved"]

    remote = {}
    offset = 0
    while True:
        response = client.get("/api/listings", params={"limit": 500, "offset": offset, "listing_status": "active"})
        response.raise_for_status()
        page = response.json()
        for row in page["items"]:
            remote[(row["source_id"], row.get("source_listing_id"), row.get("source_url"))] = row
        offset += len(page["items"])
        if not page["items"] or offset >= page["total"]:
            break

    counts = {"created": 0, "updated": 0, "unchanged": 0, "rejected": 0}
    for source in sources:
        with Session(database_engine) as session:
            rows = session.exec(
                select(Listing).where(
                    Listing.source_id == source["source_key"],
                    Listing.is_demo.is_(False),
                    Listing.listing_status == "active",
                ).order_by(Listing.last_observed_at.desc(), Listing.id.desc()).limit(limit)
            ).all()
            for listing in rows:
                if listing.category not in source["permitted_categories"]:
                    continue
                known = remote.get((listing.source_id, listing.source_listing_id, listing.source_url))
                if known and known["asking_price"] == listing.asking_price and _time(known["last_observed_at"]) >= _time(listing.last_observed_at):
                    counts["unchanged"] += 1
                    continue
                response = client.post("/api/listings", json=listing_payload(listing, source["permitted_fields"]))
                if response.status_code in {401, 503}:
                    raise RuntimeError("The hosted ingestion token was not accepted. Match MARKETPULSE_INGEST_TOKEN in the root .env and the Vercel API environment.")
                if response.status_code in {403, 409, 422}:
                    counts["rejected"] += 1
                    logger.warning("Hosted API rejected one %s listing (HTTP %s).", source["source_key"], response.status_code)
                    continue
                response.raise_for_status()
                counts["created" if response.status_code == 201 else "updated"] += 1
        logger.info("Checked locally collected records for %s.", source["name"])
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-base-url",
        default=os.getenv(
            "MARKETPULSE_API_BASE_URL", "https://marketpulse-nigeria-pi.vercel.app"
        ),
    )
    parser.add_argument("--once", action="store_true", help="Publish one batch, then exit.")
    parser.add_argument("--limit", type=int, default=100, help="Recent local records per enabled source, per cycle.")
    parser.add_argument("--interval", type=int, default=300, help="Seconds between update cycles.")
    args = parser.parse_args()
    parsed = urlsplit(args.api_base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        parser.error("Use the hosted HTTPS origin, without credentials or an /api path.")
    if not 1 <= args.limit <= 5000 or args.interval < 60:
        parser.error("Use a limit from 1 to 5000 and an interval of at least 60 seconds.")
    credentials = remote_credentials()
    ingest = credentials.get("MARKETPULSE_INGEST_TOKEN", "")
    if len(ingest) < 32:
        logger.error("Set MARKETPULSE_INGEST_TOKEN in the project root .env to match the Vercel API environment.")
        return 1
    headers = {"X-Ingestion-Token": ingest}
    if credentials.get("MARKETPULSE_READ_TOKEN"):
        headers["Authorization"] = f"Bearer {credentials['MARKETPULSE_READ_TOKEN']}"

    try:
        with httpx.Client(base_url=args.api_base_url.rstrip("/"), headers=headers, timeout=60, follow_redirects=False) as client:
            while True:
                try:
                    counts = sync_once(client, limit=args.limit)
                    logger.info("Published: %s new, %s updated, %s unchanged, %s rejected.", counts["created"], counts["updated"], counts["unchanged"], counts["rejected"])
                except (httpx.HTTPError, RuntimeError) as error:
                    # Do not print request headers, credential values, or response bodies.
                    status = getattr(getattr(error, "response", None), "status_code", None)
                    logger.error("Sync did not complete (%s%s). Check hosted API status and the root .env credentials.", type(error).__name__, f", HTTP {status}" if status else "")
                    if args.once:
                        return 1
                if args.once:
                    return 1 if counts["rejected"] else 0
                time.sleep(args.interval)
    except KeyboardInterrupt:
        logger.info("Publishing stopped.")
        return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    raise SystemExit(main())
