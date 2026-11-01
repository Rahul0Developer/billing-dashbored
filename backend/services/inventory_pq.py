"""
Inventory Restocking Priority Engine (Powered by Min-Heap Priority Queue)
Under-the-hood DSA: Maintains real-time heap ordering of supermarket products
based on stock depletion ratio: (stock_quantity / reorder_level).
Items closest to empty are extracted at the top of the queue in O(log N) time.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict
from backend.models.domain import Product


@dataclass(order=True)
class RestockItem:
    """Heap wrapper. Lower depletion ratio = higher restocking urgency."""
    urgency_ratio: float
    sequence_id: int
    product: Product = field(compare=False)


class InventoryPriorityQueue:
    """
    Min-Heap Priority Queue managing automated stock replenishment alerts.
    """

    def __init__(self):
        self._heap: List[RestockItem] = []
        self._counter: int = 0

    def push(self, product: Product) -> None:
        """
        Calculates replenishment urgency ratio and inserts in O(log N).
        Urgency ratio = stock_quantity / reorder_level.
        Example: stock=2, reorder=10 -> ratio=0.2 (Extremely urgent!)
        """
        self._counter += 1
        ratio = float(product.stock_quantity) / max(1.0, float(product.reorder_level))
        entry = RestockItem(urgency_ratio=ratio, sequence_id=self._counter, product=product)
        self._heap.append(entry)
        self._sift_up(len(self._heap) - 1)

    def pop(self) -> Optional[Product]:
        """Extracts the most critically depleted product in O(log N)."""
        if not self._heap:
            return None

        top_item = self._heap[0].product
        last_item = self._heap.pop()

        if self._heap:
            self._heap[0] = last_item
            self._sift_down(0)

        return top_item

    def get_critical_alerts(self, threshold_ratio: float = 1.0, limit: int = 10) -> List[Dict[str, Any]]:
        """Returns sorted list of low-stock products needing immediate reorder."""
        # Work on a copy of the heap to avoid mutating the live queue
        copy_items = sorted(self._heap, key=lambda x: x.urgency_ratio)
        alerts = []
        for item in copy_items:
            if item.urgency_ratio <= threshold_ratio:
                p = item.product
                alerts.append({
                    "barcode": p.barcode,
                    "sku": p.sku,
                    "name": p.name,
                    "category": p.category,
                    "current_stock": p.stock_quantity,
                    "reorder_level": p.reorder_level,
                    "urgency_ratio": round(item.urgency_ratio, 2),
                    "is_out_of_stock": p.stock_quantity <= 0
                })
                if len(alerts) >= limit:
                    break
        return alerts

    def _sift_up(self, idx: int) -> None:
        while idx > 0:
            parent = (idx - 1) // 2
            if self._heap[idx] < self._heap[parent]:
                self._heap[idx], self._heap[parent] = self._heap[parent], self._heap[idx]
                idx = parent
            else:
                break

    def _sift_down(self, idx: int) -> None:
        size = len(self._heap)
        while True:
            left = 2 * idx + 1
            right = 2 * idx + 2
            smallest = idx

            if left < size and self._heap[left] < self._heap[smallest]:
                smallest = left
            if right < size and self._heap[right] < self._heap[smallest]:
                smallest = right

            if smallest != idx:
                self._heap[idx], self._heap[smallest] = self._heap[smallest], self._heap[idx]
                idx = smallest
            else:
                break

    def __len__(self) -> int:
        return len(self._heap)

