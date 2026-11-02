"""
SQLite Database Connection & Comprehensive Retail Store Schema
Optimized with indexes for high-throughput retail checkout, stock tracking, and audits.
"""

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Generator, Union
from backend.config import DATABASE_PATH

TABLES_SQL = """
PRAGMA foreign_keys = ON;

-- Supermarket Store Branches (Multi-Branch Architecture)
CREATE TABLE IF NOT EXISTS branches (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    address TEXT NOT NULL,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    pincode TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    gstin TEXT,
    manager_name TEXT,
    is_headquarters INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

-- Store Employees / Cashiers / Admins
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'CASHIER',
    pin TEXT NOT NULL,
    branch_id TEXT NOT NULL DEFAULT 'BR-DEL-01',
    is_active INTEGER NOT NULL DEFAULT 1
);

-- Suppliers / Vendors
CREATE TABLE IF NOT EXISTS suppliers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    contact_person TEXT,
    phone TEXT,
    email TEXT,
    address TEXT,
    gstin TEXT,
    payment_terms TEXT DEFAULT 'Net-30'
);

-- Customer Footfall & Loyalty
CREATE TABLE IF NOT EXISTS customers (
    phone TEXT PRIMARY KEY,
    membership_code TEXT UNIQUE,
    name TEXT NOT NULL,
    email TEXT,
    address TEXT,
    visit_count INTEGER NOT NULL DEFAULT 1,
    total_spent TEXT NOT NULL DEFAULT '0.00',
    loyalty_points INTEGER NOT NULL DEFAULT 0,
    tier TEXT NOT NULL DEFAULT 'BRONZE',
    first_visited_at TEXT NOT NULL,
    last_visited_at TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);

-- Supermarket Catalog & Stock
CREATE TABLE IF NOT EXISTS products (
    barcode TEXT PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    brand TEXT NOT NULL,
    unit TEXT NOT NULL DEFAULT 'pcs',
    cost_price TEXT NOT NULL,
    selling_price TEXT NOT NULL,
    mrp TEXT NOT NULL,
    stock_quantity INTEGER NOT NULL DEFAULT 0,
    reorder_level INTEGER NOT NULL DEFAULT 10,
    tax_rate_percent TEXT NOT NULL DEFAULT '5.00',
    supplier_name TEXT,
    expiry_date TEXT,
    subcategory TEXT,
    is_active INTEGER NOT NULL DEFAULT 1
);

-- Branch Specific Inventory Allocations
CREATE TABLE IF NOT EXISTS branch_inventory (
    branch_id TEXT NOT NULL,
    barcode TEXT NOT NULL,
    stock_quantity INTEGER NOT NULL DEFAULT 0,
    reorder_level INTEGER NOT NULL DEFAULT 10,
    shelf_location TEXT DEFAULT 'Aisle 1',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (branch_id, barcode),
    FOREIGN KEY(branch_id) REFERENCES branches(id) ON DELETE CASCADE,
    FOREIGN KEY(barcode) REFERENCES products(barcode) ON DELETE CASCADE
);

-- Stock Movements Audit Trail
CREATE TABLE IF NOT EXISTS stock_movements (
    id TEXT PRIMARY KEY,
    barcode TEXT NOT NULL,
    movement_type TEXT NOT NULL,
    quantity_change INTEGER NOT NULL,
    previous_stock INTEGER NOT NULL,
    new_stock INTEGER NOT NULL,
    reason TEXT NOT NULL,
    reference_id TEXT NOT NULL,
    branch_id TEXT NOT NULL DEFAULT 'BR-DEL-01',
    destination_branch_id TEXT,
    user_id TEXT NOT NULL DEFAULT 'SYSTEM',
    timestamp TEXT NOT NULL
    -- No FK on barcode: the movement ledger is an append-only audit trail that
    -- must survive product deletion (and accept synthetic system entries).
);

-- Sales Orders / Invoices
CREATE TABLE IF NOT EXISTS orders (
    bill_number TEXT PRIMARY KEY,
    cashier_id TEXT NOT NULL,
    cashier_name TEXT NOT NULL,
    customer_phone TEXT,
    customer_name TEXT,
    customer_tier TEXT NOT NULL DEFAULT 'BRONZE',
    payment_method TEXT NOT NULL,
    tendered_amount TEXT NOT NULL DEFAULT '0.00',
    change_amount TEXT NOT NULL DEFAULT '0.00',
    order_discount TEXT NOT NULL DEFAULT '0.00',
    points_redeemed INTEGER NOT NULL DEFAULT 0,
    points_discount_amount TEXT NOT NULL DEFAULT '0.00',
    subtotal TEXT NOT NULL DEFAULT '0.00',
    grand_total TEXT NOT NULL DEFAULT '0.00',
    total_savings TEXT NOT NULL DEFAULT '0.00',
    total_tax TEXT NOT NULL DEFAULT '0.00',
    total_cogs TEXT NOT NULL DEFAULT '0.00',
    status TEXT NOT NULL DEFAULT 'COMPLETED',
    notes TEXT,
    branch_id TEXT NOT NULL DEFAULT 'BR-DEL-01',
    branch_name TEXT NOT NULL DEFAULT 'Indirapuram Flagship',
    created_at TEXT NOT NULL
);

-- Line Items
CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_number TEXT NOT NULL,
    barcode TEXT NOT NULL,
    product_name TEXT NOT NULL,
    category TEXT NOT NULL,
    unit TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_mrp TEXT NOT NULL,
    unit_price TEXT NOT NULL,
    cost_price TEXT NOT NULL,
    tax_rate_percent TEXT NOT NULL,
    line_discount TEXT NOT NULL DEFAULT '0.00',
    total_amount TEXT NOT NULL,
    is_returned INTEGER NOT NULL DEFAULT 0,
    branch_id TEXT NOT NULL DEFAULT 'BR-DEL-01',
    FOREIGN KEY(bill_number) REFERENCES orders(bill_number) ON DELETE CASCADE
);

-- Multiple Payment Tenders (Split Payments)
CREATE TABLE IF NOT EXISTS payments (
    id TEXT PRIMARY KEY,
    bill_number TEXT NOT NULL,
    method TEXT NOT NULL,
    amount TEXT NOT NULL,
    transaction_ref TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(bill_number) REFERENCES orders(bill_number) ON DELETE CASCADE
);

-- Returns & Refunds
CREATE TABLE IF NOT EXISTS returns (
    id TEXT PRIMARY KEY,
    return_number TEXT NOT NULL UNIQUE,
    original_bill_number TEXT NOT NULL,
    customer_phone TEXT,
    cashier_id TEXT NOT NULL,
    refund_amount TEXT NOT NULL,
    reason TEXT NOT NULL,
    authorized_by TEXT NOT NULL DEFAULT '',
    branch_id TEXT NOT NULL DEFAULT 'BR-DEL-01',
    created_at TEXT NOT NULL,
    FOREIGN KEY(original_bill_number) REFERENCES orders(bill_number) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS return_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    return_id TEXT NOT NULL,
    barcode TEXT NOT NULL,
    product_name TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    refund_unit_price TEXT NOT NULL,
    total_refund TEXT NOT NULL,
    FOREIGN KEY(return_id) REFERENCES returns(id) ON DELETE CASCADE
);

-- Cashier Shifts & Drawer Reconciliation (Z-Report)
CREATE TABLE IF NOT EXISTS cash_shifts (
    id TEXT PRIMARY KEY,
    cashier_id TEXT NOT NULL,
    cashier_name TEXT NOT NULL,
    shift_number INTEGER NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT,
    opening_float TEXT NOT NULL DEFAULT '2000.00',
    total_cash_sales TEXT NOT NULL DEFAULT '0.00',
    total_upi_sales TEXT NOT NULL DEFAULT '0.00',
    total_card_sales TEXT NOT NULL DEFAULT '0.00',
    total_refunds TEXT NOT NULL DEFAULT '0.00',
    cash_drops TEXT NOT NULL DEFAULT '0.00',
    actual_counted_cash TEXT NOT NULL DEFAULT '0.00',
    is_closed INTEGER NOT NULL DEFAULT 0,
    branch_id TEXT NOT NULL DEFAULT 'BR-DEL-01',
    notes TEXT
);

-- Store Operational Expenses
CREATE TABLE IF NOT EXISTS expenses (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    amount TEXT NOT NULL,
    expense_date TEXT NOT NULL,
    description TEXT NOT NULL,
    payment_mode TEXT NOT NULL DEFAULT 'BANK_TRANSFER',
    vendor_name TEXT,
    receipt_reference TEXT,
    branch_id TEXT NOT NULL DEFAULT 'BR-DEL-01',
    created_at TEXT NOT NULL
);

-- Security Audit Logs
CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    details TEXT,
    timestamp TEXT NOT NULL
);
"""

INDEXES_SQL = """
-- Fast POS Barcode & Date Query Indexes
CREATE INDEX IF NOT EXISTS idx_prod_sku ON products(sku);
CREATE INDEX IF NOT EXISTS idx_prod_cat ON products(category);
CREATE INDEX IF NOT EXISTS idx_cust_membership ON customers(membership_code);
CREATE INDEX IF NOT EXISTS idx_orders_cust ON orders(customer_phone);
CREATE INDEX IF NOT EXISTS idx_orders_date ON orders(created_at);
CREATE INDEX IF NOT EXISTS idx_orders_branch ON orders(branch_id);
CREATE INDEX IF NOT EXISTS idx_order_items_bill ON order_items(bill_number);
CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(expense_date);
CREATE INDEX IF NOT EXISTS idx_expenses_cat ON expenses(category);
CREATE INDEX IF NOT EXISTS idx_expenses_branch ON expenses(branch_id);
CREATE INDEX IF NOT EXISTS idx_movements_barcode ON stock_movements(barcode);
CREATE INDEX IF NOT EXISTS idx_movements_branch ON stock_movements(branch_id);
CREATE INDEX IF NOT EXISTS idx_shifts_cashier ON cash_shifts(cashier_id);
CREATE INDEX IF NOT EXISTS idx_shifts_branch ON cash_shifts(branch_id);
CREATE INDEX IF NOT EXISTS idx_branch_inv_bc ON branch_inventory(barcode);
"""

SCHEMA_SQL = TABLES_SQL + "\n" + INDEXES_SQL


class DatabaseManager:
    def __init__(self, db_path: Union[Path, str] = DATABASE_PATH):
        self.db_path = Path(db_path)
        self.initialize_schema()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def atomic(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Executes a block of operations within an atomic, immediate SQLite transaction.
        If any exception occurs, the entire transaction is rolled back immediately.
        """
        conn = self.get_connection()
        conn.execute("BEGIN IMMEDIATE;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize_schema(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript(TABLES_SQL)
            
            # Migration check: Ensure newly added columns exist in existing tables
            cursor = conn.cursor()
            
            # customers table migrations
            cust_cols = [r[1] for r in cursor.execute("PRAGMA table_info(customers);").fetchall()]
            if "address" not in cust_cols:
                cursor.execute("ALTER TABLE customers ADD COLUMN address TEXT;")
            if "membership_code" not in cust_cols:
                cursor.execute("ALTER TABLE customers ADD COLUMN membership_code TEXT;")
            cursor.execute("UPDATE customers SET membership_code = 'MEM-' || phone WHERE membership_code IS NULL OR membership_code = '';")

            # products table migrations
            prod_cols = [r[1] for r in cursor.execute("PRAGMA table_info(products);").fetchall()]
            if "supplier_name" not in prod_cols:
                cursor.execute("ALTER TABLE products ADD COLUMN supplier_name TEXT;")
            if "expiry_date" not in prod_cols:
                cursor.execute("ALTER TABLE products ADD COLUMN expiry_date TEXT;")
            if "subcategory" not in prod_cols:
                cursor.execute("ALTER TABLE products ADD COLUMN subcategory TEXT;")
                
            # orders table migrations
            order_cols = [r[1] for r in cursor.execute("PRAGMA table_info(orders);").fetchall()]
            if "status" not in order_cols:
                cursor.execute("ALTER TABLE orders ADD COLUMN status TEXT NOT NULL DEFAULT 'COMPLETED';")
            if "notes" not in order_cols:
                cursor.execute("ALTER TABLE orders ADD COLUMN notes TEXT DEFAULT '';")
                
            # order_items table migrations
            item_cols = [r[1] for r in cursor.execute("PRAGMA table_info(order_items);").fetchall()]
            if "is_returned" not in item_cols:
                cursor.execute("ALTER TABLE order_items ADD COLUMN is_returned INTEGER NOT NULL DEFAULT 0;")
            if "branch_id" not in item_cols:
                cursor.execute("ALTER TABLE order_items ADD COLUMN branch_id TEXT NOT NULL DEFAULT 'BR-DEL-01';")

            # orders table branch migrations
            if "branch_id" not in order_cols:
                cursor.execute("ALTER TABLE orders ADD COLUMN branch_id TEXT NOT NULL DEFAULT 'BR-DEL-01';")
            if "branch_name" not in order_cols:
                cursor.execute("ALTER TABLE orders ADD COLUMN branch_name TEXT NOT NULL DEFAULT 'Indirapuram Flagship';")

            # returns table branch migrations
            ret_cols = [r[1] for r in cursor.execute("PRAGMA table_info(returns);").fetchall()]
            if "branch_id" not in ret_cols:
                cursor.execute("ALTER TABLE returns ADD COLUMN branch_id TEXT NOT NULL DEFAULT 'BR-DEL-01';")
            if "authorized_by" not in ret_cols:
                cursor.execute("ALTER TABLE returns ADD COLUMN authorized_by TEXT NOT NULL DEFAULT '';")

            # cash_shifts table branch migrations
            shift_cols = [r[1] for r in cursor.execute("PRAGMA table_info(cash_shifts);").fetchall()]
            if "branch_id" not in shift_cols:
                cursor.execute("ALTER TABLE cash_shifts ADD COLUMN branch_id TEXT NOT NULL DEFAULT 'BR-DEL-01';")

            # expenses table branch migrations
            exp_cols = [r[1] for r in cursor.execute("PRAGMA table_info(expenses);").fetchall()]
            if "branch_id" not in exp_cols:
                cursor.execute("ALTER TABLE expenses ADD COLUMN branch_id TEXT NOT NULL DEFAULT 'BR-DEL-01';")

            # stock_movements table branch migrations
            mov_cols = [r[1] for r in cursor.execute("PRAGMA table_info(stock_movements);").fetchall()]
            if "branch_id" not in mov_cols:
                cursor.execute("ALTER TABLE stock_movements ADD COLUMN branch_id TEXT NOT NULL DEFAULT 'BR-DEL-01';")
            if "destination_branch_id" not in mov_cols:
                cursor.execute("ALTER TABLE stock_movements ADD COLUMN destination_branch_id TEXT;")

            # One-time migration: drop legacy FK(barcode) on stock_movements.
            # The movement ledger is an append-only audit trail; it must accept
            # synthetic system entries and survive product deletion. SQLite
            # cannot DROP CONSTRAINT, so rebuild the table preserving rows.
            _mov_sql = cursor.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='stock_movements';"
            ).fetchone()
            if _mov_sql and _mov_sql[0] and "FOREIGN KEY" in _mov_sql[0]:
                cols = [r[1] for r in cursor.execute("PRAGMA table_info(stock_movements);").fetchall()]
                col_list = ", ".join(cols)
                # Rebuild the DDL from PRAGMA column metadata (type + notnull +
                # default, PK kept), dropping every FOREIGN KEY clause.
                coldefs = []
                for cid, cname, ctype, notnull, dflt, pk in cursor.execute(
                    "PRAGMA table_info(stock_movements);"
                ).fetchall():
                    d = f"{cname} {ctype or 'TEXT'}"
                    if pk:
                        d += " PRIMARY KEY"
                    if notnull and not pk:
                        d += " NOT NULL"
                    if dflt is not None:
                        d += f" DEFAULT {dflt}"
                    coldefs.append(d)
                new_ddl = "CREATE TABLE stock_movements_new (" + ", ".join(coldefs) + ");"
                cursor.execute("PRAGMA foreign_keys=OFF;")
                try:
                    cursor.execute(new_ddl)
                    cursor.execute(f"INSERT INTO stock_movements_new ({col_list}) SELECT {col_list} FROM stock_movements;")
                    cursor.execute("DROP TABLE stock_movements;")
                    cursor.execute("ALTER TABLE stock_movements_new RENAME TO stock_movements;")
                finally:
                    cursor.execute("PRAGMA foreign_keys=ON;")

            # users table branch migrations
            user_cols = [r[1] for r in cursor.execute("PRAGMA table_info(users);").fetchall()]
            if "branch_id" not in user_cols:
                cursor.execute("ALTER TABLE users ADD COLUMN branch_id TEXT NOT NULL DEFAULT 'BR-DEL-01';")

            # Safely create all performance indexes now that all columns are guaranteed to exist
            conn.executescript(INDEXES_SQL)

            # Clean up any legacy store names in existing database
            cursor.execute("UPDATE branches SET name = REPLACE(name, 'Reliance Smart Bazaar - ', '') WHERE name LIKE '%Reliance%';")
            cursor.execute("UPDATE branches SET email = REPLACE(email, '@reliancesmart.com', '@apexretail.io') WHERE email LIKE '%reliancesmart%';")
            cursor.execute("UPDATE orders SET branch_name = REPLACE(branch_name, 'Reliance Smart Bazaar - ', '') WHERE branch_name LIKE '%Reliance%';")
            cursor.execute("UPDATE stock_movements SET reason = REPLACE(reason, 'Reliance Smart', 'Apex Retail') WHERE reason LIKE '%Reliance%';")

            # Seed default store branches if empty
            branch_count = cursor.execute("SELECT COUNT(*) FROM branches;").fetchone()[0]
            if branch_count == 0:
                now_str = datetime.now().isoformat()
                cursor.execute("""
                    INSERT INTO branches (id, code, name, address, city, state, pincode, phone, email, gstin, manager_name, is_headquarters, is_active, created_at)
                    VALUES 
                    ('BR-DEL-01', 'DEL-FLAGSHIP', 'Indirapuram Flagship Store', 'Plot 4A, Indirapuram Commercial Hub', 'Ghaziabad / Delhi NCR', 'Uttar Pradesh', '201014', '+91 1800 200 8899', 'flagship.del@apexretail.io', '07AAACR1234F1Z5', 'Vikram Malhotra', 1, 1, ?),
                    ('BR-MUM-02', 'MUM-BANDRA', 'Bandra West Store', 'Linking Road, Bandra West', 'Mumbai', 'Maharashtra', '400050', '+91 1800 200 8898', 'bandra.mum@apexretail.io', '27AAACR1234F1Z1', 'Sunil Deshmukh', 0, 1, ?),
                    ('BR-BLR-03', 'BLR-WHITEFIELD', 'Whitefield Tech Hub Store', 'ITPL Main Road, Whitefield', 'Bengaluru', 'Karnataka', '560066', '+91 1800 200 8897', 'whitefield.blr@apexretail.io', '29AAACR1234F1Z8', 'Ananya Hegde', 0, 1, ?);
                """, (now_str, now_str, now_str))
