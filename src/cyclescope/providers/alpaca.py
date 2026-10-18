import json
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any, Literal
from zoneinfo import ZoneInfo

import httpx
from pydantic import ValidationError

from cyclescope.domain.errors import InvalidProviderData, ProviderUnavailable
from cyclescope.domain.models import BarBatch, DailyBar, DataKind, DateRange
from cyclescope.providers.base import instrument_for

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_PAGES = 20


class AlpacaProvider:
    """Bounded, synchronous historical-bars adapter. No network calls on import."""

    provider_id = "alpaca"
    data_kind: DataKind = "real"

    def __init__(
        self,
        key_id: str | None,
        secret_key: str | None,
        feed: Literal["iex", "sip"] = "iex",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.key_id = key_id
        self.secret_key = secret_key
        self.feed = feed
        self.provider_id = f"alpaca-{feed}"
        self.transport = transport

    def get_daily_bars(self, symbol: str, start: date, end: date) -> BarBatch:
        instrument_for(symbol)
        DateRange(start=start, end=end)
        if not self.key_id or not self.secret_key:
            raise ProviderUnavailable(
                "Alpaca requires APCA_API_KEY_ID and APCA_API_SECRET_KEY; no synthetic fallback"
            )
        zone = ZoneInfo("America/New_York")
        params = {
            "timeframe": "1Day",
            "start": datetime.combine(start, time.min, zone).isoformat(),
            # Alpaca's end is inclusive: next midnight can include the NEXT daily bar.
            "end": datetime.combine(end, time.max, zone).isoformat(),
            "adjustment": "all",
            "feed": self.feed,
            "sort": "asc",
            "limit": "10000",
        }
        bars: list[DailyBar] = []
        tokens: set[str] = set()
        fetched_at = datetime.now(UTC)
        try:
            with httpx.Client(
                timeout=10,
                follow_redirects=False,
                transport=self.transport,
                headers={"APCA-API-KEY-ID": self.key_id, "APCA-API-SECRET-KEY": self.secret_key},
            ) as client:
                for _ in range(MAX_PAGES):
                    with client.stream(
                        "GET", f"https://data.alpaca.markets/v2/stocks/{symbol}/bars", params=params
                    ) as response:
                        if response.status_code != 200:
                            raise ProviderUnavailable(
                                f"Alpaca returned HTTP {response.status_code}; "
                                "check feed access/limits"
                            )
                        content = bytearray()
                        for chunk in response.iter_bytes(chunk_size=65536):
                            content.extend(chunk)
                            if len(content) > MAX_RESPONSE_BYTES:
                                raise InvalidProviderData("Provider response exceeds size limit")
                    payload = json.loads(content, parse_float=Decimal)
                    if not isinstance(payload, dict) or not isinstance(payload.get("bars"), list):
                        raise InvalidProviderData("Provider response has no valid bars array")
                    if payload.get("symbol") != symbol:
                        raise InvalidProviderData("Provider response symbol does not match request")
                    bars.extend(self._parse_bar(symbol, row) for row in payload["bars"])
                    if len(bars) > 4000:
                        raise InvalidProviderData("Provider exceeded bounded daily-bar count")
                    token = payload.get("next_page_token")
                    if token is None:
                        break
                    if not isinstance(token, str) or not token or token in tokens:
                        raise InvalidProviderData(
                            "Provider pagination token is invalid or repeated"
                        )
                    tokens.add(token)
                    params["page_token"] = token
                else:
                    raise InvalidProviderData("Provider pagination exceeded page limit")
        except httpx.HTTPError as exc:
            raise ProviderUnavailable("Alpaca network request failed or timed out") from exc
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            raise InvalidProviderData("Malformed provider bar payload") from exc
        return BarBatch(
            symbol=symbol,
            provider=self.provider_id,
            data_kind=self.data_kind,
            data_version=f"alpaca-v2:feed={self.feed}:adjustment=all",
            fetched_at=fetched_at,
            bars=tuple(bars),
        )

    @staticmethod
    def _parse_bar(symbol: str, row: Any) -> DailyBar:
        if not isinstance(row, dict) or not isinstance(row.get("t"), str):
            raise InvalidProviderData("Malformed provider bar")
        timestamp = datetime.fromisoformat(row["t"].replace("Z", "+00:00"))
        if timestamp.utcoffset() is None:
            raise InvalidProviderData("Provider timestamp must include a timezone")
        try:
            return DailyBar(
                symbol=symbol,
                session_date=timestamp.astimezone(ZoneInfo("America/New_York")).date(),
                open=row["o"],
                high=row["h"],
                low=row["l"],
                close=row["c"],
                volume=row["v"],
            )
        except ValidationError as exc:
            raise InvalidProviderData("Provider OHLCV validation failed") from exc
