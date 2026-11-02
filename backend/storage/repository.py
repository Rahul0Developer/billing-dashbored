"""
Comprehensive Supermarket Data Access Repository (Repository Pattern)
Provides atomic database persistence, queries, and entity mapping with full transaction safety.
Supports transactional Unit-of-Work across billing, stock deductions, returns, and financial audits.
"""

from contextlib import contextmanager
from datetime import datetime, date
from decimal import Decimal
import sqlite3
from typing import List, Optional, Dict, Any, Generator
import uuid

from backend.models.domain import (
    Customer,
    CustomerTier,
    Product,
    OrderItem,
    Order,
    OrderStatus,
    Expense,
    ExpenseCategory,
    PaymentMethod,
    PaymentRecord,
    User,
    UserRole,
    Supplier,
    StockMovement,
    StockMovementType,
    ReturnRecord,
    CashShift,
    StoreBranch,
    BranchStock,
    round_curr,
)
from backend.models.exceptions import InsufficientStockError, ProductNotFoundError, POSTransactionError
from backend.storage.db import DatabaseManager


class RetailRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    @contextmanager
    def atomic(self) -> Generator[sqlite3.Connection, None, None]:
        """Exposes atomic, immediate transaction scope from the underlying DatabaseManager."""
        with self.db.atomic() as conn:
            yield conn

    @contextmanager
    def _get_connection(self, conn: Optional[sqlite3.Connection] = None) -> Generator[sqlite3.Connection, None, None]:
        """Reuses an active transaction connection if provided, otherwise opens a managed standalone connection."""
        if conn is not None:
            yield conn
        else:
            with self.db.connection() as c:
                yield c

    # ========================================================================
    # MULTI-BRANCH STORE NETWORK REPOSITORY
    # ========================================================================
    def save_branch(self, b: StoreBranch, conn: Optional[sqlite3.Connection] = None) -> None:
        sql = """
        INSERT INTO branches (
            id, code, name, address, city, state, pincode,
            phone, email, gstin, manager_name, is_headquarters, is_active, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            code = excluded.code,
            name = excluded.name,
            address = excluded.address,
            city = excluded.city,
            state = excluded.state,
            pincode = excluded.pincode,
            phone = excluded.phone,
            email = excluded.email,
            gstin = excluded.gstin,
            manager_name = excluded.manager_name,
            is_headquarters = excluded.is_headquarters,
            is_active = excluded.is_active;
        """
        with self._get_connection(conn) as c:
            c.execute(sql, (
                b.id, b.code, b.name, b.address, b.city, b.state, b.pincode,
                b.phone, b.email, b.gstin, b.manager_name,
                1 if b.is_headquarters else 0, 1 if b.is_active else 0,
                b.created_at.isoformat()
            ))

    def get_branch_by_id(self, branch_id: str, conn: Optional[sqlite3.Connection] = None) -> Optional[StoreBranch]:
        sql = "SELECT * FROM branches WHERE id = ?;"
        with self._get_connection(conn) as c:
            row = c.execute(sql, (branch_id.strip(),)).fetchone()
            if not row:
                return None
            return self._row_to_branch(row)

    def get_branch_by_code(self, code: str, conn: Optional[sqlite3.Connection] = None) -> Optional[StoreBranch]:
        sql = "SELECT * FROM branches WHERE code = ?;"
        with self._get_connection(conn) as c:
            row = c.execute(sql, (code.strip().upper(),)).fetchone()
            if not row:
                return None
            return self._row_to_branch(row)

    def list_branches(self) -> List[StoreBranch]:
        sql = "SELECT * FROM branches WHERE is_active = 1 ORDER BY is_headquarters DESC, name ASC;"
        with self.db.connection() as conn:
            rows = conn.execute(sql).fetchall()
            return [self._row_to_branch(r) for r in rows]

    def _row_to_branch(self, r: sqlite3.Row) -> StoreBranch:
        return StoreBranch(
            id=r["id"],
            code=r["code"],
            name=r["name"],
            address=r["address"],
            city=r["city"],
            state=r["state"],
            pincode=r["pincode"],
            phone=r["phone"] or "",
            email=r["email"] or "",
            gstin=r["gstin"] or "",
            manager_name=r["manager_name"] or "",
            is_headquarters=bool(r["is_headquarters"]),
            is_active=bool(r["is_active"]),
            created_at=datetime.fromisoformat(r["created_at"])
        )

    # --- Multi-Branch Inventory Allocations & Transfers ---
    def set_branch_stock(
        self,
        branch_id: str,
        barcode: str,
        quantity: int,
        reorder_level: int = 10,
        shelf_location: str = "Aisle 1",
        conn: Optional[sqlite3.Connection] = None
    ) -> None:
        sql = """
        INSERT INTO branch_inventory (branch_id, barcode, stock_quantity, reorder_level, shelf_location, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(branch_id, barcode) DO UPDATE SET
            stock_quantity = excluded.stock_quantity,
            reorder_level = excluded.reorder_level,
            shelf_location = excluded.shelf_location,
            updated_at = excluded.updated_at;
        """
        with self._get_connection(conn) as c:
            c.execute(sql, (
                branch_id.strip(), barcode.strip(), quantity, reorder_level, shelf_location, datetime.now().isoformat()
            ))

    def get_branch_stock(self, branch_id: str, barcode: str, conn: Optional[sqlite3.Connection] = None) -> Optional[BranchStock]:
        sql = "SELECT * FROM branch_inventory WHERE branch_id = ? AND barcode = ?;"
        with self._get_connection(conn) as c:
            row = c.execute(sql, (branch_id.strip(), barcode.strip())).fetchone()
            if not row:
                return None
            return BranchStock(
                branch_id=row["branch_id"],
                barcode=row["barcode"],
                stock_quantity=row["stock_quantity"],
                reorder_level=row["reorder_level"],
                shelf_location=row["shelf_location"] or "Aisle 1",
                updated_at=datetime.fromisoformat(row["updated_at"])
            )

    def list_branch_inventory(self, branch_id: str) -> List[Dict[str, Any]]:
        sql = """
        SELECT 
            p.barcode, p.sku, p.name, p.category, p.brand, p.unit,
            p.cost_price, p.selling_price, p.mrp, p.tax_rate_percent,
            COALESCE(bi.stock_quantity, p.stock_quantity) as stock_quantity,
            COALESCE(bi.reorder_level, p.reorder_level) as reorder_level,
            COALESCE(bi.shelf_location, 'Aisle 1') as shelf_location
        FROM products p
        LEFT JOIN branch_inventory bi ON p.barcode = bi.barcode AND bi.branch_id = ?
        WHERE p.is_active = 1
        ORDER BY p.category ASC, p.name ASC;
        """
        with self.db.connection() as conn:
            rows = conn.execute(sql, (branch_id.strip(),)).fetchall()
            return [
                {
                    "barcode": r["barcode"],
                    "sku": r["sku"],
                    "name": r["name"],
                    "category": r["category"],
                    "brand": r["brand"],
                    "unit": r["unit"],
                    "cost_price": float(r["cost_price"]),
                    "selling_price": float(r["selling_price"]),
                    "mrp": float(r["mrp"]),
                    "tax_rate_percent": float(r["tax_rate_percent"]),
                    "stock_quantity": r["stock_quantity"],
                    "reorder_level": r["reorder_level"],
                    "shelf_location": r["shelf_location"],
                    "is_low_stock": r["stock_quantity"] <= r["reorder_level"],
                    "is_out_of_stock": r["stock_quantity"] <= 0
                }
                for r in rows
            ]

    def deduct_branch_stock_atomic(self, branch_id: str, barcode: str, quantity: int, conn: sqlite3.Connection) -> int:
        """
        Atomically inspects and decrements branch stock within an open transaction.
        Also maintains synchronization with global catalog stock.
        """
        row = conn.execute("SELECT stock_quantity FROM branch_inventory WHERE branch_id = ? AND barcode = ?;", (branch_id.strip(), barcode.strip())).fetchone()
        if not row:
            p_row = conn.execute("SELECT stock_quantity, reorder_level, name FROM products WHERE barcode = ?;", (barcode.strip(),)).fetchone()
            if not p_row:
                raise ProductNotFoundError(barcode)
            init_stock = p_row["stock_quantity"]
            conn.execute(
                "INSERT INTO branch_inventory (branch_id, barcode, stock_quantity, reorder_level, shelf_location, updated_at) VALUES (?, ?, ?, ?, ?, ?);",
                (branch_id.strip(), barcode.strip(), init_stock, p_row["reorder_level"], "Aisle 1", datetime.now().isoformat())
            )
            row = conn.execute("SELECT stock_quantity FROM branch_inventory WHERE branch_id = ? AND barcode = ?;", (branch_id.strip(), barcode.strip())).fetchone()

        curr_stock = row["stock_quantity"]
        p_row = conn.execute("SELECT name FROM products WHERE barcode = ?;", (barcode.strip(),)).fetchone()
        name = p_row["name"] if p_row else barcode
        if quantity <= 0:
            raise POSTransactionError(
                f"Quantity must be a positive integer for item '{name}'.", code="INVALID_QUANTITY"
            )
        if curr_stock < quantity:
            raise InsufficientStockError(barcode, name, curr_stock, quantity)

        new_stock = curr_stock - quantity
        updated = conn.execute(
            "UPDATE branch_inventory SET stock_quantity = ?, updated_at = ? "
            "WHERE branch_id = ? AND barcode = ? AND stock_quantity = ?;",
            (new_stock, datetime.now().isoformat(), branch_id.strip(), barcode.strip(), curr_stock),
        )
        if updated.rowcount != 1:
            # Optimistic-lock failure: another transaction changed this row.
            raise POSTransactionError(
                f"Concurrent stock update detected for '{name}'. Please retry the sale.",
                code="STOCK_CONFLICT",
            )

        # Also decrement master product stock for single-store fallback / overall catalog view
        conn.execute("UPDATE products SET stock_quantity = MAX(0, stock_quantity - ?) WHERE barcode = ?;", (quantity, barcode.strip()))
        return new_stock

    def restore_branch_stock_atomic(self, branch_id: str, barcode: str, quantity: int, conn: sqlite3.Connection) -> int:
        """Atomically restores returned stock to a specific branch."""
        row = conn.execute("SELECT stock_quantity FROM branch_inventory WHERE branch_id = ? AND barcode = ?;", (branch_id.strip(), barcode.strip())).fetchone()
        if row:
            new_stock = row["stock_quantity"] + quantity
            conn.execute("UPDATE branch_inventory SET stock_quantity = ?, updated_at = ? WHERE branch_id = ? AND barcode = ?;",
                         (new_stock, datetime.now().isoformat(), branch_id.strip(), barcode.strip()))
        else:
            new_stock = quantity
            conn.execute("INSERT INTO branch_inventory (branch_id, barcode, stock_quantity, updated_at) VALUES (?, ?, ?, ?);",
                         (branch_id.strip(), barcode.strip(), new_stock, datetime.now().isoformat()))

        conn.execute("UPDATE products SET stock_quantity = stock_quantity + ? WHERE barcode = ?;", (quantity, barcode.strip()))
        return new_stock

    def transfer_stock_between_branches(
        self,
        from_branch_id: str,
        to_branch_id: str,
        barcode: str,
        quantity: int,
        reason: str = "Inter-branch balance",
        user_id: str = "MGR-01",
        conn: Optional[sqlite3.Connection] = None
    ) -> Dict[str, Any]:
        """Executes an atomic inter-branch stock transfer with audit trail movements."""
        if from_branch_id == to_branch_id:
            raise ValueError("Source and destination branch cannot be the same!")

        with self._get_connection(conn) as c:
            # Check source stock
            src_row = c.execute("SELECT stock_quantity FROM branch_inventory WHERE branch_id = ? AND barcode = ?;", (from_branch_id, barcode)).fetchone()
            if not src_row:
                p_row = c.execute("SELECT stock_quantity FROM products WHERE barcode = ?;", (barcode,)).fetchone()
                init_stock = p_row["stock_quantity"] if p_row else 0
                c.execute("INSERT INTO branch_inventory (branch_id, barcode, stock_quantity, updated_at) VALUES (?, ?, ?, ?);",
                          (from_branch_id, barcode, init_stock, datetime.now().isoformat()))
                src_row = c.execute("SELECT stock_quantity FROM branch_inventory WHERE branch_id = ? AND barcode = ?;", (from_branch_id, barcode)).fetchone()

            if src_row["stock_quantity"] < quantity:
                p_row = c.execute("SELECT name FROM products WHERE barcode = ?;", (barcode,)).fetchone()
                p_name = p_row["name"] if p_row else barcode
                raise InsufficientStockError(barcode, p_name, src_row["stock_quantity"], quantity)

            old_src = src_row["stock_quantity"]
            new_src = old_src - quantity
            c.execute("UPDATE branch_inventory SET stock_quantity = ?, updated_at = ? WHERE branch_id = ? AND barcode = ?;",
                      (new_src, datetime.now().isoformat(), from_branch_id, barcode))

            # Update dest stock
            dest_row = c.execute("SELECT stock_quantity FROM branch_inventory WHERE branch_id = ? AND barcode = ?;", (to_branch_id, barcode)).fetchone()
            old_dest = dest_row["stock_quantity"] if dest_row else 0
            new_dest = old_dest + quantity
            c.execute("""
                INSERT INTO branch_inventory (branch_id, barcode, stock_quantity, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(branch_id, barcode) DO UPDATE SET
                    stock_quantity = excluded.stock_quantity,
                    updated_at = excluded.updated_at;
            """, (to_branch_id, barcode, new_dest, datetime.now().isoformat()))

            # Record Transfer Out movement
            trans_id = f"TRF-{uuid.uuid4().hex[:8].upper()}"
            self.record_stock_movement(StockMovement(
                id=f"MOV-{uuid.uuid4().hex[:8].upper()}",
                barcode=barcode,
                movement_type=StockMovementType.TRANSFER_OUT,
                quantity_change=-quantity,
                previous_stock=old_src,
                new_stock=new_src,
                reason=f"Transfer to {to_branch_id}: {reason}",
                reference_id=trans_id,
                branch_id=from_branch_id,
                destination_branch_id=to_branch_id,
                user_id=user_id,
                timestamp=datetime.now()
            ), conn=c)

            # Record Transfer In movement
            self.record_stock_movement(StockMovement(
                id=f"MOV-{uuid.uuid4().hex[:8].upper()}",
                barcode=barcode,
                movement_type=StockMovementType.TRANSFER_IN,
                quantity_change=quantity,
                previous_stock=old_dest,
                new_stock=new_dest,
                reason=f"Transfer from {from_branch_id}: {reason}",
                reference_id=trans_id,
                branch_id=to_branch_id,
                destination_branch_id=from_branch_id,
                user_id=user_id,
                timestamp=datetime.now()
            ), conn=c)

            return {
                "success": True,
                "transfer_id": trans_id,
                "from_branch_id": from_branch_id,
                "to_branch_id": to_branch_id,
                "barcode": barcode,
                "quantity": quantity,
                "transferred_quantity": quantity,
                "from_branch_new_stock": new_src,
                "source_remaining_stock": new_src,
                "to_branch_new_stock": new_dest,
                "target_new_stock": new_dest
            }

    # ========================================================================
    # USER & AUTHENTICATION REPOSITORY
    # ========================================================================
    def save_user(self, user: User, conn: Optional[sqlite3.Connection] = None) -> None:
        sql = """
        INSERT INTO users (id, username, full_name, role, pin, branch_id, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            full_name = excluded.full_name,
            role = excluded.role,
            pin = excluded.pin,
            branch_id = excluded.branch_id,
            is_active = excluded.is_active;
        """
        with self._get_connection(conn) as c:
            c.execute(sql, (
                user.id, user.username, user.full_name, user.role.value, user.pin,
                getattr(user, "branch_id", "BR-DEL-01"), 1 if user.is_active else 0
            ))

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        sql = "SELECT * FROM users WHERE id = ?;"
        with self.db.connection() as conn:
            row = conn.execute(sql, (user_id,)).fetchone()
            if not row:
                return None
            return User(
                id=row["id"],
                username=row["username"],
                full_name=row["full_name"],
                role=UserRole(row["role"]),
                pin=row["pin"],
                is_active=bool(row["is_active"])
            )

    def get_user_by_username(self, username: str) -> Optional[User]:
        sql = "SELECT * FROM users WHERE username = ?;"
        with self.db.connection() as conn:
            row = conn.execute(sql, (username,)).fetchone()
            if not row:
                return None
            return User(
                id=row["id"],
                username=row["username"],
                full_name=row["full_name"],
                role=UserRole(row["role"]),
                pin=row["pin"],
                is_active=bool(row["is_active"])
            )

    def list_users(self) -> List[User]:
        sql = "SELECT * FROM users WHERE is_active = 1 ORDER BY full_name ASC;"
        with self.db.connection() as conn:
            rows = conn.execute(sql).fetchall()
            return [
                User(
                    id=r["id"],
                    username=r["username"],
                    full_name=r["full_name"],
                    role=UserRole(r["role"]),
                    pin=r["pin"],
                    is_active=bool(r["is_active"])
                )
                for r in rows
            ]

    # ========================================================================
    # CUSTOMER REPOSITORY (Footfall, Visit Frequency & Spend Analytics)
    # ========================================================================
    def save_customer(self, customer: Customer, conn: Optional[sqlite3.Connection] = None) -> None:
        mem_code = customer.membership_code or f"MEM-{customer.phone}"
        sql = """
        INSERT INTO customers (
            phone, membership_code, name, email, address, visit_count, total_spent, loyalty_points,
            tier, first_visited_at, last_visited_at, is_active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(phone) DO UPDATE SET
            membership_code = excluded.membership_code,
            name = excluded.name,
            email = excluded.email,
            address = excluded.address,
            visit_count = excluded.visit_count,
            total_spent = excluded.total_spent,
            loyalty_points = excluded.loyalty_points,
            tier = excluded.tier,
            last_visited_at = excluded.last_visited_at,
            is_active = excluded.is_active;
        """
        with self._get_connection(conn) as c:
            c.execute(sql, (
                customer.phone,
                mem_code,
                customer.name,
                customer.email,
                customer.address,
                customer.visit_count,
                str(customer.total_spent),
                customer.loyalty_points,
                customer.tier.value,
                customer.first_visited_at.isoformat(),
                customer.last_visited_at.isoformat(),
                1 if customer.is_active else 0,
            ))

    def get_customer_by_phone(self, phone: str, conn: Optional[sqlite3.Connection] = None) -> Optional[Customer]:
        sql = "SELECT * FROM customers WHERE phone = ?;"
        with self._get_connection(conn) as c:
            row = c.execute(sql, (phone.strip(),)).fetchone()
            if not row:
                return None
            return self._row_to_customer(row)

    def get_customer_by_membership_code(self, membership_code: str, conn: Optional[sqlite3.Connection] = None) -> Optional[Customer]:
        sql = "SELECT * FROM customers WHERE UPPER(membership_code) = ?;"
        with self._get_connection(conn) as c:
            row = c.execute(sql, (membership_code.strip().upper(),)).fetchone()
            if not row:
                return None
            return self._row_to_customer(row)

    def get_customer_by_phone_or_code(self, identifier: str) -> Optional[Customer]:
        """
        Smart identifier lookup matching phone or membership QR code.
        Handles prefixes (+91, RETAIL:MEM:..., MEM-...).
        """
        clean = identifier.strip()
        if not clean:
            return None

        # Check QR payload format: "RETAIL:MEM:{code}:{phone}"
        if clean.startswith("RETAIL:MEM:"):
            parts = clean.split(":")
            if len(parts) >= 4 and parts[3]:
                found = self.get_customer_by_phone(parts[3])
                if found:
                    return found
            if len(parts) >= 3 and parts[2]:
                found = self.get_customer_by_membership_code(parts[2])
                if found:
                    return found

        # Direct phone check
        direct_phone = clean.replace("+91", "").replace(" ", "").replace("-", "")
        if direct_phone.isdigit() and len(direct_phone) == 10:
            cust = self.get_customer_by_phone(direct_phone)
            if cust:
                return cust

        # Check membership code
        cust_by_code = self.get_customer_by_membership_code(clean)
        if cust_by_code:
            return cust_by_code

        # Fallback check phone = ? or membership_code = ?
        sql = "SELECT * FROM customers WHERE phone = ? OR UPPER(membership_code) = ?;"
        with self.db.connection() as conn:
            row = conn.execute(sql, (clean, clean.upper())).fetchone()
            if row:
                return self._row_to_customer(row)

        return None

    def get_customer_purchase_insights(self, phone: str) -> Dict[str, Any]:
        """
        Deep customer shopping intelligence: purchase history, category preferences,
        top bought products, visit intervals, and lifetime stats.
        """
        cust = self.get_customer_by_phone(phone)
        orders = self.list_orders_by_customer(phone)
        completed_orders = [o for o in orders if o.status == OrderStatus.COMPLETED]

        total_orders = len(completed_orders)
        total_spent = sum((o.grand_total for o in completed_orders), Decimal("0.00"))
        total_savings = sum((o.total_savings for o in completed_orders), Decimal("0.00"))

        category_spend: Dict[str, Decimal] = {}
        category_units: Dict[str, int] = {}
        product_counts: Dict[str, Dict[str, Any]] = {}
        payment_methods: Dict[str, int] = {}

        for o in completed_orders:
            pm = o.payment_method.value
            payment_methods[pm] = payment_methods.get(pm, 0) + 1
            for item in o.items:
                if not item.is_returned:
                    c_name = item.category or "Groceries"
                    category_spend[c_name] = category_spend.get(c_name, Decimal("0.00")) + item.net_total
                    category_units[c_name] = category_units.get(c_name, 0) + item.quantity

                    if item.product_name not in product_counts:
                        product_counts[item.product_name] = {
                            "barcode": item.barcode,
                            "name": item.product_name,
                            "category": item.category,
                            "units": 0,
                            "spent": Decimal("0.00")
                        }
                    product_counts[item.product_name]["units"] += item.quantity
                    product_counts[item.product_name]["spent"] += item.net_total

        total_cat_spend = sum(category_spend.values(), Decimal("0.00"))
        category_breakdown = []
        for cat, amt in sorted(category_spend.items(), key=lambda x: x[1], reverse=True):
            pct = float(round((amt / total_cat_spend) * 100, 1)) if total_cat_spend > 0 else 0.0
            category_breakdown.append({
                "category": cat,
                "spent": float(round_curr(amt)),
                "units": category_units.get(cat, 0),
                "percentage": pct
            })

        top_products = sorted(product_counts.values(), key=lambda x: x["units"], reverse=True)[:5]
        top_products_formatted = [
            {
                "barcode": p.get("barcode", ""),
                "name": p["name"],
                "category": p["category"],
                "units": p["units"],
                "spent": float(round_curr(p["spent"]))
            }
            for p in top_products
        ]

        pref_payment = max(payment_methods.items(), key=lambda x: x[1])[0] if payment_methods else "UPI_QR"

        recent_invoices = [
            {
                "bill_number": o.bill_number,
                "date": o.created_at.strftime("%d-%b-%Y %I:%M %p"),
                "grand_total": float(o.grand_total),
                "items_count": o.total_items_count,
                "savings": float(o.total_savings),
                "payment_method": o.payment_method.value,
                "status": o.status.value,
                "items": [
                    {
                        "barcode": i.barcode,
                        "name": i.product_name,
                        "quantity": i.quantity,
                        "price": float(i.unit_price),
                        "total": float(i.net_total)
                    }
                    for i in o.items
                ]
            }
            for o in completed_orders[:10]
        ]

        spent_val = float(round_curr(cust.total_spent if cust else total_spent))
        return {
            "phone": phone,
            "name": cust.name if cust else "Customer",
            "membership_code": cust.membership_code if cust else f"MEM-{phone}",
            "membership_qr_data": cust.membership_qr_data if cust else f"RETAIL:MEM:MEM-{phone}:{phone}",
            "tier": cust.tier.value if cust else "BRONZE",
            "loyalty_points": cust.loyalty_points if cust else 0,
            "points_cash_value": float(cust.loyalty_points) if cust else 0.0,
            "visit_count": cust.visit_count if cust else total_orders,
            "total_orders": total_orders,
            "total_spent": spent_val,
            "lifetime_spent": spent_val,
            "lifetime_savings": float(round_curr(total_savings)),
            "average_basket": float(round_curr(cust.average_basket_value)) if cust else 0.0,
            "days_since_last_visit": cust.days_since_last_visit if cust else 0,
            "preferred_payment_method": pref_payment,
            "category_preferences": category_breakdown,
            "top_purchased_products": top_products_formatted,
            "recent_orders": recent_invoices
        }

    def list_customers(self, limit: int = 100) -> List[Customer]:
        sql = "SELECT * FROM customers WHERE is_active = 1 ORDER BY visit_count DESC, total_spent DESC LIMIT ?;"
        with self.db.connection() as conn:
            rows = conn.execute(sql, (limit,)).fetchall()
            return [self._row_to_customer(r) for r in rows]

    def _row_to_customer(self, r: sqlite3.Row) -> Customer:
        keys = r.keys()
        addr = r["address"] if ("address" in keys and r["address"]) else ""
        email = r["email"] if ("email" in keys and r["email"]) else ""
        mem_code = r["membership_code"] if ("membership_code" in keys and r["membership_code"]) else f"MEM-{r['phone']}"
        return Customer(
            phone=r["phone"],
            name=r["name"],
            membership_code=mem_code,
            email=email,
            address=addr,
            visit_count=r["visit_count"],
            total_spent=Decimal(r["total_spent"]),
            loyalty_points=r["loyalty_points"],
            tier=CustomerTier(r["tier"]),
            first_visited_at=datetime.fromisoformat(r["first_visited_at"]),
            last_visited_at=datetime.fromisoformat(r["last_visited_at"]),
            is_active=bool(r["is_active"])
        )

    # ========================================================================
    # PRODUCT CATALOG & INVENTORY REPOSITORY
    # ========================================================================
    def save_product(self, product: Product, conn: Optional[sqlite3.Connection] = None) -> None:
        sql = """
        INSERT INTO products (
            barcode, sku, name, category, brand, unit,
            cost_price, selling_price, mrp, stock_quantity,
            reorder_level, tax_rate_percent, supplier_name,
            expiry_date, subcategory, is_active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(barcode) DO UPDATE SET
            sku = excluded.sku,
            name = excluded.name,
            category = excluded.category,
            brand = excluded.brand,
            unit = excluded.unit,
            cost_price = excluded.cost_price,
            selling_price = excluded.selling_price,
            mrp = excluded.mrp,
            stock_quantity = excluded.stock_quantity,
            reorder_level = excluded.reorder_level,
            tax_rate_percent = excluded.tax_rate_percent,
            supplier_name = excluded.supplier_name,
            expiry_date = excluded.expiry_date,
            subcategory = excluded.subcategory,
            is_active = excluded.is_active;
        """
        exp_str = product.expiry_date.isoformat() if product.expiry_date else None
        with self._get_connection(conn) as c:
            c.execute(sql, (
                product.barcode,
                product.sku,
                product.name,
                product.category,
                product.brand,
                product.unit,
                str(product.cost_price),
                str(product.selling_price),
                str(product.mrp),
                product.stock_quantity,
                product.reorder_level,
                str(product.tax_rate_percent),
                product.supplier_name,
                exp_str,
                product.subcategory,
                1 if product.is_active else 0,
            ))

    def get_product_by_barcode(self, barcode: str, conn: Optional[sqlite3.Connection] = None) -> Optional[Product]:
        sql = "SELECT * FROM products WHERE barcode = ? OR sku = ?;"
        with self._get_connection(conn) as c:
            row = c.execute(sql, (barcode.strip(), barcode.strip())).fetchone()
            if not row:
                return None
            return self._row_to_product(row)

    def list_products(self) -> List[Product]:
        sql = "SELECT * FROM products WHERE is_active = 1 ORDER BY category ASC, name ASC;"
        with self.db.connection() as conn:
            rows = conn.execute(sql).fetchall()
            return [self._row_to_product(r) for r in rows]

    def update_stock(self, barcode: str, new_quantity: int, conn: Optional[sqlite3.Connection] = None) -> None:
        sql = "UPDATE products SET stock_quantity = ? WHERE barcode = ?;"
        with self._get_connection(conn) as c:
            c.execute(sql, (new_quantity, barcode))

    def deduct_product_stock_atomic(self, barcode: str, quantity: int, conn: sqlite3.Connection) -> Product:
        """
        Atomically inspects and decrements shelf stock within an open transaction.
        Raises ProductNotFoundError if barcode does not exist.
        Raises InsufficientStockError if available stock is less than requested quantity.
        """
        row = conn.execute("SELECT * FROM products WHERE barcode = ?;", (barcode.strip(),)).fetchone()
        if not row:
            raise ProductNotFoundError(barcode)

        current_stock = row["stock_quantity"]
        name = row["name"]
        if current_stock < quantity:
            raise InsufficientStockError(barcode, name, current_stock, quantity)

        new_stock = current_stock - quantity
        conn.execute("UPDATE products SET stock_quantity = ? WHERE barcode = ?;", (new_stock, barcode.strip()))

        prod = self._row_to_product(row)
        prod.stock_quantity = new_stock
        return prod

    def restore_product_stock_atomic(self, barcode: str, quantity: int, conn: sqlite3.Connection) -> Product:
        """
        Atomically increments shelf stock within an open transaction.
        """
        row = conn.execute("SELECT * FROM products WHERE barcode = ?;", (barcode.strip(),)).fetchone()
        if not row:
            raise ProductNotFoundError(barcode)

        current_stock = row["stock_quantity"]
        new_stock = current_stock + quantity
        conn.execute("UPDATE products SET stock_quantity = ? WHERE barcode = ?;", (new_stock, barcode.strip()))

        prod = self._row_to_product(row)
        prod.stock_quantity = new_stock
        return prod

    def _row_to_product(self, r: sqlite3.Row) -> Product:
        keys = r.keys()
        exp_d = date.fromisoformat(r["expiry_date"]) if ("expiry_date" in keys and r["expiry_date"]) else None
        supp_name = r["supplier_name"] if ("supplier_name" in keys and r["supplier_name"]) else ""
        subcat = r["subcategory"] if ("subcategory" in keys and r["subcategory"]) else ""
        return Product(
            barcode=r["barcode"],
            sku=r["sku"],
            name=r["name"],
            category=r["category"],
            brand=r["brand"],
            unit=r["unit"],
            cost_price=Decimal(r["cost_price"]),
            selling_price=Decimal(r["selling_price"]),
            mrp=Decimal(r["mrp"]),
            stock_quantity=r["stock_quantity"],
            reorder_level=r["reorder_level"],
            tax_rate_percent=Decimal(r["tax_rate_percent"]),
            supplier_name=supp_name,
            expiry_date=exp_d,
            subcategory=subcat,
            is_active=bool(r["is_active"])
        )

    # ========================================================================
    # STOCK MOVEMENTS AUDIT REPOSITORY
    # ========================================================================
    def record_stock_movement(self, movement: StockMovement, conn: Optional[sqlite3.Connection] = None) -> None:
        sql = """
        INSERT INTO stock_movements (
            id, barcode, movement_type, quantity_change, previous_stock,
            new_stock, reason, reference_id, branch_id, destination_branch_id, user_id, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        with self._get_connection(conn) as c:
            c.execute(sql, (
                movement.id,
                movement.barcode,
                movement.movement_type.value,
                movement.quantity_change,
                movement.previous_stock,
                movement.new_stock,
                movement.reason,
                movement.reference_id,
                getattr(movement, "branch_id", "BR-DEL-01"),
                getattr(movement, "destination_branch_id", None),
                movement.user_id,
                movement.timestamp.isoformat()
            ))

    def list_stock_movements(self, limit: int = 100, branch_id: Optional[str] = None) -> List[StockMovement]:
        params: List[Any] = []
        sql = "SELECT * FROM stock_movements"
        if branch_id and branch_id != "ALL":
            sql += " WHERE branch_id = ?"
            params.append(branch_id.strip())
        sql += " ORDER BY timestamp DESC LIMIT ?;"
        params.append(limit)

        with self.db.connection() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [
                StockMovement(
                    id=r["id"],
                    barcode=r["barcode"],
                    movement_type=StockMovementType(r["movement_type"]),
                    quantity_change=r["quantity_change"],
                    previous_stock=r["previous_stock"],
                    new_stock=r["new_stock"],
                    reason=r["reason"],
                    reference_id=r["reference_id"],
                    branch_id=r["branch_id"] if "branch_id" in r.keys() else "BR-DEL-01",
                    destination_branch_id=r["destination_branch_id"] if "destination_branch_id" in r.keys() else None,
                    user_id=r["user_id"],
                    timestamp=datetime.fromisoformat(r["timestamp"])
                )
                for r in rows
            ]

    def record_audit_log(
        self,
        actor_id: str,
        action: str,
        entity_type: str,
        entity_id: str,
        details: str = "",
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Append an immutable security-audit record (voids, PIN overrides,
        stock adjustments, shift closes, price changes, etc.)."""
        import uuid as _uuid
        with self.db.connection() as conn:
            conn.execute(
                "INSERT INTO audit_logs (id, user_id, action, entity_type, entity_id, details, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?);",
                (
                    f"AUD-{_uuid.uuid4().hex[:12].upper()}",
                    actor_id or "SYSTEM",
                    action,
                    entity_type,
                    entity_id,
                    details,
                    (timestamp or datetime.now()).isoformat(),
                ),
            )

    def list_audit_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?;", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ========================================================================
    # ORDER / BILLING & SPLIT PAYMENTS REPOSITORY
    # ========================================================================
    def save_order(self, order: Order, conn: Optional[sqlite3.Connection] = None) -> None:
        with self._get_connection(conn) as c:
            order_sql = """
            INSERT INTO orders (
                bill_number, cashier_id, cashier_name, customer_phone,
                customer_name, customer_tier, payment_method, tendered_amount,
                change_amount, order_discount, points_redeemed, points_discount_amount,
                subtotal, grand_total, total_savings, total_tax, total_cogs,
                status, notes, branch_id, branch_name, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(bill_number) DO UPDATE SET
                status = excluded.status,
                notes = excluded.notes;
            """
            c.execute(order_sql, (
                order.bill_number,
                order.cashier_id,
                order.cashier_name,
                order.customer_phone,
                order.customer_name,
                order.customer_tier.value,
                order.payment_method.value,
                str(order.tendered_amount),
                str(order.change_amount),
                str(order.order_discount),
                order.points_redeemed,
                str(order.points_discount_amount),
                str(order.subtotal),
                str(order.grand_total),
                str(order.total_savings),
                str(order.total_tax),
                str(order.total_cogs),
                order.status.value,
                order.notes,
                getattr(order, "branch_id", "BR-DEL-01"),
                getattr(order, "branch_name", "Indirapuram Flagship"),
                order.created_at.isoformat()
            ))

            # Items
            c.execute("DELETE FROM order_items WHERE bill_number = ?;", (order.bill_number,))
            item_sql = """
            INSERT INTO order_items (
                bill_number, barcode, product_name, category, unit,
                quantity, unit_mrp, unit_price, cost_price,
                tax_rate_percent, line_discount, total_amount, is_returned, branch_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """
            for itm in order.items:
                c.execute(item_sql, (
                    order.bill_number,
                    itm.barcode,
                    itm.product_name,
                    itm.category,
                    itm.unit,
                    itm.quantity,
                    str(itm.unit_mrp),
                    str(itm.unit_price),
                    str(itm.cost_price),
                    str(itm.tax_rate_percent),
                    str(itm.line_discount),
                    str(itm.net_total),
                    1 if itm.is_returned else 0,
                    getattr(itm, "branch_id", getattr(order, "branch_id", "BR-DEL-01"))
                ))

            # Split Payments
            if order.split_payments:
                c.execute("DELETE FROM payments WHERE bill_number = ?;", (order.bill_number,))
                pay_sql = """
                INSERT INTO payments (id, bill_number, method, amount, transaction_ref, created_at)
                VALUES (?, ?, ?, ?, ?, ?);
                """
                for p in order.split_payments:
                    c.execute(pay_sql, (
                        p.id, p.bill_number, p.method.value, str(p.amount), p.transaction_ref, p.created_at.isoformat()
                    ))

    def list_orders(self, limit: int = 150, branch_id: Optional[str] = None) -> List[Order]:
        params: List[Any] = []
        sql = "SELECT * FROM orders"
        if branch_id and branch_id != "ALL":
            sql += " WHERE branch_id = ?"
            params.append(branch_id.strip())
        sql += " ORDER BY created_at DESC LIMIT ?;"
        params.append(limit)

        with self.db.connection() as conn:
            order_rows = conn.execute(sql, tuple(params)).fetchall()
            return [self._build_order(conn, r) for r in order_rows]

    def list_completed_orders(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        branch_id: Optional[str] = None
    ) -> List[Order]:
        """Lists active non-cancelled orders (COMPLETED, PARTIALLY_REFUNDED, REFUNDED) within an optional timeframe and branch."""
        sql = "SELECT * FROM orders WHERE status != 'CANCELLED'"
        params: List[Any] = []
        if branch_id and branch_id != "ALL":
            sql += " AND branch_id = ?"
            params.append(branch_id.strip())
        if start_time:
            sql += " AND created_at >= ?"
            params.append(start_time.isoformat())
        if end_time:
            sql += " AND created_at <= ?"
            params.append(end_time.isoformat())
        sql += " ORDER BY created_at DESC;"

        with self.db.connection() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [self._build_order(conn, r) for r in rows]

    def get_order_by_bill_number(self, bill_number: str, conn: Optional[sqlite3.Connection] = None) -> Optional[Order]:
        with self._get_connection(conn) as c:
            row = c.execute("SELECT * FROM orders WHERE bill_number = ?;", (bill_number.strip(),)).fetchone()
            if not row:
                return None
            return self._build_order(c, row)

    def list_orders_by_customer(self, phone: str) -> List[Order]:
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM orders WHERE customer_phone = ? ORDER BY created_at DESC;", (phone.strip(),)
            ).fetchall()
            return [self._build_order(conn, r) for r in rows]

    def update_order_status(self, bill_number: str, new_status: OrderStatus, notes: str = "", conn: Optional[sqlite3.Connection] = None) -> None:
        sql = "UPDATE orders SET status = ?, notes = notes || ' ' || ? WHERE bill_number = ?;"
        with self._get_connection(conn) as c:
            c.execute(sql, (new_status.value, notes, bill_number))

    def _build_order(self, conn: sqlite3.Connection, r: sqlite3.Row) -> Order:
        bill_num = r["bill_number"]
        r_keys = r.keys()
        b_id = r["branch_id"] if "branch_id" in r_keys else "BR-DEL-01"
        b_name = r["branch_name"] if "branch_name" in r_keys else "Indirapuram Flagship"

        item_rows = conn.execute("SELECT * FROM order_items WHERE bill_number = ?;", (bill_num,)).fetchall()
        items = [
            OrderItem(
                barcode=ir["barcode"],
                product_name=ir["product_name"],
                category=ir["category"],
                unit=ir["unit"],
                quantity=ir["quantity"],
                unit_mrp=Decimal(ir["unit_mrp"]),
                unit_price=Decimal(ir["unit_price"]),
                cost_price=Decimal(ir["cost_price"]),
                tax_rate_percent=Decimal(ir["tax_rate_percent"]),
                line_discount=Decimal(ir["line_discount"]),
                is_returned=bool(ir["is_returned"]),
                branch_id=ir["branch_id"] if "branch_id" in ir.keys() else b_id
            )
            for ir in item_rows
        ]

        pay_rows = conn.execute("SELECT * FROM payments WHERE bill_number = ?;", (bill_num,)).fetchall()
        split_pays = [
            PaymentRecord(
                id=pr["id"],
                bill_number=pr["bill_number"],
                method=PaymentMethod(pr["method"]),
                amount=Decimal(pr["amount"]),
                transaction_ref=pr["transaction_ref"] or "",
                created_at=datetime.fromisoformat(pr["created_at"])
            )
            for pr in pay_rows
        ]

        return Order(
            bill_number=bill_num,
            cashier_id=r["cashier_id"],
            cashier_name=r["cashier_name"],
            customer_phone=r["customer_phone"],
            customer_name=r["customer_name"] or "Walk-in Customer",
            customer_tier=CustomerTier(r["customer_tier"]),
            items=items,
            payment_method=PaymentMethod(r["payment_method"]),
            tendered_amount=Decimal(r["tendered_amount"]),
            change_amount=Decimal(r["change_amount"]),
            order_discount=Decimal(r["order_discount"]),
            points_redeemed=r["points_redeemed"],
            points_discount_amount=Decimal(r["points_discount_amount"]),
            status=OrderStatus(r["status"]) if "status" in r_keys else OrderStatus.COMPLETED,
            notes=r["notes"] or "",
            branch_id=b_id,
            branch_name=b_name,
            split_payments=split_pays,
            created_at=datetime.fromisoformat(r["created_at"])
        )

    # ========================================================================
    # RETURNS & REFUNDS REPOSITORY
    # ========================================================================
    def save_return(self, ret: ReturnRecord, returned_items: List[Dict[str, Any]], conn: Optional[sqlite3.Connection] = None) -> None:
        with self._get_connection(conn) as c:
            ret_sql = """
            INSERT INTO returns (id, return_number, original_bill_number, customer_phone, cashier_id, refund_amount, reason, branch_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """
            c.execute(ret_sql, (
                ret.id, ret.return_number, ret.original_bill_number, ret.customer_phone,
                ret.cashier_id, str(ret.refund_amount), ret.reason,
                getattr(ret, "branch_id", "BR-DEL-01"), ret.created_at.isoformat()
            ))

            ret_item_sql = """
            INSERT INTO return_items (return_id, barcode, product_name, quantity, refund_unit_price, total_refund)
            VALUES (?, ?, ?, ?, ?, ?);
            """
            for itm in returned_items:
                c.execute(ret_item_sql, (
                    ret.id, itm["barcode"], itm["product_name"], itm["quantity"],
                    str(itm["unit_price"]), str(itm["total"])
                ))
                # Mark as returned in order_items
                c.execute(
                    "UPDATE order_items SET is_returned = 1 WHERE bill_number = ? AND barcode = ?;",
                    (ret.original_bill_number, itm["barcode"])
                )

    def list_returns(self, limit: int = 50, branch_id: Optional[str] = None) -> List[ReturnRecord]:
        params: List[Any] = []
        sql = "SELECT * FROM returns"
        if branch_id and branch_id != "ALL":
            sql += " WHERE branch_id = ?"
            params.append(branch_id.strip())
        sql += " ORDER BY created_at DESC LIMIT ?;"
        params.append(limit)

        with self.db.connection() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [
                ReturnRecord(
                    id=r["id"],
                    return_number=r["return_number"],
                    original_bill_number=r["original_bill_number"],
                    customer_phone=r["customer_phone"],
                    cashier_id=r["cashier_id"],
                    refund_amount=Decimal(r["refund_amount"]),
                    reason=r["reason"],
                    branch_id=r["branch_id"] if "branch_id" in r.keys() else "BR-DEL-01",
                    created_at=datetime.fromisoformat(r["created_at"])
                )
                for r in rows
            ]

    # ========================================================================
    # CASHIER SHIFT & DRAWER RECONCILIATION (Z-REPORT)
    # ========================================================================
    def get_active_shift(self, cashier_id: str, branch_id: Optional[str] = None, conn: Optional[sqlite3.Connection] = None) -> Optional[CashShift]:
        sql = "SELECT * FROM cash_shifts WHERE cashier_id = ? AND is_closed = 0"
        params: List[Any] = [cashier_id]
        if branch_id and branch_id != "ALL":
            sql += " AND branch_id = ?"
            params.append(branch_id.strip())
        sql += " ORDER BY start_time DESC LIMIT 1;"

        with self._get_connection(conn) as c:
            row = c.execute(sql, tuple(params)).fetchone()
            if not row:
                return None
            return self._row_to_shift(row)

    def save_shift(self, shift: CashShift, conn: Optional[sqlite3.Connection] = None) -> None:
        sql = """
        INSERT INTO cash_shifts (
            id, cashier_id, cashier_name, shift_number, start_time, end_time,
            opening_float, total_cash_sales, total_upi_sales, total_card_sales,
            total_refunds, cash_drops, actual_counted_cash, is_closed, branch_id, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            end_time = excluded.end_time,
            total_cash_sales = excluded.total_cash_sales,
            total_upi_sales = excluded.total_upi_sales,
            total_card_sales = excluded.total_card_sales,
            total_refunds = excluded.total_refunds,
            cash_drops = excluded.cash_drops,
            actual_counted_cash = excluded.actual_counted_cash,
            is_closed = excluded.is_closed,
            branch_id = excluded.branch_id,
            notes = excluded.notes;
        """
        end_str = shift.end_time.isoformat() if shift.end_time else None
        with self._get_connection(conn) as c:
            c.execute(sql, (
                shift.id, shift.cashier_id, shift.cashier_name, shift.shift_number,
                shift.start_time.isoformat(), end_str, str(shift.opening_float),
                str(shift.total_cash_sales), str(shift.total_upi_sales), str(shift.total_card_sales),
                str(shift.total_refunds), str(shift.cash_drops), str(shift.actual_counted_cash),
                1 if shift.is_closed else 0, getattr(shift, "branch_id", "BR-DEL-01"), shift.notes
            ))

    def list_shifts(self, limit: int = 30, branch_id: Optional[str] = None) -> List[CashShift]:
        sql = "SELECT * FROM cash_shifts"
        params: List[Any] = []
        if branch_id and branch_id != "ALL":
            sql += " WHERE branch_id = ?"
            params.append(branch_id.strip())
        sql += " ORDER BY start_time DESC LIMIT ?;"
        params.append(limit)
        with self.db.connection() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [self._row_to_shift(r) for r in rows]

    def _row_to_shift(self, r: sqlite3.Row) -> CashShift:
        end_t = datetime.fromisoformat(r["end_time"]) if r["end_time"] else None
        return CashShift(
            id=r["id"],
            cashier_id=r["cashier_id"],
            cashier_name=r["cashier_name"],
            shift_number=r["shift_number"],
            start_time=datetime.fromisoformat(r["start_time"]),
            end_time=end_t,
            opening_float=Decimal(r["opening_float"]),
            total_cash_sales=Decimal(r["total_cash_sales"]),
            total_upi_sales=Decimal(r["total_upi_sales"]),
            total_card_sales=Decimal(r["total_card_sales"]),
            total_refunds=Decimal(r["total_refunds"]),
            cash_drops=Decimal(r["cash_drops"]),
            actual_counted_cash=Decimal(r["actual_counted_cash"]),
            is_closed=bool(r["is_closed"]),
            branch_id=r["branch_id"] if "branch_id" in r.keys() else "BR-DEL-01",
            notes=r["notes"] or ""
        )

    # ========================================================================
    # EXPENSES OPERATIONS (Weekly, Monthly, Yearly Tracking)
    # ========================================================================
    def save_expense(self, expense: Expense, conn: Optional[sqlite3.Connection] = None) -> None:
        sql = """
        INSERT INTO expenses (
            id, category, amount, expense_date, description,
            payment_mode, vendor_name, receipt_reference, branch_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            category = excluded.category,
            amount = excluded.amount,
            expense_date = excluded.expense_date,
            description = excluded.description,
            payment_mode = excluded.payment_mode,
            vendor_name = excluded.vendor_name,
            receipt_reference = excluded.receipt_reference,
            branch_id = excluded.branch_id;
        """
        with self._get_connection(conn) as c:
            c.execute(sql, (
                expense.id,
                expense.category.value,
                str(expense.amount),
                expense.expense_date.isoformat(),
                expense.description,
                expense.payment_mode,
                expense.vendor_name,
                expense.receipt_reference,
                getattr(expense, "branch_id", "BR-DEL-01"),
                expense.created_at.isoformat()
            ))

    def list_expenses(self, limit: int = 300, branch_id: Optional[str] = None) -> List[Expense]:
        sql = "SELECT * FROM expenses"
        params: List[Any] = []
        if branch_id and branch_id != "ALL":
            sql += " WHERE (branch_id = ? OR branch_id = 'ALL' OR branch_id IS NULL)"
            params.append(branch_id.strip())
        sql += " ORDER BY expense_date DESC, created_at DESC LIMIT ?;"
        params.append(limit)

        with self.db.connection() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [
                Expense(
                    id=r["id"],
                    category=ExpenseCategory(r["category"]),
                    amount=Decimal(r["amount"]),
                    expense_date=date.fromisoformat(r["expense_date"]),
                    description=r["description"],
                    payment_mode=r["payment_mode"],
                    vendor_name=r["vendor_name"] or "",
                    receipt_reference=r["receipt_reference"] or "",
                    branch_id=r["branch_id"] if "branch_id" in r.keys() else "BR-DEL-01",
                    created_at=datetime.fromisoformat(r["created_at"])
                )
                for r in rows
            ]

    def delete_expense(self, expense_id: str, conn: Optional[sqlite3.Connection] = None) -> bool:
        sql = "DELETE FROM expenses WHERE id = ?;"
        with self._get_connection(conn) as c:
            cursor = c.execute(sql, (expense_id,))
            return cursor.rowcount > 0

    # ========================================================================
    # SUPPLIERS REPOSITORY
    # ========================================================================
    def save_supplier(self, s: Supplier, conn: Optional[sqlite3.Connection] = None) -> None:
        sql = """
        INSERT INTO suppliers (id, name, contact_person, phone, email, address, gstin, payment_terms)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            contact_person = excluded.contact_person,
            phone = excluded.phone,
            email = excluded.email,
            address = excluded.address,
            gstin = excluded.gstin,
            payment_terms = excluded.payment_terms;
        """
        with self._get_connection(conn) as c:
            c.execute(sql, (s.id, s.name, s.contact_person, s.phone, s.email, s.address, s.gstin, s.payment_terms))

    def list_suppliers(self) -> List[Supplier]:
        sql = "SELECT * FROM suppliers ORDER BY name ASC;"
        with self.db.connection() as conn:
            rows = conn.execute(sql).fetchall()
            return [
                Supplier(
                    id=r["id"],
                    name=r["name"],
                    contact_person=r["contact_person"] or "",
                    phone=r["phone"] or "",
                    email=r["email"] or "",
                    address=r["address"] or "",
                    gstin=r["gstin"] or "",
                    payment_terms=r["payment_terms"] or "Net-30"
                )
                for r in rows
            ]

    # ========================================================================
    # FINANCIAL REPORTING & AUDIT RECONCILIATION AGGREGATES
    # ========================================================================
    def get_financial_summary_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        branch_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes unified database queries to calculate exact financial metrics across
        completed orders, returns, and expenses sharing consistent SQLite records.
        Supports single branch filtering or consolidated enterprise-wide multi-branch view.
        """
        start_str = start_date.isoformat()
        end_str = end_date.isoformat()
        s_date_str = start_date.strftime("%Y-%m-%d")
        e_date_str = end_date.strftime("%Y-%m-%d")

        with self.db.connection() as conn:
            # 1. Orders
            order_sql = """
                SELECT 
                    COUNT(*) as completed_orders,
                    COALESCE(SUM(CAST(grand_total AS REAL)), 0.0) as gross_revenue,
                    COALESCE(SUM(CAST(total_cogs AS REAL)), 0.0) as gross_cogs,
                    COALESCE(SUM(CAST(total_savings AS REAL)), 0.0) as total_savings,
                    COALESCE(SUM(CAST(total_tax AS REAL)), 0.0) as total_tax,
                    COUNT(DISTINCT customer_phone) as unique_customers
                FROM orders 
                WHERE status != 'CANCELLED' AND created_at >= ? AND created_at <= ?
            """
            order_params: List[Any] = [start_str, end_str]
            if branch_id and branch_id != "ALL":
                order_sql += " AND branch_id = ?"
                order_params.append(branch_id.strip())
            order_row = conn.execute(order_sql + ";", tuple(order_params)).fetchone()

            # 2. Refunds
            refund_sql = """
                SELECT 
                    COUNT(*) as return_count,
                    COALESCE(SUM(CAST(refund_amount AS REAL)), 0.0) as total_refunds
                FROM returns
                WHERE created_at >= ? AND created_at <= ?
            """
            refund_params: List[Any] = [start_str, end_str]
            if branch_id and branch_id != "ALL":
                refund_sql += " AND branch_id = ?"
                refund_params.append(branch_id.strip())
            refund_row = conn.execute(refund_sql + ";", tuple(refund_params)).fetchone()

            # 3. Restocked Returned Goods Procurement Cost (Returned COGS)
            ret_cogs_sql = """
                SELECT 
                    COALESCE(SUM(CAST(p.cost_price AS REAL) * ri.quantity), 0.0) as returned_cogs
                FROM return_items ri
                JOIN returns r ON ri.return_id = r.id
                JOIN products p ON ri.barcode = p.barcode
                WHERE r.created_at >= ? AND r.created_at <= ?
            """
            ret_cogs_params: List[Any] = [start_str, end_str]
            if branch_id and branch_id != "ALL":
                ret_cogs_sql += " AND r.branch_id = ?"
                ret_cogs_params.append(branch_id.strip())
            ret_cogs_row = conn.execute(ret_cogs_sql + ";", tuple(ret_cogs_params)).fetchone()

            # 4. Operational Expenses
            exp_sql = """
                SELECT 
                    COALESCE(SUM(CAST(amount AS REAL)), 0.0) as total_expenses
                FROM expenses
                WHERE expense_date >= ? AND expense_date <= ?
            """
            exp_params: List[Any] = [s_date_str, e_date_str]
            if branch_id and branch_id != "ALL":
                exp_sql += " AND (branch_id = ? OR branch_id = 'ALL' OR branch_id IS NULL)"
                exp_params.append(branch_id.strip())
            exp_row = conn.execute(exp_sql + ";", tuple(exp_params)).fetchone()

            # 5. Multi-Branch Store Performance Comparison (for consolidated or chain analysis)
            branch_breakdown = []
            b_rows = conn.execute("""
                SELECT 
                    o.branch_id,
                    COALESCE(b.name, o.branch_name, o.branch_id) as branch_name,
                    COUNT(*) as orders_count,
                    COALESCE(SUM(CAST(o.grand_total AS REAL)), 0.0) as revenue
                FROM orders o
                LEFT JOIN branches b ON o.branch_id = b.id
                WHERE o.status != 'CANCELLED' AND o.created_at >= ? AND o.created_at <= ?
                GROUP BY o.branch_id
                ORDER BY revenue DESC;
            """, (start_str, end_str)).fetchall()
            for br in b_rows:
                branch_breakdown.append({
                    "branch_id": br["branch_id"],
                    "branch_name": br["branch_name"],
                    "orders_count": br["orders_count"],
                    "revenue": float(round_curr(Decimal(str(br["revenue"] or 0.0))))
                })

            gross_rev = Decimal(str(order_row["gross_revenue"] or 0.0))
            refunds = Decimal(str(refund_row["total_refunds"] or 0.0))
            net_rev = max(Decimal("0.00"), gross_rev - refunds)

            gross_cogs = Decimal(str(order_row["gross_cogs"] or 0.0))
            ret_cogs = Decimal(str(ret_cogs_row["returned_cogs"] or 0.0))
            net_cogs = max(Decimal("0.00"), gross_cogs - ret_cogs)

            expenses = Decimal(str(exp_row["total_expenses"] or 0.0))
            gross_profit = net_rev - net_cogs
            net_operating_profit = gross_profit - expenses
            margin_pct = (net_operating_profit / net_rev * Decimal("100.0")) if net_rev > Decimal("0.00") else Decimal("0.00")

            return {
                "branch_id": branch_id or "ALL",
                "completed_orders": order_row["completed_orders"],
                "unique_customers": order_row["unique_customers"],
                "gross_revenue": float(round_curr(gross_rev)),
                "refunds_issued": float(round_curr(refunds)),
                "net_revenue": float(round_curr(net_rev)),
                "gross_cogs": float(round_curr(gross_cogs)),
                "net_cogs": float(round_curr(net_cogs)),
                "gross_profit": float(round_curr(gross_profit)),
                "operating_expenses": float(round_curr(expenses)),
                "net_operating_profit": float(round_curr(net_operating_profit)),
                "net_profit_margin_percent": float(round(margin_pct, 1)),
                "total_savings": float(round_curr(Decimal(str(order_row["total_savings"] or 0.0)))),
                "total_tax": float(round_curr(Decimal(str(order_row["total_tax"] or 0.0)))),
                "branch_breakdown": branch_breakdown
            }

    # ========================================================================
    # SECURE CREDENTIAL HELPERS
    # ========================================================================
    def upgrade_user_pin_hash(self, user_id: str, new_hashed_pin: str) -> None:
        """
        Persist an upgraded (bcrypt/PBKDF2 hashed) credential for a user whose
        legacy plaintext PIN successfully authenticated. Never call with raw
        secrets -- hash them first via backend.security.normalize_for_storage.
        """
        sql = "UPDATE users SET pin = ? WHERE id = ?;"
        with self.db.connection() as conn:
            conn.execute(sql, (new_hashed_pin, user_id))
