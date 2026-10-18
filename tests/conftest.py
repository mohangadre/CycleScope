import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.engine import make_url

from alembic import command
from cyclescope.storage.database import make_engine


@pytest.fixture(autouse=True)
def offline_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """CI and local tests must never depend on injected market credentials."""
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "synthetic")
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a disposable PostgreSQL database")
    # This fixture migrates/truncates. Refuse the normal development database.
    if not (make_url(url).database or "").endswith("_test"):
        pytest.fail("TEST_DATABASE_URL database name must end with _test")
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    engine = make_engine(url)
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE daily_bars, ingestion_runs, instruments CASCADE"))
    yield engine
    engine.dispose()
