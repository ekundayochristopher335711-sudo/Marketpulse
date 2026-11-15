from pydantic import BaseModel, Field, HttpUrl
from typing import Optional

class NormalizedListing(BaseModel):
    title: str
    category: str
    asking_price: int
    currency: str = "NGN"
    location: str
    source_name: str
    source_url: Optional[str] = None
    condition: Optional[str] = None
    source_listing_id: Optional[str] = None

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
