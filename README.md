# Apex Enterprise Retail POS, Billing & ERP Platform
**Production-Ready Commercial Retail Management & Hypermarket Operations System**
*High-Performance Embedded DSA (Prefix Trie, LRU Cache, Min-Heap, Binary Search, Stacks) + Pure OOP Architecture*

---

## 🌟 Executive Overview: Commercial Supermarket Operations

This platform is a full-featured, enterprise-grade retail store operations and Point of Sale (POS) system engineered for high-throughput commercial supermarket and hypermarket chains.

The core architecture is built around a **high-reliability POS Transaction Engine (`POSTransactionEngine`)** with strict ACID guarantees:
- **Single-Store Ready with Multi-Branch Architecture**: Operates as a seamless single-store POS counter out of the box (defaulting to `BR-DEL-01: Indirapuram Flagship`), while architecturally designed to scale across multiple supermarket branches. Shelf stock, cashier shifts, sales, customer returns, and operational expenses are branch-isolated with atomic inter-branch logistics (`TRANSFER_OUT` and `TRANSFER_IN`).
- **Atomic Multi-Entity Transactions**: Pre-flight shelf stock validation, inventory decrements, auditable stock movements, customer footfall / lifetime spend updates, split payment records, and active cashier shift totals commit atomically or roll back completely (`BEGIN IMMEDIATE`).
- **Consistent Shared Database Records**: Billing, payment tender, stock deduction, customer returns/refunds, and executive financial reporting share a single database record schema. Cancelled and voided bills are strictly excluded from sales and COGS, and refunds are accounted for across P&L and register cash drawers.
- **Typed Domain Exceptions**: Typed error models (`InsufficientStockError`, `InvalidPaymentTenderError`, `UnauthorizedManagerError`, `ProductNotFoundError`, `OrderStateError`) mapped to standard HTTP status codes (`409`, `400`, `403`, `404`).
- **Instant Barcode Search ($O(K)$ Prefix Trie)**: Sub-millisecond barcode scan lookups and search autocomplete across thousands of supermarket SKUs.
- **Smart Customer Recognition (Mobile Phone & 2D Membership QR Code)**:
  - Cashiers identify returning customers in under 200ms using either their 10-digit mobile number, formatted mobile (`+91`), or scanning their digital/physical **Membership QR Code** (`RETAIL:MEM:{code}:{phone}`).
  - Automatically loads full customer profile, loyalty points, cash-equivalent redemption value, tier discount perks (`0%` to `5%` off), shopping frequency, and last visit days ago.
  - Interactive **Digital Membership Card** modal featuring a dynamically generated high-contrast 2D QR code canvas.
  - Interactive **Customer Shopping Habits** modal visualizing preferred product categories, spend share %, top 5 bought products, and historical bills.
- **5-Pillar Business Intelligence & Analytics Suite**:
  - **Pillar 1: Executive P&L**: Multi-period switching (`Today`, `This Week`, `This Month`, `This Year`) calculating true net profit after COGS and operational expenses.
  - **Pillar 2: Best-Selling Products**: Ranked by units sold, gross revenue, gross profit contribution, and profit margin percentages.
  - **Pillar 3: Slow-Moving & Dead Stock**: Identifies stagnant inventory with sales $\le 2$ in past 30 days, calculates total idle working capital locked in ₹, assigns risk classifications (`CRITICAL_DEAD_STOCK`, `HIGH_RISK`, `MODERATE_SLOW`), and suggests actionable clearance or return-to-vendor (RTV) strategies.
  - **Pillar 4: Customer Retention & Churn**: Computes Repeat Customer Rate %, returning vs first-time shopper counts, average customer LTV, churn telemetry (Active within 14 days, At-Risk 15-45 days, Dormant > 45 days), and loyalty tier cohorts.
  - **Pillar 5: Seasonal & Peak Demand Dynamics**: Analyzes day-of-week sales volume/revenue, hourly shopping footfall curves (identifying peak rush hours), and department demand dynamics.
  - **Pillar 6: Restock Priority Queue**: Automated replenishment queue prioritizing depleted shelf stock by depletion ratio against minimum reorder levels, calculating suggested replenishment units and procurement budget.
- **Periodic Expense Management (Weekly, Monthly, Yearly)**: Dedicated expense ledger calculating Weekly, Monthly, and Yearly operational costs (Rent, Staff Salaries, Electricity/Utilities, Packaging Bags, Wholesale Restocking, Maintenance, Transport).
- **True Net Profit & Loss (P&L) Engine**: Calculates authentic store profitability:
  $$\text{Net Operating Profit} = \text{Gross Revenue} - \text{Refunds} - \text{Net COGS} - \text{Operating Expenses}$$
- **Customer Returns & Refund Processing**: Formal returns workflow with Manager PIN authorization (`2222`), line-item quantity selection, inventory restocking, and customer lifetime spend adjustment.
- **Cash Register Shift Balancing & Z-Report Reconciliation**: Cashier drawer opening float, live cash/UPI/card sales tracking, midday safe cash drops, physical cash count entry, over/short variance calculation, and day-end Z-Report sealing.
- **Dual Invoice Formats**:
  - **80mm POS Thermal Receipt**: Standard supermarket thermal receipt formatted with store branding, GSTIN, cashier info, customer footfall banner, savings breakdown, and CGST/SGST split.
  - **Standard A4 GST Tax Invoice**: Formal tax invoice with HSN codes, buyer details, itemized tax rates, CGST/SGST assessment, and authorized signatory.
- **Stock Adjustments & Valuation**: Stock level adjustment (Damage, Discrepancy, Restock), shelf barcode price tags, bulk CSV import/export, and store valuation at procurement cost vs retail selling price.

---

## 🖥️ Modern Web UI & POS Modules

The application features a modern enterprise sidebar navigation layout (inspired by Shopify POS and modern ERP dashboards) with a **Light / Dark Mode Toggle**:

### 1. 🛒 Point of Sale (POS) Billing Counter
- **Barcode & Keyword Search**: Cashier types or scans barcodes with instant Trie autocomplete.
- **Quick-Category Shelf**: Fast filter pills for Groceries, Dairy, Snacks, Beverages, Household, Personal Care, and Apparel.
- **Smart Customer Recognition**:
  - Scan customer **Membership QR Code** or enter 10-digit mobile number.
  - Celebratory **"RETURNING (X visits) ⭐"** loyalty badge and tier discount tag.
  - Quick action buttons: **Past Invoices**, **Shopping Habits**, and **Digital Membership Card** (with live 2D QR Code).
  - One-click reward points redemption directly against the bill total.
- **Cart Line Items Table**: Instant quantity adjustment `[-] Qty [+]`, unit prices, MRP strikethroughs, and item removal.
- **Payment Tenders**: Cash (with live **Change to Return** calculation), UPI QR Code simulation, Card, and Split Tender.
- **Checkout Action**: Fast checkout with keyboard shortcut `[F9]`.

### 2. 🧾 Sales & Transaction Register
- **Transaction History**: Audit trail of all retail bills, payment tenders, and cashier names.
- **Search & Filters**: Search by invoice number, customer name, mobile, payment method, or status.
- **Action Tools**:
  - 🖨️ **Reprint Thermal Receipt**: View and print 80mm thermal receipt.
  - 📄 **View A4 GST Tax Invoice**: View and print formal tax invoice.
  - ↩️ **Process Return / Refund**: Select returned items, specify return quantity and reason, authorized with Manager PIN.
  - 🚫 **Void Transaction**: Cancel order and automatically restore inventory stock with Manager PIN.

### 3. 💵 Cash Register Shifts & Day-End Z-Report
- **Active Shift Summary**: Opening float, cash sales, UPI/card sales, total shift sales, and expected drawer cash.
- **Safe Cash Drops**: Transfer excess drawer cash into the main store safe during busy hours.
- **Day-End Z-Report**: Cashier enters counted physical cash; the system computes over/short cash variance, seals the shift, and prints the Z-report.
- **Shift Audit History**: Historical log of all closed shifts with cash variances.

### 4. 📊 Store Executive Dashboard & 5-Pillar Business Intelligence
Features an interactive BI subnavigation bar spanning 6 executive views:
- **Pillar 1: Executive P&L**: Multi-period switching (`Today`, `This Week`, `This Month`, `This Year`) calculating true net profit after COGS and operational expenses with 7-Day Sales Trend & Category Share charts.
- **Pillar 2: Best-Selling Products**: Ranked by units sold, gross revenue, gross profit contribution, and margin %.
- **Pillar 3: Slow-Moving & Dead Stock**: Identifies inventory with sales $\le 2$ in past 30 days, shows idle capital locked in ₹, and recommends specific actions (e.g. Clearance 25% Off, RTV Supplier Return, Eye-Level Endcap Display).
- **Pillar 4: Customer Retention & Churn**: Tracks Repeat Customer Rate %, returning vs first-time shopper counts, average customer LTV, churn telemetry (Active within 14 days, At-Risk 15-45 days, Dormant > 45 days), and loyalty tier spend distribution.
- **Pillar 5: Seasonal & Peak Demand**: Dual Chart.js visualizations showing Day-of-Week sales volume/revenue and Hourly Peak Shopping rush curves (8:00 AM - 10:00 PM) plus department demand dynamics.
- **Pillar 6: Restock Priority Queue**: Automated replenishment queue prioritized by stock depletion ratio against minimum reorder levels, calculating suggested replenishment units and procurement budget.

### 5. 📦 Catalog, Inventory Valuation & Stock Management
- **Valuation Cards**: Total Distinct SKUs, Total Physical Units, Procurement Cost Valuation, Retail Selling Valuation, and Potential Gross Margin.
- **Stock Adjustment**: Update shelf stock levels with classification (Discrepancy, Damage, Restock) and auditable stock movement logging.
- **Bulk CSV Import & Export**: One-click download of the store catalog as CSV, and bulk import tool to batch-upsert products.
- **Shelf Barcode Labels**: Generate and print shelf pricing label tags with barcodes and customer savings.

### 6. 👥 Customer Footfall & Loyalty CRM
- Tracks **how many times each customer visited the store** (e.g. 14 visits, 28 visits, 35 visits).
- Displays Membership ID, Customer Name, Mobile Phone, Times Visited, Loyalty Tier, Reward Points, Lifetime Spend (₹), and Average Basket Value.
- Action Buttons per customer:
  - 🧾 **Order History**: View past invoices and line items.
  - 📊 **Shopping Habits**: Category spend share % and top 5 purchased products.
  - 🪪 **Digital Card**: Opens the customer's scannable digital loyalty card with 2D QR Code.

### 7. 💸 Operating Expenses Tracker (Weekly, Monthly, Yearly)
- **3-Period Summary**: Instant totals for This Week's, This Month's, and This Year's operational expenses.
- **Expense Categories**: Rent, Electricity/Utilities, Staff Salaries, Restock, Packaging Bags, Maintenance, Marketing, Transport.
- **Add Expense Modal**: Interactive form with date picker, category dropdown, amount in ₹, payment mode, and vendor details.
- **Live Expense Ledger**: Full chronological table with deletion action.

### 8. 📑 Store Audit & Data Exports
- 1-Click CSV Download for **Sales Transactions Report**.
- 1-Click CSV Download for **Operating Expenses Ledger**.
- 1-Click CSV Download for **Active Catalog & Inventory Report**.

### 9. 🏢 Multi-Branch Store Network & Inter-Branch Transfers
- **Single-Store Default**: Out of the box, functions seamlessly as a single-store POS counter for **Indirapuram Flagship (`BR-DEL-01`)**.
- **Dynamic Branch Switcher**: Topbar store switcher allows cashiers and regional managers to toggle between individual store locations (`Indirapuram Flagship`, `Bandra West`, `Whitefield`) or view chain-wide consolidated data (`All Branches`).
- **Store Location Status**: Dynamic sidebar badge displaying active branch name, store code, and live operational status.
- **Store Performance Cards**: Live metrics per branch displaying Store Code, Address, Phone, Store Manager, Completed Orders Count, and Gross Sales.
- **Multi-Branch Comparative Table**: Side-by-side comparison of branch sales performance and store metadata.
- **Register Store Branch Modal**: Onboard new retail outlets with code, GSTIN, address, store manager, and auto-seeded baseline inventory.
- **Inter-Branch Stock Transfer Modal**: Atomic inventory transfers with live validation, deducting stock from the source branch and adding stock to the destination branch with dual stock movement logging (`TRANSFER_OUT` & `TRANSFER_IN`).

---

## ⚡ Embedded Data Structures & Algorithms

| Data Structure / Algorithm | File Implementation | Commercial Supermarket Purpose | Complexity |
|---|---|---|---|
| **Prefix Trie (Prefix Tree)** | `backend/services/search_engine.py` | Sub-millisecond cashier barcode scanner input & keyword autocomplete across the catalog. | **$O(K)$** ($K$ = query length) |
| **LRU Cache** (Doubly-Linked List + Hash Map) | `backend/services/cache_service.py` | Ultra-fast in-memory lookup of active customer loyalty sessions by phone number. | **$O(1)$** Reads & Writes |
| **Min-Heap Priority Queue** | `backend/services/inventory_pq.py` | Real-time shelf replenishment queue ranking critically low stock items by depletion ratio. | **$O(\log N)$** Push & Pop |
| **Binary Search Interval Mapping** | `backend/services/pricing_engine.py` | Evaluates wholesale volume discount slabs and loyalty tier perks. | **$O(\log K)$** Slabs Lookup |
| **Action Stacks** | `backend/services/pos_service.py` | Cart undo/reversal operations and transaction rollback. | **$O(1)$** Push & Pop |

---

## 🏗️ Clean Architecture & Directory Structure

```
EnterpriseBillingSystem/
├── backend/
│   ├── app.py                  # FastAPI server (REST endpoints, global exception handlers & UI)
│   ├── config.py               # Store profile (Apex Retail brand, GSTIN, currency)
│   ├── models/                 # OOP Domain Models & Typed Exceptions
│   │   ├── domain.py           # Domain entities (Customer, Product, Order, Expense, Shift, Return)
│   │   ├── exceptions.py       # Typed domain exceptions (InsufficientStockError, etc.)
│   │   └── __init__.py
│   ├── services/               # Business Logic with embedded DSA & Transaction Processing:
│   │   ├── transaction_engine.py # Dedicated ACID POS transaction engine (Sales, Returns, Voids)
│   │   ├── search_engine.py    # Prefix Trie search engine ($O(K)$)
│   │   ├── cache_service.py    # LRU Cache (Doubly-Linked List + Hash Map, $O(1)$)
│   │   ├── inventory_pq.py     # Min-Heap Priority Queue for restocking ($O(\log N)$)
│   │   ├── pricing_engine.py   # Binary search tiered discounts ($O(\log K)$)
│   │   ├── pos_service.py      # Cart builder, checkout preview, receipt & A4 invoice
│   │   ├── customer_service.py # Customer footfall, visits tracking, loyalty tiers
│   │   ├── expense_service.py  # Weekly, Monthly, Yearly expense tracking & P&L
│   │   ├── analytics_service.py# Dashboard KPIs & multi-period P&L aggregates
│   │   ├── returns_service.py  # Customer returns, refunds & manager PIN authorization
│   │   ├── register_service.py # Cash register shifts, safe drops & Day-End Z-Report
│   │   └── inventory_service.py# Stock adjustments, valuation, CSV import/export
│   ├── storage/
│   │   ├── db.py               # SQLite database manager with atomic BEGIN IMMEDIATE transactions
│   │   └── repository.py       # Unified repository pattern with atomic stock deduction & P&L
│   └── seed_retail_data.py     # Supermarket catalog, footfall customers, expenses & past orders
│
├── frontend/                   # Modern Retail POS & ERP Dashboard UI
│   ├── index.html              # Single-Page Application with enterprise sidebar & 12 modals
│   ├── css/
│   │   └── styles.css          # Light/Dark theme CSS variables, responsive layout & print styles
│   └── js/
│       └── app.js              # Frontend controller, API integration, Cart management & Chart.js
│
├── tests/
│   ├── test_retail_store.py    # Unit & Integration tests for DSA, stock atomicity, shifts, & P&L
│   └── test_api_endpoints.py   # FastAPI HTTP endpoint tests for checkout, returns, and dashboard
│
├── run_retail_pos.py           # 1-Click launcher script (auto-starts server & opens browser)
└── README.md                   # Technical documentation
```

---

## 🚀 Quick Start Guide

### 1. Requirements
- Python 3.10+
- Dependencies: `fastapi`, `uvicorn`, `pydantic`

### 2. Launch the Application (1-Click)
Run the master launcher script from the project root:
```bash
python run_retail_pos.py
```
This will:
1. Initialize the SQLite database at `data/retail_store.db`.
2. Seed FMCG supermarket products, frequent customers with real visit histories, expenses, and orders.
3. Start the FastAPI server on `http://localhost:8000`.
4. Automatically open your default web browser to the POS interface.

### 3. Run the Automated Test Suite
To execute all 27 comprehensive unit, integration, and API tests:
```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

### 4. Interactive REST API Documentation
Explore the full Swagger interactive API documentation at:
```
http://localhost:8000/docs
```

Key REST API endpoints:
- `POST /api/pos/calculate` - Preview cart subtotal, GST, discounts, and customer savings
- `POST /api/pos/checkout` - Execute atomic ACID sale transaction with branch stock deduction
- `GET /api/customers/recognize?identifier=` - Smart Customer Recognition via mobile (+91) or 2D QR Code
- `GET /api/customers/{identifier}/insights` - Customer shopping habits, category spend %, top products
- `GET /api/analytics/business-intelligence?branch_id=` - 5-Pillar Business Intelligence analytics suite
- `GET /api/orders` & `GET /api/orders/{bill_number}` - Order history with thermal receipt and A4 tax invoice
- `POST /api/returns/process` - Process customer returns with manager PIN and stock restoration
- `POST /api/orders/{bill_number}/void` - Void order and restore inventory atomically
- `GET /api/shifts/current` & `POST /api/shifts/close` - Shift cash management and day-end Z-Report
- `GET /api/expenses` & `POST /api/expenses` - Periodic operating expenses ledger (Weekly, Monthly, Yearly)
- `GET /api/dashboard?branch_id=` - Multi-period executive P&L metrics with branch filtering
- `GET /api/branches` & `POST /api/branches` - Multi-branch store management and registration
- `GET /api/branches/{id}/inventory` - Branch-specific physical shelf stock levels
- `POST /api/inventory/transfer` - Atomic inter-branch stock logistics with dual movement logs

---

## 🔐 Default Authorization PINs
- **Store Manager PIN**: `2222` (Used to authorize refunds, void bills, and stock adjustments)
- **System Admin PIN**: `9999` (Master administrative override)
