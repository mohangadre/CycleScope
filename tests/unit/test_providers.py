from datetime import date
from decimal import Decimal

import httpx
import pytest

from cyclescope.domain.errors import (
    InsufficientData,
    InvalidProviderData,
    ProviderUnavailable,
    UnknownSymbol,
)
from cyclescope.domain.models import CORE_CATALOG as CATALOG
from cyclescope.domain.models import DateRange
from cyclescope.providers.alpaca import MAX_RESPONSE_BYTES, AlpacaProvider
from cyclescope.providers.synthetic import SyntheticProvider
from cyclescope.services.ingestion import validate_batch

START, END = date(2024, 1, 2), date(2024, 1, 3)
PERIOD = DateRange(start=START, end=END)


def row(day: str = "2024-01-02") -> dict[str, object]:
    return {"t": day + "T05:00:00Z", "o": 100, "h": 102, "l": 99, "c": 101, "v": 1000}


def adapter(handler: object) -> AlpacaProvider:
    return AlpacaProvider("test-key", "test-secret", transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def test_fixtures_deterministic_valid_and_labeled() -> None:
    provider = SyntheticProvider()
    for instrument in CATALOG:
        a = provider.get_daily_bars(instrument.symbol, START, END)
        b = provider.get_daily_bars(instrument.symbol, START, END)
        assert a.bars == b.bars
        assert a.data_kind == "synthetic"
        assert len(a.bars) == 2
        assert a.fetched_at.utcoffset().total_seconds() == 0
        validate_batch(a, instrument.symbol, PERIOD)


def test_fixture_unknown_symbol() -> None:
    with pytest.raises(UnknownSymbol):
        SyntheticProvider().get_daily_bars("INVALID", START, END)


@pytest.mark.parametrize(
    "change,exception",
    [
        ("empty", InsufficientData),
        ("duplicate", InvalidProviderData),
        ("reverse", InvalidProviderData),
        ("missing", InsufficientData),
        ("outside", InvalidProviderData),
        ("symbol", InvalidProviderData),
    ],
)
def test_ingestion_rejects_incomplete_and_corrupt_batches(
    change: str, exception: type[Exception]
) -> None:
    batch = SyntheticProvider().get_daily_bars("SPY", START, END)
    a, b = batch.bars
    bars = {
        "empty": (),
        "duplicate": (a, a),
        "reverse": (b, a),
        "missing": (a,),
        "outside": (a.model_copy(update={"session_date": date(2024, 1, 1)}), b),
        "symbol": (a.model_copy(update={"symbol": "QQQ"}), b),
    }[change]
    with pytest.raises(exception):
        validate_batch(batch.model_copy(update={"bars": bars}), "SPY", PERIOD)


def test_missing_credentials_never_requests_or_falls_back() -> None:
    with pytest.raises(ProviderUnavailable, match="no synthetic fallback"):
        AlpacaProvider(None, None).get_daily_bars("SPY", START, END)


def test_alpaca_pagination_and_adjustment() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.url.host == "data.alpaca.markets"
        assert request.headers["APCA-API-KEY-ID"] == "test-key"
        assert request.url.params["adjustment"] == "all"
        assert request.url.params["feed"] == "iex"
        assert request.url.params["end"].startswith("2024-01-03T23:59:59.999999")
        page = request.url.params.get("page_token")
        return httpx.Response(
            200,
            json={
                "symbol": "SPY",
                "bars": [row("2024-01-03" if page else "2024-01-02")],
                "next_page_token": None if page else "page2",
            },
        )

    batch = adapter(handler).get_daily_bars("SPY", START, END)
    assert len(calls) == 2
    assert batch.provider == "alpaca-iex"
    assert batch.data_kind == "real"
    assert batch.adjustment_basis == "split_dividend_adjusted"
    assert batch.bars[0].close == Decimal("101")
    validate_batch(batch, "SPY", PERIOD)


@pytest.mark.parametrize("status", [401, 403, 429, 500, 503, 302])
def test_upstream_failures_sanitized(status: int) -> None:
    with pytest.raises(ProviderUnavailable) as error:
        adapter(lambda _: httpx.Response(status, text="secret upstream content")).get_daily_bars(
            "SPY", START, END
        )
    assert "secret" not in str(error.value)


def test_timeout_is_sanitized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("secret timeout details", request=request)

    with pytest.raises(ProviderUnavailable, match="timed out"):
        adapter(handler).get_daily_bars("SPY", START, END)


@pytest.mark.parametrize(
    "payload",
    [
        {"symbol": "SPY"},
        {"symbol": "QQQ", "bars": []},
        {"symbol": "SPY", "bars": [None]},
        {"symbol": "SPY", "bars": [{**row(), "c": 0}]},
        {"symbol": "SPY", "bars": [{**row(), "t": "2024-01-02T00:00:00"}]},
        {"symbol": "SPY", "bars": [{**row(), "v": 1.5}]},
        {"symbol": "SPY", "bars": [], "next_page_token": []},
    ],
)
def test_malformed_payload(payload: dict[str, object]) -> None:
    with pytest.raises(InvalidProviderData):
        adapter(lambda _: httpx.Response(200, json=payload)).get_daily_bars("SPY", START, END)


def test_repeated_page_token_and_invalid_json() -> None:
    for response in [
        httpx.Response(200, content=b"invalid JSON"),
        httpx.Response(
            200,
            json={
                "symbol": "SPY",
                "bars": [],
                "next_page_token": "loop",
            },
        ),
    ]:
        with pytest.raises(InvalidProviderData):
            adapter(lambda _, result=response: result).get_daily_bars("SPY", START, END)


def test_response_size_bound() -> None:
    with pytest.raises(InvalidProviderData, match="size limit"):
        adapter(
            lambda _: httpx.Response(200, content=b"x" * (MAX_RESPONSE_BYTES + 1))
        ).get_daily_bars("SPY", START, END)


def test_daily_timestamp_converted_to_exchange_session() -> None:
    # 01:00 UTC on Jan 3 is still Jan 2 in New York. Never take UTC date naively.
    payload = {"symbol": "SPY", "bars": [{**row(), "t": "2024-01-03T01:00:00Z"}]}
    batch = adapter(lambda _: httpx.Response(200, json=payload)).get_daily_bars("SPY", START, END)
    assert batch.bars[0].session_date == START
