from fyers_apiv3 import fyersModel

from app.core.config import settings


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