from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.screener_repository import (
    ScreenerRepository,
)


class ScreenerEventService:

    def __init__(self):

        self.repository = ScreenerRepository()

    async def record_screened(
        self,
        db: AsyncSession,
        stock_id: int,
        trading_date: date,
        event_time,
        ltp: Decimal,
        percentage_change: Decimal,
    ) -> None:

        await self.repository.add_screened_stock(
            db=db,
            stock_id=stock_id,
            trading_date=trading_date,
            trigger_time=event_time,
            ltp=ltp,
            percentage_change=percentage_change,
        )

        await self.repository.add_event(
            db=db,
            stock_id=stock_id,
            trading_date=trading_date,
            event_type="SCREENED",
            event_time=event_time,
            ltp=ltp,
            percentage_change=percentage_change,
        )

        await db.commit()

    async def record_removed(
        self,
        db: AsyncSession,
        stock_id: int,
        trading_date: date,
        event_time,
        ltp: Decimal,
        percentage_change: Decimal,
    ) -> None:

        await self.repository.remove_screened_stock(
            db=db,
            stock_id=stock_id,
            trading_date=trading_date,
        )

        await self.repository.add_event(
            db=db,
            stock_id=stock_id,
            trading_date=trading_date,
            event_type="REMOVED",
            event_time=event_time,
            ltp=ltp,
            percentage_change=percentage_change,
        )

        await db.commit()