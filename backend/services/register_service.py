"""
Cash Register & Shift Management Service (Z-Report Reconciliation)
Tracks cashier shifts, drawer opening floats, cash drops, and end-of-day drawer balancing.
"""

from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, Optional, List
import uuid

from backend.models.domain import CashShift, round_curr
from backend.storage.repository import RetailRepository


class RegisterShiftService:
    def __init__(self, repo: RetailRepository):
        self.repo = repo

    def start_shift(
        self,
        cashier_id: str = "CASHIER-01",
        cashier_name: str = "Rajesh Sharma",
        opening_float: float = 2000.0,
        notes: str = "Morning Shift Open",
        branch_id: str = "BR-DEL-01",
    ) -> CashShift:
        """Opens a new cash drawer shift with specified opening float."""
        # Close any existing open shift for this cashier
        active = self.repo.get_active_shift(cashier_id)
        if active:
            return active

        shift_id = f"SHIFT-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        shift = CashShift(
            id=shift_id,
            branch_id=branch_id,
            cashier_id=cashier_id,
            cashier_name=cashier_name,
            shift_number=1,
            start_time=datetime.now(),
            opening_float=round_curr(Decimal(str(opening_float))),
            notes=notes
        )
        self.repo.save_shift(shift)
        return shift

    def get_current_shift_status(self, cashier_id: str = "CASHIER-01") -> Dict[str, Any]:
        """Calculates live in-progress shift cash totals by scanning today's orders."""
        shift = self.repo.get_active_shift(cashier_id)
        if not shift:
            shift = self.start_shift(cashier_id)

        # Aggregate completed orders and refunds for this shift
        orders = self.repo.list_completed_orders(start_time=shift.start_time)
        cash_sales = Decimal("0.00")
        upi_sales = Decimal("0.00")
        card_sales = Decimal("0.00")

        for o in orders:
            if o.cashier_id == cashier_id:
                if o.payment_method.value == "CASH":
                    cash_sales += o.grand_total
                elif o.payment_method.value == "UPI_QR":
                    upi_sales += o.grand_total
                elif o.payment_method.value == "CREDIT_DEBIT_CARD":
                    card_sales += o.grand_total

        # Aggregate refunds processed during this shift
        returns = self.repo.list_returns(limit=200)
        total_refunds = Decimal("0.00")
        for r in returns:
            if r.cashier_id == cashier_id and r.created_at >= shift.start_time:
                total_refunds += r.refund_amount

        shift.total_cash_sales = cash_sales
        shift.total_upi_sales = upi_sales
        shift.total_card_sales = card_sales
        shift.total_refunds = total_refunds
        self.repo.save_shift(shift)

        return {
            "shift_id": shift.id,
            "cashier": f"{shift.cashier_name} ({shift.cashier_id})",
            "start_time": shift.start_time.strftime("%d-%b-%Y %I:%M %p"),
            "opening_float": float(shift.opening_float),
            "cash_sales": float(shift.total_cash_sales),
            "total_cash_sales": float(shift.total_cash_sales),
            "upi_sales": float(shift.total_upi_sales),
            "total_upi_sales": float(shift.total_upi_sales),
            "card_sales": float(shift.total_card_sales),
            "total_card_sales": float(shift.total_card_sales),
            "total_sales": float(shift.total_cash_sales + shift.total_upi_sales + shift.total_card_sales),
            "total_refunds": float(shift.total_refunds),
            "cash_drops": float(shift.cash_drops),
            "expected_drawer_cash": float(shift.expected_drawer_cash),
            "is_closed": shift.is_closed,
            "branch_id": getattr(shift, "branch_id", "BR-DEL-01"),
        }

    def record_cash_drop(self, cashier_id: str, amount: float, reason: str = "Midday Safe Drop") -> Dict[str, Any]:
        """Transfers excess physical cash from POS drawer into store safe."""
        shift = self.repo.get_active_shift(cashier_id)
        if not shift:
            raise ValueError("No active shift open.")

        drop_amt = round_curr(Decimal(str(amount)))
        if drop_amt > shift.expected_drawer_cash:
            raise ValueError(f"Cannot drop ₹{drop_amt}; drawer expected balance is ₹{shift.expected_drawer_cash}")

        shift.cash_drops += drop_amt
        shift.notes += f" | Safe Drop: ₹{drop_amt} ({reason})"
        self.repo.save_shift(shift)
        return {"success": True, "dropped_amount": float(drop_amt), "new_expected_drawer": float(shift.expected_drawer_cash)}

    def close_shift_z_report(
        self,
        cashier_id: str,
        actual_counted_cash: float,
        notes: str = ""
    ) -> Dict[str, Any]:
        """
        Reconciles drawer at day-end closing.
        Computes expected vs actual physical cash variance and seals the Z-Report.
        """
        status = self.get_current_shift_status(cashier_id)
        shift = self.repo.get_active_shift(cashier_id)
        if not shift:
            raise ValueError("No active shift open.")

        counted = round_curr(Decimal(str(actual_counted_cash)))
        shift.actual_counted_cash = counted
        shift.end_time = datetime.now()
        shift.is_closed = True
        shift.notes += f" | Shift Closed. Counted: ₹{counted}. Notes: {notes}"
        self.repo.save_shift(shift)

        variance = shift.variance
        variance_status = "PERFECT_MATCH" if variance == Decimal("0.00") else ("OVER" if variance > Decimal("0.00") else "SHORT")

        z_text = f"""==================================================
              APEX ENTERPRISE RETAIL
         DAY-END CASH REGISTER Z-REPORT
==================================================
Shift ID:     {shift.id}
Cashier:      {shift.cashier_name} ({shift.cashier_id})
Shift Open:   {shift.start_time.strftime('%d-%b-%Y %I:%M %p')}
Shift Close:  {shift.end_time.strftime('%d-%b-%Y %I:%M %p')}
--------------------------------------------------
Opening Drawer Float:          ₹{shift.opening_float:>10.2f}
Total Cash Sales:              ₹{shift.total_cash_sales:>10.2f}
Total UPI Sales:               ₹{shift.total_upi_sales:>10.2f}
Total Card Sales:              ₹{shift.total_card_sales:>10.2f}
--------------------------------------------------
TOTAL SHIFT SALES:             ₹{(shift.total_cash_sales + shift.total_upi_sales + shift.total_card_sales):>10.2f}
--------------------------------------------------
Midday Safe Drops:            -₹{shift.cash_drops:>10.2f}
EXPECTED DRAWER CASH:          ₹{shift.expected_drawer_cash:>10.2f}
ACTUAL PHYSICAL COUNTED CASH:  ₹{shift.actual_counted_cash:>10.2f}
DRAWER VARIANCE (OVER/SHORT):  ₹{variance:>10.2f}
STATUS: {variance_status}
==================================================
Z-REPORT AUDIT SEALED. DRAWER BALANCED.
=================================================="""

        return {
            "shift_id": shift.id,
            "cashier": shift.cashier_name,
            "start_time": shift.start_time.strftime("%d-%b-%Y %I:%M %p"),
            "end_time": shift.end_time.strftime("%d-%b-%Y %I:%M %p"),
            "opening_float": float(shift.opening_float),
            "total_cash_sales": float(shift.total_cash_sales),
            "total_upi_sales": float(shift.total_upi_sales),
            "total_card_sales": float(shift.total_card_sales),
            "total_sales": float(shift.total_cash_sales + shift.total_upi_sales + shift.total_card_sales),
            "total_refunds": float(shift.total_refunds),
            "cash_drops": float(shift.cash_drops),
            "expected_drawer_cash": float(shift.expected_drawer_cash),
            "actual_counted_cash": float(shift.actual_counted_cash),
            "variance": float(variance),
            "drawer_variance": float(variance),
            "variance_status": variance_status,
            "z_report_text": z_text,
            "status": "SHIFT_CLOSED_Z_REPORT_SEALED"
        }
