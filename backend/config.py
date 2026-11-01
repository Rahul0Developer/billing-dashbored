"""
Retail Store Global Configuration & Business Entity Settings
Professional enterprise retail operations, POS billing, and ERP configuration.
"""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = BASE_DIR / "data" / "retail_store.db"
RECEIPTS_DIR = BASE_DIR / "data" / "receipts"

# Ensure data directories exist
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class StoreProfile:
    """Store identification printed on thermal receipts and reports."""
    name: str = "APEX ENTERPRISE RETAIL"
    tagline: str = "Enterprise Hypermarket & Retail Operations"
    store_code: str = "APEX-HQ-01"
    gstin: str = "07AAACR1234F1Z5"
    fssai_license: str = "10018011002234"
    cin_number: str = "U74999MH2006PLC160533"
    address_line1: str = "Plot 42, Sector 18, Commercial Hub"
    address_line2: str = "Gurugram, NCR - 122001"
    support_phone: str = "+91 1800 200 8899"
    support_email: str = "support@apexretail.io"
    website: str = "www.apexretail.io"
    currency_symbol: str = "₹"
    currency_code: str = "INR"
    default_cgst_percent: Decimal = Decimal("9.00")
    default_sgst_percent: Decimal = Decimal("9.00")


STORE_PROFILE = StoreProfile()

