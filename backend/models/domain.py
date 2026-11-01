"""
Retail Enterprise Domain Models (OOP Architecture)
Encapsulates real supermarket and retail store entities with strict financial typing,
business invariants, and behavioral methods.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import List, Optional, Dict, Any


def round_curr(amount: Decimal) -> Decimal:
    """Rounds currency amounts to 2 decimal places using standard commercial rounding."""
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class UserRole(str, Enum):
    """Role-based access permissions."""
    ADMIN = "ADMIN"                     # Full access
    STORE_MANAGER = "STORE_MANAGER"     # P&L, inventory adjustments, refunds, shift reconciliation
    CASHIER = "CASHIER"                 # POS terminal, customer lookup, thermal receipt printing
    INVENTORY_MANAGER = "INVENTORY_MANAGER" # Stock updates, purchase orders, supplier coordination


class CustomerTier(str, Enum):
    """Retail loyalty classification based on visit frequency and lifetime spend."""
    BRONZE = "BRONZE"      # 1 - 4 visits
    SILVER = "SILVER"      # 5 - 14 visits (1% discount)
    GOLD = "GOLD"          # 15 - 29 visits (2.5% discount)
    PLATINUM = "PLATINUM"  # 30+ visits (5% discount + priority checkout)


class PaymentMethod(str, Enum):
    """Store checkout payment channels."""
    CASH = "CASH"
    UPI_QR = "UPI_QR"
    CREDIT_DEBIT_CARD = "CREDIT_DEBIT_CARD"
    LOYALTY_POINTS = "LOYALTY_POINTS"
    SPLIT = "SPLIT"


class OrderStatus(str, Enum):
    """Transaction states."""
    COMPLETED = "COMPLETED"
    REFUNDED = "REFUNDED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    CANCELLED = "CANCELLED"


class StockMovementType(str, Enum):
    """Stock movement audit trail classification."""
    SALE = "SALE"
    RETURN_RESTOCK = "RETURN_RESTOCK"
    PURCHASE_RECEIPT = "PURCHASE_RECEIPT"
    ADJUSTMENT_DAMAGE = "ADJUSTMENT_DAMAGE"
    ADJUSTMENT_DISCREPANCY = "ADJUSTMENT_DISCREPANCY"
    MANUAL_CORRECTION = "MANUAL_CORRECTION"
    TRANSFER_OUT = "TRANSFER_OUT"
    TRANSFER_IN = "TRANSFER_IN"


class ExpenseCategory(str, Enum):
    """Store operational expenditure classification."""
    RENT = "RENT"
    ELECTRICITY_UTILITIES = "ELECTRICITY_UTILITIES"
    STAFF_SALARIES = "STAFF_SALARIES"
    INVENTORY_RESTOCK = "INVENTORY_RESTOCK"
    MAINTENANCE_REPAIRS = "MAINTENANCE_REPAIRS"
    PACKAGING_BAGS = "PACKAGING_BAGS"
    MARKETING_PROMOTIONS = "MARKETING_PROMOTIONS"
    LOGISTICS_TRANSPORT = "LOGISTICS_TRANSPORT"
    MISCELLANEOUS = "MISCELLANEOUS"


@dataclass
class StoreBranch:
    """
    Physical supermarket store / branch location in a multi-store retail chain.
    Enables single-store demonstration today and multi-store expansion across cities.
    """
    id: str  # e.g. "BR-DEL-01"
    code: str  # e.g. "DEL-FLAGSHIP"
    name: str  # e.g. "Indirapuram Flagship Store"
    address: str  # e.g. "Plot 4A, Indirapuram Commercial Hub"
    city: str  # e.g. "Ghaziabad / Delhi NCR"
    state: str  # e.g. "Uttar Pradesh"
    pincode: str  # e.g. "201014"
    phone: str = "+91 1800 200 8899"
    email: str = "flagship.store@apexretail.io"
    gstin: str = "07AAACR1234F1Z5"
    manager_name: str = "Vikram Malhotra"
    is_headquarters: bool = True
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class BranchStock:
    """
    Product inventory allocation for a specific supermarket branch.
    """
    branch_id: str
    barcode: str
    stock_quantity: int
    reorder_level: int = 10
    shelf_location: str = "Aisle 1"
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class User:
    """Store employee / user record."""
    id: str
    username: str
    full_name: str
    role: UserRole
    pin: str  # 4-digit fast cashier PIN
    branch_id: str = "BR-DEL-01"
    is_active: bool = True

    def verify_pin(self, candidate_pin: str) -> bool:
        return self.pin.strip() == candidate_pin.strip()


@dataclass
class Customer:
    """
    Supermarket customer entity tracking footfall, visit frequency,
    and lifetime shopping value.
    """
    phone: str
    name: str
    membership_code: str = ""
    email: str = ""
    address: str = ""
    visit_count: int = 1
    total_spent: Decimal = Decimal("0.00")
    loyalty_points: int = 0
    tier: CustomerTier = CustomerTier.BRONZE
    first_visited_at: datetime = field(default_factory=datetime.now)
    last_visited_at: datetime = field(default_factory=datetime.now)
    is_active: bool = True

    def __post_init__(self) -> None:
        if not self.membership_code and self.phone:
            self.membership_code = f"MEM-{self.phone}"

    def record_new_visit(self, bill_amount: Decimal) -> None:
        """
        Updates visit statistics and auto-promotes customer loyalty tier.
        Earns 1 loyalty point for every 100 currency units spent.
        """
        self.visit_count += 1
        self.last_visited_at = datetime.now()
        self.total_spent = round_curr(self.total_spent + bill_amount)
        
        # Calculate points earned (1 point per ₹100 spent)
        points_earned = int(bill_amount // Decimal("100.00"))
        self.loyalty_points += points_earned

        # Auto-tier promotion based on store visit frequency
        if self.visit_count >= 30:
            self.tier = CustomerTier.PLATINUM
        elif self.visit_count >= 15:
            self.tier = CustomerTier.GOLD
        elif self.visit_count >= 5:
            self.tier = CustomerTier.SILVER
        else:
            self.tier = CustomerTier.BRONZE

    @property
    def average_basket_value(self) -> Decimal:
        """Average spend per store visit."""
        if self.visit_count <= 0:
            return Decimal("0.00")
        return round_curr(self.total_spent / Decimal(self.visit_count))

    @property
    def days_since_last_visit(self) -> int:
        delta = datetime.now() - self.last_visited_at
        return max(0, delta.days)

    @property
    def customer_segment(self) -> str:
        """Behavioral customer segmentation."""
        if self.visit_count <= 1:
            return "NEW_CUSTOMER"
        if self.days_since_last_visit >= 30:
            return "INACTIVE"
        if self.visit_count >= 15 or self.total_spent >= Decimal("20000.00"):
            return "VIP_HIGH_VALUE"
        return "RETURNING_REGULAR"

    @property
    def membership_qr_data(self) -> str:
        """Standardized QR code payload for digital membership card scanning."""
        return f"RETAIL:MEM:{self.membership_code}:{self.phone}"


@dataclass
class Supplier:
    """Wholesale vendor / distributor supplying inventory."""
    id: str
    name: str
    contact_person: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    gstin: str = ""
    payment_terms: str = "Net-30"


@dataclass
class Product:
    """
    Catalog SKU / Barcode item in supermarket inventory.
    Tracks MRP, selling price, purchase cost (COGS), and on-shelf stock.
    """
    barcode: str
    sku: str
    name: str
    category: str
    brand: str
    unit: str  # kg, pcs, pack, liter, meter
    cost_price: Decimal    # Supplier wholesale procurement cost
    selling_price: Decimal # Store discounted price
    mrp: Decimal           # Maximum Retail Price printed on packaging
    stock_quantity: int
    reorder_level: int = 10
    tax_rate_percent: Decimal = Decimal("5.00")
    supplier_name: str = ""
    expiry_date: Optional[date] = None
    subcategory: str = ""
    is_active: bool = True

    @property
    def discount_on_mrp(self) -> Decimal:
        """Customer savings compared to Maximum Retail Price."""
        return max(Decimal("0.00"), round_curr(self.mrp - self.selling_price))

    @property
    def profit_margin(self) -> Decimal:
        """Store gross profit per unit."""
        return max(Decimal("0.00"), round_curr(self.selling_price - self.cost_price))

    @property
    def inventory_valuation_cost(self) -> Decimal:
        """Total current stock value evaluated at purchase procurement cost."""
        return round_curr(self.cost_price * Decimal(max(0, self.stock_quantity)))

    @property
    def inventory_valuation_retail(self) -> Decimal:
        """Total current stock value evaluated at selling retail price."""
        return round_curr(self.selling_price * Decimal(max(0, self.stock_quantity)))

    def has_stock(self, quantity: int) -> bool:
        return self.stock_quantity >= quantity

    def deduct_stock(self, quantity: int) -> None:
        if not self.has_stock(quantity):
            raise ValueError(f"Insufficient stock for {self.name}. Available: {self.stock_quantity}, Requested: {quantity}")
        self.stock_quantity -= quantity

    def restock(self, quantity: int) -> None:
        self.stock_quantity += quantity


@dataclass
class StockMovement:
    """Auditable log of every inventory delta."""
    id: str
    barcode: str
    movement_type: StockMovementType
    quantity_change: int
    previous_stock: int
    new_stock: int
    reason: str
    reference_id: str
    branch_id: str = "BR-DEL-01"
    destination_branch_id: Optional[str] = None
    user_id: str = "SYSTEM"
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class OrderItem:
    """Individual line item scanned at the billing counter."""
    barcode: str
    product_name: str
    category: str
    unit: str
    quantity: int
    unit_mrp: Decimal
    unit_price: Decimal
    cost_price: Decimal
    tax_rate_percent: Decimal
    line_discount: Decimal = Decimal("0.00")
    is_returned: bool = False
    branch_id: str = "BR-DEL-01"

    @property
    def gross_total(self) -> Decimal:
        return round_curr(self.unit_price * Decimal(self.quantity))

    @property
    def mrp_total(self) -> Decimal:
        return round_curr(self.unit_mrp * Decimal(self.quantity))

    @property
    def net_total(self) -> Decimal:
        return max(Decimal("0.00"), self.gross_total - self.line_discount)

    @property
    def total_savings(self) -> Decimal:
        """Savings vs printed MRP."""
        return max(Decimal("0.00"), self.mrp_total - self.net_total)

    @property
    def tax_amount(self) -> Decimal:
        """Included tax component."""
        return round_curr(self.net_total * (self.tax_rate_percent / Decimal("100.00")))

    @property
    def cogs_total(self) -> Decimal:
        """Cost of Goods Sold for profit analytics."""
        return round_curr(self.cost_price * Decimal(self.quantity))


@dataclass
class PaymentRecord:
    """Individual payment record supporting split tenders."""
    id: str
    bill_number: str
    method: PaymentMethod
    amount: Decimal
    transaction_ref: str = ""
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Order:
    """
    Completed retail sales transaction / bill.
    Enterprise POS invoice structure with full tax breakdown.
    """
    bill_number: str
    cashier_id: str
    cashier_name: str
    customer_phone: Optional[str]
    customer_name: str
    customer_tier: CustomerTier
    items: List[OrderItem] = field(default_factory=list)
    payment_method: PaymentMethod = PaymentMethod.CASH
    tendered_amount: Decimal = Decimal("0.00")
    change_amount: Decimal = Decimal("0.00")
    order_discount: Decimal = Decimal("0.00")
    points_redeemed: int = 0
    points_discount_amount: Decimal = Decimal("0.00")
    status: OrderStatus = OrderStatus.COMPLETED
    notes: str = ""
    branch_id: str = "BR-DEL-01"
    branch_name: str = "Indirapuram Flagship"
    split_payments: List[PaymentRecord] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def total_items_count(self) -> int:
        return sum(item.quantity for item in self.items)

    @property
    def active_items_count(self) -> int:
        return sum(item.quantity for item in self.items if not item.is_returned)

    @property
    def total_mrp(self) -> Decimal:
        return round_curr(sum((item.mrp_total for item in self.items), Decimal("0.00")))

    @property
    def subtotal(self) -> Decimal:
        return round_curr(sum((item.gross_total for item in self.items), Decimal("0.00")))

    @property
    def total_tax(self) -> Decimal:
        return round_curr(sum((item.tax_amount for item in self.items), Decimal("0.00")))

    @property
    def grand_total(self) -> Decimal:
        calculated = self.subtotal - self.order_discount - self.points_discount_amount
        return max(Decimal("0.00"), round_curr(calculated))

    @property
    def total_savings(self) -> Decimal:
        """Total savings = (Total MRP - Grand Total)."""
        return max(Decimal("0.00"), round_curr(self.total_mrp - self.grand_total))

    @property
    def total_cogs(self) -> Decimal:
        """Total cost of goods sold for this bill."""
        return round_curr(sum((item.cogs_total for item in self.items), Decimal("0.00")))

    @property
    def gross_profit(self) -> Decimal:
        """Gross margin for this bill: Grand Total - Total COGS."""
        return round_curr(self.grand_total - self.total_cogs)


@dataclass
class ReturnRecord:
    """Documenting product returns and refunds."""
    id: str
    return_number: str
    original_bill_number: str
    customer_phone: Optional[str]
    cashier_id: str
    refund_amount: Decimal
    reason: str
    branch_id: str = "BR-DEL-01"
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class CashShift:
    """Cash register shift tracking & reconciliation (Z-Report)."""
    id: str
    cashier_id: str
    cashier_name: str
    shift_number: int
    start_time: datetime
    end_time: Optional[datetime] = None
    opening_float: Decimal = Decimal("2000.00")
    total_cash_sales: Decimal = Decimal("0.00")
    total_upi_sales: Decimal = Decimal("0.00")
    total_card_sales: Decimal = Decimal("0.00")
    total_refunds: Decimal = Decimal("0.00")
    cash_drops: Decimal = Decimal("0.00")
    actual_counted_cash: Decimal = Decimal("0.00")
    is_closed: bool = False
    branch_id: str = "BR-DEL-01"
    notes: str = ""

    @property
    def total_sales(self) -> Decimal:
        """Total gross sales across all payment modes for this shift."""
        return round_curr(self.total_cash_sales + self.total_upi_sales + self.total_card_sales)

    @property
    def expected_drawer_cash(self) -> Decimal:
        """Expected cash in drawer = Opening Float + Cash Sales - Refunds - Cash Drops."""
        return round_curr(self.opening_float + self.total_cash_sales - self.total_refunds - self.cash_drops)

    @property
    def variance(self) -> Decimal:
        """Cash discrepancy: Actual Counted - Expected."""
        return round_curr(self.actual_counted_cash - self.expected_drawer_cash)

    @property
    def cash_variance(self) -> Decimal:
        """Alias for variance to support legacy and API naming."""
        return self.variance


@dataclass
class Expense:
    """
    Store operational expense entry.
    Tracks fixed and variable costs (Rent, Salaries, Electricity, Maintenance, Restock).
    """
    id: str
    category: ExpenseCategory
    amount: Decimal
    expense_date: date
    description: str
    payment_mode: str = "BANK_TRANSFER"
    vendor_name: str = ""
    receipt_reference: str = ""
    branch_id: str = "BR-DEL-01"
    created_at: datetime = field(default_factory=datetime.now)
