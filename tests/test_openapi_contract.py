"""The OpenAPI surface matches the work order's route contract."""

from __future__ import annotations


def test_routes_and_methods(app):
    paths = app.openapi()["paths"]
    collection = "/api/finance/companies/{company_id}/invoice-profiles"
    item = collection + "/{profile_id}"
    assert set(paths[collection]) == {"get", "post"}
    assert set(paths[item]) == {"get", "patch", "delete"}


def test_create_response_201_and_delete_204(app):
    paths = app.openapi()["paths"]
    collection = "/api/finance/companies/{company_id}/invoice-profiles"
    item = collection + "/{profile_id}"
    assert "201" in paths[collection]["post"]["responses"]
    assert "204" in paths[item]["delete"]["responses"]