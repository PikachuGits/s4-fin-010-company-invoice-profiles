"""Local audit sink for invoice-profile mutations (S2-AUDIT stub).

Every mutation writes one row per touched profile containing the full
before/after snapshots plus a field-level diff, the operator and the time.
Rows are written in the same transaction as the mutation, so an audit entry
can never describe a change that was rolled back.

Production integration: S2-AUDIT owns the audit log.  ``app/audit.py`` is the
single replacement point — swap ``LocalChangeLogSink`` for a client posting to
``POST /internal/audit/events`` while keeping the same payload shape.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class InvoiceProfileChangeLog(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "finance_invoice_profile_change_log"

    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    old_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    diff: Mapped[dict] = mapped_column(JSONB, nullable=False)
    operator_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "action IN ('create', 'update', 'delete')",
            name="ck_finance_invoice_profile_change_log_action",
        ),
        Index(
            "ix_finance_invoice_profile_change_log_entity",
            "entity_id",
            "created_at",
        ),
    )