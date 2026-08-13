from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal

from app.models.daily_closing_price import DailyClosingPrice


class ClosingPriceRepository:

    async def get_stock_ids_with_closing_price(
        self,
        db: AsyncSession,
        trading_date: date,
    ) -> set[int]:

        result = await db.execute(
            select(DailyClosingPrice.stock_id)
            .where(
                DailyClosingPrice.trading_date
                == trading_date
            )
        )

        return set(result.scalars().all())

    async def get_by_stock_and_date(
        self,
        db: AsyncSession,
        stock_id: int,
        trading_date: date,
    ) -> DailyClosingPrice | None:

        result = await db.execute(
            select(DailyClosingPrice).where(
                DailyClosingPrice.stock_id == stock_id,
                DailyClosingPrice.trading_date == trading_date,
            )
        )

        return result.scalar_one_or_none()

    async def get_for_trading_date(
        self,
        db: AsyncSession,
        trading_date: date,
    ):

        result = await db.execute(
            select(DailyClosingPrice)
            .where(
                DailyClosingPrice.trading_date
                == trading_date
            )
        )

        return list(
            result.scalars().all()
        )

    async def load_previous_close_data(
        self,
        screener_service,
        previous_trading_date: date,
    ):

        async with AsyncSessionLocal() as db:

            closing_prices = (
                await self.get_for_trading_date(
                    db=db,
                    trading_date=previous_trading_date,
                )
            )

            screener_service.load_previous_closes(
                closing_prices
            )

    async def save(
        self,
        db: AsyncSession,
        stock_id: int,
        trading_date: date,
        closing_price: Decimal,
    ) -> None:
        """Atomic upsert: Inserts or updates closing price cleanly without duplicate key constraint crashes"""
        stmt = pg_insert(DailyClosingPrice).values(
            stock_id=stock_id,
            trading_date=trading_date,
            closing_price=closing_price,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["stock_id", "trading_date"],
            set_={"closing_price": closing_price},
        )
        await db.execute(stmt)