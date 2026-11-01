"""
Retail Supermarket Seed Data Generator
Pre-populates authentic supermarket catalog, customer footfall history,
past sales, and weekly/monthly/yearly operational expenses.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
import random

from backend.models.domain import (
    Customer,
    CustomerTier,
    Product,
    OrderItem,
    Order,
    Expense,
    ExpenseCategory,
    PaymentMethod,
    round_curr,
)
from backend.storage.db import DatabaseManager
from backend.storage.repository import RetailRepository


def seed_store_data(db_manager: DatabaseManager) -> None:
    repo = RetailRepository(db_manager)

    # Check if already seeded
    existing_prods = repo.list_products()
    if len(existing_prods) >= 15:
        # Check if branch inventory is already seeded
        delhi_stock = repo.get_branch_stock("BR-DEL-01", existing_prods[0].barcode)
        if not delhi_stock:
            print("[*] Seeding Multi-Branch Inventory Allocations across branches...")
            for b_id, multiplier, aisle in [
                ("BR-DEL-01", 1.0, "Aisle 1 - Flagship"),
                ("BR-MUM-02", 0.75, "Rack B - Bandra"),
                ("BR-BLR-03", 0.60, "Shelf C - Whitefield")
            ]:
                for p in existing_prods:
                    qty = max(10, int(p.stock_quantity * multiplier))
                    repo.set_branch_stock(b_id, p.barcode, qty, p.reorder_level, shelf_location=aisle)
            print("[OK] Multi-Branch Allocations Seeded!")
        return  # Already populated

    print("[*] Seeding Supermarket Products, Customers, Orders, and Expenses...")

    # ========================================================================
    # 1. AUTHENTIC SUPERMARKET PRODUCTS (FMCG Staples, Dairy, Household, Apparel)
    # ========================================================================
    products = [
        # --- GROCERIES & STAPLES ---
        Product(
            barcode="8901030889211",
            sku="SKU-GRO-001",
            name="Aashirvaad Superior MP Shudh Chakki Atta (5 kg)",
            category="Groceries",
            brand="Aashirvaad",
            unit="pack",
            cost_price=Decimal("210.00"),
            selling_price=Decimal("245.00"),
            mrp=Decimal("275.00"),
            stock_quantity=85,
            reorder_level=20,
            tax_rate_percent=Decimal("0.00")
        ),
        Product(
            barcode="8901499008123",
            sku="SKU-GRO-002",
            name="Fortune Sunlite Refined Sunflower Oil Pouch (1 L)",
            category="Groceries",
            brand="Fortune",
            unit="liter",
            cost_price=Decimal("118.00"),
            selling_price=Decimal("139.00"),
            mrp=Decimal("165.00"),
            stock_quantity=60,
            reorder_level=15,
            tax_rate_percent=Decimal("5.00")
        ),
        Product(
            barcode="8901138810245",
            sku="SKU-GRO-003",
            name="India Gate Basmati Rice Classic (5 kg)",
            category="Groceries",
            brand="India Gate",
            unit="pack",
            cost_price=Decimal("460.00"),
            selling_price=Decimal("540.00"),
            mrp=Decimal("625.00"),
            stock_quantity=40,
            reorder_level=12,
            tax_rate_percent=Decimal("5.00")
        ),
        Product(
            barcode="8901058852219",
            sku="SKU-GRO-004",
            name="Tata Salt Vacuum Evaporated Iodised (1 kg)",
            category="Groceries",
            brand="Tata Salt",
            unit="pack",
            cost_price=Decimal("21.00"),
            selling_price=Decimal("26.00"),
            mrp=Decimal("28.00"),
            stock_quantity=150,
            reorder_level=30,
            tax_rate_percent=Decimal("0.00")
        ),
        Product(
            barcode="8901725181120",
            sku="SKU-GRO-005",
            name="Tata Sampann Unpolished Toor Dal / Arhar Dal (1 kg)",
            category="Groceries",
            brand="Tata Sampann",
            unit="pack",
            cost_price=Decimal("142.00"),
            selling_price=Decimal("168.00"),
            mrp=Decimal("195.00"),
            stock_quantity=75,
            reorder_level=15,
            tax_rate_percent=Decimal("5.00")
        ),

        # --- DAIRY, BREAD & BREAKFAST ---
        Product(
            barcode="8901262010051",
            sku="SKU-DAI-006",
            name="Amul Pasteurized Salted Table Butter (500 g)",
            category="Dairy",
            brand="Amul",
            unit="pack",
            cost_price=Decimal("235.00"),
            selling_price=Decimal("265.00"),
            mrp=Decimal("275.00"),
            stock_quantity=45,
            reorder_level=15,
            tax_rate_percent=Decimal("12.00")
        ),
        Product(
            barcode="8901262020012",
            sku="SKU-DAI-007",
            name="Amul Taaza Homogenised Toned Milk (1 L Tetra)",
            category="Dairy",
            brand="Amul",
            unit="liter",
            cost_price=Decimal("62.00"),
            selling_price=Decimal("70.00"),
            mrp=Decimal("74.00"),
            stock_quantity=8,  # LOW STOCK FOR DEMO ALERT
            reorder_level=25,
            tax_rate_percent=Decimal("5.00")
        ),
        Product(
            barcode="8901063012882",
            sku="SKU-DAI-008",
            name="Britannia 100% Whole Wheat Brown Bread (400 g)",
            category="Dairy",
            brand="Britannia",
            unit="pack",
            cost_price=Decimal("38.00"),
            selling_price=Decimal("48.00"),
            mrp=Decimal("55.00"),
            stock_quantity=5,  # LOW STOCK FOR DEMO ALERT
            reorder_level=15,
            tax_rate_percent=Decimal("5.00")
        ),

        # --- SNACKS, BEVERAGES & CONFECTIONERY ---
        Product(
            barcode="8901058859114",
            sku="SKU-SNK-009",
            name="Maggi 2-Minute Masala Instant Noodles (4-Pack, 280 g)",
            category="Snacks",
            brand="Nestle",
            unit="pack",
            cost_price=Decimal("42.00"),
            selling_price=Decimal("52.00"),
            mrp=Decimal("58.00"),
            stock_quantity=110,
            reorder_level=25,
            tax_rate_percent=Decimal("12.00")
        ),
        Product(
            barcode="8904004400281",
            sku="SKU-SNK-010",
            name="Haldiram's Nagpur Aloo Bhujia (400 g)",
            category="Snacks",
            brand="Haldiram",
            unit="pack",
            cost_price=Decimal("85.00"),
            selling_price=Decimal("105.00"),
            mrp=Decimal("120.00"),
            stock_quantity=90,
            reorder_level=20,
            tax_rate_percent=Decimal("12.00")
        ),
        Product(
            barcode="8901764012220",
            sku="SKU-BEV-011",
            name="Coca-Cola Original Refreshing Soft Drink (750 ml)",
            category="Beverages",
            brand="Coca-Cola",
            unit="bottle",
            cost_price=Decimal("30.00"),
            selling_price=Decimal("38.00"),
            mrp=Decimal("40.00"),
            stock_quantity=70,
            reorder_level=20,
            tax_rate_percent=Decimal("18.00")
        ),
        Product(
            barcode="7613035345612",
            sku="SKU-BEV-012",
            name="Nescafe Classic 100% Pure Instant Coffee Jar (100 g)",
            category="Beverages",
            brand="Nescafe",
            unit="jar",
            cost_price=Decimal("260.00"),
            selling_price=Decimal("310.00"),
            mrp=Decimal("350.00"),
            stock_quantity=35,
            reorder_level=10,
            tax_rate_percent=Decimal("18.00")
        ),
        Product(
            barcode="7622201402213",
            sku="SKU-SNK-013",
            name="Cadbury Dairy Milk Silk Chocolate Bar (150 g)",
            category="Snacks",
            brand="Cadbury",
            unit="bar",
            cost_price=Decimal("135.00"),
            selling_price=Decimal("165.00"),
            mrp=Decimal("185.00"),
            stock_quantity=65,
            reorder_level=15,
            tax_rate_percent=Decimal("18.00")
        ),

        # --- PERSONAL CARE & CLEANING ---
        Product(
            barcode="8901030771231",
            sku="SKU-HOU-014",
            name="Surf Excel Matic Front Load Detergent Powder (2 kg)",
            category="Household",
            brand="Surf Excel",
            unit="pack",
            cost_price=Decimal("390.00"),
            selling_price=Decimal("465.00"),
            mrp=Decimal("530.00"),
            stock_quantity=50,
            reorder_level=12,
            tax_rate_percent=Decimal("18.00")
        ),
        Product(
            barcode="8901030012891",
            sku="SKU-HOU-015",
            name="Vim Dishwash Gel Lemon Active Degreasers (750 ml)",
            category="Household",
            brand="Vim",
            unit="bottle",
            cost_price=Decimal("140.00"),
            selling_price=Decimal("170.00"),
            mrp=Decimal("199.00"),
            stock_quantity=55,
            reorder_level=15,
            tax_rate_percent=Decimal("18.00")
        ),
        Product(
            barcode="8901396112001",
            sku="SKU-PER-016",
            name="Dettol Antiseptic Liquid Disinfectant (550 ml)",
            category="Personal Care",
            brand="Dettol",
            unit="bottle",
            cost_price=Decimal("170.00"),
            selling_price=Decimal("205.00"),
            mrp=Decimal("234.00"),
            stock_quantity=40,
            reorder_level=10,
            tax_rate_percent=Decimal("12.00")
        ),
        Product(
            barcode="8901314010332",
            sku="SKU-PER-017",
            name="Colgate Strong Teeth Calcium Dental Cream (200 g)",
            category="Personal Care",
            brand="Colgate",
            unit="tube",
            cost_price=Decimal("88.00"),
            selling_price=Decimal("108.00"),
            mrp=Decimal("125.00"),
            stock_quantity=80,
            reorder_level=20,
            tax_rate_percent=Decimal("18.00")
        ),

        # --- APPAREL & FASHION ---
        Product(
            barcode="8907812001124",
            sku="SKU-APP-018",
            name="Men's Classic Cotton Pique Polo T-Shirt (Navy Blue, L)",
            category="Apparel",
            brand="V-Trends",
            unit="pcs",
            cost_price=Decimal("260.00"),
            selling_price=Decimal("449.00"),
            mrp=Decimal("699.00"),
            stock_quantity=30,
            reorder_level=8,
            tax_rate_percent=Decimal("5.00")
        ),
        Product(
            barcode="8907812002235",
            sku="SKU-APP-019",
            name="Women's Embroidered Straight Fit Rayon Kurti (M)",
            category="Apparel",
            brand="V-Trends",
            unit="pcs",
            cost_price=Decimal("340.00"),
            selling_price=Decimal("599.00"),
            mrp=Decimal("999.00"),
            stock_quantity=22,
            reorder_level=6,
            tax_rate_percent=Decimal("5.00")
        ),
        Product(
            barcode="8907812003346",
            sku="SKU-APP-020",
            name="Kids Sporty Breathable Cotton Track Pants (Age 8-10)",
            category="Apparel",
            brand="JuniorClub",
            unit="pcs",
            cost_price=Decimal("180.00"),
            selling_price=Decimal("299.00"),
            mrp=Decimal("499.00"),
            stock_quantity=18,
            reorder_level=5,
            tax_rate_percent=Decimal("5.00")
        ),
    ]
    for p in products:
        repo.save_product(p)
        # Allocate multi-branch inventory across default chain locations
        repo.set_branch_stock("BR-DEL-01", p.barcode, p.stock_quantity, p.reorder_level, shelf_location="Aisle 1 - Flagship")
        repo.set_branch_stock("BR-MUM-02", p.barcode, max(10, int(p.stock_quantity * 0.75)), p.reorder_level, shelf_location="Rack B - Bandra")
        repo.set_branch_stock("BR-BLR-03", p.barcode, max(15, int(p.stock_quantity * 0.60)), p.reorder_level, shelf_location="Shelf C - Whitefield")

    # ========================================================================
    # 2. FREQUENT CUSTOMERS WITH VISIT TRACKING
    # ========================================================================
    now = datetime.now()
    customers = [
        Customer(
            phone="9810188442",
            name="Rahul Sharma",
            email="rahul.sharma@gmail.com",
            visit_count=14,  # Frequent Shopper!
            total_spent=Decimal("18450.00"),
            loyalty_points=184,
            tier=CustomerTier.SILVER,
            first_visited_at=now - timedelta(days=120),
            last_visited_at=now - timedelta(days=2)
        ),
        Customer(
            phone="9871022319",
            name="Priya Patel",
            email="priya.patel@outlook.com",
            visit_count=28,  # Regular Family Shopper (Gold)!
            total_spent=Decimal("42600.00"),
            loyalty_points=426,
            tier=CustomerTier.GOLD,
            first_visited_at=now - timedelta(days=240),
            last_visited_at=now - timedelta(days=1)
        ),
        Customer(
            phone="9911223344",
            name="Anjali Verma",
            email="anjali.v@yahoo.com",
            visit_count=6,
            total_spent=Decimal("7890.00"),
            loyalty_points=78,
            tier=CustomerTier.SILVER,
            first_visited_at=now - timedelta(days=60),
            last_visited_at=now - timedelta(days=5)
        ),
        Customer(
            phone="9823091122",
            name="Vikramaditya Rao",
            email="vikram.rao@enterprise.io",
            visit_count=35,  # Top VIP Customer (Platinum)!
            total_spent=Decimal("68400.00"),
            loyalty_points=684,
            tier=CustomerTier.PLATINUM,
            first_visited_at=now - timedelta(days=320),
            last_visited_at=now - timedelta(days=3)
        ),
        Customer(
            phone="9845012345",
            name="Sneha Kulkarni",
            email="sneha.k@gmail.com",
            visit_count=2,
            total_spent=Decimal("2150.00"),
            loyalty_points=21,
            tier=CustomerTier.BRONZE,
            first_visited_at=now - timedelta(days=15),
            last_visited_at=now - timedelta(days=8)
        )
    ]
    for c in customers:
        repo.save_customer(c)

    # ========================================================================
    # 3. STORE OPERATING EXPENSES (WEEKLY, MONTHLY, YEARLY)
    # ========================================================================
    today = date.today()
    expenses = [
        # --- FIXED MONTHLY OVERHEADS ---
        Expense(
            id="EXP-202610-RENT01",
            category=ExpenseCategory.RENT,
            amount=Decimal("125000.00"),
            expense_date=date(today.year, today.month, 1),
            description="Supermarket Commercial Ground Floor Lease (Sector 18 Hub)",
            payment_mode="NEFT_WIRE",
            vendor_name="DLF Commercial Properties Ltd",
            receipt_reference="RENT-OCT-4021"
        ),
        Expense(
            id="EXP-202610-SAL01",
            category=ExpenseCategory.STAFF_SALARIES,
            amount=Decimal("84000.00"),
            expense_date=date(today.year, today.month, 1),
            description="Monthly Store Staff Payroll (4 Cashiers, 2 Shelf Handlers, 1 Guard)",
            payment_mode="BANK_TRANSFER",
            vendor_name="Staff Direct Bank Transfer",
            receipt_reference="PAYROLL-202610"
        ),
        Expense(
            id="EXP-202610-ELEC01",
            category=ExpenseCategory.ELECTRICITY_UTILITIES,
            amount=Decimal("38450.00"),
            expense_date=date(today.year, today.month, 5),
            description="Commercial Power & Heavy Refrigeration Chiller Electricity Bill",
            payment_mode="ONLINE_RTGS",
            vendor_name="Dakshin Haryana Bijli Vitran Nigam (DHBVN)",
            receipt_reference="ELEC-OCT-99881"
        ),

        # --- WEEKLY & OPERATIONAL EXPENSES ---
        Expense(
            id="EXP-202610-RESTOCK01",
            category=ExpenseCategory.INVENTORY_RESTOCK,
            amount=Decimal("62500.00"),
            expense_date=today - timedelta(days=3),
            description="Weekly Staples & FMCG Bulk Wholesale Consignment (Atta, Oil, Ghee)",
            payment_mode="CHEQUE",
            vendor_name="Metro Cash & Carry Wholesale",
            receipt_reference="INV-MTR-8812"
        ),
        Expense(
            id="EXP-202610-PACK01",
            category=ExpenseCategory.PACKAGING_BAGS,
            amount=Decimal("4800.00"),
            expense_date=today - timedelta(days=4),
            description="10,000 Recyclable Cotton Fabric & Paper Grocery Carry Bags",
            payment_mode="UPI",
            vendor_name="EcoBags Industries",
            receipt_reference="ECO-7741"
        ),
        Expense(
            id="EXP-202610-MAINT01",
            category=ExpenseCategory.MAINTENANCE_REPAIRS,
            amount=Decimal("6500.00"),
            expense_date=today - timedelta(days=2),
            description="Chiller Condenser Servicing and POS Thermal Barcode Scanner Calibration",
            payment_mode="CASH",
            vendor_name="Apex Technicians",
            receipt_reference="SERV-4410"
        ),
        Expense(
            id="EXP-202610-LOGIST01",
            category=ExpenseCategory.LOGISTICS_TRANSPORT,
            amount=Decimal("8200.00"),
            expense_date=today - timedelta(days=1),
            description="Warehouse to Retail Store Tempo Transport & Unloading Freight",
            payment_mode="UPI",
            vendor_name="FastFreight Logistics",
            receipt_reference="FF-9921"
        ),

        # --- PRIOR MONTH / YEARLY EXPENSES ---
        Expense(
            id="EXP-202609-MKT01",
            category=ExpenseCategory.MARKETING_PROMOTIONS,
            amount=Decimal("15000.00"),
            expense_date=today - timedelta(days=40),
            description="Festive Diwali Shopping Pamphlets & Local Hoarding Advertisement",
            payment_mode="BANK_TRANSFER",
            vendor_name="City Publicity House",
            receipt_reference="MKT-DLI-110"
        ),
        Expense(
            id="EXP-202608-INS01",
            category=ExpenseCategory.MISCELLANEOUS,
            amount=Decimal("28000.00"),
            expense_date=today - timedelta(days=70),
            description="Annual Comprehensive Commercial Fire & Burglary Insurance Policy",
            payment_mode="NEFT_WIRE",
            vendor_name="ICICI Lombard General Insurance",
            receipt_reference="POL-7721-COMM"
        )
    ]
    for exp in expenses:
        repo.save_expense(exp)

    # ========================================================================
    # 4. HISTORICAL SAMPLE STORE BILLS (POPULATES DASHBOARD CHARTS)
    # ========================================================================
    for day_offset in range(12, -1, -1):
        order_date = now - timedelta(days=day_offset, hours=random.randint(1, 8))
        sample_cust = random.choice(customers)

        # Pick 2-4 items for this bill
        sample_prods = random.sample(products, k=random.randint(2, 4))
        bill_items = []
        for p in sample_prods:
            qty = random.randint(1, 3)
            bill_items.append(OrderItem(
                barcode=p.barcode,
                product_name=p.name,
                category=p.category,
                unit=p.unit,
                quantity=qty,
                unit_mrp=p.mrp,
                unit_price=p.selling_price,
                cost_price=p.cost_price,
                tax_rate_percent=p.tax_rate_percent
            ))

        subtot = round_curr(sum((i.gross_total for i in bill_items), Decimal("0.00")))
        disc = round_curr(subtot * Decimal("0.02"))  # 2% discount
        g_total = subtot - disc

        ts = int(order_date.timestamp()) % 100000
        bill = Order(
            bill_number=f"BILL-{order_date.strftime('%Y%m%d')}-{ts:05d}",
            cashier_id="CASHIER-01",
            cashier_name="Rajesh Sharma",
            customer_phone=sample_cust.phone,
            customer_name=sample_cust.name,
            customer_tier=sample_cust.tier,
            items=bill_items,
            payment_method=random.choice([PaymentMethod.UPI_QR, PaymentMethod.CASH, PaymentMethod.CREDIT_DEBIT_CARD]),
            tendered_amount=g_total,
            change_amount=Decimal("0.00"),
            order_discount=disc,
            created_at=order_date
        )
        repo.save_order(bill)

    print("[OK] Supermarket Seed Data Loaded Successfully!")
