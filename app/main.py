import asyncio
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
from app.models.stocks import Stock
from app.models.daily_closing_price import DailyClosingPrice

from app.core.config import settings
from app.core.fyers_token_manager import is_token_valid, refresh_access_token_via_refresh_token

BASE_DIR = Path(__file__).resolve().parent

# Module-level screener service so routes can access screened state
screener_service: ScreenerService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global screener_service

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
        symbols = await repo.get_active_symbols(db)
        print(f"[STARTUP] Loaded {len(symbols)} active symbols from Database.")

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

    # 3. Create MarketDataService that feeds ticks into the screener
    market_data_service = MarketDataService(screener_service)

    # 4. Start the screener event worker (consumes event_queue → writes to DB)
    worker = ScreenerEventWorker(screener_service)
    worker_task = asyncio.create_task(worker.run())
    print("[STARTUP] ScreenerEventWorker started (background DB persistence).")

    # 5. Create a combined tick handler that feeds BOTH live_store and screener
    def combined_on_tick(message):
        live_store.process_tick(message)
        market_data_service.process_message(message)

    # Store screener reference on live_store so broadcasts can include screened data
    live_store.screener_service = screener_service

    # 6. Start background broadcast task
    broadcast_task = asyncio.create_task(live_store.broadcast_updates())

    # 7. Start FYERS WebSocket in Full Mode (litemode=False)
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
                await websocket.receive_text()
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
    return {
        "status": "ok",
        "ws_connected": live_store.is_ws_connected,
        "total_ticks": live_store.total_ticks,
        "monitored_symbols": len(live_store._data),
        "screened_stocks": screened_count,
    }

@app.get("/health/database")
async def database_health(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT 1"))
    value = result.scalar_one()
    return {
        "database": "connected",
        "result": value,
    }