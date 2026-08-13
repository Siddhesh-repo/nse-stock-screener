import os
import re
from pathlib import Path
from fyers_apiv3 import fyersModel
from app.core.config import settings

ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"

def is_token_valid() -> bool:
    """Check if the current FYERS access token is valid by testing get_profile()"""
    try:
        fyers = fyersModel.FyersModel(
            client_id=settings.fyers_client_id,
            token=settings.fyers_access_token,
            is_async=False,
            log_path=""
        )
        profile = fyers.get_profile()
        return profile.get("s") == "ok" and profile.get("code") == 200
    except Exception as e:
        print(f"[TOKEN CHECK ERROR] {e}")
        return False

def update_env_file(key: str, value: str) -> None:
    """Helper to update a key-value pair in .env file cleanly"""
    if not ENV_PATH.exists():
        print(f"[ENV ERROR] .env file not found at {ENV_PATH}")
        return

    content = ENV_PATH.read_text(encoding="utf-8")
    pattern = re.compile(rf"^{key}=.*$", re.MULTILINE)

    if pattern.search(content):
        updated_content = pattern.sub(f"{key}={value}", content)
    else:
        updated_content = content.strip() + f"\n{key}={value}\n"

    ENV_PATH.write_text(updated_content, encoding="utf-8")
    print(f"[ENV SUCCESS] Updated {key} in .env file.")

def refresh_access_token_via_refresh_token(refresh_token: str) -> str | None:
    """
    Generate a new 24-hour access_token using refresh_token grant type
    """
    try:
        session = fyersModel.SessionModel(
            client_id=settings.fyers_client_id,
            secret_key=settings.fyers_secret_key,
            grant_type="refresh_token"
        )
        session.set_token(refresh_token)
        response = session.generate_token()

        if response.get("s") == "ok" and "access_token" in response:
            new_access_token = response["access_token"]
            update_env_file("FYERS_ACCESS_TOKEN", new_access_token)
            settings.fyers_access_token = new_access_token
            print("[TOKEN REFRESH SUCCESS] Successfully renewed FYERS access token!")
            return new_access_token
        else:
            print(f"[TOKEN REFRESH FAILED] {response}")
            return None
    except Exception as e:
        print(f"[TOKEN REFRESH EXCEPTION] {e}")
        return None
