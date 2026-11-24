"""Unit tests for the field validators (no database needed)."""

from __future__ import annotations

import pytest

from app import validators as v
from tests.factories import (
    CHARSET,
    VALID_TAX_15,
    VALID_TAX_20,
    VALID_USCC,
    make_uscc,
)


class TestTaxId:
    def test_known_gb_example_passes(self):
        # GB 32100-2015 附录示例代码。
        assert v.validate_tax_id("91350100M000100Y43") == "91350100M000100Y43"

    def test_generated_codes_pass(self):
        for prefix in ("91120116MA05XW123", "91350100M000100Y4", "11440300MB2D00013"):
            code = make_uscc(prefix)
            assert v.validate_tax_id(code) == code

    def test_check_digit_error_rejected(self):
        wrong = VALID_USCC[:17] + ("0" if VALID_USCC[17] != "0" else "1")
        with pytest.raises(v.ValidationFailure) as exc:
            v.validate_tax_id(wrong)
        assert exc.value.code == "tax_id_check_digit"

    def test_lengths_15_and_20_pass(self):
        assert v.validate_tax_id(VALID_TAX_15) == VALID_TAX_15
        assert v.validate_tax_id(VALID_TAX_20) == VALID_TAX_20

    @pytest.mark.parametrize("bad", ["12345678901234", "1234567890123456", "12345678901234567",
                                     "1234567890123456789", "123456789012345678901", ""])
    def test_wrong_length_rejected(self, bad):
        with pytest.raises(v.ValidationFailure) as exc:
            v.validate_tax_id(bad)
        assert exc.value.code == "tax_id_length"

    @pytest.mark.parametrize("illegal", ["I", "O", "Z", "S", "V"])
    def test_18_char_illegal_charset(self, illegal):
        prefix = "91120116MA05XW12" + illegal
        code = prefix + "0"
        with pytest.raises(v.ValidationFailure) as exc:
            v.validate_tax_id(code)
        assert exc.value.code == "tax_id_charset"

    def test_normalizes_spaces_and_case(self):
        spaced = " " + VALID_USCC.lower()[:9] + " " + VALID_USCC.lower()[9:] + " "
        assert v.validate_tax_id(spaced) == VALID_USCC

    def test_15_digit_non_alnum_rejected(self):
        with pytest.raises(v.ValidationFailure) as exc:
            v.validate_tax_id("110101-12345678")
        assert exc.value.code in ("tax_id_length", "tax_id_charset")

    def test_check_character_matches_independent_weights(self):
        # 独立实现：Wi = 3^i mod 31，与实现中的常量表互为验证。
        for prefix in ("91120116MA05XW123", "91350100M000100Y4"):
            total = sum(CHARSET.index(c) * pow(3, i, 31) for i, c in enumerate(prefix))
            assert v.uscc_check_character(prefix) == CHARSET[(31 - total % 31) % 31]


class TestSpecialInvoice:
    FULL = dict(
        registered_address="虚构市示例区演示路 1 号",
        registered_phone="022-12345678",
        bank_name="示例银行虚构支行",
        bank_account="6222021234567890123",
    )

    def test_general_skips_required_fields(self):
        v.validate_special_invoice_fields(
            "general", registered_address=None, registered_phone=None,
            bank_name=None, bank_account=None,
        )

    def test_special_full_passes(self):
        v.validate_special_invoice_fields("special", **self.FULL)

    @pytest.mark.parametrize("missing", list(FULL))
    def test_special_missing_any_field_fails(self, missing):
        kwargs = dict(self.FULL)
        kwargs[missing] = None
        with pytest.raises(v.ValidationFailure) as exc:
            v.validate_special_invoice_fields("special", **kwargs)
        assert exc.value.code == "special_invoice_required"
        assert exc.value.field == missing

    def test_special_blank_string_fails(self):
        kwargs = dict(self.FULL)
        kwargs["bank_name"] = "   "
        with pytest.raises(v.ValidationFailure):
            v.validate_special_invoice_fields("special", **kwargs)


class TestNameMismatch:
    def test_match_clears_reason(self):
        assert v.validate_name_mismatch("甲公司", "甲公司", "旧原因") is None

    def test_mismatch_requires_reason(self):
        with pytest.raises(v.ValidationFailure) as exc:
            v.validate_name_mismatch("甲分公司", "甲公司", None)
        assert exc.value.code == "name_mismatch_reason_required"

    def test_mismatch_blank_reason_rejected(self):
        with pytest.raises(v.ValidationFailure):
            v.validate_name_mismatch("甲分公司", "甲公司", "   ")

    def test_mismatch_with_reason_passes(self):
        assert v.validate_name_mismatch("甲分公司", "甲公司", "分支机构抬头") == "分支机构抬头"


class TestBankAccount:
    def test_mask_keeps_last4(self):
        assert v.mask_bank_account("6222021234567890123") == "****0123"

    def test_mask_short_account_fully_hidden(self):
        assert v.mask_bank_account("1234") == "****"

    def test_mask_none(self):
        assert v.mask_bank_account(None) is None

    def test_normalize_strips_spaces(self):
        assert v.normalize_bank_account("6222 0212 3456 7890 123") == "6222021234567890123"

    def test_normalize_rejects_letters_and_short(self):
        with pytest.raises(v.ValidationFailure):
            v.normalize_bank_account("ABC12345678")
        with pytest.raises(v.ValidationFailure):
            v.normalize_bank_account("1234567")

    def test_normalize_none_and_blank(self):
        assert v.normalize_bank_account(None) is None
        assert v.normalize_bank_account("   ") is None


class TestContactFields:
    def test_email_ok(self):
        assert v.validate_email("a@b.example") == "a@b.example"

    @pytest.mark.parametrize("bad", ["no-at", "a@b", "a b@c.example"])
    def test_email_bad(self, bad):
        with pytest.raises(v.ValidationFailure):
            v.validate_email(bad)

    def test_phone_ok(self):
        assert v.validate_phone("registered_phone", "022-1234 5678") == "022-1234 5678"

    def test_phone_bad(self):
        with pytest.raises(v.ValidationFailure):
            v.validate_phone("receive_phone", "电话123")