from .base import MarketplaceConnector
from .aae import AaeConnector
from .enytinplus import EnytinPlusConnector
from .facebook_marketplace import FacebookMarketplaceConnector
from .jax import JaxConnector
from .jiji import JijiConnector
from .naijabargains import NaijaBargainsConnector


class ConnectorRegistry:
    def __init__(self) -> None:
        self._connectors: dict[str, type[MarketplaceConnector]] = {}

    def register(self, connector_type: type[MarketplaceConnector]) -> None:
        key = connector_type.source_key
        if key in self._connectors:
            raise ValueError(f"A connector is already registered for {key}.")
        self._connectors[key] = connector_type

    def get(self, source_key: str) -> type[MarketplaceConnector] | None:
        return self._connectors.get(source_key)

    def available(self, source_key: str) -> bool:
        return source_key in self._connectors


connector_registry = ConnectorRegistry()
connector_registry.register(AaeConnector)
connector_registry.register(EnytinPlusConnector)
connector_registry.register(FacebookMarketplaceConnector)
connector_registry.register(JaxConnector)
connector_registry.register(JijiConnector)
connector_registry.register(NaijaBargainsConnector)
