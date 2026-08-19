from collections import deque
from dataclasses import dataclass
from datetime import datetime, time, timezone, timedelta
from decimal import Decimal
import threading
from typing import Any, Dict, List, Literal, Optional
from zoneinfo import ZoneInfo

from app.schemas.candle import Candle, Timeframe
from app.schemas.market_data import MarketTick

# Timezone constant for Asia/Kolkata (IST)
try:
    IST = ZoneInfo("Asia/Kolkata")
except Exception:
    IST = timezone(timedelta(hours=5, minutes=30))

MARKET_OPEN_TIME = time(9, 15, 0)
MARKET_CLOSE_TIME = time(15, 30, 0)
MARKET_OPEN_MINUTES = 9 * 60 + 15  # 555 minutes past midnight
DEFAULT_MAX_CANDLES = 375  # Number of 1-min candles in a full trading day (09:15 - 15:30)

# Timeframe durations in minutes
TIMEFRAME_MINUTES: Dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
}

CandleEventType = Literal["update", "new", "closed"]


@dataclass(slots=True)
class CandleEvent:
    """Event emitted by CandleService when candle state changes."""
    event_type: CandleEventType
    candle: Candle
    closed_candle: Optional[Candle] = None  # Set when event_type is "new" (the candle that just closed)


class SymbolCandleState:
    """Internal thread-safe state container for a single symbol's candle history."""
    __slots__ = (
        "symbol",
        "current_1m",
        "rolling_1m",
        "last_tick_time",
        "lock",
    )

    def __init__(self, symbol: str, max_candles: int = DEFAULT_MAX_CANDLES):
        self.symbol: str = symbol
        self.current_1m: Optional[Candle] = None
        self.rolling_1m: deque[Candle] = deque(maxlen=max_candles)
        self.last_tick_time: int = 0
        self.lock: threading.Lock = threading.Lock()


class CandleService:
    """Core Candle Service responsible for converting MarketTicks into 1-minute OHLC candles,

    managing forming candles, maintaining rolling in-memory history, and enforcing market
    session and timezone boundaries without database or external dependencies.
    """

    def __init__(self, max_candles_per_symbol: int = DEFAULT_MAX_CANDLES):
        self._max_candles = max_candles_per_symbol
        self._states: Dict[str, SymbolCandleState] = {}
        self._global_lock = threading.Lock()

    def _get_or_create_state(self, symbol: str) -> SymbolCandleState:
        with self._global_lock:
            if symbol not in self._states:
                self._states[symbol] = SymbolCandleState(
                    symbol=symbol,
                    max_candles=self._max_candles,
                )
            return self._states[symbol]

    @staticmethod
    def get_bucket_timestamp(ts: datetime | int | float) -> int:
        """Calculates the 1-minute bucket timestamp (epoch seconds) for a given timestamp

        in Asia/Kolkata timezone.
        """
        if isinstance(ts, (int, float)):
            dt_obj = datetime.fromtimestamp(float(ts), tz=IST)
        elif isinstance(ts, datetime):
            if ts.tzinfo is None:
                dt_obj = ts.replace(tzinfo=IST)
            else:
                dt_obj = ts.astimezone(IST)
        else:
            raise ValueError(f"Unsupported timestamp format: {type(ts)}")

        # Floor datetime to start of minute
        bucket_dt = dt_obj.replace(second=0, microsecond=0)
        return int(bucket_dt.timestamp())

    @staticmethod
    def is_within_market_session(ts: datetime | int | float) -> bool:
        """Checks if a given timestamp falls within regular NSE market hours (09:15:00 - 15:30:00 IST)."""
        if isinstance(ts, (int, float)):
            dt_obj = datetime.fromtimestamp(float(ts), tz=IST)
        elif isinstance(ts, datetime):
            if ts.tzinfo is None:
                dt_obj = ts.replace(tzinfo=IST)
            else:
                dt_obj = ts.astimezone(IST)
        else:
            return False

        t = dt_obj.time()
        return MARKET_OPEN_TIME <= t <= MARKET_CLOSE_TIME

    @staticmethod
    def get_timeframe_bucket(epoch_ts: int, timeframe: str) -> int:
        """Calculates the start-of-bucket epoch for a given timeframe aligned to market open (09:15 IST).

        For 1m, returns the same epoch. For 5m/15m/30m/1h, floors to the nearest
        timeframe boundary anchored at 09:15.
        """
        if timeframe == "1m":
            return epoch_ts

        tf_minutes = TIMEFRAME_MINUTES.get(timeframe, 1)
        dt_obj = datetime.fromtimestamp(epoch_ts, tz=IST)
        minutes_since_midnight = dt_obj.hour * 60 + dt_obj.minute
        minutes_since_open = minutes_since_midnight - MARKET_OPEN_MINUTES
        bucket_offset = (minutes_since_open // tf_minutes) * tf_minutes
        bucket_minutes = MARKET_OPEN_MINUTES + bucket_offset

        bucket_hour = bucket_minutes // 60
        bucket_minute = bucket_minutes % 60
        bucket_dt = dt_obj.replace(hour=bucket_hour, minute=bucket_minute, second=0, microsecond=0)
        return int(bucket_dt.timestamp())

    def process_tick(self, tick: MarketTick) -> Optional[CandleEvent]:
        """Processes an incoming MarketTick and updates the symbol's 1-minute candle state.

        Returns a CandleEvent describing the state change, or None if the tick is ignored.
        """
        if tick is None or not tick.symbol or tick.ltp is None:
            return None

        # Check market session
        if not self.is_within_market_session(tick.timestamp):
            # Pre-market ticks (< 09:15) are ignored for candle generation.
            # Ticks at > 15:30 finalize any open candle without starting a new one.
            if isinstance(tick.timestamp, (int, float)):
                dt_obj = datetime.fromtimestamp(float(tick.timestamp), tz=IST)
            else:
                dt_obj = tick.timestamp if tick.timestamp.tzinfo else tick.timestamp.replace(tzinfo=IST)
                dt_obj = dt_obj.astimezone(IST)

            state = self._get_or_create_state(tick.symbol)
            with state.lock:
                if dt_obj.time() > MARKET_CLOSE_TIME and state.current_1m is not None:
                    state.current_1m.is_closed = True
                    closed = state.current_1m
                    state.rolling_1m.append(state.current_1m)
                    state.current_1m = None
                    return CandleEvent(event_type="closed", candle=closed)
            return None

        bucket_ts = self.get_bucket_timestamp(tick.timestamp)
        tick_epoch = int(tick.timestamp.timestamp()) if isinstance(tick.timestamp, datetime) else int(tick.timestamp)
        ltp = Decimal(str(tick.ltp))

        state = self._get_or_create_state(tick.symbol)

        with state.lock:
            # Case 1: No current forming candle exists (e.g. first tick of session or after close)
            if state.current_1m is None:
                state.current_1m = Candle(
                    symbol=tick.symbol,
                    timestamp=bucket_ts,
                    open=ltp,
                    high=ltp,
                    low=ltp,
                    close=ltp,
                    volume=0,
                    is_closed=False,
                )
                state.last_tick_time = tick_epoch
                return CandleEvent(event_type="new", candle=state.current_1m)

            # Case 2: Tick belongs to the current active 1-minute bucket
            if bucket_ts == state.current_1m.timestamp:
                state.current_1m.high = max(state.current_1m.high, ltp)
                state.current_1m.low = min(state.current_1m.low, ltp)

                # Only update close if tick is not out-of-order within the same bucket
                if tick_epoch >= state.last_tick_time:
                    state.current_1m.close = ltp
                    state.last_tick_time = tick_epoch

                return CandleEvent(event_type="update", candle=state.current_1m)

            # Case 3: Minute Rollover / New Bucket Starts (bucket_ts > current_1m.timestamp)
            if bucket_ts > state.current_1m.timestamp:
                # Finalize current forming candle
                state.current_1m.is_closed = True
                closed_candle = state.current_1m
                state.rolling_1m.append(state.current_1m)

                # Initialize new forming candle for the new bucket
                state.current_1m = Candle(
                    symbol=tick.symbol,
                    timestamp=bucket_ts,
                    open=ltp,
                    high=ltp,
                    low=ltp,
                    close=ltp,
                    volume=0,
                    is_closed=False,
                )
                state.last_tick_time = tick_epoch
                return CandleEvent(
                    event_type="new",
                    candle=state.current_1m,
                    closed_candle=closed_candle,
                )

            # Case 4: Out-of-Order / Late Tick (bucket_ts < current_1m.timestamp)
            if bucket_ts < state.current_1m.timestamp:
                # Search in rolling_1m history for the matching historical candle
                for hist_candle in state.rolling_1m:
                    if hist_candle.timestamp == bucket_ts:
                        hist_candle.high = max(hist_candle.high, ltp)
                        hist_candle.low = min(hist_candle.low, ltp)
                        break
                # Do not modify state.current_1m for late ticks belonging to prior buckets
                return CandleEvent(event_type="update", candle=state.current_1m)

        return None

    def get_current_candle(self, symbol: str) -> Optional[Candle]:
        """Returns the current active forming candle for a symbol, if any."""
        with self._global_lock:
            state = self._states.get(symbol)
        if not state:
            return None
        with state.lock:
            return state.current_1m

    def get_rolling_candles(self, symbol: str) -> List[Candle]:
        """Returns a copy of closed rolling 1-minute candles for a symbol."""
        with self._global_lock:
            state = self._states.get(symbol)
        if not state:
            return []
        with state.lock:
            return list(state.rolling_1m)

    def get_all_candles(self, symbol: str) -> List[Candle]:
        """Returns a list of all closed candles plus the current forming candle if present."""
        with self._global_lock:
            state = self._states.get(symbol)
        if not state:
            return []
        with state.lock:
            result = list(state.rolling_1m)
            if state.current_1m is not None:
                result.append(state.current_1m)
            return result

    def get_candles_for_timeframe(self, symbol: str, timeframe: str) -> List[Candle]:
        """Returns 1m candles aggregated to the requested timeframe.

        For "1m", returns all candles directly.
        For higher timeframes, groups 1m candles into the appropriate buckets.
        """
        all_1m = self.get_all_candles(symbol)

        if timeframe == "1m" or not all_1m:
            return all_1m

        return self.aggregate_candles(all_1m, timeframe)

    def aggregate_candles(self, candles_1m: List[Candle], timeframe: str) -> List[Candle]:
        """Aggregates a list of 1m candles into higher-timeframe candles."""
        if timeframe == "1m" or not candles_1m:
            return candles_1m

        tf_minutes = TIMEFRAME_MINUTES.get(timeframe)
        if tf_minutes is None:
            return candles_1m

        grouped: Dict[int, List[Candle]] = {}
        for c in candles_1m:
            bucket = self.get_timeframe_bucket(c.timestamp, timeframe)
            grouped.setdefault(bucket, []).append(c)

        aggregated: List[Candle] = []
        for bucket_ts in sorted(grouped.keys()):
            group = grouped[bucket_ts]
            first = group[0]
            last = group[-1]

            # A higher-TF candle is closed only when all constituent 1m candles are closed
            # AND the expected number of 1m candles for the bucket are present
            all_closed = all(c.is_closed for c in group)
            expected_count = tf_minutes  # One 1m candle per minute in the bucket
            is_complete = all_closed and len(group) >= expected_count

            agg = Candle(
                symbol=first.symbol,
                timestamp=bucket_ts,
                open=first.open,
                high=max(c.high for c in group),
                low=min(c.low for c in group),
                close=last.close,
                volume=sum(c.volume for c in group),
                is_closed=is_complete,
            )
            aggregated.append(agg)

        return aggregated

    @staticmethod
    def parse_fyers_history(symbol: str, fyers_response: dict) -> List[Candle]:
        """Parses a FYERS history API response into a list of Candle objects.

        FYERS candle format: [timestamp, open, high, low, close, volume]
        """
        candles_raw = fyers_response.get("candles", [])
        if not candles_raw:
            return []

        result: List[Candle] = []
        for row in candles_raw:
            if len(row) < 6:
                continue
            result.append(Candle(
                symbol=symbol,
                timestamp=int(row[0]),
                open=Decimal(str(row[1])),
                high=Decimal(str(row[2])),
                low=Decimal(str(row[3])),
                close=Decimal(str(row[4])),
                volume=int(row[5]),
                is_closed=True,
            ))
        return result

    def merge_historical_and_live(
        self,
        symbol: str,
        historical: List[Candle],
        timeframe: str,
    ) -> List[Candle]:
        """Merges historical candles from FYERS with live in-memory candles.

        Deduplicates by timestamp (live candles take priority over historical for
        the same bucket because they contain the most up-to-date data).
        """
        live = self.get_candles_for_timeframe(symbol, timeframe)

        # Build a set of live timestamps for dedup
        live_timestamps = {c.timestamp for c in live}

        # Take historical candles that don't overlap with live
        merged = [c for c in historical if c.timestamp not in live_timestamps]
        merged.extend(live)
        merged.sort(key=lambda c: c.timestamp)
        return merged

    def clear_symbol(self, symbol: str) -> None:
        """Clears state for a single symbol."""
        with self._global_lock:
            self._states.pop(symbol, None)

    def clear_all(self) -> None:
        """Clears state for all symbols."""
        with self._global_lock:
            self._states.clear()
