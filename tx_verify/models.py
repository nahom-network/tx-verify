"""Unified result model shared across all payment verifiers."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class TransactionResult:
    """Standard verification result returned by every provider.

    Fields that appear on every receipt are typed attributes.
    Provider-specific or variable fields go into ``meta``.
    """

    success: bool
    error: str | None = None

    provider: str | None = None
    transaction_reference: str | None = None
    receipt_number: str | None = None

    payer_name: str | None = None
    payer_account: str | None = None
    payer_phone: str | None = None

    receiver_name: str | None = None
    receiver_account: str | None = None

    amount: float | None = None
    service_charge: float | None = None
    vat: float | None = None
    total_amount: float | None = None
    amount_in_words: str | None = None

    transaction_date: datetime | None = None
    transaction_type: str | None = None
    transaction_status: str | None = None
    payment_channel: str | None = None
    payment_method: str | None = None
    narrative: str | None = None
    currency: str | None = None

    meta: dict[str, Any] = field(default_factory=dict)
