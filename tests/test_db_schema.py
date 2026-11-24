"""Schema-level assertions: unified columns, constraints, partial index."""

from __future__ import annotations

from sqlalchemy import inspect

COMMON_COLUMNS = {"id", "org_id", "site_id", "created_at", "created_by", "updated_at", "deleted_at"}

PROFILE_COLUMNS = COMMON_COLUMNS | {
    "company_id", "title", "tax_id", "registered_address", "registered_phone",
    "bank_name", "bank_account", "default_invoice_type", "receive_email",
    "receive_phone", "is_default", "name_mismatch_reason",
}


class TestSchema:
    def test_profile_columns(self, engine):
        cols = {c["name"] for c in inspect(engine).get_columns("company_invoice_profiles")}
        assert PROFILE_COLUMNS <= cols

    def test_change_log_columns(self, engine):
        cols = {c["name"] for c in inspect(engine).get_columns("finance_invoice_profile_change_log")}
        assert COMMON_COLUMNS | {"entity_id", "company_id", "action", "old_value", "new_value", "diff", "operator_id"} <= cols

    def test_id_is_uuid(self, engine):
        for table in ("company_invoice_profiles", "finance_invoice_profile_change_log"):
            col = next(c for c in inspect(engine).get_columns(table) if c["name"] == "id")
            assert str(col["type"]).upper() == "UUID"

    def test_partial_unique_default_index(self, engine):
        indexes = inspect(engine).get_indexes("company_invoice_profiles")
        idx = next(i for i in indexes if i["name"] == "uq_company_invoice_profiles_default")
        assert idx["unique"] is True
        assert idx["column_names"] == ["org_id", "company_id"]
        with engine.connect() as conn:
            from sqlalchemy import text

            definition = conn.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE indexname = 'uq_company_invoice_profiles_default'"
                )
            ).scalar_one()
        assert "WHERE" in definition and "is_default" in definition and "deleted_at IS NULL" in definition

    def test_check_constraints_present(self, engine):
        with engine.connect() as conn:
            from sqlalchemy import text

            names = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT conname FROM pg_constraint WHERE conrelid = "
                        "'company_invoice_profiles'::regclass AND contype = 'c'"
                    )
                )
            }
        assert {
            "ck_company_invoice_profiles_tax_id_len",
            "ck_company_invoice_profiles_invoice_type",
            "ck_company_invoice_profiles_special_required",
        } <= names