"""
Point of Sale (POS) Billing Service
Manages cashier barcode search, cart previews, and interfaces with the
central POSTransactionEngine for atomic checkout and transaction lifecycles.
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
    round_curr,
)
from backend.services.search_engine import ProductSearchEngine
from backend.services.pricing_engine import LoyaltyPricingEngine
from backend.services.inventory_pq import InventoryPriorityQueue
from backend.services.customer_service import CustomerService
from backend.services.transaction_engine import POSTransactionEngine
from backend.storage.repository import RetailRepository


class POSService:
    def __init__(
        self,
        repo: RetailRepository,
        search_engine: ProductSearchEngine,
        inventory_pq: InventoryPriorityQueue,
        customer_service: CustomerService,
        engine: Optional[POSTransactionEngine] = None
    ):
        self.repo = repo
        self.search_engine = search_engine
        self.inventory_pq = inventory_pq
        self.customer_service = customer_service
        self.engine = engine or POSTransactionEngine(
            repo=self.repo,
            search_engine=self.search_engine,
            inventory_pq=self.inventory_pq,
            cache_service=getattr(self.customer_service, "cache", None)
        )
        self._warmup_index()

    def _warmup_index(self) -> None:
        """Loads all store products into Trie search engine & Priority Queue."""
        products = self.repo.list_products()
        for p in products:
            self.search_engine.index_product(p)
            self.inventory_pq.push(p)

    def search_products(self, query: str, limit: int = 15) -> List[Dict[str, Any]]:
        """Instant sub-millisecond barcode & product search for cashiers."""
        matches = self.search_engine.search_prefix(query, limit=limit)
        seen = set()
        results = []
        for p in matches:
            if p.barcode not in seen:
                seen.add(p.barcode)
                results.append({
                    "barcode": p.barcode,
                    "sku": p.sku,
                    "name": p.name,
                    "category": p.category,
                    "brand": p.brand,
                    "unit": p.unit,
                    "cost_price": float(p.cost_price),
                    "selling_price": float(p.selling_price),
                    "mrp": float(p.mrp),
                    "discount_on_mrp": float(p.discount_on_mrp),
                    "stock_quantity": p.stock_quantity,
                    "tax_rate_percent": float(p.tax_rate_percent),
                    "is_low_stock": p.stock_quantity <= p.reorder_level,
                    "is_out_of_stock": p.stock_quantity <= 0
                })
        return results

    def calculate_cart_preview(
        self,
        raw_items: List[Dict[str, Any]],
        customer_phone: Optional[str] = None,
        points_to_redeem: int = 0,
        branch_id: str = "BR-DEL-01",
    ) -> Dict[str, Any]:
        """
        Computes live cart totals, tax breakdown, savings, customer tier discounts,
        and stock availability for the active branch.
        """
        customer = None
        tier = CustomerTier.BRONZE
        if customer_phone:
            customer = self.customer_service.lookup_customer(customer_phone)
            if customer:
                tier = customer.tier

        cart_items: List[Dict[str, Any]] = []
        subtotal = Decimal("0.00")
        total_mrp = Decimal("0.00")
        total_tax = Decimal("0.00")

        for itm in raw_items:
            barcode = itm.get("barcode", "").strip()
            qty = int(itm.get("quantity", 1))
            if qty <= 0:
                continue

            prod = self.repo.get_product_by_barcode(barcode)
            if not prod:
                continue

            b_stock = self.repo.get_branch_stock(branch_id, barcode) if branch_id else None
            effective_stock = b_stock.stock_quantity if b_stock else prod.stock_quantity
            effective_reorder = b_stock.reorder_level if b_stock else prod.reorder_level

            line_subtotal = round_curr(prod.selling_price * Decimal(qty))
            line_mrp_total = round_curr(prod.mrp * Decimal(qty))
            tax_rate = prod.tax_rate_percent / Decimal("100.0")
            line_tax = round_curr(line_subtotal * tax_rate / (Decimal("1.0") + tax_rate))

            subtotal += line_subtotal
            total_mrp += line_mrp_total
            total_tax += line_tax

            cart_items.append({
                "barcode": prod.barcode,
                "name": prod.name,
                "quantity": qty,
                "unit": prod.unit,
                "unit_price": float(prod.selling_price),
                "unit_mrp": float(prod.mrp),
                "total": float(line_subtotal),
                "is_low_stock": (effective_stock - qty) <= effective_reorder,
                "available_stock": effective_stock,
            })

        disc_info = LoyaltyPricingEngine.calculate_basket_discounts(subtotal, customer_tier=tier)
        order_discount = disc_info["total_discount"]

        points_discount = Decimal("0.00")
        actual_points_used = 0
        if customer and points_to_redeem > 0:
            actual_points_used = min(points_to_redeem, customer.loyalty_points)
            points_discount = round_curr(Decimal(actual_points_used) * Decimal("0.50"))

        grand_total = max(Decimal("0.00"), subtotal - order_discount - points_discount)
        total_savings = round_curr(max(Decimal("0.00"), total_mrp - grand_total))

        half_tax = round_curr(total_tax / Decimal("2.0"))

        return {
            "items": cart_items,
            "items_count": sum(i["quantity"] for i in cart_items),
            "subtotal": float(round_curr(subtotal)),
            "total_mrp": float(round_curr(total_mrp)),
            "total_savings": float(total_savings),
            "total_tax": float(round_curr(total_tax)),
            "cgst": float(half_tax),
            "sgst": float(total_tax - half_tax),
            "tier_discount_percent": float(disc_info.get("tier_discount_pct", Decimal("0.00"))),
            "tier_discount_amount": float(disc_info.get("tier_discount_amt", Decimal("0.00"))),
            "volume_discount_amount": float(disc_info.get("volume_discount_amt", Decimal("0.00"))),
            "order_discount": float(order_discount),
            "points_redeemed": actual_points_used,
            "points_discount": float(points_discount),
            "grand_total": float(round_curr(grand_total)),
            "customer_tier": tier.value
        }

    def checkout(
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
        Delegates atomic sale execution to POSTransactionEngine.
        Ensures stock, payments, footfall, and orders share a single atomic transaction.
        """
        return self.engine.execute_sale(
            raw_items=raw_items,
            payment_method=payment_method,
            tendered_amount=tendered_amount,
            cashier_id=cashier_id,
            cashier_name=cashier_name,
            customer_phone=customer_phone,
            customer_name=customer_name,
            points_to_redeem=points_to_redeem,
            split_payments=split_payments,
            branch_id=branch_id,
        )

    def void_order(self, bill_number: str, manager_pin: str, reason: str = "Cashier Void / Order Cancelled") -> Dict[str, Any]:
        """
        Delegates atomic voiding to POSTransactionEngine.
        """
        return self.engine.void_order(bill_number, manager_pin, reason)

    def format_thermal_receipt(self, order: Order, customer: Optional[Customer]) -> str:
        """Renders an authentic 80mm Supermarket Thermal Receipt."""
        return self.engine.format_thermal_receipt(order, customer)

    def format_a4_tax_invoice(self, order: Order, customer: Optional[Customer]) -> str:
        """Renders a formal A4 GST Tax Invoice layout in clean HTML."""
        return self.engine.format_a4_tax_invoice(order, customer)
