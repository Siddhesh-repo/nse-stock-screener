from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(slots=True)
class MarketTick:
    symbol: str
    ltp: Decimal
    timestamp: datetime
    chp: Decimal | None = None
    prev_close_price: Decimal | None = None