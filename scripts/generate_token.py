import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from fyers_apiv3 import fyersModel
from app.core.config import settings
from app.core.fyers_token_manager import update_env_file, is_token_valid

def main():
    print("=" * 70)
    print(" FYERS TOKEN GENERATION & AUTO-SAVER UTILITY")
    print("=" * 70)

    if is_token_valid():
        print("✅ Current FYERS Access Token in .env is VALID and ACTIVE!")
        print("No action needed.\n")
        return

    print("⚠️ Current token is expired or invalid. Generating auth URL...\n")

    session = fyersModel.SessionModel(
        client_id=settings.fyers_client_id,
        secret_key=settings.fyers_secret_key,
        redirect_uri=settings.fyers_redirect_uri,
        response_type="code",
        grant_type="authorization_code",
    )

    auth_url = session.generate_authcode()
    print("1. Open this URL in your browser and authorize login:")
    print(f"\n   {auth_url}\n")
    print("2. Copy the 'auth_code' parameter from the redirected browser URL bar.")
    
    auth_code = input("\nEnter the auth_code here: ").strip()

    if not auth_code:
        print("No auth_code provided. Exiting.")
        return

    session.set_token(auth_code)
    response = session.generate_token()

    if response.get("s") == "ok" and "access_token" in response:
        access_token = response["access_token"]
        update_env_file("FYERS_ACCESS_TOKEN", access_token)
        
        if "refresh_token" in response:
            update_env_file("FYERS_REFRESH_TOKEN", response["refresh_token"])

        print("\n🎉 Token generation SUCCESS! New FYERS access token saved to .env file.")
    else:
        print(f"\n❌ Error generating token: {response}")

if __name__ == "__main__":
    main()