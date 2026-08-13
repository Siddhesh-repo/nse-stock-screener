from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stocks import Stock
from app.schemas.instrument import Instrument


class StockRepository:

    async def get_active_symbols(
        self,
        db: AsyncSession,
    ) -> list[str]:

        result = await db.execute(
            select(Stock.symbol)
            .where(
                Stock.is_active.is_(True)
            )
            .order_by(Stock.id)
        )

        return list(result.scalars().all())

    async def sync_instruments(
        self,
        db: AsyncSession,
        instruments: list[Instrument],
    ) -> None:

        result = await db.execute(
            select(Stock)
        )

        existing_stocks = {
            stock.symbol: stock
            for stock in result.scalars().all()
        }

        seen_symbols: set[str] = set()

        inserted = 0
        updated = 0

        for instrument in instruments:

            seen_symbols.add(instrument.symbol)

            stock = existing_stocks.get(
                instrument.symbol
            )

            if stock is None:

                stock = Stock(
                    symbol=instrument.symbol,
                    display_symbol=instrument.display_symbol,
                    token=instrument.token,
                    exchange=instrument.exchange,
                    isin=instrument.isin,
                    is_active=True,
                )

                db.add(stock)

                inserted += 1

            else:

                stock.display_symbol = (
                    instrument.display_symbol
                )

                stock.token = instrument.token
                stock.exchange = instrument.exchange
                stock.isin = instrument.isin
                stock.is_active = True

                updated += 1

        deactivated = 0

        for symbol, stock in existing_stocks.items():

            if symbol not in seen_symbols:
                stock.is_active = False
                deactivated += 1

        await db.commit()

        print(f"Inserted: {inserted}")
        print(f"Updated: {updated}")
        print(f"Deactivated: {deactivated}")