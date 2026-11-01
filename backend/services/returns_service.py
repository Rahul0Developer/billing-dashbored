"""
Retail Store Returns & Refunds Processing Service
Interfaces with the POSTransactionEngine for atomic returns, inventory restitution,
customer spend rollbacks, and cashier shift balance adjustments.
"""

from typing import List, Dict, Any, Optional

from backend.models.domain import ReturnRecord
from backend.services.inventory_pq import InventoryPriorityQueue
from backend.services.transaction_engine import POSTransactionEngine
from backend.services.search_engine import ProductSearchEngine
from backend.storage.repository import RetailRepository


class ReturnsService:
    def __init__(
        self,
        repo: RetailRepository,
        inventory_pq: InventoryPriorityQueue,
        engine: Optional[POSTransactionEngine] = None
    ):
        self.repo = repo
        self.inventory_pq = inventory_pq
        self.engine = engine or POSTransactionEngine(
            repo=self.repo,
            search_engine=ProductSearchEngine(),
            inventory_pq=self.inventory_pq
        )

    def process_return(
        self,
        bill_number: str,
        items_to_return: List[Dict[str, Any]],
        manager_pin: str,
        cashier_id: str = "CASHIER-01",
        reason: str = "Customer Return / Exchange"
    ) -> Dict[str, Any]:
        """
        Delegates atomic return processing to POSTransactionEngine.
        Ensures inventory restocking, audit movements, customer spend adjustments,
        and cashier shift deductions share a single database transaction.
        """
        return self.engine.process_return(
            bill_number=bill_number,
            items_to_return=items_to_return,
            manager_pin=manager_pin,
            cashier_id=cashier_id,
            reason=reason
        )

    def list_returns(self, limit: int = 50) -> List[Dict[str, Any]]:
        records = self.repo.list_returns(limit=limit)
        return [
            {
                "id": r.id,
                "return_number": r.return_number,
                "original_bill": r.original_bill_number,
                "customer": r.customer_phone or "Walk-in",
                "cashier": r.cashier_id,
                "refund_amount": float(r.refund_amount),
                "reason": r.reason,
                "date": r.created_at.strftime("%d-%b-%Y %I:%M %p")
            }
            for r in records
        ]
