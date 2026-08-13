import sys
import hashlib
import requests
import pyotp
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from fyers_apiv3 import fyersModel
from app.core.config import settings
from app.core.fyers_token_manager import is_token_valid, update_env_file, refresh_access_token_via_refresh_token

def auto_login_with_totp(fy_id: str, pin: str, totp_key: str) -> bool:
    """100% automated daily login using FYERS v3 TOTP API endpoints"""
    try:
        app_id = settings.fyers_client_id.split("-")[0] if "-" in settings.fyers_client_id else settings.fyers_client_id
        
        # Step 1: Send TOTP
        totp_code = pyotp.TOTP(totp_key.replace(" ", "")).now()
        totp_payload = {"fy_id": fy_id, "totp": totp_code}
        
        resp1 = requests.post("https://api-t1.fyers.in/api/v3/verify-totp", json=totp_payload, timeout=10)
        res1_json = resp1.json()
        
        if res1_json.get("s") != "ok" or "request_key" not in res1_json:
            print(f"[AUTO-LOGIN TOTP FAILED] {res1_json}")
            return False
            
        request_key = res1_json["request_key"]
        
        # Step 2: Verify PIN
        pin_payload = {"fy_id": fy_id, "pin": pin, "request_key": request_key}
        resp2 = requests.post("https://api-t1.fyers.in/api/v3/verify-pin", json=pin_payload, timeout=10)
        res2_json = resp2.json()
        
        if res2_json.get("s") != "ok" or "access_token" not in res2_json:
            print(f"[AUTO-LOGIN PIN FAILED] {res2_json}")
            return False
            
        token_key = res2_json["access_token"]
        
        # Step 3: Generate Auth Code
        app_id_hash = hashlib.sha256(f"{settings.fyers_client_id}:{settings.fyers_secret_key}".encode()).hexdigest()
        auth_payload = {
            "client_id": settings.fyers_client_id,
            "redirect_uri": settings.fyers_redirect_uri,
            "response_type": "code",
            "state": "None",
            "app_id_hash": app_id_hash,
            "account_token": token_key
        }
        
        resp3 = requests.post("https://api-t1.fyers.in/api/v3/token", json=auth_payload, timeout=10)
        res3_json = resp3.json()
        
        if "Url" in res3_json or "auth_code" in res3_json:
            auth_url = res3_json.get("Url", "")
            auth_code = res3_json.get("auth_code", "")
            if not auth_code and "auth_code=" in auth_url:
                auth_code = auth_url.split("auth_code=")[1].split("&")[0]
                
            if auth_code:
                session = fyersModel.SessionModel(
                    client_id=settings.fyers_client_id,
                    secret_key=settings.fyers_secret_key,
                    redirect_uri=settings.fyers_redirect_uri,
                    response_type="code",
                    grant_type="authorization_code"
                )
                session.set_token(auth_code)
                token_resp = session.generate_token()
                
                if token_resp.get("s") == "ok" and "access_token" in token_resp:
                    new_token = token_resp["access_token"]
                    update_env_file("FYERS_ACCESS_TOKEN", new_token)
                    if "refresh_token" in token_resp:
                        update_env_file("FYERS_REFRESH_TOKEN", token_resp["refresh_token"])
                    print("[AUTO-LOGIN SUCCESS] Successfully authenticated & saved new token!")
                    return True
                    
        print(f"[AUTO-LOGIN AUTH FAILED] {res3_json}")
        return False
    except Exception as e:
        print(f"[AUTO-LOGIN EXCEPTION] {e}")
        return False

def main():
    print("=" * 70)
    print(" FYERS AUTOMATED DAILY LOGIN SYSTEM")
    print("=" * 70)

    # 1. Check if existing token is valid
    if is_token_valid():
        print("✅ FYERS Access Token is ACTIVE and VALID. No re-login required.\n")
        return True

    print("⚠️ Current Access Token is EXPIRED.")
    
    # 2. Check if Refresh Token is present
    refresh_token = getattr(settings, "fyers_refresh_token", None) or getattr(settings, "FYERS_REFRESH_TOKEN", None)
    if refresh_token:
        print("Attempting token renewal via Refresh Token...")
        new_token = refresh_access_token_via_refresh_token(refresh_token)
        if new_token:
            return True

    # 3. Check if TOTP credentials are available
    fy_id = getattr(settings, "fyers_fy_id", None)
    pin = getattr(settings, "fyers_pin", None)
    totp_key = getattr(settings, "fyers_totp_key", None)

    if fy_id and pin and totp_key:
        print("Attempting 100% automated TOTP login...")
        if auto_login_with_totp(fy_id, pin, totp_key):
            return True

    print("\nℹ️ Automated renewal requires a valid auth_code for initial login.")
    print("Please run: python scripts/generate_token.py\n")
    return False

if __name__ == "__main__":
    main()
