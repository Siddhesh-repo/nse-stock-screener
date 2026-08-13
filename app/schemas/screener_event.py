from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(slots=True)
class ScreenerEvent:

    event_type: str
    stock_id: int
    event_time: datetime
    ltp: Decimal
    percentage_change: Decimal