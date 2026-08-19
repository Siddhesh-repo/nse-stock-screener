#!/usr/bin/env python3
"""Evening Redis to PostgreSQL Flush Script.

Flushes buffered screener events and candle data accumulated in Redis streams
during trading hours into the PostgreSQL database.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add project root directory to python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.redis import init_redis, close_redis
from app.models.screened_stock import ScreenedStock
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from app.models.stocks import Stock
from app.models.intraday_candle import IntradayCandle

IST = timezone(timedelta(hours=5, minutes=30))


async def flush_candles(redis, db) -> int:
    """Read stream:candles from Redis and bulk insert into PostgreSQL intraday_candles table."""
    print("🔍 Reading candles from Redis 'stream:candles'...")
    try:
        # Build symbol -> stock_id map
        result = await db.execute(select(Stock.id, Stock.symbol))
        symbol_map = {r.symbol: r.id for r in result.all()}

        messages = await redis.xrange("stream:candles", min="-", max="+")
        if not messages:
            print("ℹ️ Stream empty. Flushing directly from Redis Sorted Sets 'candles:*:1m'...")
            keys = await redis.keys("candles:*:1m")
            inserted_count = 0
            for key in keys:
                symbol = key.replace("candles:", "").replace(":1m", "")
                stock_id = symbol_map.get(symbol)
                if not stock_id:
                    continue

                candle_items = await redis.zrange(key, 0, -1)
                for candle_raw in candle_items:
                    c = json.loads(candle_raw)
                    ts = c.get("timestamp", 0)
                    candle_dt = datetime.fromtimestamp(ts, tz=IST)

                    candle_record = IntradayCandle(
                        stock_id=stock_id,
                        resolution="1m",
                        timestamp=candle_dt,
                        open=c.get("open", 0),
                        high=c.get("high", 0),
                        low=c.get("low", 0),
                        close=c.get("close", 0),
                        volume=c.get("volume", 0),
                    )
                    db.add(candle_record)
                    inserted_count += 1

            await db.commit()
            print(f"✅ Flushed {inserted_count} candles from Sorted Sets to PostgreSQL 'intraday_candles'.")
            return inserted_count

        inserted_count = 0
        for msg_id, data in messages:
            symbol = data.get("symbol")
            resolution = data.get("resolution", "1m")
            candle_raw = data.get("data")
            if not candle_raw or not symbol:
                continue

            stock_id = symbol_map.get(symbol)
            if not stock_id:
                continue

            c = json.loads(candle_raw)
            ts = c.get("timestamp", 0)
            candle_dt = datetime.fromtimestamp(ts, tz=IST)

            candle_record = IntradayCandle(
                stock_id=stock_id,
                resolution=resolution,
                timestamp=candle_dt,
                open=c.get("open", 0),
                high=c.get("high", 0),
                low=c.get("low", 0),
                close=c.get("close", 0),
                volume=c.get("volume", 0),
            )
            db.add(candle_record)
            inserted_count += 1

        await db.commit()
        # Trim stream after successful flush
        await redis.xtrim("stream:candles", maxlen=0)
        print(f"✅ Flushed {inserted_count} candles from Redis to PostgreSQL 'intraday_candles'.")
        return inserted_count
    except Exception as e:
        await db.rollback()
        print(f"❌ Error flushing candles to PostgreSQL: {e}")
        return 0


async def flush_screener_events(redis, db) -> int:
    """Read stream:screener_events from Redis and bulk insert into PostgreSQL."""
    print("🔍 Reading screener events from Redis 'stream:screener_events'...")
    try:
        messages = await redis.xrange("stream:screener_events", min="-", max="+")
        if not messages:
            print("ℹ️ No pending screener events in Redis stream.")
            return 0

        inserted_count = 0
        for msg_id, data in messages:
            event_raw = data.get("data")
            if not event_raw:
                continue

            event_dict = json.loads(event_raw)
            
            t_str = event_dict.get("crossed_at", "")
            try:
                dt_val = datetime.fromisoformat(t_str)
                t_val = dt_val.time()
            except Exception:
                t_val = datetime.now(IST).time()

            d_str = event_dict.get("trading_date")
            try:
                d_val = datetime.strptime(d_str, "%Y-%m-%d").date()
            except Exception:
                d_val = datetime.now(IST).date()

            screened_record = ScreenedStock(
                stock_id=event_dict.get("stock_id"),
                trading_date=d_val,
                trigger_time=t_val,
                ltp=event_dict.get("trigger_price", 0),
                percentage_change=event_dict.get("trigger_percentage", 0),
            )
            db.add(screened_record)
            inserted_count += 1

        await db.commit()
        # Trim stream after successful flush
        await redis.xtrim("stream:screener_events", maxlen=0)
        print(f"✅ Flushed {inserted_count} screener events from Redis to PostgreSQL.")
        return inserted_count
    except Exception as e:
        await db.rollback()
        print(f"❌ Error flushing screener events: {e}")
        return 0


async def main():
    print("==================================================")
    print("  🌇 EVENING REDIS TO POSTGRESQL FLUSH UTILITY    ")
    print("==================================================")

    redis = await init_redis()
    if not redis:
        print("❌ Cannot connect to Redis. Flush aborted.")
        sys.exit(1)

    async with AsyncSessionLocal() as db:
        candles_flushed = await flush_candles(redis, db)
        events_flushed = await flush_screener_events(redis, db)

    await close_redis()
    print("==================================================")
    print(f"🎉 Evening flush completed! Saved {candles_flushed} candles & {events_flushed} screener events to PostgreSQL.")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(main())
