from collections.abc import Callable
from typing import Any

from fyers_apiv3.FyersWebsocket import data_ws

from app.core.config import settings


TickHandler = Callable[[dict[str, Any]], None]


class WebSocketService:

    MAX_SUBSCRIPTIONS = 5000

    def __init__(
        self,
        on_tick: TickHandler,
        litemode: bool = False,
    ):
        self.on_tick = on_tick
        self.litemode = litemode
        self.socket = None
        self.symbols: list[str] = []

    def start(
        self,
        symbols: list[str],
    ) -> None:

        if not symbols:
            raise ValueError(
                "No symbols provided for WebSocket."
            )

        if len(symbols) > self.MAX_SUBSCRIPTIONS:
            raise ValueError(
                f"{len(symbols)} symbols requested. "
                f"FYERS limit is "
                f"{self.MAX_SUBSCRIPTIONS}."
            )

        self.symbols = symbols

        access_token = (
            f"{settings.fyers_client_id}:"
            f"{settings.fyers_access_token}"
        )

        self.socket = data_ws.FyersDataSocket(
            access_token=access_token,
            log_path="",
            litemode=self.litemode,
            write_to_file=False,
            reconnect=True,
            on_connect=self._on_connect,
            on_close=self._on_close,
            on_error=self._on_error,
            on_message=self._on_message,
        )

        print(
            "Starting FYERS WebSocket..."
        )

        self.socket.connect()

    def _on_connect(self):
        print(
            "WebSocket connection established."
        )

        print(
            f"Subscribing to "
            f"{len(self.symbols)} symbols..."
        )

        self.socket.subscribe(
            symbols=self.symbols,
            data_type="SymbolUpdate",
        )

        print(
            "Subscription request sent."
        )
        self.socket.keep_running()

    def _on_message(
        self,
        message: dict[str, Any],
    ):
        self.on_tick(message)

    def _on_error(
        self,
        message: Any,
    ):
        print(
            f"[WEBSOCKET ERROR] {message}"
        )
        err_dict = None
        if isinstance(message, dict):
            err_dict = message
        elif isinstance(message, str) and "invalid_symbols" in message:
            try:
                import ast
                err_dict = ast.literal_eval(message)
            except Exception:
                pass

        if isinstance(err_dict, dict) and err_dict.get("code") == -300:
            invalid = err_dict.get("invalid_symbols", [])
            if invalid:
                print(
                    f"[WEBSOCKET] Removing {len(invalid)} invalid symbols and resubscribing..."
                )
                self.symbols = [s for s in self.symbols if s not in invalid]
                if self.socket and self.symbols:
                    try:
                        self.socket.subscribe(
                            symbols=self.symbols,
                            data_type="SymbolUpdate",
                        )
                    except Exception as err:
                        print(f"[WEBSOCKET RESUBSCRIBE ERROR] {err}")
        if isinstance(message, dict) and message.get("message") == "Token is expired":
            print("⚠️ [FYERS ALERT] Access Token has expired. Run 'python scripts/generate_token.py' to generate a fresh token.")

    def _on_close(
        self,
        message: Any,
    ):
        print(
            f"[WEBSOCKET CLOSED] {message}"
        )