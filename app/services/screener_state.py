from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(slots=True)
class ScreenedState:

    trigger_time: datetime
    ltp: Decimal
    percentage_change: Decimal


class ScreenerState:

    def __init__(self):

        # stock_id -> previous trading-day close
        self.previous_closes: dict[
            int,
            Decimal,
        ] = {}

        # stock_id -> currently screened state
        self.screened: dict[
            int,
            ScreenedState,
        ] = {}

        # symbol -> stock_id
        self.stock_ids_by_symbol: dict[
            str,
            int,
        ] = {}