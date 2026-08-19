import datetime as dt
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from app.schemas.market_data import MarketTick
from app.services.screener_service import ScreenerService

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


class MarketDataService:

    def __init__(
        self,
        screener_service: ScreenerService,
        candle_service=None,
    ):
        self.screener_service = screener_service
        self.candle_service = candle_service  # Optional CandleService instance

    def process_message(
        self,
        message: dict[str, Any],
    ) -> Any | None:

        tick = self._parse_message(message)

        if tick is None:
            return None

        self.screener_service.process_tick(
            tick
        )

        # Feed tick into CandleService if connected and return event
        if self.candle_service is not None:
            return self.candle_service.process_tick(tick)

        return None

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

        if timestamp_value is None:
            timestamp = datetime.now(IST)
        else:
            timestamp = datetime.fromtimestamp(
                float(timestamp_value),
                tz=IST,
            )

        chp_raw = message.get("chp")
        chp = Decimal(str(chp_raw)) if chp_raw is not None else None

        prev_close_raw = message.get("prev_close_price")
        prev_close_price = None
        if prev_close_raw is not None:
            try:
                val = Decimal(str(prev_close_raw))
                if val > 0:
                    prev_close_price = val
            except Exception:
                pass

        return MarketTick(
            symbol=symbol,
            ltp=Decimal(str(ltp)),
            timestamp=timestamp,
            chp=chp,
            prev_close_price=prev_close_price,
        )