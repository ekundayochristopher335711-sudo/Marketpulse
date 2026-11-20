from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlmodel import Session, select

from ..models import Listing, MarketplaceSource, PriceObservation
from ..schemas import ListingCreate


class SourceNotApprovedError(RuntimeError):
    pass


class SourceFieldNotPermittedError(RuntimeError):
    pass


class ListingIdentityConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class IngestionResult:
    listing: Listing
    created: bool
    price_changed: bool


def _normalized_title(title: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", title.casefold()).split())


def canonicalize_url(source_url: str | None) -> str | None:
    if source_url is None:
        return None

    parsed = urlsplit(source_url)
    hostname = (parsed.hostname or "").casefold()
    if ":" in hostname:
        hostname = f"[{hostname}]"
    port = parsed.port
    if port and not (
        (parsed.scheme == "https" and port == 443)
        or (parsed.scheme == "http" and port == 80)
    ):
        hostname = f"{hostname}:{port}"
    tracking_parameters = {"fbclid", "gclid", "ref", "referrer"}
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.casefold() not in tracking_parameters
        and not key.casefold().startswith("utm_")
    ]
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit(
        (parsed.scheme.casefold(), hostname, path, urlencode(query), "")
    )


def ingest_listing(
    session: Session,
    source: MarketplaceSource,
    payload: ListingCreate,
) -> IngestionResult:
    if source.permission_status != "approved" or not source.enabled:
        raise SourceNotApprovedError("The source is not enabled with approved permission.")

    if payload.source_id != source.source_key:
        raise SourceFieldNotPermittedError("The payload source does not match the authorized source.")

    if not payload.source_listing_id and not payload.source_url:
        raise ListingIdentityConflictError(
            "Each listing needs a source_listing_id or source_url so repeated observations can be deduplicated."
        )

    permitted_categories = set(json.loads(source.permitted_categories_json))
    if payload.category not in permitted_categories:
        raise SourceFieldNotPermittedError(
            "The listing category exceeds this source's approved collection scope."
        )

    supplied_fields = payload.model_fields_set - {"source_id"}
    permitted_fields = set(json.loads(source.permitted_fields_json))
    if not supplied_fields.issubset(permitted_fields):
        raise SourceFieldNotPermittedError(
            "The submitted fields exceed this source's approved field scope."
        )

    canonical_url = canonicalize_url(payload.source_url)
    existing_by_id = None
    if payload.source_listing_id:
        existing_by_id = session.exec(
            select(Listing)
            .where(
                Listing.source_id == source.source_key,
                Listing.source_listing_id == payload.source_listing_id,
            )
            .with_for_update()
        ).first()
    existing_by_url = None
    if canonical_url:
        existing_by_url = session.exec(
            select(Listing)
            .where(
                Listing.source_id == source.source_key,
                Listing.canonical_url == canonical_url,
            )
            .with_for_update()
        ).first()
    if (
        existing_by_id is not None
        and existing_by_url is not None
        and existing_by_id.id != existing_by_url.id
    ):
        raise ListingIdentityConflictError(
            "The source listing ID and canonical URL point to different stored listings."
        )
    if (
        existing_by_id is None
        and existing_by_url is not None
        and payload.source_listing_id
        and existing_by_url.source_listing_id
        and existing_by_url.source_listing_id != payload.source_listing_id
    ):
        raise ListingIdentityConflictError(
            "The canonical URL belongs to a different source listing ID."
        )
    existing = existing_by_id or existing_by_url

    observed_at = payload.observed_at or datetime.now(timezone.utc)
    values = payload.model_dump(exclude={"source_id", "observed_at"})
    price_changed = existing is not None and existing.asking_price != payload.asking_price

    if existing is None:
        listing = Listing(
            **values,
            source_id=source.source_key,
            source_name=source.name,
            normalized_title=_normalized_title(payload.title),
            canonical_url=canonical_url,
            first_discovered_at=observed_at,
            last_observed_at=observed_at,
            observed_at=observed_at,
            is_demo=False,
        )
        session.add(listing)
        session.flush()
    else:
        listing = existing
        provided_values = payload.model_dump(
            exclude={"source_id", "observed_at"},
            exclude_unset=True,
        )
        for field, value in provided_values.items():
            setattr(listing, field, value)
        if "source_url" in provided_values:
            listing.canonical_url = canonical_url
        if "title" in provided_values:
            listing.normalized_title = _normalized_title(listing.title)
        if price_changed:
            listing.last_price_update_at = observed_at
        listing.last_observed_at = observed_at
        listing.observed_at = observed_at
        session.add(listing)

    session.add(
        PriceObservation(
            listing_id=listing.id,
            asking_price=listing.asking_price,
            currency=listing.currency,
            observed_at=observed_at,
        )
    )
    session.commit()
    session.refresh(listing)
    return IngestionResult(
        listing=listing,
        created=existing is None,
        price_changed=price_changed,
    )
