"""
Customer Loyalty & Footfall Tracking Service
Monitors customer store visits, loyalty tier auto-promotions, and purchase history.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any

from backend.models.domain import Customer, CustomerTier, round_curr
from backend.services.cache_service import LRUCacheService
from backend.storage.repository import RetailRepository


class CustomerService:
    def __init__(self, repo: RetailRepository, cache: Optional[Any] = None, cache_capacity: int = 500):
        self.repo = repo
        if isinstance(cache, int):
            cache_capacity = cache
            cache = None
        self.cache: LRUCacheService[str, Customer] = cache if isinstance(cache, LRUCacheService) else LRUCacheService(capacity=cache_capacity)

    def lookup_customer(self, identifier: str) -> Optional[Customer]:
        """Looks up customer by mobile number or membership code, checking LRU Cache first."""
        clean = identifier.strip()
        if not clean:
            return None

        # Check Cache
        cached = self.cache.get(clean)
        if cached:
            return cached

        # Check DB via phone or membership QR/card code
        customer = self.repo.get_customer_by_phone_or_code(clean)
        if customer:
            self.cache.put(customer.phone, customer)
            if customer.membership_code:
                self.cache.put(customer.membership_code, customer)
        return customer

    def get_customer_by_phone(self, phone: str) -> Optional[Customer]:
        """Alias for lookup_customer to maintain full backward compatibility."""
        return self.lookup_customer(phone)

    def smart_recognize_customer(self, identifier: str) -> Dict[str, Any]:
        """
        Smart Customer Recognition:
        Identifies customer via phone or membership QR code, auto-retrieves loyalty status,
        tier benefits, purchase history, and shopping habits.
        """
        customer = self.lookup_customer(identifier)
        if not customer:
            return {
                "found": False,
                "identifier": identifier,
                "message": "No customer registered with this mobile number or membership QR code."
            }

        # Retrieve deep purchase history and behavioral insights
        insights = self.repo.get_customer_purchase_insights(customer.phone)

        # Tier discount calculation
        tier_discounts = {
            CustomerTier.BRONZE: 0.0,
            CustomerTier.SILVER: 1.0,
            CustomerTier.GOLD: 2.5,
            CustomerTier.PLATINUM: 5.0,
        }
        tier_disc = tier_discounts.get(customer.tier, 0.0)

        is_returning = customer.visit_count > 1
        visit_badge = f"Returning Customer ({customer.visit_count} visits) ⭐" if is_returning else "New Customer (1st Visit)"

        return {
            "found": True,
            "is_returning": is_returning,
            "visit_badge": visit_badge,
            "phone": customer.phone,
            "name": customer.name,
            "email": customer.email,
            "address": customer.address,
            "membership_code": customer.membership_code or f"MEM-{customer.phone}",
            "membership_qr_data": customer.membership_qr_data,
            "visit_count": customer.visit_count,
            "total_spent": float(customer.total_spent),
            "loyalty_points": customer.loyalty_points,
            "points_cash_value": float(customer.loyalty_points),
            "tier": customer.tier.value,
            "tier_discount_percent": tier_disc,
            "first_visited": customer.first_visited_at.strftime("%d-%b-%Y"),
            "last_visited": customer.last_visited_at.strftime("%d-%b-%Y %I:%M %p"),
            "days_since_last_visit": customer.days_since_last_visit,
            "avg_basket": float(customer.average_basket_value),
            "insights": insights,
            "purchase_history": insights.get("recent_orders", []),
            "category_preferences": insights.get("category_preferences", []),
            "top_purchased_products": insights.get("top_purchased_products", []),
            "digital_card": {
                "name": customer.name,
                "phone": customer.phone,
                "membership_code": customer.membership_code or f"MEM-{customer.phone}",
                "tier": customer.tier.value,
                "loyalty_points": customer.loyalty_points,
                "qr_payload": customer.membership_qr_data
            }
        }

    def get_customer_purchase_insights(self, identifier: str) -> Dict[str, Any]:
        """Calculates deep shopping habits and historical product/category preferences."""
        cust = self.lookup_customer(identifier)
        phone = cust.phone if cust else identifier.strip().replace("+91", "").replace("-", "").replace(" ", "")
        return self.repo.get_customer_purchase_insights(phone)

    def get_or_create_customer(self, phone: str, name: str = "", email: str = "") -> Customer:
        """Retrieves existing profile or registers a new customer upon first store visit."""
        cleaned_phone = phone.strip()
        existing = self.lookup_customer(cleaned_phone)
        if existing:
            if name and not existing.name:
                existing.name = name
                self.repo.save_customer(existing)
            return existing

        # First-time visitor
        new_customer = Customer(
            phone=cleaned_phone,
            membership_code=f"MEM-{cleaned_phone}",
            name=name.strip() or f"Customer-{cleaned_phone[-4:]}",
            email=email.strip(),
            visit_count=1,
            total_spent=Decimal("0.00"),
            loyalty_points=0,
            tier=CustomerTier.BRONZE,
            first_visited_at=datetime.now(),
            last_visited_at=datetime.now(),
            is_active=True
        )
        self.repo.save_customer(new_customer)
        self.cache.put(cleaned_phone, new_customer)
        self.cache.put(new_customer.membership_code, new_customer)
        return new_customer

    def record_completed_visit(self, phone: str, bill_amount: Decimal, points_used: int = 0) -> Customer:
        """Updates visit counter, deducts redeemed points, adds newly earned points, and updates tier."""
        customer = self.get_or_create_customer(phone)
        if points_used > 0:
            customer.loyalty_points = max(0, customer.loyalty_points - points_used)

        customer.record_new_visit(bill_amount)
        self.repo.save_customer(customer)
        self.cache.put(customer.phone, customer)
        if customer.membership_code:
            self.cache.put(customer.membership_code, customer)
        return customer

    def get_customer_retention_intelligence(self) -> Dict[str, Any]:
        """Computes customer retention, visit frequency distribution, and churn risk."""
        customers = self.repo.list_customers(limit=500)
        total = len(customers)
        if total == 0:
            return {
                "total_customers": 0,
                "returning_customers": 0,
                "single_visit_customers": 0,
                "repeat_customer_rate": 0.0,
                "tier_breakdown": {},
                "churn_risk": {"active": 0, "at_risk": 0, "dormant": 0},
                "average_ltv": 0.0
            }

        returning = sum(1 for c in customers if c.visit_count >= 2)
        single_visit = total - returning
        repeat_rate = round((returning / total) * 100, 1)

        tier_counts = {
            "PLATINUM": sum(1 for c in customers if c.tier == CustomerTier.PLATINUM),
            "GOLD": sum(1 for c in customers if c.tier == CustomerTier.GOLD),
            "SILVER": sum(1 for c in customers if c.tier == CustomerTier.SILVER),
            "BRONZE": sum(1 for c in customers if c.tier == CustomerTier.BRONZE),
        }

        # Churn telemetry: Active (< 14 days), At Risk (15-45 days), Dormant (> 45 days)
        active_count = sum(1 for c in customers if c.days_since_last_visit <= 14)
        at_risk_count = sum(1 for c in customers if 14 < c.days_since_last_visit <= 45)
        dormant_count = sum(1 for c in customers if c.days_since_last_visit > 45)

        total_spent_sum = sum((c.total_spent for c in customers), Decimal("0.00"))
        avg_ltv = round_curr(total_spent_sum / Decimal(total))

        return {
            "total_customers": total,
            "returning_customers": returning,
            "single_visit_customers": single_visit,
            "repeat_customer_rate": repeat_rate,
            "tier_breakdown": tier_counts,
            "churn_risk": {
                "active": active_count,
                "at_risk": at_risk_count,
                "dormant": dormant_count
            },
            "average_ltv": float(avg_ltv)
        }

    def list_top_frequent_customers(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Returns top recurring shoppers with visit count & lifetime spending metrics."""
        customers = self.repo.list_customers(limit=limit)
        results = []
        for c in customers:
            results.append({
                "phone": c.phone,
                "name": c.name,
                "membership_code": c.membership_code or f"MEM-{c.phone}",
                "membership_qr_data": c.membership_qr_data,
                "visit_count": c.visit_count,
                "total_spent": float(c.total_spent),
                "loyalty_points": c.loyalty_points,
                "tier": c.tier.value,
                "first_visited": c.first_visited_at.strftime("%Y-%m-%d"),
                "last_visited": c.last_visited_at.strftime("%Y-%m-%d %H:%M"),
                "days_since_last_visit": c.days_since_last_visit,
                "avg_basket": float(c.average_basket_value),
                "is_returning": c.visit_count > 1
            })
        return results

