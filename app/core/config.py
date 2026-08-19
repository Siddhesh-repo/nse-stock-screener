from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    fyers_client_id: str
    fyers_secret_key: str
    fyers_redirect_uri: str
    fyers_access_token: str
    fyers_refresh_token: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()