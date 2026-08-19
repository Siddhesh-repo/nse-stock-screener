import asyncio
import json
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, AsyncSessionLocal
from app.repositories.stock_repository import StockRepository
from app.repositories.closing_price_repository import ClosingPriceRepository
from app.repositories.screener_repository import ScreenerRepository
from app.services.websocket_service import WebSocketService
from app.services.live_store import live_store
from app.services.screener_service import ScreenerService
from app.services.market_data_service import MarketDataService
from app.services.screener_event_worker import ScreenerEventWorker
from app.services.candle_service import CandleService
from app.models.stocks import Stock
from app.models.daily_closing_price import DailyClosingPrice

from app.core.config import settings
from app.core.fyers_token_manager import is_token_valid, refresh_access_token_via_refresh_token
from app.core.redis import init_redis, close_redis, get_redis
from app.services.redis_tick_buffer import RedisTickBuffer

BASE_DIR = Path(__file__).resolve().parent

# Module-level screener service so routes can access screened state
screener_service: ScreenerService | None = None

# Module-level candle service so routes can access candle state
candle_service: CandleService | None = None

# Module-level fyers service for historical chart data
fyers_service_instance = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global screener_service, candle_service, fyers_service_instance

    # -1. Initialize Async Redis Pool
    await init_redis()

    # 0. Check FYERS token validity & attempt auto-refresh
    if not is_token_valid():
        print("⚠️ [STARTUP WARNING] FYERS Access Token is expired or invalid!")
        if settings.fyers_refresh_token:
            print("🔄 Attempting automatic token renewal via Refresh Token...")
            new_token = refresh_access_token_via_refresh_token(settings.fyers_refresh_token)
            if new_token:
                print("🎉 [STARTUP SUCCESS] Token auto-renewed successfully!")
            else:
                print("💡 Run: 'python scripts/generate_token.py' in your terminal to generate a fresh token.")
        else:
            print("💡 Run: 'python scripts/generate_token.py' in your terminal to generate a fresh token.")
    else:
        print("✅ [STARTUP] FYERS Access Token is ACTIVE and VALID.")

    # 1. Load active symbols from database
    async with AsyncSessionLocal() as db:
        repo = StockRepository()
        raw_symbols = await repo.get_active_symbols(db)
        delisted_symbols = {"NSE:ABMINTLLTD-EQ", "NSE:MHLXMIRU-EQ", "NSE:SHEKHAWATI-EQ", "NSE:SPECIALITY-EQ"}
        symbols = [s for s in raw_symbols if s not in delisted_symbols]
        print(f"[STARTUP] Loaded {len(symbols)} active symbols from Database ({len(delisted_symbols)} delisted filtered).")

        # 2. Set up screener pipeline
        screener_service = ScreenerService()

        # Load all active Stock objects (need id ↔ symbol mapping)
        result = await db.execute(
            select(Stock).where(Stock.is_active.is_(True))
        )
        all_stocks = list(result.scalars().all())
        screener_service.load_stocks(all_stocks)
        print(f"[STARTUP] Loaded {len(all_stocks)} stocks into screener (symbol → stock_id mapping).")

        # Load previous trading day's closing prices
        closing_repo = ClosingPriceRepository()
        result = await db.execute(
            select(DailyClosingPrice.trading_date)
            .distinct()
            .order_by(DailyClosingPrice.trading_date.desc())
            .limit(1)
        )
        latest_closing_date = result.scalar_one_or_none()

        if latest_closing_date:
            closing_prices = await closing_repo.get_for_trading_date(db, latest_closing_date)
            screener_service.load_previous_closes(closing_prices)
            print(f"[STARTUP] Loaded {len(closing_prices)} previous closing prices (date: {latest_closing_date}).")
        else:
            print("⚠️ [STARTUP] No closing price data found. Screener will not detect events until closing prices are loaded.")

        # Set trading date for the screener
        today_date = date.today()
        screener_service.trading_date = today_date

        # Load existing active screened stocks for today from DB
        screener_repo = ScreenerRepository()
        existing_screened = await screener_repo.get_screened_stocks_for_date(db, today_date)
        if existing_screened:
            screener_service.load_screened_stocks(existing_screened)
            print(f"[STARTUP] Loaded {len(existing_screened)} existing screened stocks from Database for today ({today_date}).")

    # 3. Initialize CandleService (in-memory, no DB)
    candle_service = CandleService()
    print("[STARTUP] CandleService initialized (in-memory candle engine).")

    # 4. Create MarketDataService that feeds ticks into both screener and candle service
    market_data_service = MarketDataService(screener_service, candle_service=candle_service)

    # 5. Start the screener event worker (consumes event_queue → writes to DB)
    worker = ScreenerEventWorker(screener_service)
    worker_task = asyncio.create_task(worker.run())
    print("[STARTUP] ScreenerEventWorker started (background DB persistence).")

    # 6. Create a combined tick handler that feeds live_store, screener, AND candle service
    main_loop = asyncio.get_running_loop()

    def combined_on_tick(message):
        live_store.process_tick(message)
        try:
            if main_loop and main_loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    RedisTickBuffer.push_tick(message),
                    main_loop
                )
        except Exception:
            pass

        candle_event = market_data_service.process_message(message)
        if candle_event is not None:
            live_store.queue_candle_event(
                candle_event.event_type,
                candle_event.candle,
                candle_event.closed_candle,
            )
            if candle_event.closed_candle:
                try:
                    if main_loop and main_loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            RedisTickBuffer.push_candle(
                                candle_event.closed_candle.symbol,
                                "1m",
                                candle_event.closed_candle.to_dict(),
                            ),
                            main_loop
                        )
                except Exception:
                    pass

    # Store screener + candle references on live_store
    live_store.screener_service = screener_service
    live_store.candle_service = candle_service

    # 7. Initialize FyersService for historical chart data (lazy, only used by REST endpoint)
    try:
        from app.services.fyers_service import FyersService
        fyers_service_instance = FyersService()
        print("[STARTUP] FyersService initialized for historical chart data.")
    except Exception as e:
        print(f"⚠️ [STARTUP] FyersService initialization failed (historical charts unavailable): {e}")
        fyers_service_instance = None

    # 8. Start background broadcast task
    broadcast_task = asyncio.create_task(live_store.broadcast_updates())

    # 9. Start FYERS WebSocket in Full Mode (litemode=False)
    if symbols:
        try:
            ws_service = WebSocketService(
                on_tick=combined_on_tick,
                litemode=False  # FULL MODE
            )
            # Run socket start in background thread since socket.connect() is synchronous
            asyncio.get_running_loop().run_in_executor(
                None, ws_service.start, symbols
            )
            live_store.is_ws_connected = True
            print(f"[STARTUP] FYERS DataSocket started in FULL MODE for {len(symbols)} symbols.")
        except Exception as e:
            print(f"[STARTUP ERROR] Failed to start FYERS WebSocket: {e}")

    yield

    await close_redis()
    broadcast_task.cancel()
    worker_task.cancel()

app = FastAPI(
    title="NSE Stock Screener",
    version="1.0.0",
    lifespan=lifespan,
)

@app.get("/", response_class=HTMLResponse)
async def get_index():
    template_path = BASE_DIR / "templates" / "index.html"
    if not template_path.exists():
        return HTMLResponse("<h1>Template not found</h1>", status_code=404)
    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()
    return HTMLResponse(content=content)

@app.get("/api/stocks")
async def get_stocks(
    search: str = Query("", description="Search by symbol or short name"),
    filter_type: str = Query("all", description="all, gainers, losers, high_volume"),
    sort_by: str = Query("vol_traded_today", description="sort field"),
    sort_order: str = Query("desc", description="asc or desc"),
):
    stocks = live_store.get_all_quotes(
        search=search,
        filter_type=filter_type,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    stats = live_store.get_summary_stats()
    return JSONResponse(content={
        "stocks": stocks,
        "stats": stats
    })

@app.get("/api/screened")
async def get_screened_stocks():
    """Returns the current list of screened stocks (±4% movers) from the in-memory screener state."""
    screened_list = live_store.get_screened_stocks()
    return JSONResponse(content={
        "screened": screened_list,
        "count": len(screened_list),
    })


@app.get("/api/chart/candles")
async def get_chart_candles(
    symbol: str = Query(..., description="Symbol e.g. NSE:RELIANCE-EQ"),
    resolution: str = Query("1m", description="1m, 5m, 15m, 30m, 1h, 1D"),
    range_from: str = Query("", description="Start date YYYY-MM-DD (defaults to today)"),
    range_to: str = Query("", description="End date YYYY-MM-DD (defaults to today)"),
):
    try:
        # Normalize symbol format
        if not symbol.startswith("NSE:"):
            symbol = f"NSE:{symbol}"
        if not symbol.endswith("-EQ") and not symbol.endswith("-INDEX"):
            symbol = f"{symbol}-EQ"

        today = date.today().isoformat()
        if not range_from:
            range_from = today
        if not range_to:
            range_to = today

        valid_resolutions = {"1m", "5m", "15m", "30m", "1h", "1D"}
        if resolution not in valid_resolutions:
            return JSONResponse(
                status_code=400,
                content={"error": f"Invalid resolution '{resolution}'. Valid: {sorted(valid_resolutions)}"},
            )

        # 1. Try fetching directly from Redis first for instant < 2ms performance
        redis = get_redis()
        if redis:
            try:
                items = await redis.zrange(f"candles:{symbol}:{resolution}", 0, -1)
                if items:
                    redis_candles = [json.loads(item) for item in items]
                    return JSONResponse(content={
                        "symbol": symbol,
                        "resolution": resolution,
                        "count": len(redis_candles),
                        "candles": redis_candles,
                    })
            except Exception as e:
                print(f"[CHART] Redis fetch error for {symbol}: {e}")

        # 2. Fallback to FYERS REST API if not in Redis
        historical_candles = []
        if fyers_service_instance:
            try:
                fyers_response = await asyncio.get_running_loop().run_in_executor(
                    None,
                    fyers_service_instance.get_candle_history,
                    symbol,
                    resolution,
                    range_from,
                    range_to,
                )
                historical_candles = CandleService.parse_fyers_history(symbol, fyers_response)
            except Exception as e:
                print(f"[CHART] FYERS history fetch failed for {symbol}: {e}")

        # Merge with live in-memory candles
        if candle_service:
            merged = candle_service.merge_historical_and_live(symbol, historical_candles, resolution)
        else:
            merged = historical_candles

        formatted = []
        for c in merged:
            if hasattr(c, "to_dict"):
                formatted.append(c.to_dict())
            elif isinstance(c, dict):
                formatted.append(c)

        return JSONResponse(content={
            "symbol": symbol,
            "resolution": resolution,
            "count": len(formatted),
            "candles": formatted,
        })
    except Exception as e:
        print(f"[CHART ENDPOINT ERROR] Failed to fetch candles for {symbol}: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to load chart data: {str(e)}", "candles": []},
        )


@app.websocket("/ws/live")
async def websocket_live_endpoint(websocket: WebSocket):
    await live_store.connect_ws(websocket)
    try:
        # Send initial stats & full quotes list + screened stocks
        initial_payload = {
            "type": "ticks_batch",
            "data": live_store.get_all_quotes(),
            "stats": live_store.get_summary_stats(),
            "screened": live_store.get_screened_stocks(),
        }
        await websocket.send_json(initial_payload)
        
        while True:
            try:
                raw_text = await websocket.receive_text()
                # Handle client messages (candle subscribe/unsubscribe)
                await live_store.handle_client_message(websocket, raw_text)
            except WebSocketDisconnect:
                break
            except Exception:
                await asyncio.sleep(1)
    finally:
        live_store.disconnect_ws(websocket)

@app.get("/health")
async def health_check():
    screened_count = 0
    if screener_service:
        screened_count = len(screener_service.state.screened)
    candle_symbols = 0
    if candle_service:
        candle_symbols = len(candle_service._states)
    return {
        "status": "ok",
        "ws_connected": live_store.is_ws_connected,
        "total_ticks": live_store.total_ticks,
        "monitored_symbols": len(live_store._data),
        "screened_stocks": screened_count,
        "candle_symbols": candle_symbols,
    }

@app.get("/health/database")
async def database_health(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT 1"))
    value = result.scalar_one()
    return {
        "database": "connected",
        "result": value,
    }