"""
Enterprise Point of Sale (POS) Transaction Engine
Enforces strict ACID transaction boundaries across:
- Pre-flight stock availability & tender validation
- Atomic stock deductions and inventory movements
- Order and line item persistence
- Split and single payment records
- Customer footfall tracking and tier progression
- Cash register shift balancing
- Customer returns, refunds, and bill voiding
"""

from datetime import datetime, date
from decimal import Decimal
import time
from typing import List, Dict, Any, Optional
import uuid

from backend.config import STORE_PROFILE
from backend.models.domain import (
    Customer,
    CustomerTier,
    Product,
    OrderItem,
    Order,
    OrderStatus,
    PaymentMethod,
    PaymentRecord,
    StockMovement,
    StockMovementType,
    ReturnRecord,
    UserRole,
    round_curr,
)
from backend.models.exceptions import (
    POSTransactionError,
    InsufficientStockError,
    ProductNotFoundError,
    InvalidPaymentTenderError,
    UnauthorizedManagerError,
    OrderStateError,
)
from backend.services.search_engine import ProductSearchEngine
from backend.services.pricing_engine import LoyaltyPricingEngine
from backend.services.inventory_pq import InventoryPriorityQueue
from backend.services.cache_service import LRUCacheService
from backend.storage.repository import RetailRepository

# Input bounds: hard limits that stop abusive payloads (mass-tampering / DoS).
MAX_CHECKOUT_QTY_PER_ITEM = 1000
MAX_CART_LINE_ITEMS = 200


class POSTransactionEngine:
    """
    Central Retail POS Transaction Engine.
    Ensures that billing, payment, stock deduction, returns, and financial audits
    execute atomically and maintain consistent database records at all times.
    """

    def __init__(
        self,
        repo: RetailRepository,
        search_engine: ProductSearchEngine,
        inventory_pq: InventoryPriorityQueue,
        cache_service: Optional[LRUCacheService] = None,
    ):
        self.repo = repo
        self.search_engine = search_engine
        self.inventory_pq = inventory_pq
        self.cache_service = cache_service or LRUCacheService(capacity=500)
        # Action stack for cashier undo / reversal workflows (DSA: Stack)
        self._action_stack: List[Dict[str, Any]] = []

    # ========================================================================
    # 1. ATOMIC CHECKOUT & BILLING ENGINE
    # ========================================================================
    def execute_sale(
        self,
        raw_items: List[Dict[str, Any]],
        payment_method: str = "CASH",
        tendered_amount: float = 0.0,
        cashier_id: str = "CASHIER-01",
        cashier_name: str = "Rajesh Sharma",
        customer_phone: Optional[str] = None,
        customer_name: Optional[str] = None,
        points_to_redeem: int = 0,
        split_payments: Optional[List[Dict[str, Any]]] = None,
        branch_id: str = "BR-DEL-01",
    ) -> Dict[str, Any]:
        """
        Executes an end-to-end atomic retail sale.
        If any validation fails or stock runs out, the entire transaction rolls back.
        Supports single-store POS operations and multi-branch inventory tracking.
        """
        if not raw_items:
            raise POSTransactionError("Cannot checkout: billing cart is empty.", code="EMPTY_CART")

        # Resolve branch information
        branch = self.repo.get_branch_by_id(branch_id) or self.repo.get_branch_by_code(branch_id)
        if branch:
            b_id = branch.id
            b_name = branch.name
        else:
            b_id = branch_id or "BR-DEL-01"
            b_name = "Indirapuram Flagship"

        # --- STEP 1: PRE-FLIGHT VALIDATION (Catalog & Stock Check) ---
        # NOTE: This pass only rejects unknown barcodes and obviously absurd
        # quantities. The authoritative stock check happens INSIDE the atomic
        # transaction below (deduct_branch_stock_atomic), which re-reads and
        # decrements rows under BEGIN IMMEDIATE -- closing the TOCTOU window
        # where two concurrent cashiers could oversell the same shelf stock.
        consolidated_items: Dict[str, int] = {}
        for itm in raw_items:
            barcode = str(itm.get("barcode", "")).strip()
            try:
                qty = int(itm.get("quantity", 1))
            except (TypeError, ValueError):
                raise POSTransactionError(
                    f"Invalid quantity for item '{barcode}'. Quantities must be whole numbers.",
                    code="INVALID_QUANTITY",
                )
            if qty <= 0:
                continue
            if qty > MAX_CHECKOUT_QTY_PER_ITEM:
                raise POSTransactionError(
                    f"Quantity {qty} for item '{barcode}' exceeds the per-item limit of "
                    f"{MAX_CHECKOUT_QTY_PER_ITEM}. Split the sale or use a purchase order.",
                    code="QUANTITY_LIMIT_EXCEEDED",
                )
            if not barcode:
                raise POSTransactionError("Cart contains an item without a barcode.", code="EMPTY_BARCODE")
            consolidated_items[barcode] = consolidated_items.get(barcode, 0) + qty

        if len(consolidated_items) > MAX_CART_LINE_ITEMS:
            raise POSTransactionError(
                f"Cart has more than {MAX_CART_LINE_ITEMS} distinct items.", code="CART_TOO_LARGE"
            )
        if any(qty > MAX_CHECKOUT_QTY_PER_ITEM for qty in consolidated_items.values()):
            raise POSTransactionError(
                f"Combined quantity for a single item exceeds the limit of {MAX_CHECKOUT_QTY_PER_ITEM}.",
                code="QUANTITY_LIMIT_EXCEEDED",
            )

        if not consolidated_items:
            raise POSTransactionError("No valid item quantities in cart.", code="EMPTY_CART")

        # Verify all products exist and have sufficient stock BEFORE beginning mutations
        catalog_products: Dict[str, Product] = {}
        for barcode, requested_qty in consolidated_items.items():
            prod = self.repo.get_product_by_barcode(barcode)
            if not prod:
                raise ProductNotFoundError(barcode)
            
            # Check branch stock if available, else catalog stock
            b_stock = self.repo.get_branch_stock(b_id, barcode)
            avail_stock = b_stock.stock_quantity if b_stock else prod.stock_quantity
            if avail_stock < requested_qty:
                raise InsufficientStockError(
                    barcode=prod.barcode,
                    product_name=prod.name,
                    available=avail_stock,
                    requested=requested_qty,
                )
            catalog_products[barcode] = prod

        # --- STEP 2: CUSTOMER FOOTFALL & TIER PRICING RESOLUTION ---
        customer: Optional[Customer] = None
        tier = CustomerTier.BRONZE
        if customer_phone:
            clean_phone = customer_phone.strip()
            customer = self.repo.get_customer_by_phone(clean_phone)
            if not customer:
                customer = Customer(
                    phone=clean_phone,
                    name=customer_name.strip() if customer_name else f"Customer ({clean_phone[-4:]})",
                    visit_count=1,
                    total_spent=Decimal("0.00"),
                    loyalty_points=0,
                    tier=CustomerTier.BRONZE,
                    first_visited_at=datetime.now(),
                    last_visited_at=datetime.now(),
                )
            tier = customer.tier

        # Build order items and calculate line amounts
        order_items: List[OrderItem] = []
        for barcode, qty in consolidated_items.items():
            prod = catalog_products[barcode]
            order_items.append(OrderItem(
                barcode=prod.barcode,
                product_name=prod.name,
                category=prod.category,
                unit=prod.unit,
                quantity=qty,
                unit_mrp=prod.mrp,
                unit_price=prod.selling_price,
                cost_price=prod.cost_price,
                tax_rate_percent=prod.tax_rate_percent,
                branch_id=b_id,
            ))

        subtotal = round_curr(sum((i.gross_total for i in order_items), Decimal("0.00")))
        disc_info = LoyaltyPricingEngine.calculate_basket_discounts(subtotal, customer_tier=tier)
        order_discount = disc_info["total_discount"]

        points_discount = Decimal("0.00")
        actual_points_used = 0
        if customer and points_to_redeem > 0:
            actual_points_used = min(points_to_redeem, customer.loyalty_points)
            points_discount = round_curr(Decimal(actual_points_used) * Decimal("0.50"))

        grand_total = max(Decimal("0.00"), subtotal - order_discount - points_discount)

        # --- STEP 3: PAYMENT TENDER & CHANGE CALCULATION ---
        tender_dec = Decimal(str(tendered_amount))
        change_amount = Decimal("0.00")
        pay_str = payment_method.upper().strip()
        if pay_str in ("UPI", "UPI_QR", "GPAY", "PHONEPE", "PAYTM"):
            pay_enum = PaymentMethod.UPI_QR
        elif pay_str in ("CARD", "CREDIT_CARD", "DEBIT_CARD", "CREDIT_DEBIT_CARD"):
            pay_enum = PaymentMethod.CREDIT_DEBIT_CARD
        elif pay_str in ("CASH",):
            pay_enum = PaymentMethod.CASH
        elif pay_str in ("LOYALTY_POINTS", "POINTS"):
            pay_enum = PaymentMethod.LOYALTY_POINTS
        elif pay_str in ("SPLIT", "SPLIT_PAYMENT"):
            pay_enum = PaymentMethod.SPLIT
        else:
            pay_enum = PaymentMethod(pay_str)

        split_recs: List[PaymentRecord] = []
        ts = int(time.time() * 1000) % 100000
        bill_number = f"BILL-{datetime.now().strftime('%Y%m%d')}-{ts:05d}"

        if pay_enum == PaymentMethod.CASH:
            if tender_dec < grand_total:
                raise InvalidPaymentTenderError(
                    tendered=float(tender_dec),
                    payable=float(grand_total),
                    details=f"Shortfall: ₹{(grand_total - tender_dec):.2f}"
                )
            change_amount = round_curr(tender_dec - grand_total)
            split_recs.append(PaymentRecord(
                id=f"PAY-{uuid.uuid4().hex[:8].upper()}",
                bill_number=bill_number,
                method=PaymentMethod.CASH,
                amount=grand_total,
            ))
        elif pay_enum == PaymentMethod.SPLIT and split_payments:
            sum_splits = Decimal("0.00")
            for sp in split_payments:
                amt = Decimal(str(sp.get("amount", 0)))
                sum_splits += amt
                split_recs.append(PaymentRecord(
                    id=f"PAY-{uuid.uuid4().hex[:8].upper()}",
                    bill_number=bill_number,
                    method=PaymentMethod(sp.get("method", "CASH")),
                    amount=amt,
                    transaction_ref=sp.get("ref", ""),
                ))
            if sum_splits < grand_total:
                raise InvalidPaymentTenderError(
                    tendered=float(sum_splits),
                    payable=float(grand_total),
                    details="Sum of split payments does not cover grand total."
                )
            tender_dec = sum_splits
        else:
            tender_dec = grand_total
            split_recs.append(PaymentRecord(
                id=f"PAY-{uuid.uuid4().hex[:8].upper()}",
                bill_number=bill_number,
                method=pay_enum,
                amount=grand_total,
            ))

        # --- STEP 4: ATOMIC DATABASE EXECUTION (UNIT OF WORK) ---
        updated_products: List[Product] = []

        with self.repo.atomic() as conn:
            # 1. Atomically deduct inventory stock and record auditable stock movement
            for barcode, qty in consolidated_items.items():
                b_stock = self.repo.get_branch_stock(b_id, barcode, conn=conn)
                old_stock = b_stock.stock_quantity if b_stock else catalog_products[barcode].stock_quantity
                new_stock = self.repo.deduct_branch_stock_atomic(b_id, barcode, qty, conn)
                updated_prod = self.repo.get_product_by_barcode(barcode, conn=conn)
                if updated_prod:
                    updated_products.append(updated_prod)

                self.repo.record_stock_movement(
                    StockMovement(
                        id=f"MOV-{uuid.uuid4().hex[:8].upper()}",
                        barcode=barcode,
                        movement_type=StockMovementType.SALE,
                        quantity_change=-qty,
                        previous_stock=old_stock,
                        new_stock=new_stock,
                        reason=f"POS Billing Sale [{b_name}]",
                        reference_id=bill_number,
                        user_id=cashier_id,
                        branch_id=b_id,
                    ),
                    conn=conn,
                )

            # 2. Persist the Order and line items
            order = Order(
                bill_number=bill_number,
                branch_id=b_id,
                branch_name=b_name,
                cashier_id=cashier_id,
                cashier_name=cashier_name,
                customer_phone=customer.phone if customer else None,
                customer_name=customer.name if customer else (customer_name or "Walk-in Customer"),
                customer_tier=tier,
                items=order_items,
                payment_method=pay_enum,
                tendered_amount=tender_dec,
                change_amount=change_amount,
                order_discount=order_discount,
                points_redeemed=actual_points_used,
                points_discount_amount=points_discount,
                status=OrderStatus.COMPLETED,
                notes=f"Tendered: {pay_enum.value}",
                split_payments=split_recs,
                created_at=datetime.now(),
            )
            self.repo.save_order(order, conn=conn)

            # 3. Update customer footfall, lifetime spend, and loyalty points
            if customer:
                customer.visit_count += 1
                customer.total_spent = round_curr(customer.total_spent + grand_total)
                earned_pts = int(grand_total // Decimal("100.00"))
                customer.loyalty_points = max(0, customer.loyalty_points - actual_points_used + earned_pts)
                customer.last_visited_at = datetime.now()

                # Automatic Tier Progression
                if customer.visit_count >= 30:
                    customer.tier = CustomerTier.PLATINUM
                elif customer.visit_count >= 15:
                    customer.tier = CustomerTier.GOLD
                elif customer.visit_count >= 5:
                    customer.tier = CustomerTier.SILVER
                else:
                    customer.tier = CustomerTier.BRONZE

                self.repo.save_customer(customer, conn=conn)

            # 4. Synchronize active cashier shift totals
            active_shift = self.repo.get_active_shift(cashier_id, conn=conn)
            if active_shift:
                if pay_enum == PaymentMethod.CASH:
                    active_shift.total_cash_sales += grand_total
                elif pay_enum == PaymentMethod.UPI_QR:
                    active_shift.total_upi_sales += grand_total
                elif pay_enum == PaymentMethod.CREDIT_DEBIT_CARD:
                    active_shift.total_card_sales += grand_total
                self.repo.save_shift(active_shift, conn=conn)

        # --- STEP 5: POST-COMMIT IN-MEMORY UPDATES ---
        for prod in updated_products:
            self.search_engine.index_product(prod)
            self.inventory_pq.push(prod)

        if customer:
            self.cache_service.put(customer.phone, customer)

        self._action_stack.append({
            "action": "CHECKOUT",
            "bill_number": bill_number,
            "timestamp": datetime.now(),
        })

        receipt_text = self.format_thermal_receipt(order, customer)

        return {
            "success": True,
            "bill_number": bill_number,
            "grand_total": float(order.grand_total),
            "subtotal": float(order.subtotal),
            "total_tax": float(order.total_tax),
            "total_savings": float(order.total_savings),
            "tendered_amount": float(order.tendered_amount),
            "change_amount": float(order.change_amount),
            "change_due": float(order.change_amount),
            "payment_method": order.payment_method.value,
            "customer": {
                "name": customer.name,
                "phone": customer.phone,
                "visit_count": customer.visit_count,
                "tier": customer.tier.value,
                "points": customer.loyalty_points,
            } if customer else None,
            "items_count": order.total_items_count,
            "branch_id": b_id,
            "branch_name": b_name,
            "thermal_receipt_text": receipt_text,
        }

    # ========================================================================
    # 2. ATOMIC RETURNS & REFUNDS ENGINE
    # ========================================================================
    def process_return(
        self,
        bill_number: str,
        items_to_return: List[Dict[str, Any]],
        manager_pin: str,
        cashier_id: str = "CASHIER-01",
        reason: str = "Customer Return / Exchange",
    ) -> Dict[str, Any]:
        """
        Processes a customer return atomically:
        - Validates Manager PIN authorization
        - Restores product shelf inventory
        - Logs return stock movements
        - Deducts customer spend & loyalty points
        - Updates cashier shift refund deductions
        """
        # Authorization check -- only real provisioned manager/admin accounts.
        # SECURITY: no hardcoded universal override PINs are ever honoured.
        users = self.repo.list_users()
        matched_manager = None
        for u in users:
            if u.role in (UserRole.ADMIN, UserRole.STORE_MANAGER):
                ok, new_hash = u.verify_and_upgrade_pin(manager_pin)
                if ok:
                    if new_hash:
                        # Transparently migrate legacy plaintext PIN to a hash.
                        self.repo.upgrade_user_pin_hash(u.id, u.pin)
                    matched_manager = u
                    break
        if not matched_manager:
            raise UnauthorizedManagerError("Valid Store Manager or Admin PIN is required to process refunds!")

        order = self.repo.get_order_by_bill_number(bill_number)
        if not order:
            raise POSTransactionError(f"Original bill '{bill_number}' was not found in records.", code="BILL_NOT_FOUND")

        if order.status == OrderStatus.CANCELLED:
            raise OrderStateError(bill_number, order.status.value, "process_return")

        total_refund = Decimal("0.00")
        processed_items: List[Dict[str, Any]] = []

        for ret_item in items_to_return:
            barcode = ret_item.get("barcode", "").strip()
            qty_to_return = int(ret_item.get("quantity", 1))

            matching_item = next((i for i in order.items if i.barcode == barcode), None)
            if not matching_item:
                raise POSTransactionError(f"Product barcode {barcode} was not part of bill {bill_number}.")

            if matching_item.is_returned:
                raise POSTransactionError(f"Item '{matching_item.product_name}' was already refunded on this bill.")

            if qty_to_return > matching_item.quantity:
                raise POSTransactionError(
                    f"Cannot return {qty_to_return} units of '{matching_item.product_name}'; only {matching_item.quantity} purchased."
                )

            line_refund = round_curr(matching_item.unit_price * Decimal(qty_to_return))
            total_refund += line_refund
            processed_items.append({
                "barcode": barcode,
                "product_name": matching_item.product_name,
                "quantity": qty_to_return,
                "unit_price": matching_item.unit_price,
                "total": line_refund,
            })

        return_id = f"RET-{datetime.now().strftime('%Y%m')}-{uuid.uuid4().hex[:6].upper()}"
        return_number = f"REFUND-{bill_number}-{uuid.uuid4().hex[:4].upper()}"
        order_branch_id = getattr(order, "branch_id", None) or "BR-DEL-01"

        return_rec = ReturnRecord(
            id=return_id,
            return_number=return_number,
            original_bill_number=bill_number,
            customer_phone=order.customer_phone,
            cashier_id=cashier_id,
            refund_amount=total_refund,
            reason=reason,
            authorized_by=matched_manager.id,
            branch_id=order_branch_id,
            created_at=datetime.now(),
        )

        restored_products: List[Product] = []

        # Atomic SQLite Execution
        with self.repo.atomic() as conn:
            # 1. Restore product inventory & record stock movements
            for itm in processed_items:
                barcode = itm["barcode"]
                qty = itm["quantity"]
                b_stock = self.repo.get_branch_stock(order_branch_id, barcode, conn=conn)
                old_stock = b_stock.stock_quantity if b_stock else 0
                new_stock = self.repo.restore_branch_stock_atomic(order_branch_id, barcode, qty, conn)
                restored_prod = self.repo.get_product_by_barcode(barcode, conn=conn)
                if restored_prod:
                    restored_products.append(restored_prod)

                self.repo.record_stock_movement(
                    StockMovement(
                        id=f"MOV-{uuid.uuid4().hex[:8].upper()}",
                        barcode=barcode,
                        movement_type=StockMovementType.RETURN_RESTOCK,
                        quantity_change=qty,
                        previous_stock=old_stock,
                        new_stock=new_stock,
                        reason=f"Customer Return (Bill {bill_number}): {reason}",
                        reference_id=bill_number,
                        user_id=cashier_id,
                        branch_id=order_branch_id,
                    ),
                    conn=conn,
                )

            # 2. Persist return record and mark order_items.is_returned = 1
            self.repo.save_return(return_rec, processed_items, conn=conn)

            # 3. Update order status / notes
            all_returned = len(processed_items) == len(order.items)
            new_status = OrderStatus.REFUNDED if all_returned else OrderStatus.PARTIALLY_REFUNDED
            self.repo.update_order_status(
                bill_number,
                new_status,
                notes=f"[REFUND: ₹{total_refund:.2f} via {return_number}]",
                conn=conn,
            )

            # 4. Rollback customer lifetime spend & loyalty points
            if order.customer_phone:
                cust = self.repo.get_customer_by_phone(order.customer_phone, conn=conn)
                if cust:
                    cust.total_spent = max(Decimal("0.00"), cust.total_spent - total_refund)
                    deduct_pts = int(total_refund // Decimal("100.00"))
                    cust.loyalty_points = max(0, cust.loyalty_points - deduct_pts)
                    self.repo.save_customer(cust, conn=conn)
                    self.cache_service.put(cust.phone, cust)

            # 5. Deduct from active shift
            active_shift = self.repo.get_active_shift(cashier_id, conn=conn)
            if active_shift:
                active_shift.total_refunds += total_refund
                self.repo.save_shift(active_shift, conn=conn)

        # Post-commit cache & queue synchronization
        for prod in restored_products:
            self.search_engine.index_product(prod)
            self.inventory_pq.push(prod)

        return {
            "success": True,
            "return_number": return_number,
            "original_bill_number": bill_number,
            "refund_amount": float(total_refund),
            "total_refund": float(total_refund),
            "refunded_items": processed_items,
            "processed_at": return_rec.created_at.strftime("%d-%b-%Y %I:%M %p"),
        }

    # ========================================================================
    # 3. ATOMIC BILL VOIDING ENGINE
    # ========================================================================
    def void_order(self, bill_number: str, manager_pin: str, reason: str = "Cashier Void / Order Cancelled") -> Dict[str, Any]:
        """
        Cancels an entire sale atomically:
        - Validates Manager PIN
        - Restores all purchased product quantities to inventory
        - Reverses customer footfall and spend records
        - Reverses cashier shift sales
        - Sets order status to CANCELLED
        """
        # Authorization check -- only real provisioned manager/admin accounts.
        # SECURITY: no hardcoded universal override PINs are ever honoured.
        users = self.repo.list_users()
        matched_manager = None
        for u in users:
            if u.role in (UserRole.ADMIN, UserRole.STORE_MANAGER):
                ok, new_hash = u.verify_and_upgrade_pin(manager_pin)
                if ok:
                    if new_hash:
                        self.repo.upgrade_user_pin_hash(u.id, u.pin)
                    matched_manager = u
                    break
        if not matched_manager:
            raise UnauthorizedManagerError("Manager PIN authorization required to void a bill!")

        order = self.repo.get_order_by_bill_number(bill_number)
        if not order:
            raise POSTransactionError(f"Bill '{bill_number}' not found.", code="BILL_NOT_FOUND")

        if order.status == OrderStatus.CANCELLED:
            raise OrderStateError(bill_number, order.status.value, "void_order")

        restored_products: List[Product] = []
        order_branch_id = getattr(order, "branch_id", None) or "BR-DEL-01"

        with self.repo.atomic() as conn:
            # 1. Restore all order items
            for itm in order.items:
                if not itm.is_returned:
                    b_stock = self.repo.get_branch_stock(order_branch_id, itm.barcode, conn=conn)
                    old_stock = b_stock.stock_quantity if b_stock else 0
                    new_stock = self.repo.restore_branch_stock_atomic(order_branch_id, itm.barcode, itm.quantity, conn)
                    restored_p = self.repo.get_product_by_barcode(itm.barcode, conn=conn)
                    if restored_p:
                        restored_products.append(restored_p)

                    self.repo.record_stock_movement(
                        StockMovement(
                            id=f"MOV-{uuid.uuid4().hex[:8].upper()}",
                            barcode=itm.barcode,
                            movement_type=StockMovementType.MANUAL_CORRECTION,
                            quantity_change=itm.quantity,
                            previous_stock=old_stock,
                            new_stock=new_stock,
                            reason=f"Sale Void ({bill_number}): {reason}",
                            reference_id=bill_number,
                            user_id="MANAGER_OVERRIDE",
                            branch_id=order_branch_id,
                        ),
                        conn=conn,
                    )

            # 2. Update order status
            self.repo.update_order_status(bill_number, OrderStatus.CANCELLED, notes=f"[VOIDED: {reason}]", conn=conn)

            # 3. Reverse customer footfall and spend
            if order.customer_phone:
                cust = self.repo.get_customer_by_phone(order.customer_phone, conn=conn)
                if cust:
                    cust.visit_count = max(1, cust.visit_count - 1)
                    cust.total_spent = max(Decimal("0.00"), cust.total_spent - order.grand_total)
                    deduct_pts = int(order.grand_total // Decimal("100.00"))
                    cust.loyalty_points = max(0, cust.loyalty_points - deduct_pts + order.points_redeemed)
                    self.repo.save_customer(cust, conn=conn)
                    self.cache_service.put(cust.phone, cust)

            # 4. Reverse cashier active shift sales
            active_shift = self.repo.get_active_shift(order.cashier_id, conn=conn)
            if active_shift:
                if order.payment_method == PaymentMethod.CASH:
                    active_shift.total_cash_sales = max(Decimal("0.00"), active_shift.total_cash_sales - order.grand_total)
                elif order.payment_method == PaymentMethod.UPI_QR:
                    active_shift.total_upi_sales = max(Decimal("0.00"), active_shift.total_upi_sales - order.grand_total)
                elif order.payment_method == PaymentMethod.CREDIT_DEBIT_CARD:
                    active_shift.total_card_sales = max(Decimal("0.00"), active_shift.total_card_sales - order.grand_total)
                self.repo.save_shift(active_shift, conn=conn)

        # Post-commit sync
        for prod in restored_products:
            self.search_engine.index_product(prod)
            self.inventory_pq.push(prod)

        return {
            "success": True,
            "bill_number": bill_number,
            "message": f"Bill {bill_number} voided successfully and inventory stock restored.",
        }

    # ========================================================================
    # INVOICE & THERMAL RECEIPT FORMATTERS
    # ========================================================================
    def format_thermal_receipt(self, order: Order, customer: Optional[Customer]) -> str:
        """Renders an authentic 80mm Supermarket Thermal Receipt with branch-specific details."""
        sym = STORE_PROFILE.currency_symbol
        w = 46
        sep = "=" * w
        dash = "-" * w

        branch = None
        if getattr(order, "branch_id", None):
            branch = self.repo.get_branch_by_id(order.branch_id)

        store_name = branch.name if branch else (order.branch_name or STORE_PROFILE.name)
        addr1 = branch.address if branch else STORE_PROFILE.address_line1
        addr2 = f"{branch.city}, {branch.state} - {branch.pincode}" if branch else STORE_PROFILE.address_line2
        store_gstin = (branch.gstin if branch and branch.gstin else STORE_PROFILE.gstin)
        store_phone = (branch.phone if branch and branch.phone else STORE_PROFILE.support_phone)

        lines = [
            sep,
            f"{store_name:^{w}}",
            f"{STORE_PROFILE.tagline:^{w}}",
            f"{addr1:^{w}}",
            f"{addr2:^{w}}",
            f"GSTIN: {store_gstin:^{w}}",
            f"FSSAI Lic: {STORE_PROFILE.fssai_license:^{w}}",
            f"Tel: {store_phone:^{w}}",
            sep,
            "TAX INVOICE / RETAIL BILL",
            dash,
            f"Bill No:   {order.bill_number}",
            f"Branch:    {order.branch_name or 'Main Store'} ({order.branch_id or 'BR-01'})",
            f"Date/Time: {order.created_at.strftime('%d-%b-%Y %I:%M %p')}",
            f"Cashier:   {order.cashier_name} ({order.cashier_id})",
            "Counter:   POS-04 | Shift: Morning",
        ]

        if customer:
            lines.append(dash)
            lines.append(f"Customer:  {customer.name} ({customer.phone})")
            lines.append(f"Visits:    Shopped {customer.visit_count} Times! [{customer.tier.value}]")
            lines.append(f"Points:    Balance: {customer.loyalty_points} Pts")

        lines.extend([
            dash,
            f"{'ITEM':<20} {'QTY':>4} {'MRP':>10} {'NET':>10}",
            dash,
        ])

        for itm in order.items:
            name_trunc = itm.product_name[:19]
            lines.append(f"{name_trunc:<20} {itm.quantity:>4} {sym}{itm.mrp_total:>9.2f} {sym}{itm.net_total:>9.2f}")
            if itm.total_savings > Decimal("0.00"):
                lines.append(f"  * MRP {sym}{itm.unit_mrp:.2f} -> Store Price {sym}{itm.unit_price:.2f} (Save {sym}{itm.total_savings:.2f})")

        lines.extend([
            dash,
            f"{'Gross Subtotal:':>34} {sym}{order.subtotal:>10.2f}",
        ])

        if order.order_discount > Decimal("0.00"):
            lines.append(f"{'Store Promotional Disc:':>34} -{sym}{order.order_discount:>9.2f}")
        if order.points_discount_amount > Decimal("0.00"):
            lines.append(f"{'Loyalty Points Discount:':>34} -{sym}{order.points_discount_amount:>9.2f}")

        half_tax = round_curr(order.total_tax / Decimal("2.0"))
        lines.append(f"{'CGST (Included):':>34}  {sym}{half_tax:>9.2f}")
        lines.append(f"{'SGST (Included):':>34}  {sym}{(order.total_tax - half_tax):>9.2f}")

        lines.extend([
            sep,
            f"{'GRAND TOTAL:':>30} {sym}{order.grand_total:>14.2f}",
            sep,
            f"{'Payment Tendered (' + order.payment_method.value + '):':>34} {sym}{order.tendered_amount:>10.2f}",
        ])

        if order.change_amount > Decimal("0.00"):
            lines.append(f"{'CHANGE RETURNED:':>34} {sym}{order.change_amount:>10.2f}")

        lines.extend([
            dash,
            f"*** TOTAL SAVINGS TODAY: {sym}{order.total_savings:.2f} ***",
            f"You saved {round((order.total_savings/max(Decimal('0.01'), order.total_mrp))*100, 1)}% on your printed MRP!",
            dash,
            f"{'NO CASH REFUND. EXCHANGE WITHIN 14 DAYS.':^{w}}",
            f"{'ORIGINAL BILL REQUIRED FOR EXCHANGE.':^{w}}",
            f"{'Thank you for shopping at Smart Bazaar!':^{w}}",
            f"{'Visit again at ' + STORE_PROFILE.website:^{w}}",
            sep,
        ])

        return "\n".join(lines)

    def format_a4_tax_invoice(self, order: Order, customer: Optional[Customer]) -> str:
        """Renders a formal A4 GST Tax Invoice layout in clean HTML with branch-specific details."""
        sym = STORE_PROFILE.currency_symbol
        half_tax = round_curr(order.total_tax / Decimal("2.0"))

        branch = None
        if getattr(order, "branch_id", None):
            branch = self.repo.get_branch_by_id(order.branch_id)

        store_name = branch.name if branch else (order.branch_name or STORE_PROFILE.name)
        addr1 = branch.address if branch else STORE_PROFILE.address_line1
        addr2 = f"{branch.city}, {branch.state} - {branch.pincode}" if branch else STORE_PROFILE.address_line2
        store_gstin = (branch.gstin if branch and branch.gstin else STORE_PROFILE.gstin)
        store_phone = (branch.phone if branch and branch.phone else STORE_PROFILE.support_phone)

        item_rows = ""
        for idx, itm in enumerate(order.items, start=1):
            item_rows += f"""
            <tr>
                <td style="text-align: center; border: 1px solid #cbd5e1; padding: 6px;">{idx}</td>
                <td style="border: 1px solid #cbd5e1; padding: 6px;">
                    <strong>{itm.product_name}</strong><br>
                    <small style="color: #64748b;">Barcode: {itm.barcode}</small>
                </td>
                <td style="text-align: center; border: 1px solid #cbd5e1; padding: 6px;">{itm.quantity} {itm.unit}</td>
                <td style="text-align: right; border: 1px solid #cbd5e1; padding: 6px;">{sym}{itm.unit_mrp:.2f}</td>
                <td style="text-align: right; border: 1px solid #cbd5e1; padding: 6px;">{sym}{itm.unit_price:.2f}</td>
                <td style="text-align: right; border: 1px solid #cbd5e1; padding: 6px;">{itm.tax_rate_percent}%</td>
                <td style="text-align: right; border: 1px solid #cbd5e1; padding: 6px;"><strong>{sym}{itm.net_total:.2f}</strong></td>
            </tr>
            """

        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 800px; margin: auto; padding: 20px; border: 2px solid #0f172a; color: #0f172a; background: #fff;">
            <div style="display: flex; justify-content: space-between; border-bottom: 2px solid #0f172a; padding-bottom: 12px; margin-bottom: 15px;">
                <div>
                    <h2 style="margin: 0; color: #1e3a8a;">{store_name}</h2>
                    <p style="margin: 3px 0; font-size: 12px;">{STORE_PROFILE.tagline}</p>
                    <p style="margin: 3px 0; font-size: 11px;">{addr1}, {addr2}</p>
                    <p style="margin: 3px 0; font-size: 11px;"><strong>GSTIN:</strong> {store_gstin} | <strong>FSSAI:</strong> {STORE_PROFILE.fssai_license} | <strong>Tel:</strong> {store_phone}</p>
                </div>
                <div style="text-align: right;">
                    <h3 style="margin: 0; color: #2563eb;">TAX INVOICE</h3>
                    <p style="margin: 3px 0; font-size: 12px;"><strong>Invoice No:</strong> {order.bill_number}</p>
                    <p style="margin: 3px 0; font-size: 12px;"><strong>Branch:</strong> {order.branch_name or 'Main Store'} ({order.branch_id or 'BR-01'})</p>
                    <p style="margin: 3px 0; font-size: 12px;"><strong>Date:</strong> {order.created_at.strftime('%d-%b-%Y %I:%M %p')}</p>
                    <p style="margin: 3px 0; font-size: 12px;"><strong>Status:</strong> {order.status.value}</p>
                </div>
            </div>

            <div style="display: flex; justify-content: space-between; background: #f8fafc; padding: 10px; border-radius: 6px; margin-bottom: 15px; font-size: 12px;">
                <div>
                    <strong>Billed To:</strong><br>
                    Name: {order.customer_name}<br>
                    Phone: {order.customer_phone or 'Walk-in Consumer'}<br>
                    Customer Tier: {order.customer_tier.value}
                </div>
                <div>
                    <strong>Payment & Cashier:</strong><br>
                    Payment Mode: {order.payment_method.value}<br>
                    Cashier ID: {order.cashier_name} ({order.cashier_id})
                </div>
            </div>

            <table style="width: 100%; border-collapse: collapse; font-size: 12px; margin-bottom: 15px;">
                <thead>
                    <tr style="background: #1e293b; color: #fff;">
                        <th style="padding: 8px; border: 1px solid #1e293b;">#</th>
                        <th style="padding: 8px; border: 1px solid #1e293b; text-align: left;">Description of Goods</th>
                        <th style="padding: 8px; border: 1px solid #1e293b;">Qty</th>
                        <th style="padding: 8px; border: 1px solid #1e293b; text-align: right;">MRP</th>
                        <th style="padding: 8px; border: 1px solid #1e293b; text-align: right;">Rate</th>
                        <th style="padding: 8px; border: 1px solid #1e293b; text-align: right;">GST</th>
                        <th style="padding: 8px; border: 1px solid #1e293b; text-align: right;">Amount</th>
                    </tr>
                </thead>
                <tbody>
                    {item_rows}
                </tbody>
            </table>

            <div style="display: flex; justify-content: space-between; font-size: 12px;">
                <div style="width: 50%;">
                    <p style="margin: 4px 0;"><strong>Tax Assessment:</strong></p>
                    <p style="margin: 2px 0;">CGST Amount: {sym}{half_tax:.2f}</p>
                    <p style="margin: 2px 0;">SGST Amount: {sym}{(order.total_tax - half_tax):.2f}</p>
                    <p style="margin: 6px 0; color: #059669; font-weight: bold;">You saved {sym}{order.total_savings:.2f} on this purchase!</p>
                </div>
                <div style="width: 45%; text-align: right;">
                    <p style="margin: 4px 0;">Subtotal: {sym}{order.subtotal:.2f}</p>
                    {f'<p style="margin: 4px 0; color: #dc2626;">Discounts: -{sym}{order.order_discount:.2f}</p>' if order.order_discount > 0 else ''}
                    <p style="margin: 4px 0;">Total Tax: {sym}{order.total_tax:.2f}</p>
                    <h3 style="margin: 6px 0; font-size: 18px; color: #1e3a8a; border-top: 2px dashed #0f172a; padding-top: 6px;">
                        GRAND TOTAL: {sym}{order.grand_total:.2f}
                    </h3>
                </div>
            </div>
        </div>
        """
        return html
