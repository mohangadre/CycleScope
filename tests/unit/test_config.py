import sys

import pytest
from pydantic import SecretStr

from cyclescope.cli import main
from cyclescope.config import Settings
from cyclescope.providers.alpaca import AlpacaProvider
from cyclescope.providers.factory import make_provider
from cyclescope.storage.database import make_engine


def test_provider_configuration_keeps_feeds_distinct() -> None:
    settings = Settings(
        market_data_provider="alpaca",
        apca_api_key_id=SecretStr("test-key"),
        apca_api_secret_key=SecretStr("test-secret"),
        alpaca_feed="sip",
    )
    provider = make_provider(settings)
    assert isinstance(provider, AlpacaProvider)
    assert provider.provider_id == "alpaca-sip"
    assert provider.data_kind == "real"
    assert "test-secret" not in repr(settings)


def test_requires_postgres() -> None:
    with pytest.raises(ValueError, match="postgresql"):
        make_engine("sqlite://")


def test_cli_invalid_dates_do_not_expose_configuration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cyclescope",
            "ingest",
            "--start",
            "2024-01-03",
            "--end",
            "2024-01-02",
        ],
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    assert "Invalid configuration or date range" in capsys.readouterr().err


def test_cli_database_outage(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://private:secret@127.0.0.1:1/missing")
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "synthetic")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cyclescope",
            "ingest",
            "--start",
            "2024-01-02",
            "--end",
            "2024-01-03",
        ],
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    assert "secret" not in capsys.readouterr().err
