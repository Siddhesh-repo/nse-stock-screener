import time
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stocks import Stock
from app.repositories.closing_price_repository import (
    ClosingPriceRepository,
)
from app.services.fyers_rate_limiter import (
    FyersRateLimiter,
)
from app.services.fyers_service import FyersService


class ClosingPriceService:

    def __init__(self):

        self.fyers_service = FyersService()

        self.repository = ClosingPriceRepository()

        self.rate_limiter = FyersRateLimiter(
            requests_per_second=3,
            requests_per_minute=180,
        )

    async def update_for_date(
        self,
        db: AsyncSession,
        trading_date: date,
    ) -> None:

        result = await db.execute(
            select(Stock)
            .where(
                Stock.is_active.is_(True)
            )
            .order_by(Stock.id)
        )

        stocks = result.scalars().all()

        existing_stock_ids = (
            await self.repository
            .get_stock_ids_with_closing_price(
                db=db,
                trading_date=trading_date,
            )
        )

        stocks_to_process = [
            stock
            for stock in stocks
            if stock.id not in existing_stock_ids
        ]

        print(
            f"Total active stocks: {len(stocks)}"
        )

        print(
            f"Already completed: "
            f"{len(existing_stock_ids)}"
        )

        print(
            f"Remaining: "
            f"{len(stocks_to_process)}"
        )

        successful = 0
        failed = 0

        for index, stock in enumerate(
            stocks_to_process,
            start=1,
        ):

            print(
                f"[{index}/{len(stocks_to_process)}] "
                f"{stock.symbol}"
            )

            response = await self._get_history_with_retry(
                symbol=stock.symbol,
                trading_date=trading_date,
            )

            if response is None:

                failed += 1

                continue

            if response.get("s") != "ok":

                failed += 1

                print(
                    f"[FAILED] {stock.symbol}: "
                    f"{response}"
                )

                continue

            candles = response.get(
                "candles",
                [],
            )

            if not candles:

                failed += 1

                print(
                    f"[NO DATA] {stock.symbol}"
                )

                continue

            candle = candles[0]

            closing_price = Decimal(
                str(candle[4])
            )

            await self.repository.save(
                db=db,
                stock_id=stock.id,
                trading_date=trading_date,
                closing_price=closing_price,
            )

            successful += 1

            print(
                f"[OK] {stock.symbol} "
                f"close={closing_price}"
            )

            # Commit periodically.
            if successful % 100 == 0:

                await db.commit()

                print(
                    "Checkpoint committed."
                )

        await db.commit()

        print()
        print("Completed")
        print(
            f"Successful: {successful}"
        )
        print(
            f"Failed: {failed}"
        )

    async def _get_history_with_retry(
        self,
        symbol: str,
        trading_date: date,
        max_retries: int = 3,
    ) -> dict | None:

        retry_count = 0

        while True:

            self.rate_limiter.wait()

            response = (
                self.fyers_service.get_history(
                    symbol=symbol,
                    trading_date=(
                        trading_date.isoformat()
                    ),
                )
            )

            if response.get("code") != 429:
                return response

            retry_count += 1

            if retry_count > max_retries:

                print(
                    f"[RATE LIMIT] "
                    f"{symbol} failed after "
                    f"{max_retries} retries"
                )

                return None

            wait_seconds = 10 * retry_count

            print(
                f"[429] {symbol} "
                f"waiting {wait_seconds}s "
                f"before retry "
                f"{retry_count}/{max_retries}"
            )

            time.sleep(wait_seconds)