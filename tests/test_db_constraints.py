"""Database backstops: check constraints reject invalid rows directly."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.invoice_profile import CompanyInvoiceProfile
from tests.factories import COMPANY_A, ORG_ID, SITE_ID, VALID_USCC


def _row(**overrides) -> CompanyInvoiceProfile:
    base = dict(
        org_id=ORG_ID,
        site_id=SITE_ID,
        company_id=COMPANY_A,
        title="示例企业甲（虚构）有限公司",
        tax_id=VALID_USCC,
        default_invoice_type="general",
        is_default=False,
    )
    base.update(overrides)
    return CompanyInvoiceProfile(**base)


class TestDbConstraints:
    def test_tax_id_length_backstop(self, db_session):
        db_session.add(_row(tax_id="1234567890123456"))  # 16 位
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_invoice_type_backstop(self, db_session):
        db_session.add(_row(default_invoice_type="paper"))
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_special_required_backstop(self, db_session):
        db_session.add(_row(default_invoice_type="special"))  # 四项全缺
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_special_complete_passes(self, db_session):
        db_session.add(
            _row(
                default_invoice_type="special",
                registered_address="虚构市示例区演示路 1 号",
                registered_phone="022-12345678",
                bank_name="示例银行虚构支行",
                bank_account="6222021234567890123",
            )
        )
        db_session.flush()
        db_session.rollback()