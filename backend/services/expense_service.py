"""
Store Expense Management & Periodic Financial Breakdown Service
Calculates Weekly, Monthly, and Yearly operational expenses and Net Profitability.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Any, Optional
import uuid

from backend.models.domain import Expense, ExpenseCategory, round_curr
from backend.storage.repository import RetailRepository


class ExpenseService:
    def __init__(self, repo: RetailRepository):
        self.repo = repo

    def add_expense(
        self,
        category: str,
        amount: float,
        description: str,
        expense_date: Optional[str] = None,
        payment_mode: str = "BANK_TRANSFER",
        vendor_name: str = "",
        receipt_ref: str = "",
        branch_id: str = "BR-DEL-01",
    ) -> Expense:
        """Records a store expense into the financial ledger."""
        dt = date.fromisoformat(expense_date) if expense_date else date.today()
        exp_id = f"EXP-{datetime.now().strftime('%Y%m')}-{uuid.uuid4().hex[:6].upper()}"

        expense = Expense(
            id=exp_id,
            branch_id=branch_id,
            category=ExpenseCategory(category.upper()),
            amount=round_curr(Decimal(str(amount))),
            expense_date=dt,
            description=description,
            payment_mode=payment_mode,
            vendor_name=vendor_name,
            receipt_reference=receipt_ref
        )
        self.repo.save_expense(expense)
        return expense

    def delete_expense(self, expense_id: str) -> bool:
        return self.repo.delete_expense(expense_id)

    def list_expenses(self, limit: int = 100, branch_id: Optional[str] = None) -> List[Dict[str, Any]]:
        target_branch = None if (not branch_id or branch_id.upper() == "ALL") else branch_id.strip()
        expenses = self.repo.list_expenses(limit=limit, branch_id=target_branch)
        return [
            {
                "id": e.id,
                "branch_id": e.branch_id,
                "category": e.category.value,
                "amount": float(e.amount),
                "date": e.expense_date.isoformat(),
                "description": e.description,
                "payment_mode": e.payment_mode,
                "vendor": e.vendor_name,
                "receipt_ref": e.receipt_reference
            }
            for e in expenses
        ]

    def get_periodic_expense_summary(self, as_of_date: Optional[date] = None, branch_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Aggregates store expenses into:
          1. Weekly Expenses (Current 7-day period)
          2. Monthly Expenses (Current calendar month)
          3. Yearly Expenses (Current fiscal year)
        Provides category-level breakdown for auditing.
        """
        today = as_of_date or date.today()
        start_of_week = today - timedelta(days=today.weekday())  # Monday
        start_of_month = date(today.year, today.month, 1)
        start_of_year = date(today.year, 1, 1)

        target_branch = None if (not branch_id or branch_id.upper() == "ALL") else branch_id.strip()
        all_expenses = self.repo.list_expenses(limit=1000, branch_id=target_branch)

        weekly_total = Decimal("0.00")
        monthly_total = Decimal("0.00")
        yearly_total = Decimal("0.00")

        weekly_by_category: Dict[str, Decimal] = {cat.value: Decimal("0.00") for cat in ExpenseCategory}
        monthly_by_category: Dict[str, Decimal] = {cat.value: Decimal("0.00") for cat in ExpenseCategory}
        yearly_by_category: Dict[str, Decimal] = {cat.value: Decimal("0.00") for cat in ExpenseCategory}

        for exp in all_expenses:
            amt = exp.amount
            cat = exp.category.value

            # Yearly
            if exp.expense_date >= start_of_year:
                yearly_total += amt
                yearly_by_category[cat] += amt

            # Monthly
            if exp.expense_date >= start_of_month:
                monthly_total += amt
                monthly_by_category[cat] += amt

            # Weekly
            if exp.expense_date >= start_of_week:
                weekly_total += amt
                weekly_by_category[cat] += amt

        return {
            "period_dates": {
                "today": today.isoformat(),
                "start_of_week": start_of_week.isoformat(),
                "start_of_month": start_of_month.isoformat(),
                "start_of_year": start_of_year.isoformat(),
            },
            "totals": {
                "weekly_expenses": float(round_curr(weekly_total)),
                "monthly_expenses": float(round_curr(monthly_total)),
                "yearly_expenses": float(round_curr(yearly_total)),
            },
            "category_breakdown": {
                "weekly": {k: float(v) for k, v in weekly_by_category.items() if v > Decimal("0.00")},
                "monthly": {k: float(v) for k, v in monthly_by_category.items() if v > Decimal("0.00")},
                "yearly": {k: float(v) for k, v in yearly_by_category.items() if v > Decimal("0.00")},
            }
        }
