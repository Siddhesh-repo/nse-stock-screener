import csv
import io

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.stock_repository import StockRepository
from app.schemas.instrument import Instrument


FYERS_NSE_CM_URL = "https://public.fyers.in/sym_details/NSE_CM.csv"


class InstrumentService:

    async def load_instruments(
        self,
        db: AsyncSession,
    ) -> None:

        print("Downloading FYERS symbol master...")

        csv_content = await self._download_symbol_master()

        instruments = self._parse_csv(csv_content)

        print(
            f"Parsed instruments: {len(instruments)}"
        )

        await self._sync_instruments(
            db,
            instruments,
        )

        print("Instrument synchronization completed.")

    async def _download_symbol_master(self) -> str:

        async with httpx.AsyncClient(
            timeout=30.0
        ) as client:

            response = await client.get(
                FYERS_NSE_CM_URL
            )

            response.raise_for_status()

            return response.text

    def _parse_csv(self,csv_content: str) -> list[Instrument]:

        reader = csv.reader(
            io.StringIO(csv_content)
        )

        instruments: list[Instrument] = []

        for row_number, row in enumerate(reader, start=1):

            if not row:
                continue

            if len(row) <= 13:
                print(
                    f"Skipping malformed row: {row_number}"
                )
                continue

            symbol = row[9]

            # We only want NSE equity instruments.
            if not symbol.endswith("-EQ"):
                continue

            instrument = Instrument(
                token=row[0],
                name=row[1],
                isin=row[5] or None,
                symbol=symbol,
                display_symbol=row[13],
                exchange="NSE",
                segment=row[11],
            )

            instruments.append(instrument)

        return instruments

    async def _sync_instruments(
        self,
        db: AsyncSession,
        instruments: list[Instrument],
    ) -> None:

        repository = StockRepository()

        await repository.sync_instruments(
            db,
            instruments,
        )