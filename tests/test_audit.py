"""AC4: every mutation writes audit rows with before/after diffs."""

from __future__ import annotations

from sqlalchemy import select

from app.models.change_log import InvoiceProfileChangeLog
from tests.factories import (
    BANK_ACCOUNT,
    FINANCE_USER,
    VALID_USCC,
    VALID_USCC_2,
    headers,
    profile_payload,
    special_payload,
    url,
)


def _logs(db_session, entity_id=None):
    stmt = select(InvoiceProfileChangeLog).order_by(InvoiceProfileChangeLog.created_at)
    if entity_id is not None:
        stmt = stmt.where(InvoiceProfileChangeLog.entity_id == entity_id)
    return list(db_session.execute(stmt).scalars())


def _create(client, **overrides):
    resp = client.post(url(), json=profile_payload(**overrides), headers=headers())
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestAudit:
    def test_create_writes_one_row_with_new_snapshot(self, client, db_session):
        body = _create(client)
        rows = _logs(db_session, body["id"])
        assert len(rows) == 1
        row = rows[0]
        assert row.action == "create"
        assert row.old_value is None
        assert row.new_value["tax_id"] == VALID_USCC
        assert row.new_value["bank_account"] == BANK_ACCOUNT  # 审计留全量
        assert row.diff["title"]["new"] == body["title"]
        assert row.operator_id == FINANCE_USER

    def test_ac4_patch_writes_exactly_one_row_with_diff(self, client, db_session):
        body = _create(client)
        resp = client.patch(
            url(profile_id=body["id"]),
            json={"registered_phone": "022-99998888"},
            headers=headers(),
        )
        assert resp.status_code == 200
        rows = _logs(db_session, body["id"])
        assert len(rows) == 2  # create + update
        update = rows[-1]
        assert update.action == "update"
        assert update.diff == {
            "registered_phone": {"old": "022-12345678", "new": "022-99998888"}
        }
        assert update.old_value["registered_phone"] == "022-12345678"
        assert update.new_value["registered_phone"] == "022-99998888"

    def test_noop_patch_writes_no_row(self, client, db_session):
        body = _create(client)
        resp = client.patch(
            url(profile_id=body["id"]),
            json={"registered_phone": "022-12345678"},
            headers=headers(),
        )
        assert resp.status_code == 200
        assert len(_logs(db_session, body["id"])) == 1  # 仅 create

    def test_delete_writes_row_with_old_snapshot(self, client, db_session):
        body = _create(client)
        assert client.delete(url(profile_id=body["id"]), headers=headers()).status_code == 204
        rows = _logs(db_session, body["id"])
        assert len(rows) == 2
        delete = rows[-1]
        assert delete.action == "delete"
        assert delete.old_value["tax_id"] == VALID_USCC
        assert delete.new_value is None
        assert delete.diff["tax_id"]["old"] == VALID_USCC

    def test_failed_patch_writes_nothing(self, client, db_session):
        body = _create(client)
        bad = VALID_USCC[:17] + ("0" if VALID_USCC[17] != "0" else "1")
        resp = client.patch(
            url(profile_id=body["id"]), json={"tax_id": bad}, headers=headers()
        )
        assert resp.status_code == 422
        assert len(_logs(db_session, body["id"])) == 1  # 仅 create，回滚不留审计

    def test_default_transfer_create_audits_both_profiles(self, client, db_session):
        first = _create(client)
        second = _create(client, tax_id=VALID_USCC_2, is_default=True)
        first_rows = _logs(db_session, first["id"])
        assert len(first_rows) == 2  # create + 降级 update
        demote = first_rows[-1]
        assert demote.action == "update"
        assert demote.diff == {"is_default": {"old": True, "new": False}}
        second_rows = _logs(db_session, second["id"])
        assert len(second_rows) == 1 and second_rows[0].action == "create"

    def test_default_transfer_patch_audits_both_profiles(self, client, db_session):
        first = _create(client)
        second = _create(client, tax_id=VALID_USCC_2)
        resp = client.patch(
            url(profile_id=second["id"]), json={"is_default": True}, headers=headers()
        )
        assert resp.status_code == 200
        first_rows = _logs(db_session, first["id"])
        assert first_rows[-1].diff == {"is_default": {"old": True, "new": False}}
        second_rows = _logs(db_session, second["id"])
        assert second_rows[-1].diff == {"is_default": {"old": False, "new": True}}

    def test_delete_default_audits_delete_and_promotion(self, client, db_session):
        first = _create(client)
        second = _create(client, tax_id=VALID_USCC_2, is_default=True)
        assert client.delete(url(profile_id=second["id"]), headers=headers()).status_code == 204
        second_rows = _logs(db_session, second["id"])
        assert second_rows[-1].action == "delete"
        first_rows = _logs(db_session, first["id"])
        assert first_rows[-1].diff == {"is_default": {"old": False, "new": True}}

    def test_audit_keeps_full_account_while_api_masks(self, client, db_session):
        body = _create(client, **special_payload())
        listing = client.get(url(), headers=headers("sales"))
        assert BANK_ACCOUNT not in listing.text
        row = _logs(db_session, body["id"])[0]
        assert row.new_value["bank_account"] == BANK_ACCOUNT