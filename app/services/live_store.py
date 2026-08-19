import asyncio
import json
import time
from typing import Any
from fastapi import WebSocket

from app.schemas.candle import Candle


class LiveMarketStore:
    def __init__(self):
        self._data: dict[str, dict[str, Any]] = {}
        self.active_connections: list[WebSocket] = []
        self.total_ticks: int = 0
        self.is_ws_connected: bool = False
        self.dirty_symbols: set[str] = set()
        self.screener_service = None  # Set by main.py at startup
        self.candle_service = None  # Set by main.py at startup

        # Candle subscription tracking: maps WebSocket → {symbol, resolution}
        self._candle_subscriptions: dict[WebSocket, dict[str, str]] = {}

        # Pending candle events to broadcast: list of (event_type, candle_dict, closed_candle_dict_or_None)
        self._pending_candle_events: list[dict[str, Any]] = []

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

    def queue_candle_event(self, event_type: str, candle: Candle, closed_candle: Candle | None = None) -> None:
        """Queue a candle event for broadcasting on the next broadcast cycle."""
        event = {
            "type": "candle_update" if event_type == "update" else "candle_closed" if event_type == "closed" else "candle_new",
            "symbol": candle.symbol,
            "candle": candle.to_dict(),
        }
        if closed_candle is not None:
            event["closed_candle"] = closed_candle.to_dict()
        self._pending_candle_events.append(event)

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

            current_ltp = live_data.get("ltp", state.ltp)
            current_chp = live_data.get("chp", state.percentage_change)

            screened_list.append({
                "stock_id": stock_id,
                "symbol": symbol,
                "short_name": short_name,
                "ltp": float(current_ltp) if current_ltp is not None else 0.0,
                "percentage_change": float(current_chp) if current_chp is not None else 0.0,
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
        # Clean up any candle subscriptions for this connection
        self._candle_subscriptions.pop(websocket, None)

    def subscribe_candle(self, websocket: WebSocket, symbol: str, resolution: str = "1m") -> None:
        """Register a WebSocket client for live candle updates on a specific symbol."""
        if not symbol.startswith("NSE:"):
            symbol = f"NSE:{symbol}"
        if not symbol.endswith("-EQ") and not symbol.endswith("-INDEX"):
            symbol = f"{symbol}-EQ"
        self._candle_subscriptions[websocket] = {"symbol": symbol, "resolution": resolution}

    def unsubscribe_candle(self, websocket: WebSocket) -> None:
        """Remove a WebSocket client's candle subscription."""
        self._candle_subscriptions.pop(websocket, None)

    async def handle_client_message(self, websocket: WebSocket, raw_text: str) -> None:
        """Handles incoming client messages on /ws/live for candle subscribe/unsubscribe."""
        try:
            msg = json.loads(raw_text)
        except (json.JSONDecodeError, TypeError):
            return

        action = msg.get("action")
        if action == "subscribe_candle":
            symbol = msg.get("symbol", "")
            resolution = msg.get("resolution", "1m")
            if symbol:
                self.subscribe_candle(websocket, symbol, resolution)
                # Send current live candles snapshot for the symbol
                if self.candle_service:
                    candles = self.candle_service.get_candles_for_timeframe(symbol, resolution)
                    await websocket.send_json({
                        "type": "candle_snapshot",
                        "symbol": symbol,
                        "resolution": resolution,
                        "candles": [c.to_dict() for c in candles],
                    })
        elif action == "unsubscribe_candle":
            self.unsubscribe_candle(websocket)

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

                # Broadcast pending candle events to subscribed clients
                if self._pending_candle_events and self._candle_subscriptions:
                    events = list(self._pending_candle_events)
                    self._pending_candle_events.clear()

                    disconnected = []
                    for ws, sub in list(self._candle_subscriptions.items()):
                        sub_symbol = sub["symbol"]
                        sub_resolution = sub.get("resolution", "1m")
                        for event in events:
                            if event["symbol"] != sub_symbol:
                                continue

                            # For 1m subscriptions, send the raw event directly
                            if sub_resolution == "1m":
                                try:
                                    await ws.send_json(event)
                                except Exception:
                                    disconnected.append(ws)
                                    break
                            else:
                                # For higher timeframes, aggregate and send only on
                                # candle_new or candle_closed events (not every tick update)
                                if event["type"] in ("candle_new", "candle_closed"):
                                    if self.candle_service:
                                        agg_candles = self.candle_service.get_candles_for_timeframe(sub_symbol, sub_resolution)
                                        if agg_candles:
                                            last_candle = agg_candles[-1]
                                            try:
                                                await ws.send_json({
                                                    "type": event["type"],
                                                    "symbol": sub_symbol,
                                                    "resolution": sub_resolution,
                                                    "candle": last_candle.to_dict(),
                                                })
                                            except Exception:
                                                disconnected.append(ws)
                                                break
                                elif event["type"] == "candle_update":
                                    # Throttle: only send forming candle update for higher TFs
                                    if self.candle_service:
                                        agg_candles = self.candle_service.get_candles_for_timeframe(sub_symbol, sub_resolution)
                                        if agg_candles:
                                            last_candle = agg_candles[-1]
                                            try:
                                                await ws.send_json({
                                                    "type": "candle_update",
                                                    "symbol": sub_symbol,
                                                    "resolution": sub_resolution,
                                                    "candle": last_candle.to_dict(),
                                                })
                                            except Exception:
                                                disconnected.append(ws)
                                                break
                    for conn in disconnected:
                        self.disconnect_ws(conn)
                elif self._pending_candle_events:
                    # No subscribers, clear pending events
                    self._pending_candle_events.clear()

                await asyncio.sleep(0.15)  # Send batch every 150ms
            except Exception as e:
                print(f"[BROADCAST ERROR] {e}")
                await asyncio.sleep(0.5)

live_store = LiveMarketStore()
