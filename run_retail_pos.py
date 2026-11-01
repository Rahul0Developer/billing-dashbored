"""
Apex Enterprise Retail POS, Inventory & ERP Platform
Master 1-Click Application Launcher

Usage:
    python run_retail_pos.py
"""

from pathlib import Path
import sys
import threading
import time
import webbrowser

# Ensure UTF-8 output encoding on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import uvicorn
from backend.storage.db import DatabaseManager
from backend.config import DATABASE_PATH
from backend.seed_retail_data import seed_store_data


def open_browser():
    """Opens browser automatically after a short startup delay."""
    time.sleep(1.5)
    url = "http://localhost:8000"
    print(f"\n[OK] Launching Retail POS & Store ERP Interface at: {url}")
    webbrowser.open(url)


def main():
    print("""
  ╔═════════════════════════════════════════════════════════════════════════╗
  ║             APEX ENTERPRISE RETAIL POS & STORE ERP                      ║
  ║         Supermarket Checkout • Footfall Analytics • P&L Tracker         ║
  ╚═════════════════════════════════════════════════════════════════════════╝
    """)
    print("[*] Verifying retail database and loading supermarket catalog...")
    db_manager = DatabaseManager(DATABASE_PATH)
    seed_store_data(db_manager)

    print("[*] Starting FastAPI Server with Uvicorn on http://localhost:8000 ...")
    print("    • Point of Sale (POS) Counter:   http://localhost:8000")
    print("    • Swagger REST API Docs:         http://localhost:8000/docs")
    print("    • Press Ctrl+C in this terminal to shut down.\n")

    # Start browser opener in background thread
    threading.Thread(target=open_browser, daemon=True).start()

    # Launch server
    uvicorn.run("backend.app:app", host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    main()

