"""
Executive Store Dashboard & Profit/Loss Analytics Service
Computes multi-period revenue, COGS, expenses, net profits, and stock risk telemetry
directly from unified, consistent SQLite database records.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Any, Optional

from backend.models.domain import round_curr, OrderStatus
from backend.services.expense_service import ExpenseService
from backend.services.inventory_pq import InventoryPriorityQueue
from backend.storage.repository import RetailRepository


class AnalyticsService:
    def __init__(
        self,
        repo: RetailRepository,
        expense_service: ExpenseService,
        inventory_pq: InventoryPriorityQueue
    ):
        self.repo = repo
        self.expense_service = expense_service
        self.inventory_pq = inventory_pq

    def get_dashboard_metrics(self, branch_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Calculates store KPIs across:
          - Today
          - This Week
          - This Month
          - This Year
        Grounded directly in consistent SQLite database records for completed orders,
        customer returns/refunds, and store operating expenses.
        Supports single branch filtering or consolidated enterprise-wide reporting.
        """
        now = datetime.now()
        today_date = now.date()

        # If branch_id is "ALL", treat as None for chain-wide consolidation
        target_branch = None if (not branch_id or branch_id.upper() == "ALL") else branch_id.strip()

        start_of_today = datetime.combine(today_date, datetime.min.time())
        end_of_today = datetime.combine(today_date, datetime.max.time())

        start_of_week = datetime.combine(today_date - timedelta(days=today_date.weekday()), datetime.min.time())
        start_of_month = datetime.combine(date(today_date.year, today_date.month, 1), datetime.min.time())
        start_of_year = datetime.combine(date(today_date.year, 1, 1), datetime.min.time())

        # Exact financial summaries derived directly from database tables
        today_fin = self.repo.get_financial_summary_by_date_range(start_of_today, end_of_today, branch_id=target_branch)
        week_fin = self.repo.get_financial_summary_by_date_range(start_of_week, now, branch_id=target_branch)
        month_fin = self.repo.get_financial_summary_by_date_range(start_of_month, now, branch_id=target_branch)
        year_fin = self.repo.get_financial_summary_by_date_range(start_of_year, now, branch_id=target_branch)

        # Completed orders for category distribution, top products, and 7-day trend
        completed_orders = self.repo.list_completed_orders(branch_id=target_branch)

        category_revenue: Dict[str, Decimal] = {}
        product_sales_volume: Dict[str, Dict[str, Any]] = {}

        for o in completed_orders:
            for item in o.items:
                if not item.is_returned:
                    cat = item.category
                    category_revenue[cat] = category_revenue.get(cat, Decimal("0.00")) + item.net_total

                    if item.product_name not in product_sales_volume:
                        product_sales_volume[item.product_name] = {
                            "name": item.product_name,
                            "category": item.category,
                            "quantity": 0,
                            "revenue": Decimal("0.00")
                        }
                    product_sales_volume[item.product_name]["quantity"] += item.quantity
                    product_sales_volume[item.product_name]["revenue"] += item.net_total

        # Top 8 fast moving items by volume
        top_products = sorted(
            product_sales_volume.values(),
            key=lambda x: x["quantity"],
            reverse=True
        )[:8]

        top_products_formatted = [
            {
                "name": p["name"],
                "category": p["category"],
                "units_sold": p["quantity"],
                "revenue": float(round_curr(p["revenue"]))
            }
            for p in top_products
        ]

        # Critical stock alerts from Min-Heap Priority Queue
        critical_alerts = self.inventory_pq.get_critical_alerts(threshold_ratio=1.0, limit=8)

        # 7-Day sales trend for chart
        last_7_days_sales = self._get_7_day_trend(completed_orders, today_date)

        return {
            "today": {
                "revenue": today_fin["net_revenue"],
                "gross_revenue": today_fin["gross_revenue"],
                "refunds": today_fin["refunds_issued"],
                "cogs": today_fin["net_cogs"],
                "expenses": today_fin["operating_expenses"],
                "gross_profit": today_fin["gross_profit"],
                "net_profit": today_fin["net_operating_profit"],
                "orders_count": today_fin["completed_orders"],
                "profit_margin_pct": today_fin["net_profit_margin_percent"],
                "avg_bill": float(round_curr(Decimal(str(today_fin["net_revenue"])) / Decimal(max(1, today_fin["completed_orders"]))))
            },
            "weekly": {
                "revenue": week_fin["net_revenue"],
                "gross_revenue": week_fin["gross_revenue"],
                "refunds": week_fin["refunds_issued"],
                "cogs": week_fin["net_cogs"],
                "expenses": week_fin["operating_expenses"],
                "gross_profit": week_fin["gross_profit"],
                "net_profit": week_fin["net_operating_profit"],
                "orders_count": week_fin["completed_orders"],
                "profit_margin_pct": week_fin["net_profit_margin_percent"]
            },
            "monthly": {
                "revenue": month_fin["net_revenue"],
                "gross_revenue": month_fin["gross_revenue"],
                "refunds": month_fin["refunds_issued"],
                "cogs": month_fin["net_cogs"],
                "expenses": month_fin["operating_expenses"],
                "gross_profit": month_fin["gross_profit"],
                "net_profit": month_fin["net_operating_profit"],
                "orders_count": month_fin["completed_orders"],
                "profit_margin_pct": month_fin["net_profit_margin_percent"]
            },
            "yearly": {
                "revenue": year_fin["net_revenue"],
                "gross_revenue": year_fin["gross_revenue"],
                "refunds": year_fin["refunds_issued"],
                "cogs": year_fin["net_cogs"],
                "expenses": year_fin["operating_expenses"],
                "gross_profit": year_fin["gross_profit"],
                "net_profit": year_fin["net_operating_profit"],
                "orders_count": year_fin["completed_orders"],
                "profit_margin_pct": year_fin["net_profit_margin_percent"]
            },
            "customer_savings_total": week_fin["total_savings"],
            "category_revenue": {k: float(round_curr(v)) for k, v in category_revenue.items()},
            "top_products": top_products_formatted,
            "critical_stock_alerts": critical_alerts,
            "chart_trend": last_7_days_sales,
            "branch_id": target_branch or "ALL",
            "branch_breakdown": month_fin.get("branch_breakdown", []),
        }

    def get_financial_summary(self, period: str = "today", branch_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Returns financial metrics for a specific period (today, weekly, monthly, yearly)
        computed from consistent database records.
        """
        metrics = self.get_dashboard_metrics(branch_id=branch_id)
        period_data = metrics.get(period.lower(), metrics.get("today", {}))
        return {
            **period_data,
            "completed_orders": period_data.get("orders_count", 0),
            "net_revenue": period_data.get("revenue", 0.0),
            "net_cogs": period_data.get("cogs", 0.0),
            "branch_id": metrics.get("branch_id", "ALL"),
            "branch_breakdown": metrics.get("branch_breakdown", []),
        }

    def get_comprehensive_business_intelligence(self, branch_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Deep Business Intelligence Suite for Supermarkets:
        1. Best-selling products (volume, gross revenue, profit contribution, margin %)
        2. Slow-moving stock (stagnant inventory with idle capital locked & risk rating)
        3. Customer retention & churn intelligence (repeat rate %, loyalty cohorts, churn risk)
        4. Seasonal & periodic demand patterns (day-of-week surges, peak shopping hours)
        5. Products needing restocking (Min-Heap priority, depletion ratio, suggested order qty)
        """
        target_branch = None if (not branch_id or branch_id.upper() == "ALL") else branch_id.strip()
        now = datetime.now()
        thirty_days_ago = now - timedelta(days=30)

        # Retrieve completed orders for the branch or chain-wide
        completed_orders = self.repo.list_completed_orders(branch_id=target_branch)
        all_products = self.repo.list_products()

        # Branch-specific inventory mapping if a branch is chosen
        branch_inventory_map = {}
        if target_branch:
            b_inv = self.repo.list_branch_inventory(target_branch)
            for item in b_inv:
                branch_inventory_map[item["barcode"]] = item["stock_quantity"]

        # -------------------------------------------------------------
        # 1. BEST-SELLING PRODUCTS (Volume, Revenue, Profit Margins)
        # -------------------------------------------------------------
        product_performance: Dict[str, Dict[str, Any]] = {}
        for p in all_products:
            product_performance[p.barcode] = {
                "barcode": p.barcode,
                "sku": p.sku,
                "name": p.name,
                "category": p.category,
                "brand": p.brand,
                "cost_price": float(p.cost_price),
                "selling_price": float(p.selling_price),
                "current_stock": branch_inventory_map.get(p.barcode, p.stock_quantity),
                "reorder_level": p.reorder_level,
                "units_sold_30d": 0,
                "total_units_sold": 0,
                "gross_revenue": Decimal("0.00"),
                "total_cost": Decimal("0.00"),
                "gross_profit": Decimal("0.00")
            }

        # Analyze line items in completed orders
        for o in completed_orders:
            is_recent_30d = o.created_at >= thirty_days_ago
            for item in o.items:
                if not item.is_returned:
                    bc = item.barcode
                    if bc not in product_performance:
                        product_performance[bc] = {
                            "barcode": bc,
                            "sku": item.barcode,
                            "name": item.product_name,
                            "category": item.category,
                            "brand": "General",
                            "cost_price": float(item.cost_price),
                            "selling_price": float(item.unit_price),
                            "current_stock": 0,
                            "reorder_level": 10,
                            "units_sold_30d": 0,
                            "total_units_sold": 0,
                            "gross_revenue": Decimal("0.00"),
                            "total_cost": Decimal("0.00"),
                            "gross_profit": Decimal("0.00")
                        }

                    product_performance[bc]["total_units_sold"] += item.quantity
                    product_performance[bc]["gross_revenue"] += item.net_total
                    c_cost = item.cost_price * item.quantity
                    product_performance[bc]["total_cost"] += c_cost
                    product_performance[bc]["gross_profit"] += (item.net_total - c_cost)

                    if is_recent_30d:
                        product_performance[bc]["units_sold_30d"] += item.quantity

        # Rank Best Sellers
        sorted_by_revenue = sorted(
            [p for p in product_performance.values() if p["total_units_sold"] > 0],
            key=lambda x: (x["gross_revenue"], x["total_units_sold"]),
            reverse=True
        )

        best_selling_products = []
        for idx, p in enumerate(sorted_by_revenue[:10], start=1):
            rev = p["gross_revenue"]
            profit = p["gross_profit"]
            margin_pct = float(round((profit / rev * 100), 1)) if rev > Decimal("0.00") else 0.0
            best_selling_products.append({
                "rank": idx,
                "barcode": p["barcode"],
                "sku": p["sku"],
                "name": p["name"],
                "category": p["category"],
                "brand": p["brand"],
                "units_sold": p["total_units_sold"],
                "units_sold_30d": p["units_sold_30d"],
                "gross_revenue": float(round_curr(rev)),
                "gross_profit": float(round_curr(profit)),
                "profit_margin_percent": margin_pct,
                "current_stock": p["current_stock"]
            })

        # -------------------------------------------------------------
        # 2. SLOW-MOVING & DEAD STOCK (Tied-up Working Capital)
        # -------------------------------------------------------------
        slow_moving_candidates = []
        total_locked_capital = Decimal("0.00")

        for bc, p in product_performance.items():
            stock = p["current_stock"]
            if stock > 0:
                units_30d = p["units_sold_30d"]
                cost = Decimal(str(p["cost_price"]))
                locked_capital = round_curr(cost * Decimal(stock))

                # Identify slow-moving: sales in 30 days <= 2
                if units_30d <= 2:
                    total_locked_capital += locked_capital
                    if units_30d == 0:
                        risk_level = "CRITICAL_DEAD_STOCK" if locked_capital >= Decimal("5000.00") else "HIGH_RISK"
                        action = "Weekend Clearance 25% Off / RTV Supplier Return"
                    elif units_30d <= 1:
                        risk_level = "HIGH_RISK"
                        action = "Promotional 15% Markdown / Bundle with Top Seller"
                    else:
                        risk_level = "MODERATE_SLOW"
                        action = "Reposition to Eye-Level Endcap Display"

                    slow_moving_candidates.append({
                        "barcode": p["barcode"],
                        "sku": p["sku"],
                        "name": p["name"],
                        "category": p["category"],
                        "brand": p["brand"],
                        "current_stock": stock,
                        "units_sold_30d": units_30d,
                        "cost_price": float(cost),
                        "selling_price": float(p["selling_price"]),
                        "capital_locked": float(locked_capital),
                        "risk_level": risk_level,
                        "recommended_action": action
                    })

        # Sort slow-moving by capital locked descending
        slow_moving_stock = sorted(slow_moving_candidates, key=lambda x: x["capital_locked"], reverse=True)

        # -------------------------------------------------------------
        # 3. CUSTOMER RETENTION & CHURN INTELLIGENCE
        # -------------------------------------------------------------
        all_customers = self.repo.list_customers(limit=1000)
        total_customers = len(all_customers)
        returning_customers = sum(1 for c in all_customers if c.visit_count >= 2)
        single_visit_customers = total_customers - returning_customers
        repeat_rate = round((returning_customers / total_customers * 100), 1) if total_customers > 0 else 0.0

        # Loyalty Tier cohorts
        tier_cohorts = {
            "PLATINUM": {"count": 0, "spend": Decimal("0.00")},
            "GOLD": {"count": 0, "spend": Decimal("0.00")},
            "SILVER": {"count": 0, "spend": Decimal("0.00")},
            "BRONZE": {"count": 0, "spend": Decimal("0.00")},
        }
        for c in all_customers:
            t_val = c.tier.value
            if t_val in tier_cohorts:
                tier_cohorts[t_val]["count"] += 1
                tier_cohorts[t_val]["spend"] += c.total_spent

        # Churn telemetry
        active_customers = sum(1 for c in all_customers if c.days_since_last_visit <= 14)
        at_risk_customers = sum(1 for c in all_customers if 14 < c.days_since_last_visit <= 45)
        dormant_customers = sum(1 for c in all_customers if c.days_since_last_visit > 45)

        total_customer_spend = sum((c.total_spent for c in all_customers), Decimal("0.00"))
        avg_ltv = round_curr(total_customer_spend / Decimal(max(1, total_customers)))

        customer_retention = {
            "total_customers": total_customers,
            "returning_customers": returning_customers,
            "single_visit_customers": single_visit_customers,
            "repeat_customer_rate_percent": repeat_rate,
            "average_lifetime_value": float(avg_ltv),
            "churn_status": {
                "active_recent": active_customers,
                "at_risk_cooling": at_risk_customers,
                "dormant_churned": dormant_customers
            },
            "tier_distribution": [
                {"tier": k, "customers_count": v["count"], "total_spend": float(round_curr(v["spend"]))}
                for k, v in tier_cohorts.items()
            ]
        }

        # -------------------------------------------------------------
        # 4. SEASONAL & PERIODIC DEMAND PATTERNS
        # -------------------------------------------------------------
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        dow_revenue = {d: Decimal("0.00") for d in day_names}
        dow_orders = {d: 0 for d in day_names}

        hour_labels = [f"{h:02d}:00" for h in range(8, 23)]
        hourly_orders = {h: 0 for h in hour_labels}
        hourly_revenue = {h: Decimal("0.00") for h in hour_labels}

        cat_demand: Dict[str, Dict[str, Any]] = {}

        for o in completed_orders:
            d_name = o.created_at.strftime("%A")
            if d_name in dow_revenue:
                dow_revenue[d_name] += o.grand_total
                dow_orders[d_name] += 1

            h_str = f"{o.created_at.hour:02d}:00"
            if h_str in hourly_orders:
                hourly_orders[h_str] += 1
                hourly_revenue[h_str] += o.grand_total

            for it in o.items:
                if not it.is_returned:
                    c = it.category or "Groceries"
                    if c not in cat_demand:
                        cat_demand[c] = {"category": c, "revenue": Decimal("0.00"), "units": 0}
                    cat_demand[c]["revenue"] += it.net_total
                    cat_demand[c]["units"] += it.quantity

        day_of_week_pattern = [
            {"day": d, "revenue": float(round_curr(dow_revenue[d])), "orders_count": dow_orders[d]}
            for d in day_names
        ]

        hourly_peak_pattern = [
            {"hour": h, "orders_count": hourly_orders[h], "revenue": float(round_curr(hourly_revenue[h]))}
            for h in hour_labels
        ]

        total_cat_rev = sum((c["revenue"] for c in cat_demand.values()), Decimal("0.00"))
        category_demand_pattern = [
            {
                "category": c["category"],
                "revenue": float(round_curr(c["revenue"])),
                "units_sold": c["units"],
                "share_percent": float(round((c["revenue"] / total_cat_rev * 100), 1)) if total_cat_rev > 0 else 0.0
            }
            for c in sorted(cat_demand.values(), key=lambda x: x["revenue"], reverse=True)
        ]

        seasonal_demand = {
            "day_of_week": day_of_week_pattern,
            "hourly_peaks": hourly_peak_pattern,
            "category_distribution": category_demand_pattern,
            "busiest_day": max(day_of_week_pattern, key=lambda x: x["revenue"])["day"] if day_of_week_pattern else "Saturday",
            "peak_hour": max(hourly_peak_pattern, key=lambda x: x["orders_count"])["hour"] if hourly_peak_pattern else "18:00"
        }

        # -------------------------------------------------------------
        # 5. PRODUCTS THAT NEED RESTOCKING (Restock Priority Queue)
        # -------------------------------------------------------------
        restock_items = []
        total_restock_budget = Decimal("0.00")

        for p in all_products:
            stock = branch_inventory_map.get(p.barcode, p.stock_quantity)
            reorder = p.reorder_level
            if stock <= reorder:
                depletion_ratio = round(stock / max(1, reorder), 2)
                suggested_qty = max(5, (reorder * 3) - stock)
                cost = p.cost_price
                est_cost = round_curr(cost * Decimal(suggested_qty))
                total_restock_budget += est_cost

                if stock == 0:
                    urgency = "EMERGENCY_OUT_OF_STOCK"
                    badge_color = "danger"
                elif depletion_ratio <= 0.5:
                    urgency = "CRITICAL_LOW_STOCK"
                    badge_color = "warning"
                else:
                    urgency = "REORDER_RECOMMENDED"
                    badge_color = "info"

                restock_items.append({
                    "barcode": p.barcode,
                    "sku": p.sku,
                    "name": p.name,
                    "category": p.category,
                    "brand": p.brand,
                    "current_stock": stock,
                    "reorder_level": reorder,
                    "depletion_ratio": depletion_ratio,
                    "urgency": urgency,
                    "badge_color": badge_color,
                    "suggested_order_quantity": suggested_qty,
                    "unit_cost": float(cost),
                    "estimated_restock_cost": float(est_cost),
                    "supplier": getattr(p, "supplier_name", "Primary FMCG Distributor") or "Primary FMCG Distributor"
                })

        restock_priority_queue = sorted(restock_items, key=lambda x: (x["current_stock"], x["depletion_ratio"]))

        return {
            "branch_id": target_branch or "ALL",
            "evaluated_at": now.strftime("%d-%b-%Y %I:%M %p"),
            "best_selling_products": best_selling_products,
            "slow_moving_stock": {
                "items": slow_moving_stock,
                "total_slow_items_count": len(slow_moving_stock),
                "total_locked_capital": float(round_curr(total_locked_capital))
            },
            "customer_retention": customer_retention,
            "seasonal_demand": seasonal_demand,
            "restock_priority": {
                "items": restock_priority_queue,
                "items_needing_restock_count": len(restock_priority_queue),
                "out_of_stock_count": sum(1 for r in restock_priority_queue if r["current_stock"] == 0),
                "estimated_total_restock_cost": float(round_curr(total_restock_budget))
            }
        }

    def _get_7_day_trend(self, orders: List[Any], today: date) -> List[Dict[str, Any]]:
        trend = []
        for i in range(6, -1, -1):
            target_day = today - timedelta(days=i)
            day_str = target_day.strftime("%a (%d %b)")
            day_rev = Decimal("0.00")
            day_count = 0
            for o in orders:
                if o.created_at.date() == target_day and o.status == OrderStatus.COMPLETED:
                    day_rev += o.grand_total
                    day_count += 1
            trend.append({
                "date": day_str,
                "revenue": float(round_curr(day_rev)),
                "orders_count": day_count
            })
        return trend
