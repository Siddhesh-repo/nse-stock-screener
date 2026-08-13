import sys
from pathlib import Path

# Add project root directory to sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import asyncio
from datetime import date

from app.core.database import AsyncSessionLocal
from app.repositories.stock_repository import (
    StockRepository,
)
from app.services.market_data_service import (
    MarketDataService,
)
from app.services.screener_service import (
    ScreenerService,
)
from app.services.websocket_service import (
    WebSocketService,
)


async def load_stocks():

    repository = StockRepository()

    async with AsyncSessionLocal() as db:

        return await repository.get_active_symbols(
            db
        )


async def main():

    symbols = await load_stocks()

    screener_service = ScreenerService()

    screener_service.trading_date = (
        date.today()
    )

    market_data_service = MarketDataService(
        screener_service=screener_service
    )

    websocket_service = WebSocketService(
        on_tick=(
            market_data_service.process_message
        )
    )

    websocket_service.start(
        symbols=symbols
    )

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())