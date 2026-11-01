"""
High-Performance In-Memory Cache Service (Powered by LRU Cache)
Under-the-hood DSA: Combines a Doubly-Linked List + Hash Map to achieve strictly
O(1) lookups and O(1) writes for active cashier customer sessions and price data.
"""

from typing import Generic, TypeVar, Optional, Dict, Any
import threading

K = TypeVar("K")
V = TypeVar("V")


class DListNode(Generic[K, V]):
    def __init__(self, key: Optional[K] = None, value: Optional[V] = None):
        self.key: Optional[K] = key
        self.value: Optional[V] = value
        self.prev: Optional["DListNode[K, V]"] = None
        self.next: Optional["DListNode[K, V]"] = None


class LRUCacheService(Generic[K, V]):
    """Thread-safe LRU Cache ensuring instant O(1) response times."""

    def __init__(self, capacity: int = 500):
        self.capacity = capacity
        self._map: Dict[K, DListNode[K, V]] = {}
        self._head = DListNode[K, V]()
        self._tail = DListNode[K, V]()
        self._head.next = self._tail
        self._tail.prev = self._head
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def _add_to_front(self, node: DListNode[K, V]) -> None:
        node.prev = self._head
        node.next = self._head.next
        if self._head.next:
            self._head.next.prev = node
        self._head.next = node

    def _remove(self, node: DListNode[K, V]) -> None:
        if node.prev:
            node.prev.next = node.next
        if node.next:
            node.next.prev = node.prev

    def get(self, key: K) -> Optional[V]:
        with self._lock:
            node = self._map.get(key)
            if not node:
                self._misses += 1
                return None
            self._hits += 1
            self._remove(node)
            self._add_to_front(node)
            return node.value

    def put(self, key: K, value: V) -> None:
        with self._lock:
            if key in self._map:
                node = self._map[key]
                node.value = value
                self._remove(node)
                self._add_to_front(node)
                return

            new_node = DListNode(key, value)
            self._map[key] = new_node
            self._add_to_front(new_node)

            if len(self._map) > self.capacity:
                lru = self._tail.prev
                if lru and lru != self._head:
                    self._remove(lru)
                    if lru.key in self._map:
                        del self._map[lru.key]

    def invalidate(self, key: K) -> None:
        with self._lock:
            if key in self._map:
                node = self._map.pop(key)
                self._remove(node)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100.0) if total > 0 else 0.0
            return {
                "size": len(self._map),
                "capacity": self.capacity,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate_percent": round(hit_rate, 1)
            }

