"""
Inventory & Stock Operations Service
Manages stock adjustments, valuation, bulk CSV imports/exports, and shelf barcode generation.
"""

import csv
from datetime import datetime, date
from decimal import Decimal
import io
from typing import List, Dict, Any, Optional
import uuid

from backend.models.domain import Product, StockMovement, StockMovementType, round_curr
from backend.services.inventory_pq import InventoryPriorityQueue
from backend.services.search_engine import ProductSearchEngine
from backend.storage.repository import RetailRepository


class InventoryService:
    def __init__(
        self,
        repo: RetailRepository,
        inventory_pq: InventoryPriorityQueue,
        search_engine: ProductSearchEngine
    ):
        self.repo = repo
        self.inventory_pq = inventory_pq
        self.search_engine = search_engine

    def adjust_stock(
        self,
        barcode: str,
        new_quantity: int,
        reason_type: str,
        notes: str = "",
        user_id: str = "INVENTORY_MANAGER",
        branch_id: str = "BR-DEL-01",
    ) -> Dict[str, Any]:
        """
        Manually updates product shelf quantity and creates an auditable stock movement record.
        Maintains synchronization between branch inventory and catalog.
        """
        prod = self.repo.get_product_by_barcode(barcode)
        if not prod:
            raise ValueError(f"Product barcode {barcode} was not found.")

        old_stock = prod.stock_quantity
        delta = new_quantity - old_stock
        prod.stock_quantity = new_quantity
        self.repo.save_product(prod)
        self.inventory_pq.push(prod)

        # Update branch inventory allocation
        self.repo.set_branch_stock(branch_id, barcode, new_quantity, prod.reorder_level)

        # Map movement type
        m_type = StockMovementType.MANUAL_CORRECTION
        if reason_type == "DAMAGE":
            m_type = StockMovementType.ADJUSTMENT_DAMAGE
        elif reason_type == "DISCREPANCY":
            m_type = StockMovementType.ADJUSTMENT_DISCREPANCY
        elif reason_type == "RESTOCK":
            m_type = StockMovementType.PURCHASE_RECEIPT

        movement = StockMovement(
            id=f"MOV-{uuid.uuid4().hex[:8].upper()}",
            barcode=barcode,
            movement_type=m_type,
            quantity_change=delta,
            previous_stock=old_stock,
            new_stock=new_quantity,
            reason=f"Stock Adjustment ({reason_type}) [{branch_id}]: {notes}".strip(),
            reference_id="MANUAL_ADJUSTMENT",
            user_id=user_id,
            branch_id=branch_id,
        )
        self.repo.record_stock_movement(movement)

        return {
            "success": True,
            "barcode": barcode,
            "name": prod.name,
            "previous_stock": old_stock,
            "new_stock": new_quantity,
            "delta": delta,
            "branch_id": branch_id,
        }

    def get_branch_inventory(self, branch_id: str = "BR-DEL-01") -> List[Dict[str, Any]]:
        """Returns stock inventory levels allocated to a specific branch."""
        return self.repo.list_branch_inventory(branch_id)

    def transfer_stock(
        self,
        from_branch_id: str,
        to_branch_id: str,
        barcode: str,
        quantity: int,
        reason: str = "Inter-branch balance",
        user_id: str = "MGR-01"
    ) -> Dict[str, Any]:
        """
        Executes an atomic stock transfer between two store branches.
        Generates corresponding TRANSFER_OUT and TRANSFER_IN audit records.
        """
        return self.repo.transfer_stock_between_branches(
            from_branch_id=from_branch_id,
            to_branch_id=to_branch_id,
            barcode=barcode,
            quantity=quantity,
            reason=reason,
            user_id=user_id,
        )

    def get_inventory_valuation(self) -> Dict[str, Any]:
        """Calculates total store stock valuation at procurement cost vs potential retail revenue."""
        products = self.repo.list_products()
        total_items = len(products)
        total_units = sum(p.stock_quantity for p in products)
        total_cost_val = sum((p.inventory_valuation_cost for p in products), Decimal("0.00"))
        total_retail_val = sum((p.inventory_valuation_retail for p in products), Decimal("0.00"))
        potential_gross_margin = total_retail_val - total_cost_val

        out_of_stock_count = sum(1 for p in products if p.stock_quantity <= 0)
        low_stock_count = sum(1 for p in products if 0 < p.stock_quantity <= p.reorder_level)

        return {
            "total_distinct_skus": total_items,
            "total_physical_units": total_units,
            "total_cost_valuation": float(round_curr(total_cost_val)),
            "total_retail_valuation": float(round_curr(total_retail_val)),
            "potential_gross_margin": float(round_curr(potential_gross_margin)),
            "low_stock_items": low_stock_count,
            "out_of_stock_items": out_of_stock_count
        }

    def export_catalog_to_csv(self) -> str:
        """Exports the entire active store catalog to a CSV string."""
        products = self.repo.list_products()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Barcode", "SKU", "Name", "Category", "Brand", "Unit",
            "CostPrice", "SellingPrice", "MRP", "StockQuantity", "ReorderLevel", "TaxRatePercent"
        ])
        for p in products:
            writer.writerow([
                p.barcode, p.sku, p.name, p.category, p.brand, p.unit,
                str(p.cost_price), str(p.selling_price), str(p.mrp),
                p.stock_quantity, p.reorder_level, str(p.tax_rate_percent)
            ])
        return output.getvalue()

    def import_catalog_from_csv(self, csv_text: str) -> Dict[str, Any]:
        """Parses CSV text and batch upserts products into the catalog and Trie search engine."""
        reader = csv.DictReader(io.StringIO(csv_text))
        imported_count = 0
        for row in reader:
            barcode = row.get("Barcode", "").strip()
            if not barcode:
                continue
            prod = Product(
                barcode=barcode,
                sku=row.get("SKU", f"SKU-{barcode[:6]}").strip(),
                name=row.get("Name", "Imported Item").strip(),
                category=row.get("Category", "General").strip(),
                brand=row.get("Brand", "Store Brand").strip(),
                unit=row.get("Unit", "pcs").strip(),
                cost_price=Decimal(row.get("CostPrice", "0.00")),
                selling_price=Decimal(row.get("SellingPrice", "0.00")),
                mrp=Decimal(row.get("MRP", "0.00")),
                stock_quantity=int(row.get("StockQuantity", 0)),
                reorder_level=int(row.get("ReorderLevel", 10)),
                tax_rate_percent=Decimal(row.get("TaxRatePercent", "5.00"))
            )
            self.repo.save_product(prod)
            self.search_engine.index_product(prod)
            self.inventory_pq.push(prod)
            imported_count += 1

        return {"success": True, "imported_products": imported_count}

    def generate_shelf_barcode_tag(self, barcode: str) -> Dict[str, Any]:
        """Generates barcode shelf label payload for price tag printing."""
        prod = self.repo.get_product_by_barcode(barcode)
        if not prod:
            raise ValueError("Product not found.")

        return {
            "barcode": prod.barcode,
            "sku": prod.sku,
            "name": prod.name,
            "category": prod.category,
            "brand": prod.brand,
            "selling_price": float(prod.selling_price),
            "mrp": float(prod.mrp),
            "save_amount": float(prod.discount_on_mrp)
        }

