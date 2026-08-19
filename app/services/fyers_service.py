from fyers_apiv3 import fyersModel

from app.core.config import settings

# Maps our timeframe strings to FYERS resolution values
FYERS_RESOLUTION_MAP = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
    "1D": "1D",
}


class FyersService:

    def __init__(self):
        self.client = fyersModel.FyersModel(
            client_id=settings.fyers_client_id,
            token=settings.fyers_access_token,
            is_async=False,
            log_path="",
        )

    def get_history(
        self,
        symbol: str,
        trading_date: str,
    ) -> dict:

        data = {
            "symbol": symbol,
            "resolution": "1D",
            "date_format": "1",
            "range_from": trading_date,
            "range_to": trading_date,
            "cont_flag": "1",
        }

        return self.client.history(data=data)

    def get_candle_history(
        self,
        symbol: str,
        resolution: str,
        range_from: str,
        range_to: str,
    ) -> dict:
        """Fetches historical candle data from FYERS REST API.

        Args:
            symbol: FYERS symbol format e.g. "NSE:RELIANCE-EQ".
            resolution: Timeframe string e.g. "1m", "5m", "15m", "30m", "1h", "1D".
            range_from: Start date in YYYY-MM-DD format.
            range_to: End date in YYYY-MM-DD format.

        Returns:
            FYERS API response dict containing 'candles' key with
            [[timestamp, open, high, low, close, volume], ...] data.
        """
        fyers_resolution = FYERS_RESOLUTION_MAP.get(resolution, resolution)

        data = {
            "symbol": symbol,
            "resolution": fyers_resolution,
            "date_format": "1",
            "range_from": range_from,
            "range_to": range_to,
            "cont_flag": "1",
        }

        return self.client.history(data=data)