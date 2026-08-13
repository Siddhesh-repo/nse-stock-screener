from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.schemas.market_data import MarketTick
from app.services.screener_service import ScreenerService


class MarketDataService:

    def __init__(
        self,
        screener_service: ScreenerService,
    ):
        self.screener_service = screener_service

    def process_message(
        self,
        message: dict[str, Any],
    ) -> None:

        tick = self._parse_message(message)

        if tick is None:
            return

        self.screener_service.process_tick(
            tick
        )

    def _parse_message(
        self,
        message: dict[str, Any],
    ) -> MarketTick | None:

        # Ignore non-market-data messages
        if "symbol" not in message:
            return None

        symbol = message.get("symbol")

        if not symbol:
            return None

        ltp = message.get("ltp")

        if ltp is None:
            return None

        timestamp_value = (
            message.get("timestamp")
            or message.get("t")
        )

        import datetime as dt

        IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

        if timestamp_value is None:
            timestamp = datetime.now(
                IST
            )

        else:
            timestamp = datetime.fromtimestamp(
                float(timestamp_value),
                tz=IST,
            )

        return MarketTick(
            symbol=symbol,
            ltp=Decimal(str(ltp)),
            timestamp=timestamp,
        )