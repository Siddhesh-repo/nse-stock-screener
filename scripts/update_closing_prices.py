import sys
from pathlib import Path

# Add project root directory to sys.path so 'app' module imports work directly
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import argparse
import asyncio
from datetime import date

from app.core.database import AsyncSessionLocal
from app.services.closing_price_service import (
    ClosingPriceService,
)


async def main(trading_date: date):

    service = ClosingPriceService()

    async with AsyncSessionLocal() as db:

        await service.update_for_date(
            db=db,
            trading_date=trading_date,
        )


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Update daily closing prices"
    )

    parser.add_argument(
        "--date",
        required=True,
        help="Trading date in YYYY-MM-DD format",
    )

    args = parser.parse_args()

    trading_date = date.fromisoformat(
        args.date
    )

    asyncio.run(
        main(trading_date)
    )