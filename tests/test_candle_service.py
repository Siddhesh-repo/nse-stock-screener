import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from datetime import datetime, time, timezone, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.schemas.market_data import MarketTick
from app.services.candle_service import CandleService, CandleEvent, IST


def make_tick(
    symbol: str,
    ltp: float | Decimal,
    year: int = 2026,
    month: int = 8,
    day: int = 17,
    hour: int = 10,
    minute: int = 15,
    second: int = 0,
    microsecond: int = 0,
) -> MarketTick:
    dt = datetime(year, month, day, hour, minute, second, microsecond, tzinfo=IST)
    return MarketTick(
        symbol=symbol,
        ltp=Decimal(str(ltp)),
        timestamp=dt,
    )


def test_first_tick_creates_candle():
    service = CandleService()
    tick = make_tick("NSE:RELIANCE-EQ", 2950.0, minute=15, second=10)

    event = service.process_tick(tick)
    assert event is not None
    assert isinstance(event, CandleEvent)
    assert event.event_type == "new"
    candle = event.candle
    assert candle.symbol == "NSE:RELIANCE-EQ"
    assert candle.open == Decimal("2950.0")
    assert candle.high == Decimal("2950.0")
    assert candle.low == Decimal("2950.0")
    assert candle.close == Decimal("2950.0")
    assert candle.is_closed is False

    current = service.get_current_candle("NSE:RELIANCE-EQ")
    assert current == candle


def test_second_tick_updates_candle():
    service = CandleService()
    t1 = make_tick("NSE:RELIANCE-EQ", 2950.0, minute=15, second=10)
    t2 = make_tick("NSE:RELIANCE-EQ", 2955.0, minute=15, second=20)

    service.process_tick(t1)
    event = service.process_tick(t2)

    assert event is not None
    assert event.event_type == "update"
    candle = event.candle
    assert candle.open == Decimal("2950.0")
    assert candle.high == Decimal("2955.0")
    assert candle.low == Decimal("2950.0")
    assert candle.close == Decimal("2955.0")
    assert candle.is_closed is False


def test_high_update():
    service = CandleService()
    t1 = make_tick("NSE:TATASTEEL-EQ", 150.0, minute=15, second=0)
    t2 = make_tick("NSE:TATASTEEL-EQ", 155.0, minute=15, second=15)
    t3 = make_tick("NSE:TATASTEEL-EQ", 152.0, minute=15, second=30)

    service.process_tick(t1)
    service.process_tick(t2)
    event = service.process_tick(t3)

    assert event.candle.high == Decimal("155.0")
    assert event.candle.close == Decimal("152.0")


def test_low_update():
    service = CandleService()
    t1 = make_tick("NSE:INFY-EQ", 1800.0, minute=15, second=0)
    t2 = make_tick("NSE:INFY-EQ", 1785.0, minute=15, second=10)
    t3 = make_tick("NSE:INFY-EQ", 1790.0, minute=15, second=20)

    service.process_tick(t1)
    service.process_tick(t2)
    event = service.process_tick(t3)

    assert event.candle.low == Decimal("1785.0")
    assert event.candle.close == Decimal("1790.0")


def test_close_update():
    service = CandleService()
    t1 = make_tick("NSE:SBIN-EQ", 800.0, minute=15, second=0)
    t2 = make_tick("NSE:SBIN-EQ", 805.0, minute=15, second=20)
    t3 = make_tick("NSE:SBIN-EQ", 802.5, minute=15, second=45)

    service.process_tick(t1)
    service.process_tick(t2)
    event = service.process_tick(t3)

    assert event.candle.close == Decimal("802.5")


def test_minute_rollover():
    service = CandleService()
    # Bucket 10:15
    t1 = make_tick("NSE:RELIANCE-EQ", 2950.0, minute=15, second=10)
    t2 = make_tick("NSE:RELIANCE-EQ", 2960.0, minute=15, second=50)

    # Bucket 10:16 (triggers rollover)
    t3 = make_tick("NSE:RELIANCE-EQ", 2958.0, minute=16, second=5)

    service.process_tick(t1)
    service.process_tick(t2)

    event = service.process_tick(t3)

    # Event should be "new" with closed_candle set
    assert event.event_type == "new"
    assert event.closed_candle is not None
    assert event.closed_candle.is_closed is True
    assert event.closed_candle.open == Decimal("2950.0")
    assert event.closed_candle.high == Decimal("2960.0")
    assert event.closed_candle.close == Decimal("2960.0")

    # Check that previous candle is finalized in rolling history
    rolling = service.get_rolling_candles("NSE:RELIANCE-EQ")
    assert len(rolling) == 1
    assert rolling[0].is_closed is True

    # Check new forming candle
    new_candle = event.candle
    assert new_candle.is_closed is False
    assert new_candle.open == Decimal("2958.0")
    assert new_candle.close == Decimal("2958.0")


def test_multiple_symbols():
    service = CandleService()
    t_rel1 = make_tick("NSE:RELIANCE-EQ", 2950.0, minute=15, second=5)
    t_tcs1 = make_tick("NSE:TCS-EQ", 4200.0, minute=15, second=10)
    t_rel2 = make_tick("NSE:RELIANCE-EQ", 2955.0, minute=15, second=20)

    e_rel = service.process_tick(t_rel1)
    e_tcs = service.process_tick(t_tcs1)
    e_rel_upd = service.process_tick(t_rel2)

    assert e_rel.candle.symbol == "NSE:RELIANCE-EQ"
    assert e_tcs.candle.symbol == "NSE:TCS-EQ"
    assert e_tcs.candle.open == Decimal("4200.0")
    assert e_rel_upd.candle.high == Decimal("2955.0")
    assert service.get_current_candle("NSE:TCS-EQ").close == Decimal("4200.0")


def test_missing_tick_periods():
    service = CandleService()
    # Tick at 10:15
    t1 = make_tick("NSE:RELIANCE-EQ", 2950.0, minute=15, second=10)
    # No ticks at 10:16, 10:17, 10:18!
    # Tick arrives at 10:19
    t2 = make_tick("NSE:RELIANCE-EQ", 2970.0, minute=19, second=5)

    service.process_tick(t1)
    service.process_tick(t2)

    rolling = service.get_rolling_candles("NSE:RELIANCE-EQ")
    assert len(rolling) == 1
    assert rolling[0].is_closed is True
    # Bucket for 10:15 candle
    dt_closed = datetime.fromtimestamp(rolling[0].timestamp, tz=IST)
    assert dt_closed.minute == 15

    current = service.get_current_candle("NSE:RELIANCE-EQ")
    dt_current = datetime.fromtimestamp(current.timestamp, tz=IST)
    assert dt_current.minute == 19
    # No manufactured candles for 10:16, 10:17, 10:18
    all_candles = service.get_all_candles("NSE:RELIANCE-EQ")
    assert len(all_candles) == 2


def test_duplicate_ticks():
    service = CandleService()
    t1 = make_tick("NSE:RELIANCE-EQ", 2950.0, minute=15, second=10)
    t2 = make_tick("NSE:RELIANCE-EQ", 2950.0, minute=15, second=10)

    service.process_tick(t1)
    event = service.process_tick(t2)

    assert event.candle.open == Decimal("2950.0")
    assert event.candle.high == Decimal("2950.0")
    assert event.candle.low == Decimal("2950.0")
    assert event.candle.close == Decimal("2950.0")
    assert service.get_rolling_candles("NSE:RELIANCE-EQ") == []


def test_out_of_order_ticks():
    service = CandleService()
    # 10:15 candle
    t1 = make_tick("NSE:RELIANCE-EQ", 2950.0, minute=15, second=10)
    service.process_tick(t1)

    # Rollover to 10:16 candle
    t2 = make_tick("NSE:RELIANCE-EQ", 2960.0, minute=16, second=5)
    service.process_tick(t2)

    # Late tick belonging to 10:15 arrives with new HIGH (2965.0)
    t_late = make_tick("NSE:RELIANCE-EQ", 2965.0, minute=15, second=40)
    service.process_tick(t_late)

    # Verify that closed 10:15 candle high was updated
    rolling = service.get_rolling_candles("NSE:RELIANCE-EQ")
    assert len(rolling) == 1
    assert rolling[0].high == Decimal("2965.0")
    # Verify current 10:16 forming candle remains unchanged by the late tick
    current = service.get_current_candle("NSE:RELIANCE-EQ")
    assert current.open == Decimal("2960.0")


def test_market_open_boundary():
    service = CandleService()
    # Pre-market tick at 09:14:59 IST (should be ignored)
    t_pre = make_tick("NSE:RELIANCE-EQ", 2940.0, hour=9, minute=14, second=59)
    res_pre = service.process_tick(t_pre)
    assert res_pre is None
    assert service.get_current_candle("NSE:RELIANCE-EQ") is None

    # Market open tick at 09:15:00 IST
    t_open = make_tick("NSE:RELIANCE-EQ", 2945.0, hour=9, minute=15, second=0)
    res_open = service.process_tick(t_open)
    assert res_open is not None
    assert res_open.candle.open == Decimal("2945.0")


def test_market_close_boundary():
    service = CandleService()
    # Tick at 15:29:50 IST (last regular minute)
    t_last = make_tick("NSE:RELIANCE-EQ", 2950.0, hour=15, minute=29, second=50)
    service.process_tick(t_last)

    # Post-market tick at 15:30:05 IST
    t_post = make_tick("NSE:RELIANCE-EQ", 2952.0, hour=15, minute=30, second=5)
    event = service.process_tick(t_post)

    # 15:29 candle should be finalized and pushed to rolling
    rolling = service.get_rolling_candles("NSE:RELIANCE-EQ")
    assert len(rolling) == 1
    assert rolling[0].is_closed is True
    assert rolling[0].close == Decimal("2950.0")

    # Event should report the close
    assert event is not None
    assert event.event_type == "closed"

    # Current forming candle should be None (closed for day)
    assert service.get_current_candle("NSE:RELIANCE-EQ") is None


def test_timezone_handling():
    service = CandleService()
    # UTC timestamp representing 09:15 IST (03:45 UTC)
    dt_utc = datetime(2026, 8, 17, 3, 45, 0, tzinfo=timezone.utc)
    tick = MarketTick(symbol="NSE:RELIANCE-EQ", ltp=Decimal("2950.0"), timestamp=dt_utc)

    event = service.process_tick(tick)
    assert event is not None

    # Convert bucket timestamp back to IST and verify hour 9, minute 15
    bucket_dt = datetime.fromtimestamp(event.candle.timestamp, tz=IST)
    assert bucket_dt.hour == 9
    assert bucket_dt.minute == 15


def test_rolling_history_limit():
    max_limit = 5
    service = CandleService(max_candles_per_symbol=max_limit)

    # Generate 10 minute rollovers
    for m in range(15, 25):
        t = make_tick("NSE:RELIANCE-EQ", 2900 + m, minute=m, second=0)
        service.process_tick(t)

    rolling = service.get_rolling_candles("NSE:RELIANCE-EQ")
    assert len(rolling) == max_limit
    # Max limit should retain only the most recent 5 closed candles
    minutes = [datetime.fromtimestamp(c.timestamp, tz=IST).minute for c in rolling]
    assert minutes == [19, 20, 21, 22, 23]


if __name__ == "__main__":
    test_first_tick_creates_candle()
    test_second_tick_updates_candle()
    test_high_update()
    test_low_update()
    test_close_update()
    test_minute_rollover()
    test_multiple_symbols()
    test_missing_tick_periods()
    test_duplicate_ticks()
    test_out_of_order_ticks()
    test_market_open_boundary()
    test_market_close_boundary()
    test_timezone_handling()
    test_rolling_history_limit()
    print("✅ All 14 CandleService unit tests passed successfully!")
