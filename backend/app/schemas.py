from datetime import datetime
from typing import Literal, Optional
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SourceField = Literal[
    "source_listing_id",
    "title",
    "description",
    "category",
    "subcategory",
    "brand",
    "model",
    "asking_price",
    "currency",
    "location",
    "state",
    "city",
    "locality",
    "source_url",
    "condition",
    "observed_at",
]


class ListingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=80)
    source_listing_id: Optional[str] = Field(default=None, max_length=255)
    title: str = Field(min_length=1, max_length=500)
    description: Optional[str] = Field(default=None, max_length=10000)
    category: str = Field(min_length=1, max_length=120)
    subcategory: Optional[str] = Field(default=None, max_length=120)
    brand: Optional[str] = Field(default=None, max_length=120)
    model: Optional[str] = Field(default=None, max_length=120)
    asking_price: int = Field(gt=0, le=10_000_000_000)
    currency: Literal["NGN"] = "NGN"
    location: str = Field(min_length=1, max_length=200)
    state: Optional[str] = Field(default=None, max_length=100)
    city: Optional[str] = Field(default=None, max_length=100)
    locality: Optional[str] = Field(default=None, max_length=120)
    source_url: Optional[str] = Field(default=None, max_length=2048)
    condition: Optional[str] = Field(default=None, max_length=80)
    observed_at: Optional[datetime] = None
    data_quality_score: Optional[float] = Field(default=None, ge=0, le=1)

    @field_validator(
        "source_id", "title", "category", "location", mode="before"
    )
    @classmethod
    def reject_blank_required_text(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            raise ValueError("This value cannot be blank.")
        return value

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        try:
            parsed = urlsplit(value)
            valid = (
                parsed.scheme in {"http", "https"}
                and parsed.hostname is not None
                and parsed.username is None
                and parsed.password is None
            )
            parsed.port
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("source_url must be a valid http or https URL without credentials.")
        return value


class ListingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: str
    source_listing_id: Optional[str]
    title: str
    normalized_title: Optional[str]
    description: Optional[str]
    category: str
    subcategory: Optional[str]
    brand: Optional[str]
    model: Optional[str]
    asking_price: int
    currency: str
    location: str
    state: Optional[str]
    city: Optional[str]
    locality: Optional[str]
    source_name: str
    source_url: Optional[str]
    canonical_url: Optional[str]
    condition: Optional[str]
    listing_status: str
    first_discovered_at: datetime
    last_observed_at: datetime
    last_price_update_at: Optional[datetime]
    data_quality_score: Optional[float]
    observed_at: datetime
    is_demo: bool


class PaginatedListings(BaseModel):
    items: list[ListingRead]
    total: int
    offset: int
    limit: int


class MarketplaceSourceRead(BaseModel):
    source_key: str
    name: str
    access_method: str
    permission_status: str
    enabled: bool
    minimum_interval_seconds: int
    permitted_categories: list[str]
    permitted_fields: list[str]
    retention_days: Optional[int]
    last_success_at: Optional[datetime]
    next_run_at: Optional[datetime]
    permission_reference_present: bool
    connector_available: bool


class MarketplaceSourceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_method: Literal["none", "api", "feed", "authorized_web"]
    permission_status: Literal["unknown", "pending", "approved", "denied"]
    enabled: bool = False
    minimum_interval_seconds: int = Field(ge=30, le=3600)
    permitted_categories: list[str] = Field(default_factory=list, max_length=100)
    permitted_fields: list[SourceField] = Field(default_factory=list, max_length=16)
    permission_reference: Optional[str] = Field(default=None, max_length=2000)
    retention_days: Optional[int] = Field(default=None, ge=1, le=3650)

    @model_validator(mode="after")
    def validate_approval_scope(self):
        if self.permission_status == "approved":
            if self.access_method == "none":
                raise ValueError("Approved sources need an authorized access method.")
            if not self.permission_reference or not self.permission_reference.strip():
                raise ValueError("Approved sources need a permission reference.")
            if not self.permitted_categories or not self.permitted_fields:
                raise ValueError("Approved sources need explicit categories and fields.")
            required_fields = {"title", "category", "asking_price", "location"}
            if not required_fields.issubset(self.permitted_fields):
                raise ValueError("Approved sources must permit the fields required to normalize listings.")
            if not {"source_listing_id", "source_url"}.intersection(self.permitted_fields):
                raise ValueError("Approved sources must permit a stable listing identity field.")
        if self.enabled and self.permission_status != "approved":
            raise ValueError("Only approved sources can be enabled.")
        return self


class CollectionRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_key: str
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    discovered_count: int
    updated_count: int
    duplicate_count: int
    error_count: int
    error_summary: Optional[str]


class AuditLogRead(BaseModel):
    id: int
    actor: str
    action: str
    source_key: Optional[str]
    details: dict[str, object]
    created_at: datetime


class CategoryMarketMetric(BaseModel):
    category: str
    active_listings: int
    median_asking_price_ngn: Optional[int]


class LocationMarketMetric(BaseModel):
    state: Optional[str]
    city: Optional[str]
    active_listings: int


class ListingMomentumMetric(BaseModel):
    category: str
    current_7_day_listings: int
    previous_7_day_listings: int
    change_percent: Optional[float]
    signal: Literal[
        "increasing_listing_activity",
        "decreasing_listing_activity",
        "stable_listing_activity",
        "no_prior_activity",
    ]


class MarketOverview(BaseModel):
    as_of: datetime
    period_days: int
    total_listings: int
    active_listings: int
    median_asking_price_ngn: Optional[int]
    newly_discovered_in_period: int
    enabled_sources: int
    latest_collection_at: Optional[datetime]
    collection_success_rate_percent: Optional[float]
    price_reductions: int
    price_increases: int
    categories: list[CategoryMarketMetric]
    locations: list[LocationMarketMetric]
    listing_momentum: list[ListingMomentumMetric]
    limitations: list[str]


class PriceHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    listing_id: int
    asking_price: int
    currency: str
    observed_at: datetime
    change_amount_ngn: Optional[int] = None
    change_percent: Optional[float] = None


class AnalysisCategory(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    listing_count: int = Field(ge=1, le=100000)
    median_asking_price_ngn: int = Field(ge=1, le=10_000_000_000)
    price_reductions: int = Field(ge=0, le=100000)
    engagement_records: int = Field(ge=0, le=100000)


class MarketAnalysisRequest(BaseModel):
    listing_count: int = Field(ge=1, le=100000)
    median_asking_price_ngn: int = Field(ge=1, le=10_000_000_000)
    price_reductions: int = Field(ge=0, le=100000)
    engagement_records: int = Field(ge=0, le=100000)
    categories: list[AnalysisCategory] = Field(min_length=1, max_length=100)


class MarketAnalysisResponse(BaseModel):
    analysis: str
    model: str


class MarketAnalysisStatus(BaseModel):
    configured: bool
    model: Optional[str] = None
    local_only: bool
