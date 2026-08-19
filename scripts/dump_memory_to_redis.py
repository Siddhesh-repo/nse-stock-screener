#!/usr/bin/env python3
"""RAM to Redis Memory Dumper.

Fetches 3+ hours of in-memory candle and quote data from the active running
FastAPI server and writes it directly into Redis before server restart.
"""

import asyncio
import json
import sys
from pathlib import Path
import httpx

# Add project root directory to python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.redis import init_redis, close_redis
from app.services.redis_tick_buffer import RedisTickBuffer


async def main():
    print("==================================================")
    print(" 💾 BACKUP IN-MEMORY CANDLES & QUOTES TO REDIS   ")
    print("==================================================")

    redis = await init_redis()
    if not redis:
        print("❌ Cannot connect to Redis. Aborting backup.")
        sys.exit(1)

    base_url = "http://127.0.0.1:8000"
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Fetch live quotes snapshot
        print("📥 Fetching active stock quotes from running server...")
        try:
            res = await client.get(f"{base_url}/api/stocks")
            data = res.json()
            stocks = data.get("stocks", [])
            print(f"✅ Found {len(stocks)} active stocks in running memory.")

            # Save live quotes to Redis Hash
            for quote in stocks:
                symbol = quote.get("symbol")
                if symbol:
                    await RedisTickBuffer.push_tick(quote)
            print(f"✅ Saved {len(stocks)} quote snapshots into Redis Hash 'stock:quotes'.")

        except Exception as e:
            print(f"❌ Failed to fetch stocks: {e}")
            stocks = []

        # 2. Fetch in-memory candles for each symbol (1m and 5m)
        total_candles_saved = 0
        resolutions = ["1m"]

        for i, stock in enumerate(stocks, 1):
            symbol = stock.get("symbol")
            if not symbol:
                continue

            for res_code in resolutions:
                try:
                    resp = await client.get(
                        f"{base_url}/api/chart/candles",
                        params={"symbol": symbol, "resolution": res_code},
                    )
                    c_data = resp.json()
                    candles = c_data.get("candles", [])

                    for c in candles:
                        await RedisTickBuffer.push_candle(symbol, res_code, c)
                        total_candles_saved += 1

                except Exception as e:
                    print(f"⚠️ Error fetching candles for {symbol} ({res_code}): {e}")

            if i % 10 == 0 or i == len(stocks):
                print(f"  Processed {i}/{len(stocks)} stocks... ({total_candles_saved} candles saved so far)")

    await close_redis()
    print("==================================================")
    print(f"🎉 SUCCESS! Dumped {total_candles_saved} candles & {len(stocks)} stock quotes to Redis!")
    print("==================================================")
    print("💡 You can now safely restart your Uvicorn server!")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(main())
