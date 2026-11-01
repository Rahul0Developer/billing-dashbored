"""
Enterprise Billing System - Seed Data Generator
Pre-populates the database with realistic enterprise clients, products,
and historical invoices for demonstration and testing.
"""

from datetime import date, timedelta, datetime
from decimal import Decimal
import uuid

from core.enums import CustomerTier, TaxType, InvoiceStatus, PaymentMethod
from core.models import Address, Customer, Product, InvoiceItem, Invoice, Payment
from storage.database import DatabaseManager
from storage.repository import (
    CustomerRepository,
    ProductRepository,
    InvoiceRepository,
    LedgerRepository,
)
from services.billing_service import BillingService
from services.payment_service import PaymentService
from patterns.builder import InvoiceBuilder


def seed_database(db_manager: DatabaseManager) -> None:
    """Populates realistic commercial records if database is empty."""
    cust_repo = CustomerRepository(db_manager)
    prod_repo = ProductRepository(db_manager)
    inv_repo = InvoiceRepository(db_manager)
    ledger_repo = LedgerRepository(db_manager)

    # Check if already seeded
    if len(cust_repo.list_all()) > 0:
        return

    # 1. Seed Customers
    customers = [
        Customer(
            id="CUST-1001",
            name="Alexander Vance",
            email="finance@acmeglobal.com",
            company_name="Acme Global Corporation",
            tax_identifier="US-EIN-129845110",
            billing_address=Address("450 Mission Street, Floor 18", "San Francisco", "CA", "94105"),
            tier=CustomerTier.ENTERPRISE,
            credit_limit=Decimal("50000.00"),
            outstanding_balance=Decimal("0.00")
        ),
        Customer(
            id="CUST-1002",
            name="Elena Rostova",
            email="ap@nexuscybernetics.io",
            company_name="Nexus Cybernetics Systems",
            tax_identifier="US-EIN-992384112",
            billing_address=Address("100 Tech Square, Suite 400", "Cambridge", "MA", "02139"),
            tier=CustomerTier.VIP,
            credit_limit=Decimal("100000.00"),
            outstanding_balance=Decimal("0.00")
        ),
        Customer(
            id="CUST-1003",
            name="Marcus Sterling",
            email="billing@horizonlogistics.com",
            company_name="Horizon Freight Logistics",
            tax_identifier="US-EIN-441209331",
            billing_address=Address("742 Evergreen Parkway", "Chicago", "IL", "60601"),
            tier=CustomerTier.WHOLESALE,
            credit_limit=Decimal("20000.00"),
            outstanding_balance=Decimal("0.00")
        ),
        Customer(
            id="CUST-1004",
            name="Chloe Bennett",
            email="chloe@stellardesign.studio",
            company_name="Stellar Studio Innovations",
            tax_identifier="US-EIN-662319004",
            billing_address=Address("88 Soho Street", "New York", "NY", "10012"),
            tier=CustomerTier.RETAIL,
            credit_limit=Decimal("4000.00"),
            outstanding_balance=Decimal("0.00")
        ),
    ]
    for c in customers:
        cust_repo.save(c)

    # 2. Seed Products
    products = [
        Product(
            sku="SKU-SRV-001",
            name="Cloud Dedicated Compute Node (64 vCPU, 256GB)",
            category="Infrastructure",
            unit_price=Decimal("450.00"),
            cost_price=Decimal("180.00"),
            stock_quantity=45,
            tax_type=TaxType.STANDARD,
            description="High-performance cloud virtualization cluster instance."
        ),
        Product(
            sku="SKU-SUP-002",
            name="24/7 Enterprise Tier-1 Support SLA",
            category="Services",
            unit_price=Decimal("1200.00"),
            cost_price=Decimal("400.00"),
            stock_quantity=999,
            tax_type=TaxType.STANDARD,
            description="Dedicated technical account manager with 15-minute response SLA."
        ),
        Product(
            sku="SKU-STR-003",
            name="Encrypted NVMe Object Storage (10 TB Block)",
            category="Infrastructure",
            unit_price=Decimal("85.00"),
            cost_price=Decimal("28.00"),
            stock_quantity=150,
            tax_type=TaxType.STANDARD,
            description="Distributed geo-redundant block storage."
        ),
        Product(
            sku="SKU-LIC-004",
            name="Enterprise AI Agent Autonomous Workflow License",
            category="Software",
            unit_price=Decimal("2500.00"),
            cost_price=Decimal("350.00"),
            stock_quantity=500,
            tax_type=TaxType.STANDARD,
            description="Annual per-tenant license for production AI operations."
        ),
        Product(
            sku="SKU-SEC-005",
            name="Zero-Trust Hardware Security Appliance",
            category="Hardware",
            unit_price=Decimal("890.00"),
            cost_price=Decimal("520.00"),
            stock_quantity=20,
            tax_type=TaxType.STANDARD,
            description="Rackmount hardware cryptographic accelerator."
        ),
        Product(
            sku="SKU-AUD-006",
            name="Cybersecurity & SOC-2 Compliance Audit",
            category="Consulting",
            unit_price=Decimal("3500.00"),
            cost_price=Decimal("1500.00"),
            stock_quantity=50,
            tax_type=TaxType.EXEMPT,
            description="Full-scope third-party penetration testing and compliance verification."
        ),
    ]
    for p in products:
        prod_repo.save(p)

    # 3. Create Sample Invoices via BillingService
    billing_svc = BillingService(cust_repo, prod_repo, inv_repo, ledger_repo)
    payment_svc = PaymentService(cust_repo, inv_repo, ledger_repo)

    # Invoice 1: Acme Global (Issued, partially paid)
    builder1 = (
        InvoiceBuilder()
        .for_customer(customers[0])
        .set_dates(date.today() - timedelta(days=25), date.today() + timedelta(days=5))
        .add_line_item(products[0], quantity=4)  # 4 * 450 = 1800
        .add_line_item(products[1], quantity=1)  # 1200
        .apply_order_discount(Decimal("100.00"))
        .with_notes("Q4 Infrastructure Expansion")
    )
    inv1 = billing_svc.create_invoice(builder1)
    billing_svc.issue_invoice(inv1.invoice_number)
    # Acme pays a partial payment
    payment_svc.process_payment(
        invoice_number=inv1.invoice_number,
        amount=Decimal("1500.00"),
        payment_method=PaymentMethod.BANK_TRANSFER,
        transaction_reference="WIRE-ACME-8849",
        notes="Partial progress wire transfer."
    )

    # Invoice 2: Horizon Logistics (Overdue for 45 days!)
    builder2 = (
        InvoiceBuilder()
        .for_customer(customers[2])
        .set_dates(date.today() - timedelta(days=75), date.today() - timedelta(days=45))
        .add_line_item(products[2], quantity=12) # 12 * 85 = 1020
        .add_line_item(products[4], quantity=2)  # 2 * 890 = 1780
        .with_notes("Fleet telematics cloud storage")
    )
    inv2 = billing_svc.create_invoice(builder2)
    inv2 = billing_svc.issue_invoice(inv2.invoice_number)
    # Transition to OVERDUE
    inv2.transition_to(InvoiceStatus.OVERDUE)
    inv_repo.save(inv2)

    # Invoice 3: Stellar Studio (Current issued invoice)
    builder3 = (
        InvoiceBuilder()
        .for_customer(customers[3])
        .set_dates(date.today() - timedelta(days=5), date.today() + timedelta(days=25))
        .add_line_item(products[3], quantity=1)  # 2500
        .with_notes("Design workflow AI license")
    )
    inv3 = billing_svc.create_invoice(builder3)
    billing_svc.issue_invoice(inv3.invoice_number)
