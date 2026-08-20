"""Custom service-layer exceptions."""


class BusinessRuleError(Exception):
    """Raised when business rules or validations are violated."""


class InsufficientStockError(BusinessRuleError):
    """Raised when a sale cannot be fulfilled with available stock."""
