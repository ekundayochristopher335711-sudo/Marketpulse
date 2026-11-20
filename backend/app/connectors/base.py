import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from time import monotonic
from typing import AsyncIterator, Literal

import httpx
from pydantic import BaseModel, ConfigDict

from ..schemas import ListingCreate

AccessMethod = Literal["none", "api", "feed", "authorized_web"]
PermissionStatus = Literal["unknown", "pending", "approved", "denied"]
COLLECTOR_USER_AGENT = "MarketPulseAuthorizedCollector/1.0"


class ConnectorConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_key: str
    enabled: bool
    permission_status: PermissionStatus
    access_method: AccessMethod
    minimum_interval_seconds: int
    permitted_categories: tuple[str, ...]
    permitted_fields: frozenset[str]
    permission_reference: str | None


class ConnectorNotAuthorizedError(RuntimeError):
    pass


class RequestRateLimiter:
    def __init__(self, minimum_interval_seconds: float):
        if minimum_interval_seconds <= 0:
            raise ValueError("The request interval must be positive.")
        self._interval = minimum_interval_seconds
        self._last_request = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            delay = self._interval - (monotonic() - self._last_request)
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_request = monotonic()


class MarketplaceConnector(ABC):
    source_key: str
    supported_access_methods: frozenset[str] = frozenset()

    def __init__(self, config: ConnectorConfig):
        if not config.enabled or config.permission_status != "approved":
            raise ConnectorNotAuthorizedError(
                f"Source {config.source_key} is not enabled with approved permission."
            )
        if config.access_method == "none":
            raise ConnectorNotAuthorizedError(
                f"Source {config.source_key} has no approved access method."
            )
        if not config.permission_reference:
            raise ConnectorNotAuthorizedError(
                f"Source {config.source_key} has no permission reference."
            )
        if self.source_key != config.source_key:
            raise ValueError("Connector and source configuration do not match.")

        self.config = config
        self.rate_limiter = RequestRateLimiter(config.minimum_interval_seconds)
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10, read=25, write=10, pool=10),
            limits=httpx.Limits(max_connections=2, max_keepalive_connections=1),
            headers={"User-Agent": COLLECTOR_USER_AGENT},
            follow_redirects=False,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        await self._client.aclose()

    async def request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        await self.rate_limiter.wait()
        response = await self._client.request(method, url, **kwargs)
        response.raise_for_status()
        return response

    @abstractmethod
    async def discover_listings(
        self, since: datetime | None
    ) -> AsyncIterator[ListingCreate]:
        raise NotImplementedError

    @abstractmethod
    async def healthcheck(self) -> bool:
        raise NotImplementedError
