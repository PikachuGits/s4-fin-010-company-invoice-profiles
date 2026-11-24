"""The one-default-per-company invariant."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.invoice_profile import CompanyInvoiceProfile
from tests.factories import (
    COMPANY_A,
    ORG_ID,
    SITE_ID,
    VALID_USCC,
    VALID_USCC_2,
    headers,
    profile_payload,
    url,
)


def _create(client, **overrides):
    resp = client.post(url(), json=profile_payload(**overrides), headers=headers())
    assert resp.status_code == 201, resp.text
    return resp.json()


def _defaults(client) -> list[dict]:
    items = client.get(url(), headers=headers()).json()["items"]
    return [i for i in items if i["is_default"]]


class TestDefaultInvariant:
    def test_first_profile_forced_default(self, client):
        body = _create(client, is_default=False)
        assert body["is_default"] is True

    def test_second_not_default_keeps_first(self, client):
        first = _create(client)
        second = _create(client, tax_id=VALID_USCC_2, is_default=False)
        assert second["is_default"] is False
        defaults = _defaults(client)
        assert len(defaults) == 1 and defaults[0]["id"] == first["id"]

    def test_create_new_default_demotes_previous(self, client):
        first = _create(client)
        second = _create(client, tax_id=VALID_USCC_2, is_default=True)
        assert second["is_default"] is True
        defaults = _defaults(client)
        assert len(defaults) == 1 and defaults[0]["id"] == second["id"]
        detail = client.get(url(profile_id=first["id"]), headers=headers()).json()
        assert detail["is_default"] is False

    def test_patch_cannot_unset_default(self, client):
        pid = _create(client)["id"]
        resp = client.patch(
            url(profile_id=pid), json={"is_default": False}, headers=headers()
        )
        assert resp.status_code == 422
        assert resp.json()["detail"][0]["code"] == "default_transfer_required"

    def test_patch_transfers_default(self, client):
        first = _create(client)
        second = _create(client, tax_id=VALID_USCC_2)
        resp = client.patch(
            url(profile_id=second["id"]), json={"is_default": True}, headers=headers()
        )
        assert resp.status_code == 200
        defaults = _defaults(client)
        assert len(defaults) == 1 and defaults[0]["id"] == second["id"]

    def test_delete_default_promotes_oldest_remaining(self, client):
        first = _create(client)
        second = _create(client, tax_id=VALID_USCC_2, is_default=True)
        resp = client.delete(url(profile_id=second["id"]), headers=headers())
        assert resp.status_code == 204
        defaults = _defaults(client)
        assert len(defaults) == 1 and defaults[0]["id"] == first["id"]

    def test_delete_last_profile_leaves_none(self, client):
        pid = _create(client)["id"]
        assert client.delete(url(profile_id=pid), headers=headers()).status_code == 204
        assert _defaults(client) == []

    def test_db_partial_unique_index_blocks_two_defaults(self, client, db_session):
        _create(client)
        db_session.add(
            CompanyInvoiceProfile(
                org_id=ORG_ID,
                site_id=SITE_ID,
                company_id=COMPANY_A,
                title="示例企业甲（虚构）有限公司",
                tax_id=VALID_USCC_2,
                default_invoice_type="general",
                is_default=True,
            )
        )
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_soft_deleted_default_does_not_block_new_default(self, client):
        first = _create(client)
        assert client.delete(url(profile_id=first["id"]), headers=headers()).status_code == 204
        second = _create(client, tax_id=VALID_USCC_2, is_default=True)
        assert second["is_default"] is True