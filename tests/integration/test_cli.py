import sys

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from cyclescope.cli import main
from cyclescope.storage.models import DailyBarRow

pytestmark = pytest.mark.postgres


def test_cli_ingests_all_symbols_then_repeats_without_duplicate_bars(
    db: Engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
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
            "2024-03-28",
        ],
    )
    main()
    main()
    out = capsys.readouterr().out
    assert out.count('"data_kind": "synthetic"') == 8
    with Session(db) as session:
        assert session.scalar(select(func.count()).select_from(DailyBarRow)) == 244


def test_cli_provider_failure_and_missing_credentials(
    db: Engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "alpaca")
    monkeypatch.setenv("APCA_API_KEY_ID", "")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cyclescope",
            "ingest",
            "--symbol",
            "SPY",
            "--start",
            "2024-01-02",
            "--end",
            "2024-01-03",
        ],
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    assert "provider_unavailable" in capsys.readouterr().err
    with Session(db) as session:
        assert session.scalar(select(func.count()).select_from(DailyBarRow)) == 0
