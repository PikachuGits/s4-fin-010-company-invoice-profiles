"""``company_invoice_profiles`` — 企业开票资料.

One company may hold several profiles (e.g. branches); at most one active
profile per company is the default, enforced by a partial unique index.
``company_id`` references the S2-CRM company object; because S2-CRM is a
separate delivery the column carries no cross-module foreign key — existence
is checked through the CRM integration point (``app/crm.py``).
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class CompanyInvoiceProfile(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "company_invoice_profiles"

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    title: Mapped[str] = mapped_column(String(200), nullable=False)  # 抬头（企业全称）
    tax_id: Mapped[str] = mapped_column(String(20), nullable=False)  # 纳税人识别号
    registered_address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    registered_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(200), nullable=True)  # 开户行
    bank_account: Mapped[str | None] = mapped_column(String(32), nullable=True)
    default_invoice_type: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'general'")
    )
    receive_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    receive_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    name_mismatch_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "char_length(tax_id) IN (15, 18, 20)",
            name="ck_company_invoice_profiles_tax_id_len",
        ),
        CheckConstraint(
            "default_invoice_type IN ('general', 'special')",
            name="ck_company_invoice_profiles_invoice_type",
        ),
        # 专票必须四项齐全（应用层返回 422，这里是数据库兜底）。
        CheckConstraint(
            "default_invoice_type <> 'special' OR ("
            "registered_address IS NOT NULL AND char_length(trim(registered_address)) > 0 AND "
            "registered_phone IS NOT NULL AND char_length(trim(registered_phone)) > 0 AND "
            "bank_name IS NOT NULL AND char_length(trim(bank_name)) > 0 AND "
            "bank_account IS NOT NULL AND char_length(trim(bank_account)) > 0)",
            name="ck_company_invoice_profiles_special_required",
        ),
        # 一家企业只能有 1 份默认（仅约束未软删除的行）。
        Index(
            "uq_company_invoice_profiles_default",
            "org_id",
            "company_id",
            unique=True,
            postgresql_where=text("is_default AND deleted_at IS NULL"),
        ),
        Index(
            "ix_company_invoice_profiles_company",
            "org_id",
            "company_id",
        ),
    )