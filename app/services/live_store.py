import asyncio
import time
from typing import Any
from fastapi import WebSocket

class LiveMarketStore:
    def __init__(self):
        self._data: dict[str, dict[str, Any]] = {}
        self.active_connections: list[WebSocket] = []
        self.total_ticks: int = 0
        self.is_ws_connected: bool = False
        self.dirty_symbols: set[str] = set()
        self.screener_service = None  # Set by main.py at startup

    def process_tick(self, message: dict[str, Any]) -> None:
        symbol = message.get("symbol")
        if not symbol:
            return

        self.total_ticks += 1
        prev_quote = self._data.get(symbol, {})
        prev_ltp = prev_quote.get("ltp")

        ltp = message.get("ltp", prev_quote.get("ltp", 0.0))
        ch = message.get("ch", prev_quote.get("ch", 0.0))
        chp = message.get("chp", prev_quote.get("chp", 0.0))

        # Direction indicator for tick flash
        direction = "neutral"
        if prev_ltp is not None and ltp != prev_ltp:
            direction = "up" if ltp > prev_ltp else "down"

        short_name = symbol.replace("NSE:", "").replace("-EQ", "").replace("-INDEX", "")

        quote = {
            "symbol": symbol,
            "short_name": short_name,
            "ltp": float(ltp) if ltp is not None else 0.0,
            "ch": float(ch) if ch is not None else 0.0,
            "chp": float(chp) if chp is not None else 0.0,
            "open_price": float(message.get("open_price", prev_quote.get("open_price", 0.0))),
            "high_price": float(message.get("high_price", prev_quote.get("high_price", 0.0))),
            "low_price": float(message.get("low_price", prev_quote.get("low_price", 0.0))),
            "prev_close_price": float(message.get("prev_close_price", prev_quote.get("prev_close_price", 0.0))),
            "avg_trade_price": float(message.get("avg_trade_price", prev_quote.get("avg_trade_price", 0.0))),
            "vol_traded_today": int(message.get("vol_traded_today", prev_quote.get("vol_traded_today", 0))),
            "last_traded_qty": int(message.get("last_traded_qty", prev_quote.get("last_traded_qty", 0))),
            "last_traded_time": message.get("last_traded_time", prev_quote.get("last_traded_time", None)),
            "bid_price": float(message.get("bid_price", prev_quote.get("bid_price", 0.0))),
            "bid_size": int(message.get("bid_size", prev_quote.get("bid_size", 0))),
            "ask_price": float(message.get("ask_price", prev_quote.get("ask_price", 0.0))),
            "ask_size": int(message.get("ask_size", prev_quote.get("ask_size", 0))),
            "tot_buy_qty": int(message.get("tot_buy_qty", prev_quote.get("tot_buy_qty", 0))),
            "tot_sell_qty": int(message.get("tot_sell_qty", prev_quote.get("tot_sell_qty", 0))),
            "direction": direction,
            "updated_at": time.strftime("%H:%M:%S"),
        }

        self._data[symbol] = quote
        self.dirty_symbols.add(symbol)

    def get_all_quotes(
        self,
        search: str = "",
        filter_type: str = "all",
        sort_by: str = "symbol",
        sort_order: str = "asc",
    ) -> list[dict[str, Any]]:
        quotes = list(self._data.values())

        if search:
            search_lower = search.lower()
            quotes = [
                q for q in quotes
                if search_lower in q["symbol"].lower() or search_lower in q["short_name"].lower()
            ]

        if filter_type == "gainers":
            quotes = [q for q in quotes if q["ch"] > 0]
        elif filter_type == "losers":
            quotes = [q for q in quotes if q["ch"] < 0]
        elif filter_type == "high_volume":
            quotes = [q for q in quotes if q["vol_traded_today"] > 1_000_000]

        reverse = (sort_order.lower() == "desc")

        def sort_key(item):
            val = item.get(sort_by, 0)
            if val is None:
                return 0
            return val

        quotes.sort(key=sort_key, reverse=reverse)
        return quotes

    def get_summary_stats(self) -> dict[str, Any]:
        all_quotes = list(self._data.values())
        gainers = sum(1 for q in all_quotes if q["ch"] > 0)
        losers = sum(1 for q in all_quotes if q["ch"] < 0)
        unchanged = sum(1 for q in all_quotes if q["ch"] == 0)
        total_vol = sum(q["vol_traded_today"] for q in all_quotes)

        top_gainer = max(all_quotes, key=lambda q: q["chp"], default=None)
        top_loser = min(all_quotes, key=lambda q: q["chp"], default=None)

        return {
            "total_symbols": len(self._data),
            "total_ticks": self.total_ticks,
            "gainers": gainers,
            "losers": losers,
            "unchanged": unchanged,
            "total_volume": total_vol,
            "is_ws_connected": self.is_ws_connected,
            "top_gainer": {
                "symbol": top_gainer["short_name"] if top_gainer else "-",
                "chp": top_gainer["chp"] if top_gainer else 0.0,
                "ltp": top_gainer["ltp"] if top_gainer else 0.0
            } if top_gainer else None,
            "top_loser": {
                "symbol": top_loser["short_name"] if top_loser else "-",
                "chp": top_loser["chp"] if top_loser else 0.0,
                "ltp": top_loser["ltp"] if top_loser else 0.0
            } if top_loser else None
        }

    def get_screened_stocks(self) -> list[dict[str, Any]]:
        """Returns the current list of screened stocks from the in-memory screener state,
        enriched with live tick data from the store."""
        if not self.screener_service:
            return []

        screened_list = []
        # Build a reverse lookup: stock_id → symbol
        id_to_symbol = {v: k for k, v in self.screener_service.state.stock_ids_by_symbol.items()}

        for stock_id, state in self.screener_service.state.screened.items():
            symbol = id_to_symbol.get(stock_id, "")
            short_name = symbol.replace("NSE:", "").replace("-EQ", "").replace("-INDEX", "")

            # Get live data from the tick store if available
            live_data = self._data.get(symbol, {})

            # Format trigger time to a clean time string (HH:MM:SS)
            added_time = ""
            if hasattr(state.trigger_time, "strftime"):
                added_time = state.trigger_time.strftime("%H:%M:%S")
            elif isinstance(state.trigger_time, str):
                if " " in state.trigger_time:
                    added_time = state.trigger_time.split(" ")[1].split(".")[0]
                elif "T" in state.trigger_time:
                    added_time = state.trigger_time.split("T")[1].split(".")[0]
                else:
                    added_time = state.trigger_time
            else:
                added_time = str(state.trigger_time)

            screened_list.append({
                "stock_id": stock_id,
                "symbol": symbol,
                "short_name": short_name,
                "ltp": float(state.ltp),
                "percentage_change": float(state.percentage_change),
                "added_time": added_time,
                "trigger_time": str(state.trigger_time) if state.trigger_time else "",
                "vol_traded_today": live_data.get("vol_traded_today", 0),
                "prev_close_price": live_data.get("prev_close_price", 0.0),
            })

        # Sort by absolute percentage change descending
        screened_list.sort(key=lambda x: abs(x["percentage_change"]), reverse=True)
        return screened_list

    async def connect_ws(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect_ws(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast_updates(self):
        """Runs continuously in background loop to send updated tick batches to connected clients"""
        while True:
            try:
                if self.dirty_symbols and self.active_connections:
                    dirty = list(self.dirty_symbols)
                    self.dirty_symbols.clear()

                    updated_quotes = [self._data[sym] for sym in dirty if sym in self._data]

                    if updated_quotes:
                        message = {
                            "type": "ticks_batch",
                            "data": updated_quotes,
                            "stats": self.get_summary_stats(),
                            "screened": self.get_screened_stocks(),
                        }
                        disconnected = []
                        for connection in list(self.active_connections):
                            try:
                                await connection.send_json(message)
                            except Exception:
                                disconnected.append(connection)

                        for conn in disconnected:
                            self.disconnect_ws(conn)

                await asyncio.sleep(0.15)  # Send batch every 150ms
            except Exception as e:
                print(f"[BROADCAST ERROR] {e}")
                await asyncio.sleep(0.5)

live_store = LiveMarketStore()
