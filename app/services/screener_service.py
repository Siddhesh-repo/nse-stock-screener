from datetime import date, datetime
from decimal import Decimal
import queue
from app.schemas.market_data import MarketTick
from app.services.screener_state import (
    ScreenedState,
    ScreenerState,
)
from app.schemas.screener_event import ScreenerEvent

ENTRY_THRESHOLD = Decimal("4")
EXIT_THRESHOLD = Decimal("2")


class ScreenerService:

    def __init__(self):

        self.state = ScreenerState()

        self.trading_date: date | None = None
        self.event_queue = queue.SimpleQueue()

        self.db_event_handler = None

    def process_tick(
        self,
        tick: MarketTick,
    ) -> None:

        stock_id = (
            self.state.stock_ids_by_symbol.get(
                tick.symbol
            )
        )

        if stock_id is None:
            return

        # Dynamically populate/update previous close baseline from live FYERS tick
        if tick.prev_close_price is not None and tick.prev_close_price > 0:
            self.state.previous_closes[stock_id] = tick.prev_close_price

        # Prioritize real-time official exchange % change from FYERS FullMode tick
        if tick.chp is not None:
            percentage_change = tick.chp
        else:
            previous_close = (
                self.state.previous_closes.get(
                    stock_id
                )
            )

            if previous_close is None:
                return

            percentage_change = (
                self.calculate_percentage_change(
                    ltp=tick.ltp,
                    previous_close=previous_close,
                )
            )


        screened_state = (
            self.state.screened.get(
                stock_id
            )
        )

        if screened_state is None:

            self._handle_not_screened(
                stock_id=stock_id,
                symbol=tick.symbol,
                tick=tick,
                percentage_change=percentage_change,
            )

        else:

            self._handle_screened(
                stock_id=stock_id,
                symbol=tick.symbol,
                tick=tick,
                percentage_change=percentage_change,
                screened_state=screened_state,
            )

    def _handle_not_screened(
        self,
        stock_id: int,
        symbol: str,
        tick: MarketTick,
        percentage_change: Decimal,
    ) -> None:

        if (
            percentage_change >= ENTRY_THRESHOLD
            or
            percentage_change <= -ENTRY_THRESHOLD
        ):

            self.state.screened[
                stock_id
            ] = ScreenedState(
                trigger_time=tick.timestamp,
                ltp=tick.ltp,
                percentage_change=percentage_change,
            )

            print(
                f"[SCREENED] "
                f"{symbol} "
                f"time={tick.timestamp} "
                f"ltp={tick.ltp} "
                f"change={percentage_change:.2f}%"
            )

            self._notify_screened(
                stock_id=stock_id,
                tick=tick,
                percentage_change=percentage_change,
            )

    def _handle_screened(
        self,
        stock_id: int,
        symbol: str,
        tick: MarketTick,
        percentage_change: Decimal,
        screened_state: ScreenedState,
    ) -> None:

        # Remove only when the change comes back
        # inside the -2% to +2% range.

        should_remove = (
            -EXIT_THRESHOLD
            < percentage_change
            < EXIT_THRESHOLD
        )

        if should_remove:

            del self.state.screened[
                stock_id
            ]

            print(
                f"[REMOVED] "
                f"{symbol} "
                f"time={tick.timestamp} "
                f"ltp={tick.ltp} "
                f"change={percentage_change:.2f}%"
            )

            self._notify_removed(
                stock_id=stock_id,
                tick=tick,
                percentage_change=percentage_change,
            )

            return

        # Still screened.
        #
        # Update current LTP/change in memory,
        # but DO NOT create another screening event.

        screened_state.ltp = tick.ltp

        screened_state.percentage_change = (
            percentage_change
        )

    def _notify_screened(
        self,
        stock_id: int,
        tick: MarketTick,
        percentage_change: Decimal,
    ) -> None:

        self.event_queue.put(
            ScreenerEvent(
                event_type="SCREENED",
                stock_id=stock_id,
                event_time=tick.timestamp,
                ltp=tick.ltp,
                percentage_change=percentage_change,
            )
        )

    def _notify_removed(
        self,
        stock_id: int,
        tick: MarketTick,
        percentage_change: Decimal,
    ) -> None:

        self.event_queue.put(
            ScreenerEvent(
                event_type="REMOVED",
                stock_id=stock_id,
                event_time=tick.timestamp,
                ltp=tick.ltp,
                percentage_change=percentage_change,
            )
        )

    def load_stocks(
        self,
        stocks,
    ) -> None:

        for stock in stocks:

            self.state.stock_ids_by_symbol[
                stock.symbol
            ] = stock.id

    def load_previous_closes(
        self,
        closing_prices,
    ) -> None:

        for closing_price in closing_prices:

            self.state.previous_closes[
                closing_price.stock_id
            ] = closing_price.closing_price

    def load_screened_stocks(
        self,
        screened_stocks,
    ) -> None:

        for screened_stock in screened_stocks:

            self.state.screened[
                screened_stock.stock_id
            ] = ScreenedState(
                trigger_time=(
                    screened_stock.trigger_time
                ),
                ltp=screened_stock.ltp,
                percentage_change=(
                    screened_stock.percentage_change
                ),
            )

    @staticmethod
    def calculate_percentage_change(
        ltp: Decimal,
        previous_close: Decimal,
    ) -> Decimal:

        if previous_close <= 0:

            raise ValueError(
                "Previous close must be greater than zero."
            )

        return (
            (ltp - previous_close)
            / previous_close
        ) * Decimal("100")