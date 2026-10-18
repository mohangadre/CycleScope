from cyclescope.config import Settings
from cyclescope.providers.alpaca import AlpacaProvider
from cyclescope.providers.base import MarketDataProvider
from cyclescope.providers.synthetic import SyntheticProvider


def make_provider(settings: Settings) -> MarketDataProvider:
    if settings.market_data_provider == "synthetic":
        return SyntheticProvider()
    if settings.market_data_provider == "synthetic_research":
        return SyntheticProvider(research=True)
    return AlpacaProvider(
        key_id=settings.apca_api_key_id.get_secret_value() if settings.apca_api_key_id else None,
        secret_key=(
            settings.apca_api_secret_key.get_secret_value()
            if settings.apca_api_secret_key
            else None
        ),
        feed=settings.alpaca_feed,
    )
