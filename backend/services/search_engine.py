"""
Real-Time POS Search Engine (Powered by Prefix Trie)
Under-the-hood DSA: Provides instant O(K) barcode and product lookup for the checkout counter,
enabling instant autocomplete keystroke searches across tens of thousands of supermarket SKUs.
"""

from typing import Dict, List, Optional, Any


class TrieNode:
    """Node in the checkout search Prefix Tree."""
    def __init__(self, char: str = ""):
        self.char = char
        self.children: Dict[str, TrieNode] = {}
        self.is_terminal: bool = False
        self.payload: Optional[Any] = None
        self.frequency: int = 0


class ProductSearchEngine:
    """
    High-velocity in-memory search index for cashier barcode scanning and search.
    Supports barcode prefix match, SKU search, and tokenized keyword search.
    """

    def __init__(self):
        self.root = TrieNode()
        self._total_entries = 0

    def insert(self, key: str, product_payload: Any) -> None:
        """Inserts a key (barcode, name, keyword) into the Prefix Trie in O(K) time."""
        if not key:
            return

        normalized = key.strip().lower()
        curr = self.root

        for char in normalized:
            if char not in curr.children:
                curr.children[char] = TrieNode(char)
            curr = curr.children[char]

        curr.is_terminal = True
        curr.payload = product_payload
        curr.frequency += 1
        self._total_entries += 1

    def search_exact_barcode(self, barcode: str) -> Optional[Any]:
        """Direct O(K) barcode scan lookup."""
        curr = self.root
        for char in barcode.strip().lower():
            if char not in curr.children:
                return None
            curr = curr.children[char]
        return curr.payload if curr.is_terminal else None

    def search_prefix(self, query: str, limit: int = 8) -> List[Any]:
        """
        Instant prefix search across barcodes and item titles.
        Returns product records matching the prefix in O(P + M) time.
        """
        results: List[Any] = []
        if not query:
            return results

        normalized = query.strip().lower()
        curr = self.root
        for char in normalized:
            if char not in curr.children:
                return results
            curr = curr.children[char]

        # Collect matches via Depth-First Search
        self._dfs_collect(curr, results, limit)
        return results

    def _dfs_collect(self, node: TrieNode, results: List[Any], limit: int) -> None:
        if len(results) >= limit:
            return

        if node.is_terminal and node.payload is not None:
            results.append(node.payload)

        for char in sorted(node.children.keys()):
            self._dfs_collect(node.children[char], results, limit)
            if len(results) >= limit:
                break

    def index_product(self, product: Any) -> None:
        """Indexes a product by barcode, SKU, full name, and word tokens."""
        # 1. Barcode (e.g. 8901030889211)
        self.insert(product.barcode, product)
        # 2. SKU (e.g. SKU-GRO-001)
        self.insert(product.sku, product)
        # 3. Full Name
        self.insert(product.name, product)
        # 4. Brand
        self.insert(product.brand, product)
        # 5. Individual words for fast partial typing (e.g., 'Atta', 'Amul', 'Rice')
        for word in product.name.split():
            clean_word = "".join(c for c in word if c.isalnum())
            if len(clean_word) >= 2:
                self.insert(clean_word, product)

