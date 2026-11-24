"""Field validators for company invoice profiles.

Taxpayer identification number (纳税人识别号) rules required by the work order:

* length must be 15, 18 or 20 characters;
* an 18-character code is a Unified Social Credit Code (统一社会信用代码,
  GB 32100-2015) and must pass the modulo-31 check-character rule;
* 15-character (legacy tax registration) and 20-character (temporary
  registration) codes are validated for length and uppercase-alphanumeric
  shape only — no national check digit exists for them.

All validators raise :class:`ValidationFailure`; the API layer converts them
to HTTP 422 with a structured ``{field, code, message}`` detail.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# GB 32100-2015 charset: digits plus uppercase letters without I O Z S V.
USCC_CHARSET = "0123456789ABCDEFGHJKLMNPQRTUWXY"
# Wi = 3**i mod 31 for i = 0..16 (weights of the first 17 characters).
USCC_WEIGHTS = (1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28)

_ALNUM_UPPER = re.compile(r"^[0-9A-Z]+$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE = re.compile(r"^[0-9+\-() ]{5,24}$")


@dataclass(frozen=True)
class ValidationFailure(Exception):
    """One field-level validation error, rendered as HTTP 422."""

    field: str
    code: str
    message: str

    def as_detail(self) -> dict[str, str]:
        return {"field": self.field, "code": self.code, "message": self.message}


def normalize_tax_id(raw: str) -> str:
    """Strip surrounding whitespace and uppercase; internal spaces removed."""

    return re.sub(r"\s+", "", raw).upper()


def uscc_check_character(code17: str) -> str:
    """Compute the GB 32100-2015 check character for the first 17 chars."""

    total = sum(USCC_CHARSET.index(ch) * w for ch, w in zip(code17, USCC_WEIGHTS))
    return USCC_CHARSET[(31 - total % 31) % 31]


def validate_tax_id(raw: str) -> str:
    """Return the normalized tax id or raise :class:`ValidationFailure`."""

    value = normalize_tax_id(raw)
    if len(value) not in (15, 18, 20):
        raise ValidationFailure(
            "tax_id", "tax_id_length", "纳税人识别号长度必须为 15、18 或 20 位"
        )
    if len(value) == 18:
        if any(ch not in USCC_CHARSET for ch in value):
            raise ValidationFailure(
                "tax_id",
                "tax_id_charset",
                "18 位统一社会信用代码含非法字符（不允许 I、O、Z、S、V）",
            )
        if uscc_check_character(value[:17]) != value[17]:
            raise ValidationFailure(
                "tax_id", "tax_id_check_digit", "18 位统一社会信用代码校验位错误"
            )
    elif not _ALNUM_UPPER.match(value):
        raise ValidationFailure(
            "tax_id", "tax_id_charset", "纳税人识别号只能包含数字与大写字母"
        )
    return value


def validate_special_invoice_fields(
    invoice_type: str,
    *,
    registered_address: str | None,
    registered_phone: str | None,
    bank_name: str | None,
    bank_account: str | None,
) -> None:
    """专票资料必须填写地址、电话、开户行与账号（缺一即 422）."""

    if invoice_type != "special":
        return
    required = {
        "registered_address": registered_address,
        "registered_phone": registered_phone,
        "bank_name": bank_name,
        "bank_account": bank_account,
    }
    for field, value in required.items():
        if value is None or not str(value).strip():
            raise ValidationFailure(
                field, "special_invoice_required", "专票资料必须填写注册地址、电话、开户行与银行账号"
            )


def validate_name_mismatch(
    title: str, crm_name: str, reason: str | None
) -> str | None:
    """抬头与 CRM 企业名不一致时允许保存，但必须填写原因.

    Returns the reason to persist: ``None`` when the names match (a stale
    reason is cleared), the trimmed reason otherwise.
    """

    if title.strip() == crm_name.strip():
        return None
    if reason is None or not reason.strip():
        raise ValidationFailure(
            "name_mismatch_reason",
            "name_mismatch_reason_required",
            "抬头与 CRM 企业名称不一致，必须填写原因",
        )
    return reason.strip()


def validate_email(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if not _EMAIL.match(value):
        raise ValidationFailure("receive_email", "email_format", "接收邮箱格式不正确")
    return value


def validate_phone(field: str, value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if not _PHONE.match(value):
        raise ValidationFailure(field, "phone_format", "电话号码格式不正确")
    return value


def normalize_bank_account(value: str | None) -> str | None:
    """Bank accounts are stored without spaces; keep digits/letters only."""

    if value is None:
        return None
    compact = re.sub(r"\s+", "", value)
    if not compact:
        return None
    if not compact.isdigit() or not (8 <= len(compact) <= 32):
        raise ValidationFailure(
            "bank_account", "bank_account_format", "银行账号须为 8–32 位数字"
        )
    return compact


def mask_bank_account(account: str | None) -> str | None:
    """列表/非财务视角只显示后 4 位；不足 5 位时全部隐藏."""

    if account is None:
        return None
    if len(account) <= 4:
        return "****"
    return "****" + account[-4:]