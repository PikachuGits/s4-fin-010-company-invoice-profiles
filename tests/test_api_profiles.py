"""API behaviour tests, including the four acceptance criteria."""

from __future__ import annotations

from tests.factories import (
    BANK_ACCOUNT,
    COMPANY_A,
    COMPANY_A_NAME,
    COMPANY_B,
    OTHER_ORG_COMPANY,
    OTHER_ORG_ID,
    VALID_TAX_15,
    VALID_TAX_20,
    VALID_USCC,
    headers,
    profile_payload,
    special_payload,
    url,
)


def _create(client, payload=None, company=COMPANY_A, role="finance"):
    return client.post(
        url(company), json=payload or profile_payload(), headers=headers(role)
    )


class TestCreate:
    def test_create_general_ok(self, client):
        resp = _create(client)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["title"] == COMPANY_A_NAME
        assert body["tax_id"] == VALID_USCC
        assert body["is_default"] is True  # 首份资料自动成为默认
        assert body["default_invoice_type"] == "general"
        # 财务角色在创建/详情响应中可见完整账号
        assert body["bank_account"] == BANK_ACCOUNT
        assert body["bank_account_masked"] is False

    def test_create_15_and_20_digit_tax_ids(self, client):
        for tax in (VALID_TAX_15, VALID_TAX_20):
            resp = _create(client, profile_payload(tax_id=tax))
            assert resp.status_code == 201, resp.text

    def test_ac1_bad_check_digit_returns_422(self, client):
        bad = VALID_USCC[:17] + ("0" if VALID_USCC[17] != "0" else "1")
        resp = _create(client, profile_payload(tax_id=bad))
        assert resp.status_code == 422
        assert resp.json()["detail"][0]["code"] == "tax_id_check_digit"

    def test_ac2_special_missing_bank_fields_returns_422(self, client):
        for missing in ("bank_name", "bank_account", "registered_address", "registered_phone"):
            payload = special_payload()
            payload.pop(missing)
            resp = _create(client, payload)
            assert resp.status_code == 422, (missing, resp.text)
            assert resp.json()["detail"][0]["code"] == "special_invoice_required"

    def test_special_complete_ok(self, client):
        resp = _create(client, special_payload())
        assert resp.status_code == 201
        assert resp.json()["default_invoice_type"] == "special"

    def test_title_mismatch_requires_reason(self, client):
        resp = _create(client, profile_payload(title="示例企业甲天津分公司（虚构）"))
        assert resp.status_code == 422
        assert resp.json()["detail"][0]["code"] == "name_mismatch_reason_required"

    def test_title_mismatch_with_reason_saves(self, client):
        resp = _create(
            client,
            profile_payload(
                title="示例企业甲天津分公司（虚构）",
                name_mismatch_reason="分支机构使用分公司抬头",
            ),
        )
        assert resp.status_code == 201
        assert resp.json()["name_mismatch_reason"] == "分支机构使用分公司抬头"

    def test_unknown_company_404(self, client):
        resp = client.post(
            url("88888888-8888-4888-8888-888888888888"),
            json=profile_payload(),
            headers=headers(),
        )
        assert resp.status_code == 404

    def test_cross_org_company_404(self, client):
        resp = _create(client, company=OTHER_ORG_COMPANY)
        assert resp.status_code == 404

    def test_missing_identity_headers_401(self, client):
        resp = client.post(url(), json=profile_payload())
        assert resp.status_code == 401

    def test_unknown_field_rejected(self, client):
        resp = _create(client, profile_payload(unknown_field="x"))
        assert resp.status_code == 422


class TestListMasking:
    def test_ac3_list_masks_account_for_every_role(self, client):
        assert _create(client, special_payload()).status_code == 201
        for role in ("finance", "admin", "ops", "sales"):
            resp = client.get(url(), headers=headers(role))
            assert resp.status_code == 200
            body = resp.json()
            assert body["total"] == 1
            item = body["items"][0]
            assert item["bank_account"] == "****" + BANK_ACCOUNT[-4:]
            assert item["bank_account_masked"] is True
            assert BANK_ACCOUNT not in resp.text

    def test_detail_full_account_only_for_finance(self, client):
        created = _create(client, special_payload()).json()
        pid = created["id"]
        resp = client.get(url(profile_id=pid), headers=headers("finance"))
        assert resp.json()["bank_account"] == BANK_ACCOUNT
        assert resp.json()["bank_account_masked"] is False
        for role in ("admin", "ops", "sales"):
            resp = client.get(url(profile_id=pid), headers=headers(role))
            assert resp.json()["bank_account"] == "****" + BANK_ACCOUNT[-4:]
            assert resp.json()["bank_account_masked"] is True
            assert BANK_ACCOUNT not in resp.text

    def test_list_scoped_to_company_and_org(self, client):
        assert _create(client).status_code == 201
        assert _create(client, profile_payload(title="示例企业乙（虚构）有限公司"),
                       company=COMPANY_B).status_code == 201
        assert client.get(url(), headers=headers()).json()["total"] == 1
        assert client.get(url(COMPANY_B), headers=headers()).json()["total"] == 1
        # 他租户视角看不到本租户企业的资料
        assert client.get(url(), headers=headers("finance", org=OTHER_ORG_ID)).status_code == 404


class TestPatch:
    def test_patch_phone_ok(self, client):
        pid = _create(client).json()["id"]
        resp = client.patch(
            url(profile_id=pid),
            json={"registered_phone": "022-87654321"},
            headers=headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["registered_phone"] == "022-87654321"

    def test_patch_bad_tax_id_422(self, client):
        pid = _create(client).json()["id"]
        bad = VALID_USCC[:17] + ("0" if VALID_USCC[17] != "0" else "1")
        resp = client.patch(url(profile_id=pid), json={"tax_id": bad}, headers=headers())
        assert resp.status_code == 422

    def test_ac2_patch_to_special_without_bank_422(self, client):
        pid = _create(
            client, profile_payload(bank_name=None, bank_account=None)
        ).json()["id"]
        resp = client.patch(
            url(profile_id=pid), json={"default_invoice_type": "special"},
            headers=headers(),
        )
        assert resp.status_code == 422
        assert resp.json()["detail"][0]["code"] == "special_invoice_required"

    def test_patch_clearing_bank_on_special_422(self, client):
        pid = _create(client, special_payload()).json()["id"]
        resp = client.patch(
            url(profile_id=pid), json={"bank_account": None}, headers=headers()
        )
        assert resp.status_code == 422

    def test_patch_title_to_mismatch_requires_reason(self, client):
        pid = _create(client).json()["id"]
        resp = client.patch(
            url(profile_id=pid), json={"title": "示例企业甲分支机构（虚构）"},
            headers=headers(),
        )
        assert resp.status_code == 422
        resp = client.patch(
            url(profile_id=pid),
            json={"title": "示例企业甲分支机构（虚构）", "name_mismatch_reason": "分支机构"},
            headers=headers(),
        )
        assert resp.status_code == 200

    def test_patch_back_to_crm_name_clears_reason(self, client):
        pid = _create(
            client,
            profile_payload(title="示例企业甲分支机构（虚构）", name_mismatch_reason="分支机构"),
        ).json()["id"]
        resp = client.patch(
            url(profile_id=pid), json={"title": COMPANY_A_NAME}, headers=headers()
        )
        assert resp.status_code == 200
        assert resp.json()["name_mismatch_reason"] is None

    def test_patch_null_title_422(self, client):
        pid = _create(client).json()["id"]
        resp = client.patch(url(profile_id=pid), json={"title": None}, headers=headers())
        assert resp.status_code == 422

    def test_patch_missing_profile_404(self, client):
        resp = client.patch(
            url(profile_id="88888888-8888-4888-8888-888888888888"),
            json={"registered_phone": "022-11111111"},
            headers=headers(),
        )
        assert resp.status_code == 404


class TestDelete:
    def test_delete_soft_removes_from_list_and_detail(self, client, db_session):
        from sqlalchemy import select
        from app.models.invoice_profile import CompanyInvoiceProfile

        pid = _create(client).json()["id"]
        resp = client.delete(url(profile_id=pid), headers=headers())
        assert resp.status_code == 204
        assert client.get(url(), headers=headers()).json()["total"] == 0
        assert client.get(url(profile_id=pid), headers=headers()).status_code == 404
        row = db_session.execute(
            select(CompanyInvoiceProfile).where(CompanyInvoiceProfile.id == pid)
        ).scalar_one()
        assert row.deleted_at is not None  # 软删除，行仍在

    def test_delete_twice_404(self, client):
        pid = _create(client).json()["id"]
        assert client.delete(url(profile_id=pid), headers=headers()).status_code == 204
        assert client.delete(url(profile_id=pid), headers=headers()).status_code == 404