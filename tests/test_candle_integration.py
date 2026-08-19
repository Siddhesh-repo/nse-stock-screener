"""Integration tests for CandleService integration with MarketDataService, LiveStore, and FyersService.

Tests cover:
- MarketDataService → CandleService tick flow
- Higher timeframe aggregation (5m, 15m, 30m, 1h)
- FYERS historical response parsing
- Historical + live candle merging
- LiveStore candle event queuing
- CandleEvent lifecycle (new, update, closed)
- Timeframe bucket boundary calculations
"""
import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from datetime import datetime, timedelta
from decimal import Decimal

from app.schemas.market_data import MarketTick
from app.schemas.candle import Candle
from app.services.candle_service import CandleService, CandleEvent, IST


def make_tick(
    symbol: str,
    ltp: float,
    hour: int = 10,
    minute: int = 15,
    second: int = 0,
) -> MarketTick:
    dt = datetime(2026, 8, 17, hour, minute, second, tzinfo=IST)
    return MarketTick(
        symbol=symbol,
        ltp=Decimal(str(ltp)),
        timestamp=dt,
    )


# --- Higher Timeframe Aggregation Tests ---

def test_5m_aggregation():
    """5 consecutive 1m candles should aggregate into one 5m candle."""
    service = CandleService()
    sym = "NSE:RELIANCE-EQ"

    # Feed ticks for 09:15 through 09:19 (5 minutes)
    prices = [(9, 15, 100), (9, 16, 105), (9, 17, 98), (9, 18, 110), (9, 19, 107)]
    for h, m, p in prices:
        service.process_tick(make_tick(sym, p, hour=h, minute=m, second=10))

    # Move to 09:20 to finalize the 09:19 candle
    service.process_tick(make_tick(sym, 108, hour=9, minute=20, second=0))

    candles_5m = service.get_candles_for_timeframe(sym, "5m")
    assert len(candles_5m) >= 1

    # First 5m candle: 09:15-09:19
    first_5m = candles_5m[0]
    bucket_dt = datetime.fromtimestamp(first_5m.timestamp, tz=IST)
    assert bucket_dt.hour == 9
    assert bucket_dt.minute == 15
    assert first_5m.open == Decimal("100")
    assert first_5m.high == Decimal("110")
    assert first_5m.low == Decimal("98")
    assert first_5m.close == Decimal("107")
    assert first_5m.is_closed is True


def test_15m_aggregation():
    """15 consecutive 1m candles should aggregate into one 15m candle."""
    service = CandleService()
    sym = "NSE:TCS-EQ"

    # Feed ticks for 09:15 through 09:29 (15 minutes)
    for m in range(15, 30):
        price = 4000 + m
        service.process_tick(make_tick(sym, price, hour=9, minute=m, second=5))

    # Move to 09:30 to finalize the 09:29 candle
    service.process_tick(make_tick(sym, 4030, hour=9, minute=30, second=0))

    candles_15m = service.get_candles_for_timeframe(sym, "15m")
    assert len(candles_15m) >= 1

    first_15m = candles_15m[0]
    bucket_dt = datetime.fromtimestamp(first_15m.timestamp, tz=IST)
    assert bucket_dt.hour == 9
    assert bucket_dt.minute == 15
    assert first_15m.open == Decimal("4015")
    assert first_15m.high == Decimal("4029")
    assert first_15m.low == Decimal("4015")
    assert first_15m.close == Decimal("4029")
    assert first_15m.is_closed is True


def test_30m_aggregation():
    """30 consecutive 1m candles should aggregate into one 30m candle."""
    service = CandleService()
    sym = "NSE:INFY-EQ"

    # Feed ticks for 09:15 through 09:44 (30 minutes)
    for m in range(15, 45):
        price = 1800 + (m - 15)
        service.process_tick(make_tick(sym, price, hour=9, minute=m, second=5))

    # Move to 09:45 to finalize the 09:44 candle
    service.process_tick(make_tick(sym, 1830, hour=9, minute=45, second=0))

    candles_30m = service.get_candles_for_timeframe(sym, "30m")
    assert len(candles_30m) >= 1

    first_30m = candles_30m[0]
    bucket_dt = datetime.fromtimestamp(first_30m.timestamp, tz=IST)
    assert bucket_dt.hour == 9
    assert bucket_dt.minute == 15
    assert first_30m.open == Decimal("1800")
    assert first_30m.close == Decimal("1829")
    assert first_30m.is_closed is True


def test_1h_aggregation():
    """60 consecutive 1m candles should aggregate into one 1h candle."""
    service = CandleService()
    sym = "NSE:SBIN-EQ"

    # Feed ticks for 09:15 through 10:14 (60 minutes)
    for i in range(60):
        h = 9 + (15 + i) // 60
        m = (15 + i) % 60
        price = 800 + i
        service.process_tick(make_tick(sym, price, hour=h, minute=m, second=5))

    # Move to 10:15 to finalize the 10:14 candle
    service.process_tick(make_tick(sym, 860, hour=10, minute=15, second=0))

    candles_1h = service.get_candles_for_timeframe(sym, "1h")
    assert len(candles_1h) >= 1

    first_1h = candles_1h[0]
    bucket_dt = datetime.fromtimestamp(first_1h.timestamp, tz=IST)
    assert bucket_dt.hour == 9
    assert bucket_dt.minute == 15
    assert first_1h.open == Decimal("800")
    assert first_1h.close == Decimal("859")
    assert first_1h.is_closed is True


def test_5m_bucket_boundaries():
    """Verify 5m buckets align to market open (09:15)."""
    service = CandleService()

    # 09:15 → bucket 09:15
    ts_0915 = datetime(2026, 8, 17, 9, 15, 0, tzinfo=IST)
    bucket = service.get_timeframe_bucket(int(ts_0915.timestamp()), "5m")
    dt = datetime.fromtimestamp(bucket, tz=IST)
    assert dt.hour == 9 and dt.minute == 15

    # 09:19 → bucket 09:15
    ts_0919 = datetime(2026, 8, 17, 9, 19, 0, tzinfo=IST)
    bucket = service.get_timeframe_bucket(int(ts_0919.timestamp()), "5m")
    dt = datetime.fromtimestamp(bucket, tz=IST)
    assert dt.hour == 9 and dt.minute == 15

    # 09:20 → bucket 09:20
    ts_0920 = datetime(2026, 8, 17, 9, 20, 0, tzinfo=IST)
    bucket = service.get_timeframe_bucket(int(ts_0920.timestamp()), "5m")
    dt = datetime.fromtimestamp(bucket, tz=IST)
    assert dt.hour == 9 and dt.minute == 20


def test_15m_bucket_boundaries():
    """Verify 15m buckets align to market open (09:15)."""
    service = CandleService()

    # 09:29 → bucket 09:15
    ts = datetime(2026, 8, 17, 9, 29, 0, tzinfo=IST)
    bucket = service.get_timeframe_bucket(int(ts.timestamp()), "15m")
    dt = datetime.fromtimestamp(bucket, tz=IST)
    assert dt.hour == 9 and dt.minute == 15

    # 09:30 → bucket 09:30
    ts = datetime(2026, 8, 17, 9, 30, 0, tzinfo=IST)
    bucket = service.get_timeframe_bucket(int(ts.timestamp()), "15m")
    dt = datetime.fromtimestamp(bucket, tz=IST)
    assert dt.hour == 9 and dt.minute == 30


def test_1h_bucket_boundaries():
    """Verify 1h buckets align to market open (09:15)."""
    service = CandleService()

    # 10:14 → bucket 09:15
    ts = datetime(2026, 8, 17, 10, 14, 0, tzinfo=IST)
    bucket = service.get_timeframe_bucket(int(ts.timestamp()), "1h")
    dt = datetime.fromtimestamp(bucket, tz=IST)
    assert dt.hour == 9 and dt.minute == 15

    # 10:15 → bucket 10:15
    ts = datetime(2026, 8, 17, 10, 15, 0, tzinfo=IST)
    bucket = service.get_timeframe_bucket(int(ts.timestamp()), "1h")
    dt = datetime.fromtimestamp(bucket, tz=IST)
    assert dt.hour == 10 and dt.minute == 15


# --- FYERS Historical Parsing Tests ---

def test_parse_fyers_history():
    """Verify parsing of FYERS REST API candle response."""
    mock_response = {
        "s": "ok",
        "candles": [
            [1723857300, 2950.10, 2955.00, 2948.50, 2954.20, 12500],
            [1723857360, 2954.20, 2958.00, 2953.00, 2956.80, 8400],
        ],
    }

    candles = CandleService.parse_fyers_history("NSE:RELIANCE-EQ", mock_response)
    assert len(candles) == 2
    assert candles[0].symbol == "NSE:RELIANCE-EQ"
    assert candles[0].open == Decimal("2950.10")
    assert candles[0].high == Decimal("2955.00")
    assert candles[0].low == Decimal("2948.50")
    assert candles[0].close == Decimal("2954.20")
    assert candles[0].volume == 12500
    assert candles[0].is_closed is True
    assert candles[1].timestamp == 1723857360


def test_parse_fyers_history_empty():
    """Empty or missing candles key returns empty list."""
    assert CandleService.parse_fyers_history("NSE:X-EQ", {}) == []
    assert CandleService.parse_fyers_history("NSE:X-EQ", {"candles": []}) == []
    assert CandleService.parse_fyers_history("NSE:X-EQ", {"s": "error"}) == []


def test_parse_fyers_history_malformed_rows():
    """Rows with fewer than 6 fields are skipped."""
    mock_response = {
        "candles": [
            [1723857300, 100, 105],  # too short, skipped
            [1723857360, 200, 210, 195, 208, 5000],  # valid
        ],
    }
    candles = CandleService.parse_fyers_history("NSE:X-EQ", mock_response)
    assert len(candles) == 1
    assert candles[0].open == Decimal("200")


# --- Historical + Live Merging Tests ---

def test_merge_historical_and_live_no_overlap():
    """Historical and live candles with distinct timestamps merge cleanly."""
    service = CandleService()
    sym = "NSE:RELIANCE-EQ"

    # Create some live candles at 10:15 and 10:16
    service.process_tick(make_tick(sym, 100, hour=10, minute=15, second=5))
    service.process_tick(make_tick(sym, 105, hour=10, minute=16, second=5))

    # Historical candles from earlier (09:15, 09:16)
    ts_0915 = int(datetime(2026, 8, 17, 9, 15, 0, tzinfo=IST).timestamp())
    ts_0916 = int(datetime(2026, 8, 17, 9, 16, 0, tzinfo=IST).timestamp())
    historical = [
        Candle(sym, ts_0915, Decimal("90"), Decimal("95"), Decimal("88"), Decimal("93"), 1000, True),
        Candle(sym, ts_0916, Decimal("93"), Decimal("97"), Decimal("92"), Decimal("96"), 800, True),
    ]

    merged = service.merge_historical_and_live(sym, historical, "1m")
    # Should have historical (2) + live (2) = 4 candles
    assert len(merged) == 4
    # Should be sorted by timestamp
    timestamps = [c.timestamp for c in merged]
    assert timestamps == sorted(timestamps)


def test_merge_historical_and_live_with_overlap():
    """When live candle timestamps overlap with historical, live takes priority."""
    service = CandleService()
    sym = "NSE:RELIANCE-EQ"

    # Create a live candle at 10:15
    service.process_tick(make_tick(sym, 100, hour=10, minute=15, second=5))

    live_ts = service.get_current_candle(sym).timestamp

    # Historical candle with the SAME timestamp as the live candle
    historical = [
        Candle(sym, live_ts, Decimal("50"), Decimal("55"), Decimal("48"), Decimal("53"), 500, True),
    ]

    merged = service.merge_historical_and_live(sym, historical, "1m")
    # Should be 1 candle (live replaces historical)
    assert len(merged) == 1
    # Live candle should be present (open=100, not 50)
    assert merged[0].open == Decimal("100")


def test_merge_with_higher_timeframe():
    """Merge should work correctly with higher timeframe aggregation."""
    service = CandleService()
    sym = "NSE:RELIANCE-EQ"

    # Create live 1m candles for 09:15-09:19
    for m in range(15, 20):
        service.process_tick(make_tick(sym, 100 + m, hour=9, minute=m, second=5))

    # Historical 5m candle from a different 5m bucket (e.g. 09:20-09:24)
    ts_0920 = int(datetime(2026, 8, 17, 9, 20, 0, tzinfo=IST).timestamp())
    historical = [
        Candle(sym, ts_0920, Decimal("200"), Decimal("210"), Decimal("195"), Decimal("205"), 5000, True),
    ]

    merged = service.merge_historical_and_live(sym, historical, "5m")
    # Should have the live 5m candle (09:15) + historical 5m candle (09:20) = 2
    assert len(merged) == 2
    timestamps = [c.timestamp for c in merged]
    assert timestamps == sorted(timestamps)


# --- CandleEvent Lifecycle Tests ---

def test_candle_event_new_on_first_tick():
    """First tick for a symbol produces a 'new' event."""
    service = CandleService()
    event = service.process_tick(make_tick("NSE:X-EQ", 100, hour=10, minute=15))
    assert event.event_type == "new"
    assert event.closed_candle is None


def test_candle_event_update_on_same_bucket():
    """Subsequent tick in the same bucket produces 'update' event."""
    service = CandleService()
    service.process_tick(make_tick("NSE:X-EQ", 100, hour=10, minute=15, second=0))
    event = service.process_tick(make_tick("NSE:X-EQ", 105, hour=10, minute=15, second=30))
    assert event.event_type == "update"


def test_candle_event_new_with_closed_on_rollover():
    """Rollover produces 'new' event with closed_candle populated."""
    service = CandleService()
    service.process_tick(make_tick("NSE:X-EQ", 100, hour=10, minute=15, second=0))
    event = service.process_tick(make_tick("NSE:X-EQ", 110, hour=10, minute=16, second=0))
    assert event.event_type == "new"
    assert event.closed_candle is not None
    assert event.closed_candle.is_closed is True
    assert event.closed_candle.close == Decimal("100")
    assert event.candle.open == Decimal("110")


def test_candle_event_closed_on_market_close():
    """Post-market tick produces 'closed' event."""
    service = CandleService()
    service.process_tick(make_tick("NSE:X-EQ", 100, hour=15, minute=29, second=50))
    event = service.process_tick(make_tick("NSE:X-EQ", 102, hour=15, minute=30, second=5))
    assert event is not None
    assert event.event_type == "closed"
    assert event.candle.is_closed is True


# --- LiveStore Candle Event Queuing Tests ---

def test_live_store_queue_candle_event():
    """LiveStore should queue candle events for broadcast."""
    from app.services.live_store import LiveMarketStore

    store = LiveMarketStore()
    candle = Candle("NSE:X-EQ", 1723857300, Decimal("100"), Decimal("105"),
                    Decimal("98"), Decimal("103"), 1000, False)

    store.queue_candle_event("update", candle)
    assert len(store._pending_candle_events) == 1
    assert store._pending_candle_events[0]["type"] == "candle_update"
    assert store._pending_candle_events[0]["symbol"] == "NSE:X-EQ"


def test_live_store_queue_candle_new_with_closed():
    """LiveStore queues 'candle_new' event with closed candle data."""
    from app.services.live_store import LiveMarketStore

    store = LiveMarketStore()
    new_candle = Candle("NSE:X-EQ", 1723857360, Decimal("103"), Decimal("108"),
                        Decimal("102"), Decimal("107"), 0, False)
    closed_candle = Candle("NSE:X-EQ", 1723857300, Decimal("100"), Decimal("105"),
                           Decimal("98"), Decimal("103"), 1000, True)

    store.queue_candle_event("new", new_candle, closed_candle)
    assert len(store._pending_candle_events) == 1
    event = store._pending_candle_events[0]
    assert event["type"] == "candle_new"
    assert "closed_candle" in event
    assert event["closed_candle"]["is_closed"] is True


# --- MarketDataService Integration Tests ---

def test_market_data_service_feeds_candle_service():
    """MarketDataService should pass parsed ticks to CandleService."""
    from unittest.mock import MagicMock

    candle_service = CandleService()

    # Create a mock screener service that accepts process_tick
    mock_screener = MagicMock()

    from app.services.market_data_service import MarketDataService
    mds = MarketDataService(mock_screener, candle_service=candle_service)

    # Simulate a raw FYERS tick message during market hours
    ts_value = datetime(2026, 8, 17, 10, 15, 5, tzinfo=IST).timestamp()
    message = {
        "symbol": "NSE:RELIANCE-EQ",
        "ltp": 2950.5,
        "timestamp": ts_value,
        "chp": 1.5,
    }

    mds.process_message(message)

    # Screener should have been called
    assert mock_screener.process_tick.called

    # CandleService should have a candle
    candle = candle_service.get_current_candle("NSE:RELIANCE-EQ")
    assert candle is not None
    assert candle.open == Decimal("2950.5")


def test_market_data_service_without_candle_service():
    """MarketDataService works normally when candle_service is None (backward compat)."""
    from unittest.mock import MagicMock

    mock_screener = MagicMock()

    from app.services.market_data_service import MarketDataService
    mds = MarketDataService(mock_screener, candle_service=None)

    ts_value = datetime(2026, 8, 17, 10, 15, 5, tzinfo=IST).timestamp()
    message = {
        "symbol": "NSE:RELIANCE-EQ",
        "ltp": 2950.5,
        "timestamp": ts_value,
    }

    # Should not raise
    mds.process_message(message)
    assert mock_screener.process_tick.called


# --- Aggregate Candles with Missing Minutes Tests ---

def test_5m_aggregation_with_missing_minutes():
    """5m candle with only 3 out of 5 constituent 1m candles should not be marked closed."""
    service = CandleService()
    sym = "NSE:RELIANCE-EQ"

    # Only create candles for 09:15, 09:17, 09:19 (skipping 09:16, 09:18)
    service.process_tick(make_tick(sym, 100, hour=9, minute=15, second=5))
    service.process_tick(make_tick(sym, 105, hour=9, minute=17, second=5))
    service.process_tick(make_tick(sym, 110, hour=9, minute=19, second=5))

    # Rollover to 09:20 to close 09:19
    service.process_tick(make_tick(sym, 108, hour=9, minute=20, second=0))

    candles_5m = service.get_candles_for_timeframe(sym, "5m")
    # First 5m candle (09:15) has only 3 constituent minutes, so is_closed=False
    first_5m = candles_5m[0]
    assert first_5m.is_closed is False
    assert first_5m.open == Decimal("100")
    assert first_5m.high == Decimal("110")
    assert first_5m.close == Decimal("110")


# --- Candle.to_dict Tests ---

def test_candle_to_dict():
    """Verify Candle.to_dict serialization."""
    candle = Candle(
        symbol="NSE:RELIANCE-EQ",
        timestamp=1723857300,
        open=Decimal("2950.10"),
        high=Decimal("2955.00"),
        low=Decimal("2948.50"),
        close=Decimal("2954.20"),
        volume=12500,
        is_closed=True,
    )
    d = candle.to_dict()
    assert d["symbol"] == "NSE:RELIANCE-EQ"
    assert d["timestamp"] == 1723857300
    assert d["open"] == 2950.10
    assert d["high"] == 2955.00
    assert d["low"] == 2948.50
    assert d["close"] == 2954.20
    assert d["volume"] == 12500
    assert d["is_closed"] is True
    # All values should be JSON-serializable types
    assert isinstance(d["open"], float)
    assert isinstance(d["volume"], int)


if __name__ == "__main__":
    test_5m_aggregation()
    test_15m_aggregation()
    test_30m_aggregation()
    test_1h_aggregation()
    test_5m_bucket_boundaries()
    test_15m_bucket_boundaries()
    test_1h_bucket_boundaries()
    test_parse_fyers_history()
    test_parse_fyers_history_empty()
    test_parse_fyers_history_malformed_rows()
    test_merge_historical_and_live_no_overlap()
    test_merge_historical_and_live_with_overlap()
    test_merge_with_higher_timeframe()
    test_candle_event_new_on_first_tick()
    test_candle_event_update_on_same_bucket()
    test_candle_event_new_with_closed_on_rollover()
    test_candle_event_closed_on_market_close()
    test_live_store_queue_candle_event()
    test_live_store_queue_candle_new_with_closed()
    test_market_data_service_feeds_candle_service()
    test_market_data_service_without_candle_service()
    test_5m_aggregation_with_missing_minutes()
    test_candle_to_dict()
    print("✅ All 23 integration tests passed successfully!")
