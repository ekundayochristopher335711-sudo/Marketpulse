from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import case, func, or_
from sqlmodel import Session, select

from ..models import CollectionRun, Listing, MarketplaceSource, PriceObservation
from ..schemas import (
    CategoryMarketMetric,
    ListingMomentumMetric,
    LocationMarketMetric,
    MarketOverview,
)


def _median_asking_price(
    session: Session,
    category: Optional[str] = None,
) -> Optional[int]:
    filters = [Listing.listing_status == "active", Listing.is_demo.is_(False)]
    if category is not None:
        filters.append(Listing.category == category)

    count = session.exec(
        select(func.count()).select_from(Listing).where(*filters)
    ).one()
    if count == 0:
        return None

    middle = count // 2
    prices = session.exec(
        select(Listing.asking_price)
        .where(*filters)
        .order_by(Listing.asking_price)
        .offset(middle if count % 2 else middle - 1)
        .limit(1 if count % 2 else 2)
    ).all()
    if count % 2:
        return int(prices[0])
    return round((int(prices[0]) + int(prices[1])) / 2)


def _price_movement_counts(session: Session) -> tuple[int, int]:
    ranked = (
        select(
            PriceObservation.listing_id.label("listing_id"),
            PriceObservation.asking_price.label("asking_price"),
            func.row_number()
            .over(
                partition_by=PriceObservation.listing_id,
                order_by=(PriceObservation.observed_at.desc(), PriceObservation.id.desc()),
            )
            .label("position"),
        )
        .subquery()
    )
    latest = (
        select(
            ranked.c.listing_id,
            ranked.c.asking_price.label("asking_price"),
        )
        .where(ranked.c.position == 1)
        .subquery()
    )
    previous = (
        select(
            ranked.c.listing_id,
            ranked.c.asking_price.label("asking_price"),
        )
        .where(ranked.c.position == 2)
        .subquery()
    )
    changes = session.exec(
        select(
            func.coalesce(
                func.sum(
                    case((latest.c.asking_price < previous.c.asking_price, 1), else_=0)
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case((latest.c.asking_price > previous.c.asking_price, 1), else_=0)
                ),
                0,
            ),
        )
        .select_from(
            latest.join(previous, latest.c.listing_id == previous.c.listing_id).join(
                Listing, Listing.id == latest.c.listing_id
            )
        )
        .where(Listing.listing_status == "active", Listing.is_demo.is_(False))
    ).one()
    return int(changes[0]), int(changes[1])


def build_market_overview(
    session: Session,
    period_days: int,
    now: Optional[datetime] = None,
) -> MarketOverview:
    as_of = now or datetime.now(timezone.utc)
    period_start = as_of - timedelta(days=period_days)
    active_filter = (Listing.listing_status == "active", Listing.is_demo.is_(False))

    total_listings = int(
        session.exec(
            select(func.count()).select_from(Listing).where(Listing.is_demo.is_(False))
        ).one()
    )
    active_listings = int(
        session.exec(
            select(func.count()).select_from(Listing).where(*active_filter)
        ).one()
    )
    median_asking_price = _median_asking_price(session)
    newly_discovered = int(
        session.exec(
            select(func.count())
            .select_from(Listing)
            .where(
                Listing.is_demo.is_(False),
                Listing.first_discovered_at >= period_start,
                Listing.first_discovered_at <= as_of,
            )
        ).one()
    )

    category_counts = session.exec(
        select(Listing.category, func.count())
        .where(*active_filter)
        .group_by(Listing.category)
        .order_by(func.count().desc())
        .limit(50)
    ).all()
    categories = [
        CategoryMarketMetric(
            category=category,
            active_listings=int(count),
            median_asking_price_ngn=_median_asking_price(session, category),
        )
        for category, count in category_counts
    ]

    location_counts = session.exec(
        select(Listing.state, Listing.city, func.count())
        .where(
            *active_filter,
            or_(Listing.state.is_not(None), Listing.city.is_not(None)),
        )
        .group_by(Listing.state, Listing.city)
        .order_by(func.count().desc())
        .limit(20)
    ).all()
    locations = [
        LocationMarketMetric(state=state, city=city, active_listings=int(count))
        for state, city, count in location_counts
    ]

    recent_start = as_of - timedelta(days=7)
    previous_start = as_of - timedelta(days=14)
    momentum_counts = session.exec(
        select(
            Listing.category,
            func.sum(
                case(
                    (
                        Listing.first_discovered_at >= recent_start,
                        1,
                    ),
                    else_=0,
                )
            ),
            func.sum(
                case(
                    (
                        (Listing.first_discovered_at >= previous_start)
                        & (Listing.first_discovered_at < recent_start),
                        1,
                    ),
                    else_=0,
                )
            ),
        )
        .where(
            Listing.is_demo.is_(False),
            Listing.listing_status == "active",
            Listing.first_discovered_at >= previous_start,
            Listing.first_discovered_at <= as_of,
        )
        .group_by(Listing.category)
        .order_by(func.sum(case((Listing.first_discovered_at >= recent_start, 1), else_=0)).desc())
        .limit(20)
    ).all()

    listing_momentum = []
    for category, current, previous_count in momentum_counts:
        current_count = int(current or 0)
        earlier_count = int(previous_count or 0)
        if earlier_count == 0:
            change_percent = None
            signal = "no_prior_activity"
        else:
            change_percent = round(
                (current_count - earlier_count) * 100 / earlier_count, 1
            )
            if current_count > earlier_count:
                signal = "increasing_listing_activity"
            elif current_count < earlier_count:
                signal = "decreasing_listing_activity"
            else:
                signal = "stable_listing_activity"
        listing_momentum.append(
            ListingMomentumMetric(
                category=category,
                current_7_day_listings=current_count,
                previous_7_day_listings=earlier_count,
                change_percent=change_percent,
                signal=signal,
            )
        )

    enabled_sources = int(
        session.exec(
            select(func.count())
            .select_from(MarketplaceSource)
            .where(
                MarketplaceSource.enabled.is_(True),
                MarketplaceSource.permission_status == "approved",
            )
        ).one()
    )
    finished_runs = session.exec(
        select(CollectionRun.status).where(
            CollectionRun.status.in_(("completed", "completed_with_errors", "failed")),
            CollectionRun.completed_at >= period_start,
            CollectionRun.completed_at <= as_of,
        )
    ).all()
    success_rate = (
        round(sum(status == "completed" for status in finished_runs) * 100 / len(finished_runs), 1)
        if finished_runs
        else None
    )
    latest_collection = session.exec(
        select(func.max(CollectionRun.completed_at)).where(
            CollectionRun.status == "completed",
            CollectionRun.completed_at >= period_start,
            CollectionRun.completed_at <= as_of,
        )
    ).one()
    price_reductions, price_increases = _price_movement_counts(session)

    return MarketOverview(
        as_of=as_of,
        period_days=period_days,
        total_listings=total_listings,
        active_listings=active_listings,
        median_asking_price_ngn=median_asking_price,
        newly_discovered_in_period=newly_discovered,
        enabled_sources=enabled_sources,
        latest_collection_at=latest_collection,
        collection_success_rate_percent=success_rate,
        price_reductions=price_reductions,
        price_increases=price_increases,
        categories=categories,
        locations=locations,
        listing_momentum=listing_momentum,
        limitations=[
            "Listing counts measure observed supply, not buyer demand or completed sales.",
            "Asking prices are not verified transaction prices.",
            "Momentum compares newly observed active listings across two seven-day periods.",
            "Location summaries include only explicit state and city fields.",
        ],
    )
