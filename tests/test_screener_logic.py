import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from datetime import date, datetime, timezone
from decimal import Decimal

from app.schemas.market_data import MarketTick
from app.services.screener_service import ScreenerService


def test_screener_logic():
    screener = ScreenerService()
    screener.trading_date = date(2026, 8, 12)

    # Register test stock: stock_id=1, previous close=100
    screener.state.stock_ids_by_symbol["NSE:TEST-EQ"] = 1
    screener.state.previous_closes[1] = Decimal("100")

    def make_tick(ltp: float) -> MarketTick:
        return MarketTick(
            symbol="NSE:TEST-EQ",
            ltp=Decimal(str(ltp)),
            timestamp=datetime.now(timezone.utc),
        )

    # 1. +3% change -> Below threshold (+4%), should NOT be screened
    screener.process_tick(make_tick(103))
    assert 1 not in screener.state.screened

    # 2. +4% change -> Reaches entry threshold (+4%), SHOULD be screened
    screener.process_tick(make_tick(104))
    assert 1 in screener.state.screened
    assert screener.state.screened[1].percentage_change == Decimal("4")

    # 3. +5% change -> Still screened, LTP updated
    screener.process_tick(make_tick(105))
    assert 1 in screener.state.screened
    assert screener.state.screened[1].percentage_change == Decimal("5")

    # 4. +2% change -> Within hysteresis range (not yet < 2%), still screened
    screener.process_tick(make_tick(102))
    assert 1 in screener.state.screened

    # 5. +1.99% change -> Drops below exit threshold (+2%), SHOULD be removed
    screener.process_tick(make_tick(101.99))
    assert 1 not in screener.state.screened

    # 6. -4% change -> Reaches entry threshold (-4%), SHOULD be screened again
    screener.process_tick(make_tick(96))
    assert 1 in screener.state.screened
    assert screener.state.screened[1].percentage_change == Decimal("-4")


if __name__ == "__main__":
    test_screener_logic()
    print("✅ test_screener_logic passed successfully!")