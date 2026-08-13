from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(slots=True)
class MarketTick:
    symbol: str
    ltp: Decimal
    timestamp: datetime