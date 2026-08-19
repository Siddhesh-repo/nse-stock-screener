from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Literal

IST = timezone(timedelta(hours=5, minutes=30))

Timeframe = Literal["1m", "5m", "15m", "30m", "1h", "1D"]


@dataclass(slots=True)
class Candle:
    symbol: str
    timestamp: int  # Unix timestamp (seconds) corresponding to start of bucket in Asia/Kolkata
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int = 0
    is_closed: bool = False

    def to_dict(self) -> dict:
        dt_ist = datetime.fromtimestamp(self.timestamp, tz=IST)
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "time_ist": dt_ist.strftime("%Y-%m-%d %H:%M:%S"),
            "open": float(self.open),
            "high": float(self.high),
            "low": float(self.low),
            "close": float(self.close),
            "volume": self.volume,
            "is_closed": self.is_closed,
        }
