"""Fictitious constants and payload factories (no real company/person data)."""

from __future__ import annotations

from uuid import UUID

ORG_ID = UUID("11111111-1111-4111-8111-111111111111")
SITE_ID = UUID("22222222-2222-4222-8222-222222222222")
COMPANY_A = UUID("33333333-3333-4333-8333-333333333333")
COMPANY_B = UUID("44444444-4444-4444-8444-444444444444")
OTHER_ORG_COMPANY = UUID("55555555-5555-4555-8555-555555555555")
OTHER_ORG_ID = UUID("99999999-9999-4999-8999-999999999999")
FINANCE_USER = UUID("66666666-6666-4666-8666-666666666666")
SALES_USER = UUID("77777777-7777-4777-8777-777777777777")

COMPANY_A_NAME = "示例企业甲（虚构）有限公司"
COMPANY_B_NAME = "示例企业乙（虚构）有限公司"

CHARSET = "0123456789ABCDEFGHJKLMNPQRTUWXY"


def make_uscc(prefix17: str) -> str:
    """Independent GB 32100-2015 implementation (weights = 3**i mod 31)."""

    assert len(prefix17) == 17
    total = sum(CHARSET.index(ch) * (pow(3, i, 31)) for i, ch in enumerate(prefix17))
    return prefix17 + CHARSET[(31 - total % 31) % 31]


VALID_USCC = make_uscc("91120116MA05XW123")
VALID_USCC_2 = make_uscc("91350100M000100Y4")
VALID_TAX_15 = "110101123456789"
VALID_TAX_20 = "11010112345678901234"
BANK_ACCOUNT = "6222021234567890123"  # 19 digits, fictitious


def headers(role: str = "finance", *, org: UUID = ORG_ID, user: UUID | None = None) -> dict:
    if user is None:
        user = FINANCE_USER if role == "finance" else SALES_USER
    return {
        "X-User-Id": str(user),
        "X-Org-Id": str(org),
        "X-Site-Id": str(SITE_ID),
        "X-Role": role,
    }


def profile_payload(**overrides) -> dict:
    base = {
        "title": COMPANY_A_NAME,
        "tax_id": VALID_USCC,
        "registered_address": "虚构市示例区演示路 1 号",
        "registered_phone": "022-12345678",
        "bank_name": "示例银行虚构支行",
        "bank_account": BANK_ACCOUNT,
        "default_invoice_type": "general",
        "receive_email": "finance@example.invalid",
        "receive_phone": "13800000000",
        "is_default": False,
    }
    base.update(overrides)
    return base


def special_payload(**overrides) -> dict:
    return profile_payload(default_invoice_type="special", **overrides)


def url(company_id: UUID = COMPANY_A, profile_id=None) -> str:
    base = f"/api/finance/companies/{company_id}/invoice-profiles"
    return f"{base}/{profile_id}" if profile_id else base