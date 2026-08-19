import json
import logging
from typing import Any
from app.core.redis import get_redis

logger = logging.getLogger(__name__)


class RedisTickBuffer:
    """Non-blocking Redis buffer for streaming ticks, quotes, candles, and screener events.

    Stores data in Redis without committing to PostgreSQL (DB commits reserved for evening flush).
    """

    MAX_TICK_STREAM_LEN = 50000  # Cap stream size to prevent RAM overflow

    @staticmethod
    async def push_tick(message: dict[str, Any]) -> None:
        """Pushes tick update to Redis Hash snapshot and Redis Stream."""
        redis = get_redis()
        if not redis:
            return

        symbol = message.get("symbol")
        if not symbol:
            return

        try:
            payload = json.dumps(message, default=str)

            # 1. Update latest snapshot hash: stock:quotes -> symbol: json_payload
            await redis.hset("stock:quotes", symbol, payload)
        except Exception as e:
            logger.debug(f"[REDIS TICK BUFFER ERROR] Failed to push tick for {symbol}: {e}")

    @staticmethod
    async def push_candle(symbol: str, resolution: str, candle_data: dict[str, Any]) -> None:
        """Pushes completed candle to Redis ZSET and Redis Stream."""
        redis = get_redis()
        if not redis or resolution != "1m":
            return

        try:
            payload = json.dumps(candle_data, default=str)
            timestamp = candle_data.get("timestamp", 0)

            # 1. Add to Sorted Set for fast range queries: candles:{symbol}:{resolution}
            await redis.zadd(f"candles:{symbol}:{resolution}", {payload: timestamp})

            # 2. Append to candle stream for evening DB flush (capped at 1,000,000 for full day)
            await redis.xadd(
                "stream:candles",
                {"symbol": symbol, "resolution": resolution, "data": payload},
                maxlen=1000000,
                approximate=True,
            )
        except Exception as e:
            logger.debug(f"[REDIS CANDLE BUFFER ERROR] Failed to push candle for {symbol}: {e}")

    @staticmethod
    async def push_screener_event(event_data: dict[str, Any]) -> None:
        """Pushes ±4% screener breakout event to Redis Stream."""
        redis = get_redis()
        if not redis:
            return

        try:
            payload = json.dumps(event_data, default=str)
            await redis.xadd("stream:screener_events", {"data": payload})
        except Exception as e:
            logger.debug(f"[REDIS SCREENER BUFFER ERROR] Failed to push screener event: {e}")
