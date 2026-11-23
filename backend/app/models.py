from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, Column, DateTime, Float, Index, String, Text
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Listing(SQLModel, table=True):
    __tablename__ = "listing"
    __table_args__ = (
        Index(
            "uq_listing_source_external_id",
            "source_id",
            "source_listing_id",
            unique=True,
        ),
        Index("ix_listing_source_id", "source_id"),
        Index("ix_listing_category_city", "category", "city"),
        Index("ix_listing_model_brand", "brand", "model"),
        Index("ix_listing_location", "location"),
        Index("ix_listing_source_url", "source_url"),
        Index(
            "uq_listing_source_canonical_url",
            "source_id",
            "canonical_url",
            unique=True,
        ),
        Index("ix_listing_discovered", "first_discovered_at"),
        Index("ix_listing_status_observed", "listing_status", "last_observed_at"),
        Index("ix_listing_price", "asking_price"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    source_id: str = Field(default="legacy", max_length=80)
    source_listing_id: Optional[str] = Field(default=None, max_length=255)
    title: str = Field(max_length=500)
    normalized_title: Optional[str] = Field(default=None, max_length=500)
    description: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    category: str = Field(max_length=120)
    subcategory: Optional[str] = Field(default=None, max_length=120)
    brand: Optional[str] = Field(default=None, max_length=120)
    model: Optional[str] = Field(default=None, max_length=120)
    asking_price: int = Field(sa_column=Column(BigInteger, nullable=False))
    currency: str = Field(default="NGN", max_length=3)
    location: str = Field(max_length=200)
    state: Optional[str] = Field(default=None, max_length=100)
    city: Optional[str] = Field(default=None, max_length=100)
    locality: Optional[str] = Field(default=None, max_length=120)
    source_name: str = Field(max_length=120)
    source_url: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    canonical_url: Optional[str] = Field(default=None, max_length=2048)
    condition: Optional[str] = Field(default=None, max_length=80)
    listing_status: str = Field(default="active", max_length=24)
    first_discovered_at: Optional[datetime] = Field(
        default_factory=utc_now, sa_type=DateTime(timezone=True)
    )
    last_observed_at: Optional[datetime] = Field(
        default_factory=utc_now, sa_type=DateTime(timezone=True)
    )
    last_price_update_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    data_quality_score: Optional[float] = Field(default=None, sa_column=Column(Float, nullable=True))
    raw_source_reference: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    observed_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    is_demo: bool = Field(default=False)


class PriceObservation(SQLModel, table=True):
    __tablename__ = "price_observation"
    __table_args__ = (
        Index("ix_price_observation_listing_time", "listing_id", "observed_at"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    listing_id: int = Field(foreign_key="listing.id", index=True)
    asking_price: int = Field(sa_column=Column(BigInteger, nullable=False))
    currency: str = Field(default="NGN", max_length=3)
    observed_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))


class MarketplaceSource(SQLModel, table=True):
    __tablename__ = "marketplace_source"

    id: Optional[int] = Field(default=None, primary_key=True)
    source_key: str = Field(unique=True, max_length=80)
    name: str = Field(max_length=120)
    access_method: str = Field(default="none", max_length=32)
    permission_status: str = Field(default="unknown", max_length=24)
    enabled: bool = Field(default=False)
    minimum_interval_seconds: int = Field(default=3600)
    permitted_categories_json: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    permitted_fields_json: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    permission_reference: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    retention_days: Optional[int] = Field(default=None)
    last_success_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    next_run_at: Optional[datetime] = Field(
        default=None, sa_type=DateTime(timezone=True), index=True
    )
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))


class CollectionRun(SQLModel, table=True):
    __tablename__ = "collection_run"

    id: Optional[int] = Field(default=None, primary_key=True)
    source_key: str = Field(foreign_key="marketplace_source.source_key", index=True, max_length=80)
    status: str = Field(default="queued", max_length=24)
    started_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    completed_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    discovered_count: int = Field(default=0)
    updated_count: int = Field(default=0)
    duplicate_count: int = Field(default=0)
    error_count: int = Field(default=0)
    error_summary: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    actor: str = Field(max_length=80)
    action: str = Field(max_length=80)
    source_key: Optional[str] = Field(default=None, max_length=80, index=True)
    details_json: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True), index=True)
