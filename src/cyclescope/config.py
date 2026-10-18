from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://cyclescope:cyclescope@localhost:5432/cyclescope"
    )
    market_data_provider: Literal["synthetic", "synthetic_research", "alpaca"] = "synthetic"
    apca_api_key_id: SecretStr | None = None
    apca_api_secret_key: SecretStr | None = None
    alpaca_feed: Literal["iex", "sip"] = "iex"
