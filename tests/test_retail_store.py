"""
Comprehensive Unit & Integration Tests for Retail Supermarket System
Validates POS checkout, Trie search, Customer Footfall tracking,
Returns & Refunds, Cash Shifts (Z-Report), Inventory Adjustments & Valuation,
Expenses, and P&L calculations.
"""

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

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
    User,
    UserRole,
    round_curr,
)
from backend.models.exceptions import (
    InsufficientStockError,
    InvalidPaymentTenderError,
    OrderStateError,
    UnauthorizedManagerError,
    ProductNotFoundError,
    POSTransactionError,
)
from backend.storage.db import DatabaseManager
from backend.storage.repository import RetailRepository
from backend.services.search_engine import ProductSearchEngine
from backend.services.cache_service import LRUCacheService
from backend.services.inventory_pq import InventoryPriorityQueue
from backend.services.customer_service import CustomerService
from backend.services.pos_service import POSService
from backend.services.expense_service import ExpenseService
from backend.services.analytics_service import AnalyticsService
from backend.services.returns_service import ReturnsService
from backend.services.register_service import RegisterShiftService
from backend.services.inventory_service import InventoryService


class TestRetailStoreEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_retail.db"
        self.db_manager = DatabaseManager(self.db_path)
        self.repo = RetailRepository(self.db_manager)

        self.search_engine = ProductSearchEngine()
        self.inventory_pq = InventoryPriorityQueue()
        self.customer_service = CustomerService(self.repo)
        self.pos_service = POSService(self.repo, self.search_engine, self.inventory_pq, self.customer_service)
        self.expense_service = ExpenseService(self.repo)
        self.analytics_service = AnalyticsService(self.repo, self.expense_service, self.inventory_pq)
        self.returns_service = ReturnsService(self.repo, self.inventory_pq, engine=self.pos_service.engine)
        self.register_service = RegisterShiftService(self.repo)
        self.inventory_service = InventoryService(self.repo, self.inventory_pq, self.search_engine)

        # Seed test manager user with PIN 2222
        self.manager = User(
            id="MGR-01",
            username="vikram",
            full_name="Vikram Malhotra",
            role=UserRole.STORE_MANAGER,
            pin="2222"
        )
        self.repo.save_user(self.manager)

        # Seed sample product
        self.prod1 = Product(
            barcode="8901030889211",
            sku="SKU-GRO-001",
            name="Aashirvaad Chakki Atta (5 kg)",
            category="Groceries",
            brand="Aashirvaad",
            unit="pack",
            cost_price=Decimal("210.00"),
            selling_price=Decimal("245.00"),
            mrp=Decimal("275.00"),
            stock_quantity=50,
            reorder_level=10,
            tax_rate_percent=Decimal("0.00")
        )
        self.repo.save_product(self.prod1)
        self.search_engine.index_product(self.prod1)
        self.inventory_pq.push(self.prod1)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_trie_search_engine(self):
        # Search by barcode prefix
        matches_bc = self.pos_service.search_products("890103")
        self.assertEqual(len(matches_bc), 1)
        self.assertEqual(matches_bc[0]["barcode"], "8901030889211")

        # Search by product name keyword
        matches_name = self.pos_service.search_products("Atta")
        self.assertEqual(len(matches_name), 1)
        self.assertEqual(matches_name[0]["name"], "Aashirvaad Chakki Atta (5 kg)")

    def test_customer_footfall_and_tier_promotion(self):
        phone = "9810012345"
        # 1st Visit
        c1 = self.customer_service.get_or_create_customer(phone, name="Amit Kumar")
        self.assertEqual(c1.visit_count, 1)
        self.assertEqual(c1.tier, CustomerTier.BRONZE)

        # Simulate completed visits
        # After 4 more visits (total 5), tier should become SILVER
        for _ in range(4):
            c1 = self.customer_service.record_completed_visit(phone, Decimal("500.00"))
        self.assertEqual(c1.visit_count, 5)
        self.assertEqual(c1.tier, CustomerTier.SILVER)

        # After reaching 15 visits, tier should become GOLD
        for _ in range(10):
            c1 = self.customer_service.record_completed_visit(phone, Decimal("500.00"))
        self.assertEqual(c1.visit_count, 15)
        self.assertEqual(c1.tier, CustomerTier.GOLD)

    def test_pos_cart_preview_and_checkout(self):
        phone = "9876543210"
        raw_items = [{"barcode": self.prod1.barcode, "quantity": 2}]

        # Preview calculation: 2 * 245 = 490.00, MRP 2 * 275 = 550.00
        preview = self.pos_service.calculate_cart_preview(raw_items, customer_phone=phone)
        self.assertEqual(preview["subtotal"], 490.00)
        self.assertEqual(preview["total_mrp"], 550.00)
        self.assertEqual(preview["total_savings"], 60.00)
        self.assertEqual(preview["grand_total"], 490.00)

        # Checkout with Cash: customer pays ₹500, change returned must be ₹10.00
        checkout_res = self.pos_service.checkout(
            raw_items=raw_items,
            payment_method="CASH",
            tendered_amount=500.0,
            customer_phone=phone,
            customer_name="Pooja Sharma"
        )
        self.assertTrue(checkout_res["success"])
        self.assertEqual(checkout_res["grand_total"], 490.00)
        self.assertEqual(checkout_res["tendered_amount"], 500.00)
        self.assertEqual(checkout_res["change_amount"], 10.00)

        # Check stock decremented from 50 to 48
        updated_prod = self.repo.get_product_by_barcode(self.prod1.barcode)
        self.assertEqual(updated_prod.stock_quantity, 48)

    def test_returns_and_refunds(self):
        phone = "9988776655"
        raw_items = [{"barcode": self.prod1.barcode, "quantity": 3}]

        # Complete sale of 3 units
        checkout_res = self.pos_service.checkout(
            raw_items=raw_items,
            payment_method="CASH",
            tendered_amount=800.0,
            customer_phone=phone,
            customer_name="Vikram Test"
        )
        bill_num = checkout_res["bill_number"]

        # Stock should be 50 - 3 = 47
        prod = self.repo.get_product_by_barcode(self.prod1.barcode)
        self.assertEqual(prod.stock_quantity, 47)

        # Return 1 unit with valid Manager PIN 2222
        return_res = self.returns_service.process_return(
            bill_number=bill_num,
            items_to_return=[{"barcode": self.prod1.barcode, "quantity": 1}],
            manager_pin="2222",
            reason="Damaged Seal"
        )
        self.assertTrue(return_res["success"])
        self.assertEqual(return_res["refund_amount"], 245.00)

        # Stock should be restored by 1 unit: 47 + 1 = 48
        prod = self.repo.get_product_by_barcode(self.prod1.barcode)
        self.assertEqual(prod.stock_quantity, 48)

        # Test invalid PIN rejection
        with self.assertRaises(ValueError):
            self.returns_service.process_return(
                bill_number=bill_num,
                items_to_return=[{"barcode": self.prod1.barcode, "quantity": 1}],
                manager_pin="0000"
            )

    def test_order_void_cancellation(self):
        raw_items = [{"barcode": self.prod1.barcode, "quantity": 5}]
        checkout_res = self.pos_service.checkout(
            raw_items=raw_items,
            payment_method="CASH",
            tendered_amount=1500.0
        )
        bill_num = checkout_res["bill_number"]

        # Stock should be 50 - 5 = 45
        self.assertEqual(self.repo.get_product_by_barcode(self.prod1.barcode).stock_quantity, 45)

        # Void order
        void_res = self.pos_service.void_order(bill_num, manager_pin="2222", reason="Cashier Error")
        self.assertTrue(void_res["success"])

        # Stock must be fully restored: 45 + 5 = 50
        self.assertEqual(self.repo.get_product_by_barcode(self.prod1.barcode).stock_quantity, 50)
        order = self.repo.get_order_by_bill_number(bill_num)
        self.assertEqual(order.status, OrderStatus.CANCELLED)

    def test_cash_register_shift_and_z_report(self):
        cashier_id = "CASHIER-TEST"
        # Start shift with 1000 float
        shift = self.register_service.start_shift(cashier_id=cashier_id, opening_float=1000.0)
        self.assertEqual(shift.opening_float, Decimal("1000.00"))

        # Check live shift status
        status = self.register_service.get_current_shift_status(cashier_id)
        self.assertEqual(status["opening_float"], 1000.00)
        self.assertEqual(status["expected_drawer_cash"], 1000.00)

        # Record a safe cash drop of 400
        drop_res = self.register_service.record_cash_drop(cashier_id, 400.0, "Safe Drop")
        self.assertTrue(drop_res["success"])
        self.assertEqual(drop_res["new_expected_drawer"], 600.00)

        # Close shift with physical count of 600 (exact match)
        z_report = self.register_service.close_shift_z_report(cashier_id, actual_counted_cash=600.0)
        self.assertEqual(z_report["drawer_variance"], 0.0)
        self.assertEqual(z_report["variance_status"], "PERFECT_MATCH")

    def test_inventory_adjustments_and_valuation(self):
        # Initial stock: 50
        val_before = self.inventory_service.get_inventory_valuation()
        self.assertEqual(val_before["total_physical_units"], 50)
        self.assertEqual(val_before["total_cost_valuation"], 50 * 210.00)
        self.assertEqual(val_before["total_retail_valuation"], 50 * 245.00)

        # Adjust stock to 60 (restock)
        adj_res = self.inventory_service.adjust_stock(
            barcode=self.prod1.barcode,
            new_quantity=60,
            reason_type="RESTOCK",
            notes="Morning shipment"
        )
        self.assertTrue(adj_res["success"])
        self.assertEqual(adj_res["new_stock"], 60)

        val_after = self.inventory_service.get_inventory_valuation()
        self.assertEqual(val_after["total_physical_units"], 60)

    def test_bulk_csv_export_and_import(self):
        csv_text = self.inventory_service.export_catalog_to_csv()
        self.assertIn("Aashirvaad Chakki Atta", csv_text)
        self.assertIn("8901030889211", csv_text)

        # Import a new SKU via CSV
        import_sample = (
            "Barcode,SKU,Name,Category,Brand,Unit,CostPrice,SellingPrice,MRP,StockQuantity,ReorderLevel,TaxRatePercent\n"
            "890999900001,SKU-TEST-01,Test Biscuit,Snacks,Parle,pcs,10.00,15.00,20.00,100,20,5.0\n"
        )
        res = self.inventory_service.import_catalog_from_csv(import_sample)
        self.assertTrue(res["success"])
        self.assertEqual(res["imported_products"], 1)

        # Verify imported product is in catalog and search engine
        imported = self.repo.get_product_by_barcode("890999900001")
        self.assertIsNotNone(imported)
        self.assertEqual(imported.name, "Test Biscuit")

    def test_expenses_weekly_monthly_yearly(self):
        today = date.today()
        # Add expenses
        self.expense_service.add_expense(
            category="RENT",
            amount=50000.0,
            description="Store Rent",
            expense_date=today.isoformat()
        )
        self.expense_service.add_expense(
            category="PACKAGING_BAGS",
            amount=2000.0,
            description="Carry Bags",
            expense_date=today.isoformat()
        )

        summary = self.expense_service.get_periodic_expense_summary(today)
        self.assertEqual(summary["totals"]["weekly_expenses"], 52000.00)
        self.assertEqual(summary["totals"]["monthly_expenses"], 52000.00)
        self.assertEqual(summary["totals"]["yearly_expenses"], 52000.00)

    def test_atomic_stock_rollback_on_insufficient_stock(self):
        # Seed second product with stock of 2
        prod2 = Product(
            barcode="8901234567890",
            sku="SKU-SNK-002",
            name="Haldiram Bhujia (400g)",
            category="Snacks",
            brand="Haldiram",
            unit="pack",
            cost_price=Decimal("80.00"),
            selling_price=Decimal("110.00"),
            mrp=Decimal("120.00"),
            stock_quantity=2,
            reorder_level=5,
            tax_rate_percent=Decimal("5.00")
        )
        self.repo.save_product(prod2)
        self.search_engine.index_product(prod2)

        # Attempt to checkout 10 units of prod1 (has 50) and 5 units of prod2 (only has 2)
        cart = [
            {"barcode": self.prod1.barcode, "quantity": 10},
            {"barcode": prod2.barcode, "quantity": 5}
        ]

        with self.assertRaises(InsufficientStockError) as ctx:
            self.pos_service.checkout(
                raw_items=cart,
                payment_method="CASH",
                tendered_amount=4000.0
            )

        self.assertIn("Insufficient stock", str(ctx.exception))
        self.assertEqual(ctx.exception.available, 2)
        self.assertEqual(ctx.exception.requested, 5)

        # Verify ATOMICITY: prod1 must NOT have decremented at all
        fresh_prod1 = self.repo.get_product_by_barcode(self.prod1.barcode)
        self.assertEqual(fresh_prod1.stock_quantity, 50)

        fresh_prod2 = self.repo.get_product_by_barcode(prod2.barcode)
        self.assertEqual(fresh_prod2.stock_quantity, 2)

        # Verify no orders or movements were committed
        orders = self.repo.list_orders()
        self.assertEqual(len(orders), 0)

    def test_atomic_tender_mismatch_rollback(self):
        cart = [{"barcode": self.prod1.barcode, "quantity": 1}]
        # prod1 price is 245.00; tender only 200.00
        with self.assertRaises(InvalidPaymentTenderError) as ctx:
            self.pos_service.checkout(
                raw_items=cart,
                payment_method="CASH",
                tendered_amount=200.0
            )

        self.assertIn("Payment tender mismatch", str(ctx.exception))
        self.assertEqual(ctx.exception.tendered, 200.0)
        self.assertEqual(ctx.exception.payable, 245.0)

        # Stock must remain unchanged
        fresh_prod1 = self.repo.get_product_by_barcode(self.prod1.barcode)
        self.assertEqual(fresh_prod1.stock_quantity, 50)
        self.assertEqual(len(self.repo.list_orders()), 0)

    def test_shared_records_consistency_across_sales_returns_and_voids(self):
        cashier_id = "CASHIER-CONSISTENCY"
        shift = self.register_service.start_shift(cashier_id=cashier_id, opening_float=500.0)
        self.assertEqual(shift.opening_float, Decimal("500.00"))

        cust = Customer(
            phone="9876543210",
            name="Pooja Patel",
            visit_count=0,
            total_spent=Decimal("0.00"),
            loyalty_points=0,
            tier=CustomerTier.BRONZE
        )
        self.repo.save_customer(cust)

        # 1. Execute Sale: 2 units of prod1 (2 * 245.00 = 490.00), paid CASH with 500.00 tendered
        cart = [{"barcode": self.prod1.barcode, "quantity": 2}]
        sale_res = self.pos_service.checkout(
            raw_items=cart,
            customer_phone="9876543210",
            cashier_id=cashier_id,
            payment_method="CASH",
            tendered_amount=500.0
        )
        bill_num = sale_res["bill_number"]
        self.assertEqual(sale_res["grand_total"], 490.00)
        self.assertEqual(sale_res["change_due"], 10.00)

        # Check DB State after Sale:
        # Stock: 50 - 2 = 48
        self.assertEqual(self.repo.get_product_by_barcode(self.prod1.barcode).stock_quantity, 48)

        # Customer: 1 visit, 490 spend, 4 points
        refreshed_cust = self.customer_service.get_customer_by_phone("9876543210")
        self.assertEqual(refreshed_cust.visit_count, 1)
        self.assertEqual(refreshed_cust.total_spent, Decimal("490.00"))
        self.assertEqual(refreshed_cust.loyalty_points, 4)

        # Shift: Expected drawer = 500 (float) + 490 (cash sales) = 990
        shift_status = self.register_service.get_current_shift_status(cashier_id)
        self.assertEqual(shift_status["total_cash_sales"], 490.00)
        self.assertEqual(shift_status["expected_drawer_cash"], 990.00)

        # Analytics: Gross Revenue = 490, Net Revenue = 490, COGS = 420 (2 * 210), Gross Profit = 70
        fin_today = self.analytics_service.get_financial_summary(period="today")
        self.assertEqual(fin_today["gross_revenue"], 490.00)
        self.assertEqual(fin_today["refunds"], 0.00)
        self.assertEqual(fin_today["net_revenue"], 490.00)
        self.assertEqual(fin_today["net_cogs"], 420.00)
        self.assertEqual(fin_today["gross_profit"], 70.00)

        # 2. Process Partial Return: 1 unit of prod1 returned
        return_res = self.returns_service.process_return(
            bill_number=bill_num,
            items_to_return=[{"barcode": self.prod1.barcode, "quantity": 1}],
            manager_pin="2222",
            cashier_id=cashier_id,
            reason="Wrong size chosen"
        )
        self.assertTrue(return_res["success"])
        self.assertEqual(return_res["refund_amount"], 245.00)

        # Check DB State after Return:
        # Stock restored: 48 + 1 = 49
        self.assertEqual(self.repo.get_product_by_barcode(self.prod1.barcode).stock_quantity, 49)

        # Customer rollback: spend 490 - 245 = 245, points 4 - 2 = 2
        refreshed_cust2 = self.customer_service.get_customer_by_phone("9876543210")
        self.assertEqual(refreshed_cust2.total_spent, Decimal("245.00"))
        self.assertEqual(refreshed_cust2.loyalty_points, 2)

        # Shift: Refunds recorded = 245, Expected drawer = 990 - 245 = 745
        shift_status2 = self.register_service.get_current_shift_status(cashier_id)
        self.assertEqual(shift_status2["total_refunds"], 245.00)
        self.assertEqual(shift_status2["expected_drawer_cash"], 745.00)

        # Analytics: Gross = 490, Refunds = 245, Net = 245, Net COGS = 210, Gross Profit = 35
        fin_today2 = self.analytics_service.get_financial_summary(period="today")
        self.assertEqual(fin_today2["gross_revenue"], 490.00)
        self.assertEqual(fin_today2["refunds"], 245.00)
        self.assertEqual(fin_today2["net_revenue"], 245.00)
        self.assertEqual(fin_today2["net_cogs"], 210.00)
        self.assertEqual(fin_today2["gross_profit"], 35.00)

        # 3. Second Sale & Void Cancellation:
        sale2_res = self.pos_service.checkout(
            raw_items=[{"barcode": self.prod1.barcode, "quantity": 1}],
            cashier_id=cashier_id,
            payment_method="UPI",
            tendered_amount=245.0
        )
        bill2_num = sale2_res["bill_number"]
        # Stock after sale 2: 49 - 1 = 48
        self.assertEqual(self.repo.get_product_by_barcode(self.prod1.barcode).stock_quantity, 48)

        # Void Bill 2 with Manager PIN
        void_res = self.pos_service.void_order(bill2_num, manager_pin="2222", reason="Customer Left")
        self.assertTrue(void_res["success"])

        # Stock restored after void: 48 + 1 = 49
        self.assertEqual(self.repo.get_product_by_barcode(self.prod1.barcode).stock_quantity, 49)

        # Analytics: Cancelled bill is completely excluded; figures remain exactly identical to post-return state
        fin_today3 = self.analytics_service.get_financial_summary(period="today")
        self.assertEqual(fin_today3["gross_revenue"], 490.00)
        self.assertEqual(fin_today3["net_revenue"], 245.00)

    def test_invalid_state_transitions(self):
        # Checkout a simple order
        sale = self.pos_service.checkout(
            raw_items=[{"barcode": self.prod1.barcode, "quantity": 1}],
            payment_method="CASH",
            tendered_amount=245.0
        )
        bill_num = sale["bill_number"]

        # Void the order
        self.pos_service.void_order(bill_num, manager_pin="2222")

        # Try to void again -> OrderStateError
        with self.assertRaises(OrderStateError):
            self.pos_service.void_order(bill_num, manager_pin="2222")

        # Try to process return on cancelled order -> OrderStateError
        with self.assertRaises(OrderStateError):
            self.returns_service.process_return(
                bill_number=bill_num,
                items_to_return=[{"barcode": self.prod1.barcode, "quantity": 1}],
                manager_pin="2222"
            )

        # Try to checkout with empty cart -> POSTransactionError
        with self.assertRaises(POSTransactionError):
            self.pos_service.checkout(raw_items=[])

    def test_multi_branch_architecture_and_transfers(self):
        # 1. Register branches
        from datetime import datetime
        from backend.models.domain import StoreBranch, StockMovementType
        branch_del = StoreBranch(
            id="BR-DEL-01", code="DEL-01", name="Indirapuram Flagship",
            address="Plot 4, Indirapuram", city="Ghaziabad", state="UP", pincode="201014",
            is_headquarters=True, is_active=True, created_at=datetime.now()
        )
        branch_mum = StoreBranch(
            id="BR-MUM-02", code="MUM-02", name="Bandra West Store",
            address="Linking Road", city="Mumbai", state="Maharashtra", pincode="400050",
            is_headquarters=False, is_active=True, created_at=datetime.now()
        )
        self.repo.save_branch(branch_del)
        self.repo.save_branch(branch_mum)

        # 2. Allocate distinct stock levels to branches
        self.repo.set_branch_stock("BR-DEL-01", self.prod1.barcode, quantity=30)
        self.repo.set_branch_stock("BR-MUM-02", self.prod1.barcode, quantity=15)

        del_stock = self.repo.get_branch_stock("BR-DEL-01", self.prod1.barcode)
        mum_stock = self.repo.get_branch_stock("BR-MUM-02", self.prod1.barcode)
        self.assertEqual(del_stock.stock_quantity, 30)
        self.assertEqual(mum_stock.stock_quantity, 15)

        # 3. Checkout at Mumbai branch: 5 units
        sale_mum = self.pos_service.checkout(
            raw_items=[{"barcode": self.prod1.barcode, "quantity": 5}],
            branch_id="BR-MUM-02",
            payment_method="CASH",
            tendered_amount=2000.0
        )
        self.assertTrue(sale_mum["success"])
        self.assertEqual(sale_mum["branch_id"], "BR-MUM-02")

        # Mumbai branch stock should be 15 - 5 = 10, Delhi stock unchanged at 30
        mum_stock_after = self.repo.get_branch_stock("BR-MUM-02", self.prod1.barcode)
        del_stock_after = self.repo.get_branch_stock("BR-DEL-01", self.prod1.barcode)
        self.assertEqual(mum_stock_after.stock_quantity, 10)
        self.assertEqual(del_stock_after.stock_quantity, 30)

        # 4. Inter-branch atomic transfer: Transfer 8 units from Delhi to Mumbai
        transfer_res = self.inventory_service.transfer_stock(
            from_branch_id="BR-DEL-01",
            to_branch_id="BR-MUM-02",
            barcode=self.prod1.barcode,
            quantity=8,
            reason="Replenish Mumbai stock from Flagship hub",
            user_id="MGR-01"
        )
        self.assertTrue(transfer_res["success"])
        self.assertEqual(transfer_res["from_branch_new_stock"], 22)  # 30 - 8
        self.assertEqual(transfer_res["to_branch_new_stock"], 18)    # 10 + 8

        # Verify audit movements recorded with TRANSFER_OUT and TRANSFER_IN
        movements = self.repo.list_stock_movements(limit=10)
        out_mov = next((m for m in movements if m.movement_type == StockMovementType.TRANSFER_OUT), None)
        in_mov = next((m for m in movements if m.movement_type == StockMovementType.TRANSFER_IN), None)
        self.assertIsNotNone(out_mov)
        self.assertIsNotNone(in_mov)
        self.assertEqual(out_mov.quantity_change, -8)
        self.assertEqual(in_mov.quantity_change, 8)

        # 5. P&L Financial Isolation:
        # Mumbai P&L reflects Mumbai sale revenue
        fin_mum = self.analytics_service.get_financial_summary(period="today", branch_id="BR-MUM-02")
        self.assertEqual(fin_mum["completed_orders"], 1)
        self.assertGreater(fin_mum["net_revenue"], 0.0)

        # Delhi P&L reflects 0 orders today
        fin_del = self.analytics_service.get_financial_summary(period="today", branch_id="BR-DEL-01")
        self.assertEqual(fin_del["completed_orders"], 0)
        self.assertEqual(fin_del["net_revenue"], 0.0)

        # Consolidated Chain Analytics reflects all branches with branch_breakdown
        fin_all = self.analytics_service.get_financial_summary(period="today", branch_id="ALL")
        self.assertEqual(fin_all["completed_orders"], 1)
        self.assertIn("branch_breakdown", fin_all)

    def test_smart_customer_recognition_and_membership_qr(self):
        # 1. Register a customer with membership code
        cust = Customer(
            phone="9876543210",
            name="Rahul Sharma",
            membership_code="MEM-9876543210",
            visit_count=4,
            tier=CustomerTier.GOLD,
            loyalty_points=120,
            total_spent=Decimal("4500.00")
        )
        self.repo.save_customer(cust)

        # 2. Recognize by 10-digit phone
        rec_phone = self.customer_service.smart_recognize_customer("9876543210")
        self.assertTrue(rec_phone["found"])
        self.assertEqual(rec_phone["name"], "Rahul Sharma")
        self.assertEqual(rec_phone["membership_code"], "MEM-9876543210")
        self.assertEqual(rec_phone["tier"], "GOLD")
        self.assertTrue(rec_phone["is_returning"])
        self.assertEqual(rec_phone["loyalty_points"], 120)

        # 3. Recognize by phone with country code prefix +91
        rec_prefix = self.customer_service.smart_recognize_customer("+91-9876543210")
        self.assertTrue(rec_prefix["found"])
        self.assertEqual(rec_prefix["phone"], "9876543210")

        # 4. Recognize by Membership Code directly
        rec_code = self.customer_service.smart_recognize_customer("MEM-9876543210")
        self.assertTrue(rec_code["found"])
        self.assertEqual(rec_code["name"], "Rahul Sharma")

        # 5. Recognize by Membership QR payload format (e.g. 2D barcode scan)
        qr_payload = "RETAIL:MEM:MEM-9876543210:9876543210"
        rec_qr = self.customer_service.smart_recognize_customer(qr_payload)
        self.assertTrue(rec_qr["found"])
        self.assertEqual(rec_qr["phone"], "9876543210")
        self.assertIn("digital_card", rec_qr)

        # 6. Unregistered customer returns found=False
        rec_unknown = self.customer_service.smart_recognize_customer("9999988888")
        self.assertFalse(rec_unknown["found"])

    def test_customer_purchase_insights_and_habits(self):
        # 1. Execute two checkouts for customer
        self.pos_service.checkout(
            raw_items=[{"barcode": self.prod1.barcode, "quantity": 2}],
            customer_phone="9876543210",
            customer_name="Rahul Sharma",
            payment_method="CASH",
            tendered_amount=1000.0
        )
        self.pos_service.checkout(
            raw_items=[{"barcode": self.prod1.barcode, "quantity": 1}],
            customer_phone="9876543210",
            payment_method="UPI_QR",
            tendered_amount=500.0
        )

        # 2. Query shopping habits and insights
        insights = self.customer_service.get_customer_purchase_insights("9876543210")
        self.assertEqual(insights["phone"], "9876543210")
        self.assertGreaterEqual(insights["total_orders"], 2)
        self.assertGreater(insights["total_spent"], 0.0)
        self.assertTrue(any(c["category"] == "Groceries" for c in insights["category_preferences"]))
        self.assertTrue(any(p["barcode"] == self.prod1.barcode for p in insights["top_purchased_products"]))
        self.assertGreaterEqual(len(insights["recent_orders"]), 2)

    def test_business_intelligence_analytics(self):
        # Perform sales to generate real transaction telemetry
        self.pos_service.checkout(
            raw_items=[{"barcode": self.prod1.barcode, "quantity": 3}],
            customer_phone="9876543210",
            payment_method="CASH",
            tendered_amount=1000.0
        )

        bi = self.analytics_service.get_comprehensive_business_intelligence()

        # 1. Best-Selling Products
        self.assertIn("best_selling_products", bi)
        self.assertIsInstance(bi["best_selling_products"], list)
        if len(bi["best_selling_products"]) > 0:
            top = bi["best_selling_products"][0]
            self.assertEqual(top["rank"], 1)
            self.assertIn("gross_revenue", top)
            self.assertIn("profit_margin_percent", top)

        # 2. Slow-Moving Stock
        self.assertIn("slow_moving_stock", bi)
        sm = bi["slow_moving_stock"]
        self.assertIn("total_locked_capital", sm)
        self.assertIn("items", sm)

        # 3. Customer Retention & Churn
        self.assertIn("customer_retention", bi)
        cr = bi["customer_retention"]
        self.assertIn("repeat_customer_rate_percent", cr)
        self.assertIn("churn_status", cr)
        self.assertIn("active_recent", cr["churn_status"])
        self.assertIn("tier_distribution", cr)

        # 4. Seasonal Demand Patterns
        self.assertIn("seasonal_demand", bi)
        sd = bi["seasonal_demand"]
        self.assertEqual(len(sd["day_of_week"]), 7)
        self.assertIn("hourly_peaks", sd)
        self.assertIn("busiest_day", sd)
        self.assertIn("peak_hour", sd)

        # 5. Restock Priority Queue
        self.assertIn("restock_priority", bi)
        rp = bi["restock_priority"]
        self.assertIn("estimated_total_restock_cost", rp)
        self.assertIn("items", rp)


if __name__ == "__main__":
    unittest.main()
