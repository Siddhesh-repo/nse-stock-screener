from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.screened_stock import ScreenedStock
from app.models.screening_event import ScreeningEvent


class ScreenerRepository:

    async def get_screened_stocks_for_date(
        self,
        db: AsyncSession,
        trading_date: date,
    ) -> list[ScreenedStock]:

        result = await db.execute(
            select(ScreenedStock).where(
                ScreenedStock.trading_date == trading_date
            )
        )

        return list(result.scalars().all())

    async def get_active_screened_stock(
        self,
        db: AsyncSession,
        stock_id: int,
        trading_date: date,
    ) -> ScreenedStock | None:

        result = await db.execute(
            select(ScreenedStock).where(
                ScreenedStock.stock_id == stock_id,
                ScreenedStock.trading_date == trading_date,
            )
        )

        records = list(result.scalars().all())
        if not records:
            return None
        return records[0]

    async def add_screened_stock(
        self,
        db: AsyncSession,
        stock_id: int,
        trading_date: date,
        trigger_time,
        ltp: Decimal,
        percentage_change: Decimal,
    ) -> ScreenedStock:

        # Ensure trigger_time is a time object
        if isinstance(trigger_time, datetime):
            trigger_time = trigger_time.time()

        # Check if record already exists for this stock and date (upsert pattern)
        existing = await self.get_active_screened_stock(
            db=db,
            stock_id=stock_id,
            trading_date=trading_date,
        )

        if existing is not None:
            existing.trigger_time = trigger_time
            existing.ltp = ltp
            existing.percentage_change = percentage_change
            return existing

        screened_stock = ScreenedStock(
            stock_id=stock_id,
            trading_date=trading_date,
            trigger_time=trigger_time,
            ltp=ltp,
            percentage_change=percentage_change,
        )

        db.add(screened_stock)

        return screened_stock

    async def remove_screened_stock(
        self,
        db: AsyncSession,
        stock_id: int,
        trading_date: date,
    ) -> None:

        result = await db.execute(
            select(ScreenedStock).where(
                ScreenedStock.stock_id == stock_id,
                ScreenedStock.trading_date == trading_date,
            )
        )

        records = list(result.scalars().all())
        for record in records:
            await db.delete(record)

    async def add_event(
        self,
        db: AsyncSession,
        stock_id: int,
        trading_date: date,
        event_type: str,
        event_time,
        ltp: Decimal,
        percentage_change: Decimal,
    ) -> ScreeningEvent:

        # Ensure event_time is a time object
        if isinstance(event_time, datetime):
            event_time = event_time.time()

        event = ScreeningEvent(
            stock_id=stock_id,
            trading_date=trading_date,
            event_type=event_type,
            event_time=event_time,
            ltp=ltp,
            percentage_change=percentage_change,
        )

        db.add(event)

        return event