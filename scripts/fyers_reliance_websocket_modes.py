import sys
from pathlib import Path

# Add project root directory to sys.path so 'app' module can be imported cleanly
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import time
import json
from fyers_apiv3.FyersWebsocket import data_ws
from app.core.config import settings

SYMBOL = "NSE:RELIANCE-EQ"

def print_header(title: str):
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)

def run_lite_mode(duration_sec: int = 5):
    print_header("MODE 1: LITE MODE (SymbolUpdate, litemode=True)")
    access_token = f"{settings.fyers_client_id}:{settings.fyers_access_token}"

    def on_connect():
        print("[LITE MODE] Connection established. Subscribing to symbol...")
        fyers.subscribe(symbols=[SYMBOL], data_type="SymbolUpdate")

    def on_message(message):
        if message.get("type") in ["cn", "lit", "sub"]:
            print(f"[LITE SYSTEM MSG] {message}")
        else:
            print(f"[LITE TICK] {json.dumps(message, indent=2)}")

    def on_error(message):
        print(f"[LITE ERROR] {message}")

    fyers = data_ws.FyersDataSocket(
        access_token=access_token,
        write_to_file=False,
        litemode=True,
        reconnect=True,
        on_connect=on_connect,
        on_message=on_message,
        on_error=on_error,
    )

    fyers.connect()
    time.sleep(duration_sec)
    fyers.close_connection()
    print("[LITE MODE] Connection closed.\n")

def run_full_mode(duration_sec: int = 5):
    print_header("MODE 2: FULL MODE (SymbolUpdate, litemode=False)")
    access_token = f"{settings.fyers_client_id}:{settings.fyers_access_token}"

    def on_connect():
        print("[FULL MODE] Connection established. Subscribing to symbol...")
        fyers.subscribe(symbols=[SYMBOL], data_type="SymbolUpdate")

    def on_message(message):
        if message.get("type") in ["cn", "ful", "sub"]:
            print(f"[FULL SYSTEM MSG] {message}")
        else:
            print(f"[FULL TICK] {json.dumps(message, indent=2)}")

    def on_error(message):
        print(f"[FULL ERROR] {message}")

    fyers = data_ws.FyersDataSocket(
        access_token=access_token,
        write_to_file=False,
        litemode=False,
        reconnect=True,
        on_connect=on_connect,
        on_message=on_message,
        on_error=on_error,
    )

    fyers.connect()
    time.sleep(duration_sec)
    fyers.close_connection()
    print("[FULL MODE] Connection closed.\n")

def run_depth_mode(duration_sec: int = 5):
    print_header("MODE 3: MARKET DEPTH MODE (DepthUpdate)")
    access_token = f"{settings.fyers_client_id}:{settings.fyers_access_token}"

    def on_connect():
        print("[DEPTH MODE] Connection established. Subscribing to depth updates...")
        fyers.subscribe(symbols=[SYMBOL], data_type="DepthUpdate")

    def on_message(message):
        if message.get("type") in ["cn", "ful", "sub"]:
            print(f"[DEPTH SYSTEM MSG] {message}")
        else:
            print(f"[DEPTH TICK] {json.dumps(message, indent=2)}")

    def on_error(message):
        print(f"[DEPTH ERROR] {message}")

    fyers = data_ws.FyersDataSocket(
        access_token=access_token,
        write_to_file=False,
        litemode=False,
        reconnect=True,
        on_connect=on_connect,
        on_message=on_message,
        on_error=on_error,
    )

    fyers.connect()
    time.sleep(duration_sec)
    fyers.close_connection()
    print("[DEPTH MODE] Connection closed.\n")

def main():
    print("=" * 80)
    print(f" FYERS WEBSOCKET DATA DEMONSTRATION FOR {SYMBOL}")
    print("=" * 80)
    
    # 1. Lite Mode
    run_lite_mode(duration_sec=4)
    time.sleep(1)

    # 2. Full Mode
    run_full_mode(duration_sec=4)
    time.sleep(1)

    # 3. Market Depth Mode
    run_depth_mode(duration_sec=4)
    time.sleep(1)

    print_header("ALL WEBSOCKET MODES COMPLETED SUCCESSFULLY")

if __name__ == "__main__":
    main()
