"""
Enterprise POS Transaction Exceptions
Defines typed domain exceptions for transaction failures, stock depletion,
tender mismatches, and authorization violations.
"""


class POSTransactionError(ValueError):
    """Base exception for all POS transaction processing failures."""
    def __init__(self, message: str, code: str = "TRANSACTION_FAILED"):
        super().__init__(message)
        self.message = message
        self.code = code


class InsufficientStockError(POSTransactionError):
    """Raised when available shelf stock is less than the requested billing quantity."""
    def __init__(self, barcode: str, product_name: str, available: int, requested: int):
        message = (
            f"Insufficient stock for '{product_name}' (Barcode: {barcode}). "
            f"Requested: {requested}, Available on shelf: {available}."
        )
        super().__init__(message, code="INSUFFICIENT_STOCK")
        self.barcode = barcode
        self.product_name = product_name
        self.available = available
        self.requested = requested


class ProductNotFoundError(POSTransactionError):
    """Raised when a scanned barcode does not exist in the active store catalog."""
    def __init__(self, barcode: str):
        message = f"Product with barcode '{barcode}' was not found in the supermarket catalog."
        super().__init__(message, code="PRODUCT_NOT_FOUND")
        self.barcode = barcode


class InvalidPaymentTenderError(POSTransactionError):
    """Raised when tendered cash or split payment amounts do not cover the payable bill total."""
    def __init__(self, tendered: float, payable: float, details: str = ""):
        message = (
            f"Payment tender mismatch: Tendered amount ₹{tendered:.2f} is less than "
            f"payable grand total ₹{payable:.2f}. {details}".strip()
        )
        super().__init__(message, code="INVALID_PAYMENT_TENDER")
        self.tendered = tendered
        self.payable = payable


class UnauthorizedManagerError(POSTransactionError):
    """Raised when an operation requires Store Manager or Admin PIN authorization."""
    def __init__(self, reason: str = "Valid Store Manager or Admin PIN required."):
        super().__init__(f"Authorization Denied: {reason}", code="UNAUTHORIZED_MANAGER")


class OrderStateError(POSTransactionError):
    """Raised when attempting an invalid state transition (e.g. refunding or voiding a cancelled bill)."""
    def __init__(self, bill_number: str, current_state: str, action: str):
        message = f"Cannot perform '{action}' on bill '{bill_number}': current status is '{current_state}'."
        super().__init__(message, code="INVALID_ORDER_STATE")
        self.bill_number = bill_number
        self.current_state = current_state
        self.action = action

