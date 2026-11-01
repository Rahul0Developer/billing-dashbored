"""
Tiered Pricing & Promotional Discount Engine (Powered by Binary Search)
Under-the-hood DSA: Uses binary search (bisect) over sorted slab intervals
to evaluate volume discounts and loyalty benefits in O(log K) logarithmic time.
"""

from bisect import bisect_right
from decimal import Decimal
from typing import List, Tuple, Dict, Any
from backend.models.domain import CustomerTier, round_curr


class LoyaltyPricingEngine:
    """
    Evaluates customer tier perks and promotional basket discounts.
    """

    # Customer loyalty tier percentage discount on total basket
    TIER_DISCOUNT_PERCENT = {
        CustomerTier.BRONZE: Decimal("0.00"),
        CustomerTier.SILVER: Decimal("1.00"),    # 1% off on 5+ visits
        CustomerTier.GOLD: Decimal("2.50"),      # 2.5% off on 15+ visits
        CustomerTier.PLATINUM: Decimal("5.00"),  # 5% off on 30+ visits
    }

    # Volume slabs: Spend thresholds -> additional bill discount %
    # Slabs: [₹0, ₹1000, ₹3000, ₹5000, ₹10000]
    VOLUME_THRESHOLDS = [1000.0, 3000.0, 5000.0, 10000.0]
    VOLUME_RATES = [
        Decimal("0.00"),  # < 1000: 0%
        Decimal("1.50"),  # 1000 - 2999: 1.5%
        Decimal("3.00"),  # 3000 - 4999: 3.0%
        Decimal("5.00"),  # 5000 - 9999: 5.0%
        Decimal("7.50"),  # 10000+: 7.5%
    ]

    @classmethod
    def calculate_basket_discounts(
        cls,
        subtotal: Decimal,
        customer_tier: CustomerTier = CustomerTier.BRONZE
    ) -> Dict[str, Any]:
        """
        Uses Binary Search (bisect_right) to calculate volume discount + tier discount.
        Time Complexity: O(log K) where K is number of slabs.
        """
        if subtotal <= Decimal("0.00"):
            return {
                "tier_discount_pct": Decimal("0.00"),
                "tier_discount_amt": Decimal("0.00"),
                "volume_discount_pct": Decimal("0.00"),
                "volume_discount_amt": Decimal("0.00"),
                "total_discount": Decimal("0.00")
            }

        # 1. Tier Discount
        tier_pct = cls.TIER_DISCOUNT_PERCENT.get(customer_tier, Decimal("0.00"))
        tier_amt = round_curr(subtotal * (tier_pct / Decimal("100.00")))

        # 2. Volume Discount via Binary Search
        idx = bisect_right(cls.VOLUME_THRESHOLDS, float(subtotal))
        volume_pct = cls.VOLUME_RATES[idx]
        volume_amt = round_curr(subtotal * (volume_pct / Decimal("100.00")))

        total_discount = tier_amt + volume_amt

        return {
            "tier_discount_pct": tier_pct,
            "tier_discount_amt": tier_amt,
            "volume_discount_pct": volume_pct,
            "volume_discount_amt": volume_amt,
            "total_discount": total_discount
        }

