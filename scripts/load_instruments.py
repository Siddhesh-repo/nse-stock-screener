import sys
from pathlib import Path

# Add project root directory to sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import asyncio

from app.core.database import AsyncSessionLocal
from app.services.instrument_service import InstrumentService


async def main():

    service = InstrumentService()

    async with AsyncSessionLocal() as db:

        await service.load_instruments(db)


if __name__ == "__main__":
    asyncio.run(main())