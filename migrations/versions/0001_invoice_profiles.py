"""company invoice profiles and local audit sink

Revision ID: 0001
Revises:
Create Date: 2026-11-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_invoice_profiles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("tax_id", sa.String(20), nullable=False),
        sa.Column("registered_address", sa.String(300), nullable=True),
        sa.Column("registered_phone", sa.String(32), nullable=True),
        sa.Column("bank_name", sa.String(200), nullable=True),
        sa.Column("bank_account", sa.String(32), nullable=True),
        sa.Column(
            "default_invoice_type",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'general'"),
        ),
        sa.Column("receive_email", sa.String(200), nullable=True),
        sa.Column("receive_phone", sa.String(32), nullable=True),
        sa.Column(
            "is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("name_mismatch_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "char_length(tax_id) IN (15, 18, 20)",
            name="ck_company_invoice_profiles_tax_id_len",
        ),
        sa.CheckConstraint(
            "default_invoice_type IN ('general', 'special')",
            name="ck_company_invoice_profiles_invoice_type",
        ),
        sa.CheckConstraint(
            "default_invoice_type <> 'special' OR ("
            "registered_address IS NOT NULL AND char_length(trim(registered_address)) > 0 AND "
            "registered_phone IS NOT NULL AND char_length(trim(registered_phone)) > 0 AND "
            "bank_name IS NOT NULL AND char_length(trim(bank_name)) > 0 AND "
            "bank_account IS NOT NULL AND char_length(trim(bank_account)) > 0)",
            name="ck_company_invoice_profiles_special_required",
        ),
    )
    op.create_index(
        "uq_company_invoice_profiles_default",
        "company_invoice_profiles",
        ["org_id", "company_id"],
        unique=True,
        postgresql_where=sa.text("is_default AND deleted_at IS NULL"),
    )
    op.create_index(
        "ix_company_invoice_profiles_company",
        "company_invoice_profiles",
        ["org_id", "company_id"],
    )

    op.create_table(
        "finance_invoice_profile_change_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("old_value", postgresql.JSONB(), nullable=True),
        sa.Column("new_value", postgresql.JSONB(), nullable=True),
        sa.Column("diff", postgresql.JSONB(), nullable=False),
        sa.Column("operator_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "action IN ('create', 'update', 'delete')",
            name="ck_finance_invoice_profile_change_log_action",
        ),
    )
    op.create_index(
        "ix_finance_invoice_profile_change_log_entity",
        "finance_invoice_profile_change_log",
        ["entity_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_finance_invoice_profile_change_log_entity",
        table_name="finance_invoice_profile_change_log",
    )
    op.drop_table("finance_invoice_profile_change_log")
    op.drop_index(
        "ix_company_invoice_profiles_company", table_name="company_invoice_profiles"
    )
    op.drop_index(
        "uq_company_invoice_profiles_default", table_name="company_invoice_profiles"
    )
    op.drop_table("company_invoice_profiles")