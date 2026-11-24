"""Enumerations frozen by this work order.

``InvoiceType`` is the default invoice type stored on a profile.  The work
order only distinguishes 普票 (general VAT invoice) and 专票 (special VAT
invoice); the enum is the single place to extend when the invoice-type
dictionary is frozen by the core team.
"""

from __future__ import annotations

from enum import Enum


class InvoiceType(str, Enum):
    general = "general"  # 增值税普通发票
    special = "special"  # 增值税专用发票


class FinanceRole(str, Enum):
    """Roles accepted from the trusted identity headers (S2-IAM stub).

    Only ``finance`` may read a full bank account number; every other role
    sees the masked form everywhere.
    """

    finance = "finance"
    admin = "admin"
    ops = "ops"
    sales = "sales"