import asyncio
import queue


from app.core.database import AsyncSessionLocal
from app.services.screener_event_service import (
    ScreenerEventService,
)


class ScreenerEventWorker:

    def __init__(
        self,
        screener_service,
    ):

        self.screener_service = screener_service

        self.event_service = (
            ScreenerEventService()
        )

    async def run(self) -> None:

        while True:

            try:

                event = (
                    self.screener_service.event_queue.get_nowait()
                )

            except queue.Empty:

                await asyncio.sleep(0.1)

                continue

            try:
                async with AsyncSessionLocal() as db:

                    if event.event_type == "SCREENED":

                        await self.event_service.record_screened(
                            db=db,
                            stock_id=event.stock_id,
                            trading_date=(
                                self.screener_service.trading_date
                            ),
                            event_time=event.event_time,
                            ltp=event.ltp,
                            percentage_change=(
                                event.percentage_change
                            ),
                        )

                    elif event.event_type == "REMOVED":

                        await self.event_service.record_removed(
                            db=db,
                            stock_id=event.stock_id,
                            trading_date=(
                                self.screener_service.trading_date
                            ),
                            event_time=event.event_time,
                            ltp=event.ltp,
                            percentage_change=(
                                event.percentage_change
                            ),
                        )
            except Exception as e:
                print(f"[WORKER ERROR] Failed to record event {event.event_type} for stock_id {event.stock_id}: {e}")