# NSE Real-Time Stock Screener

A high-performance, real-time stock screener application built with **FastAPI**, **FYERS API v3 (WebSocket DataSocket & REST)**, **SQLAlchemy 2.0 Async**, **Alembic**, and **Vanilla JS / CSS**.

The system connects to FYERS live market feeds, monitors NSE equity stocks for significant price surges (+4%) or drops (-4%) against previous closing prices, and streams real-time tickers and screened stocks to interactive web clients via WebSockets.

---

## Key Features

- **Real-Time WebSocket Streaming**: Stream live ticks for active NSE symbols using FYERS WebSocket DataSocket in Full Mode.
- **±4% Volatility Screener**: Automatically flags stocks moving $\ge +4\%$ or $\le -4\%$ from previous trading day close with hysteresis exit rules (removes when within $-2\%$ to $+2\%$).
- **Background Event Persistence**: Asynchronous queue consumer worker persists screening events to PostgreSQL.
- **FYERS Token Auto-Renewal**: Automatic validity verification on startup and token renewal using OAuth refresh tokens or TOTP credentials.
- **Interactive Web Dashboard**: Live market table with search, filter (Gainers, Losers, High Volume), sort options, and real-time tick flashing indicators.

---

## Architecture Overview

```text
nse-stock-screener/
│
├── alembic/                      # Alembic database migration scripts
│   ├── versions/                 # Migration version history
│   └── env.py                    # Migration configuration
│
├── app/                          # Main application package
│   ├── main.py                   # FastAPI app entry point & lifespan manager
│   │
│   ├── core/                     # Application configuration & credentials
│   │   ├── config.py             # Pydantic Settings loading .env
│   │   ├── database.py           # SQLAlchemy Async engine & session setup
│   │   └── fyers_token_manager.py# Token validation & OAuth auto-refresh
│   │
│   ├── models/                   # Database ORM models
│   │   ├── stocks.py             # Stock instrument master model
│   │   ├── daily_closing_price.py# Historical daily closing price model
│   │   ├── screened_stock.py     # Currently active screened stock model
│   │   └── screening_event.py    # Log of screening entry/exit events
│   │
│   ├── repositories/             # Data access layer
│   │   ├── stock_repository.py
│   │   ├── closing_price_repository.py
│   │   └── screener_repository.py
│   │
│   ├── schemas/                  # Dataclasses & DTOs
│   │   ├── instrument.py
│   │   ├── market_data.py
│   │   └── screener_event.py
│   │
│   ├── services/                 # Domain logic & services
│   │   ├── screener_service.py   # Core ±4% screening & hysteresis logic
│   │   ├── live_store.py         # Real-time tick store & WS broadcasting
│   │   ├── websocket_service.py  # FYERS DataSocket WebSocket wrapper
│   │   ├── market_data_service.py # FYERS tick parser
│   │   ├── instrument_service.py # Instrument master downloader & syncer
│   │   ├── closing_price_service.py # Historical close fetcher & rate-limiter
│   │   ├── screener_event_service.py # DB event writer
│   │   └── screener_event_worker.py  # Async queue background worker
│   │
│   └── templates/                # Frontend web dashboard
│       └── index.html
│
├── scripts/                      # Operational CLI scripts
│   ├── load_instruments.py       # Fetch FYERS symbol master & seed DB
│   ├── update_closing_prices.py  # Fetch previous day closes for active stocks
│   ├── generate_token.py         # Interactive FYERS OAuth token generator
│   ├── auto_login.py             # Automated TOTP token generator
│   └── run_market_monitor.py     # Headless CLI market monitor
│
├── tests/                        # Automated unit tests
│   └── test_screener_logic.py    # Unit tests for screening threshold logic
│
├── .env.example                  # Environment configuration template
├── alembic.ini                   # Alembic configuration
├── requirements.txt              # Project dependencies
└── README.md                     # Project documentation
```

---

## Setup & Installation

### 1. Prerequisites
- Python 3.10+
- PostgreSQL database
- Active FYERS API v3 account & API keys

### 2. Environment Configuration
Copy `.env.example` to `.env` and fill in your database and FYERS credentials:

```bash
cp .env.example .env
```

Edit `.env`:
```env
DATABASE_URL=postgresql+psycopg://username:password@localhost:5432/nse_screener_db
FYERS_CLIENT_ID=YOUR_APP_ID-100
FYERS_SECRET_KEY=YOUR_SECRET_KEY
FYERS_REDIRECT_URI=https://trade.fyers.in/api-login/redirect-uri/index.html
FYERS_ACCESS_TOKEN=YOUR_ACCESS_TOKEN
FYERS_REFRESH_TOKEN=YOUR_REFRESH_TOKEN
```

### 3. Virtual Environment & Dependencies
Create and activate a virtual environment, then install dependencies:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## Database Migrations

Apply Alembic migrations to initialize the database schema:

```bash
# Check migration history status
alembic current
alembic heads

# Apply all migrations to latest head
alembic upgrade head
```

---

## Operational Scripts

Before launching the server for the first time, populate the instrument master and closing prices:

### 1. Generate FYERS Access Token (if expired)
```bash
python scripts/generate_token.py
```

### 2. Sync NSE Equity Symbol Master
Downloads the latest FYERS symbol master CSV (`NSE_CM.csv`) and syncs equity instruments into the `stocks` table:
```bash
python scripts/load_instruments.py
```

### 3. Update Previous Day Closing Prices
Fetches historical closing prices for active symbols from FYERS API for a specific date (e.g., `YYYY-MM-DD`):
```bash
python scripts/update_closing_prices.py --date 2026-08-12
```

---

## Running the Web Application

Launch the FastAPI application server using Uvicorn:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open your browser at `http://127.0.0.1:8000/` to access the live stock screener dashboard.

---

## API Endpoints

- `GET /` : Serves the main single-page web dashboard interface.
- `GET /api/stocks` : Returns filtered and sorted live quotes with summary market statistics.
- `GET /api/screened` : Returns the list of currently screened stocks ($\ge \pm 4\%$ movers).
- `WS /ws/live` : WebSocket endpoint streaming tick updates and summary statistics to clients every 150ms.
- `GET /health` : Health check endpoint returning tick metrics, connection status, and monitored symbols count.
- `GET /health/database` : Database connectivity ping check.

---

## Running Tests

Execute the automated test suite with pytest:

```bash
pytest tests/
```

Or run standalone:
```bash
python tests/test_screener_logic.py
```
