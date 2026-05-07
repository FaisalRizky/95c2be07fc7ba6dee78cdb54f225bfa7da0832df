"""
test_main.py — API test suite

Two layers:
  Unit tests    — mock the DB via dependency_overrides; no real data needed.
  Integration   — use the real glenigan.sql; skipped automatically when absent.

Run all:       pytest
Run unit only: pytest -m unit
Run integ:     pytest -m integration
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from config.db import get_db
from main import app

# ─── Helpers ──────────────────────────────────────────────────────────────────

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "glenigan.sql")
DB_PRESENT = os.path.exists(DB_PATH)

SAMPLE_PROJECT = {
    "project_id": "P001",
    "project_name": "Manchester Bridge Refurbishment",
    "project_start": "2024-03-01 00:00:00",
    "project_end": "2025-09-01 00:00:00",
    "company": "Acme Construction Ltd",
    "description": "Major bridge refurbishment project",
    "project_value": 4800000,
    "area": "Manchester",
}

SAMPLE_AREAS = [{"area": "Leeds"}, {"area": "Manchester"}]
SAMPLE_COMPANIES = [{"company_name": "Acme Construction Ltd"}]


def _make_mock_db(projects=None, count=None, areas=None, companies=None):
    """Build a MagicMock that satisfies the DatabaseEngine protocol."""
    db = MagicMock()
    db.check_health.return_value = True

    rows = projects if projects is not None else [SAMPLE_PROJECT]

    def fetch_all_side_effect(query, params=None):
        # Match the narrow single-table area and company queries, not the full JOIN.
        q = query.strip().upper()
        if q.startswith("SELECT DISTINCT AREA FROM PROJECT_AREA_MAP"):
            return areas if areas is not None else SAMPLE_AREAS
        if q.startswith("SELECT DISTINCT COMPANY_NAME FROM COMPANIES"):
            return companies if companies is not None else SAMPLE_COMPANIES
        return rows

    def fetch_one_side_effect(query, params=None):
        q = query.strip().upper()
        # COUNT query → return cnt
        if "COUNT(*)" in q:
            return {"cnt": count if count is not None else len(rows)}
        # by-ID detail query → return matching row or None
        if params and len(params) == 1:
            match = next((r for r in rows if r.get("project_id") == params[0]), None)
            return match
        return {"cnt": count if count is not None else len(rows)}

    db.fetch_all.side_effect = fetch_all_side_effect
    db.fetch_one.side_effect = fetch_one_side_effect
    db.fetch_many_generator.return_value = iter(rows)
    return db


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """Integration test client — uses the real glenigan.sql database."""
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def unit_client():
    """
    Unit test client — injects a mock DB and stubs out Elasticsearch and bootstrap.
    No glenigan.sql required.
    """
    mock_db = _make_mock_db()
    app.dependency_overrides[get_db] = lambda: mock_db

    with (
        patch("bootstrap.run_bootstrap"),
        patch("config.search.SearchProvider") as mock_sp,
    ):
        # Force SQLite fallback path in the service layer
        mock_sp.get_engine.return_value.search_projects.return_value = (None, 0)
        with TestClient(app) as c:
            yield c

    app.dependency_overrides.clear()


# ─── Unit tests — envelope shape and validation ────────────────────────────────

class TestResponseEnvelope:
    """Every endpoint must return the canonical BaseResponse envelope."""

    @pytest.mark.unit
    def test_success_envelope_has_all_fields(self, unit_client):
        resp = unit_client.get("/api/v1/areas")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) >= {"success", "status_code", "data", "pagination", "error"}

    @pytest.mark.unit
    def test_success_status_code_field_is_200(self, unit_client):
        resp = unit_client.get("/api/v1/areas")
        assert resp.json()["status_code"] == 200

    @pytest.mark.unit
    def test_success_fields_are_correct(self, unit_client):
        resp = unit_client.get("/api/v1/areas")
        body = resp.json()
        assert body["success"] is True
        assert body["error"] is None
        assert isinstance(body["data"], list)

    @pytest.mark.unit
    def test_error_envelope_shape(self, unit_client):
        """A 422 validation error must return the full BaseResponse envelope."""
        resp = unit_client.get("/api/v1/projects?page=abc&per_page=10")  # non-numeric page
        assert resp.status_code == 422
        body = resp.json()
        assert body["success"] is False
        assert body["data"] is None
        assert body["error"]["code"] == "validation_error"

    @pytest.mark.unit
    def test_error_status_code_in_body_matches_http(self, unit_client):
        resp = unit_client.get("/api/v1/projects?page=abc&per_page=10")
        assert resp.json()["status_code"] == resp.status_code == 422

    @pytest.mark.unit
    def test_companies_returns_list_in_data(self, unit_client):
        resp = unit_client.get("/api/v1/companies")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["data"], list)
        assert body["data"] == ["Acme Construction Ltd"]

    @pytest.mark.unit
    def test_areas_returns_sorted_list_in_data(self, unit_client):
        resp = unit_client.get("/api/v1/areas")
        assert resp.status_code == 200
        assert resp.json()["data"] == ["Leeds", "Manchester"]


class TestPaginationValidation:

    @pytest.mark.unit
    def test_page_without_per_page_uses_default_per_page(self, unit_client):
        resp = unit_client.get("/api/v1/projects?page=2")
        assert resp.status_code == 200
        assert resp.json()["pagination"]["page"] == 2
        assert resp.json()["pagination"]["per_page"] == 20

    @pytest.mark.unit
    def test_per_page_without_page_uses_default_page(self, unit_client):
        resp = unit_client.get("/api/v1/projects?per_page=10")
        assert resp.status_code == 200
        assert resp.json()["pagination"]["page"] == 1
        assert resp.json()["pagination"]["per_page"] == 10

    @pytest.mark.unit
    def test_per_page_over_1000_triggers_streaming(self, unit_client):
        # per_page > 1000 switches to the streaming path — returns 200, not 422.
        resp = unit_client.get("/api/v1/projects?page=1&per_page=1001")
        assert resp.status_code == 200
        assert resp.json()["pagination"] is None  # streaming has no pagination meta

    @pytest.mark.unit
    def test_invalid_page_type_is_422(self, unit_client):
        resp = unit_client.get("/api/v1/projects?page=abc&per_page=10")
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "validation_error"

    @pytest.mark.unit
    def test_invalid_order_value_is_422(self, unit_client):
        resp = unit_client.get("/api/v1/projects?page=1&per_page=10&order=sideways")
        assert resp.status_code == 422


class TestPaginatedProjects:

    @pytest.mark.unit
    def test_paginated_response_has_pagination_meta(self, unit_client):
        resp = unit_client.get("/api/v1/projects?page=1&per_page=10")
        assert resp.status_code == 200
        body = resp.json()
        assert body["pagination"] is not None
        meta = body["pagination"]
        assert meta["page"] == 1
        assert meta["per_page"] == 10
        assert "total" in meta
        assert "total_pages" in meta

    @pytest.mark.unit
    def test_paginated_data_is_list(self, unit_client):
        resp = unit_client.get("/api/v1/projects?page=1&per_page=10")
        assert isinstance(resp.json()["data"], list)

    @pytest.mark.unit
    def test_project_row_has_expected_fields(self, unit_client):
        resp = unit_client.get("/api/v1/projects?page=1&per_page=10")
        project = resp.json()["data"][0]
        expected = {"project_id", "project_name", "project_start", "project_end",
                    "company", "description", "project_value", "area"}
        assert expected.issubset(project.keys())


class TestStreamingExport:

    @pytest.mark.unit
    def test_large_per_page_returns_streaming_json(self, unit_client):
        """per_page > 1000 must trigger streaming and emit a valid BaseResponse JSON."""
        resp = unit_client.get("/api/v1/projects?page=1&per_page=2000")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["pagination"] is None
        assert isinstance(body["data"], list)


class TestDefaultPagination:

    @pytest.mark.unit
    def test_no_pagination_params_uses_defaults(self, unit_client):
        """Omitting page+per_page must return a paginated response with defaults (page=1, per_page=20)."""
        resp = unit_client.get("/api/v1/projects")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["pagination"] is not None
        assert body["pagination"]["page"] == 1
        assert body["pagination"]["per_page"] == 20

    @pytest.mark.unit
    def test_no_pagination_data_is_list(self, unit_client):
        resp = unit_client.get("/api/v1/projects")
        assert isinstance(resp.json()["data"], list)


class TestProjectDetail:

    @pytest.mark.unit
    def test_existing_project_returns_200(self, unit_client):
        resp = unit_client.get("/api/v1/projects/P001")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["project_id"] == "P001"

    @pytest.mark.unit
    def test_missing_project_returns_404(self, unit_client):
        resp = unit_client.get("/api/v1/projects/DOES_NOT_EXIST")
        assert resp.status_code == 404
        body = resp.json()
        assert body["success"] is False
        assert body["error"]["code"] == "not_found"


# ─── Integration tests — require glenigan.sql ─────────────────────────────────

@pytest.mark.integration
@pytest.mark.skipif(not DB_PRESENT, reason="glenigan.sql not found at repo root")
class TestIntegration:

    def test_health_check(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_areas_returns_strings(self, client):
        resp = client.get("/api/v1/areas")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) > 0
        assert all(isinstance(a, str) for a in data)

    def test_companies_returns_strings(self, client):
        resp = client.get("/api/v1/companies")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) > 0
        assert all(isinstance(c, str) for c in data)

    def test_paginated_projects_respects_per_page(self, client):
        resp = client.get("/api/v1/projects?page=1&per_page=5")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) <= 5
        assert body["pagination"]["page"] == 1
        assert body["pagination"]["per_page"] == 5

    def test_page_2_differs_from_page_1(self, client):
        p1 = client.get("/api/v1/projects?page=1&per_page=5").json()["data"]
        p2 = client.get("/api/v1/projects?page=2&per_page=5").json()["data"]
        ids_p1 = {r["project_id"] for r in p1}
        ids_p2 = {r["project_id"] for r in p2}
        assert ids_p1.isdisjoint(ids_p2), "Pages must not overlap"

    def test_area_filter_returns_only_matching_area(self, client):
        areas = client.get("/api/v1/areas").json()["data"]
        if not areas:
            pytest.skip("No areas in DB")
        area = areas[0]
        resp = client.get(f"/api/v1/projects?page=1&per_page=20&area={area}")
        assert resp.status_code == 200
        for project in resp.json()["data"]:
            assert project["area"].lower() == area.lower()

    def test_sort_asc_vs_desc_gives_different_order(self, client):
        asc = client.get("/api/v1/projects?page=1&per_page=10&sort_by=project_value&order=asc")
        desc = client.get("/api/v1/projects?page=1&per_page=10&sort_by=project_value&order=desc")
        values_asc = [r["project_value"] for r in asc.json()["data"]]
        values_desc = [r["project_value"] for r in desc.json()["data"]]
        assert values_asc != values_desc

    def test_keyword_filter_returns_matching_names(self, client):
        resp = client.get("/api/v1/projects?page=1&per_page=10&keyword=road")
        assert resp.status_code == 200
        for project in resp.json()["data"]:
            assert "road" in project["project_name"].lower() or \
                   "road" in (project["description"] or "").lower()

    def test_streaming_export_is_valid_base_response(self, client):
        resp = client.get("/api/v1/projects")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["status_code"] == 200
        assert isinstance(body["data"], list)
        assert body["pagination"] is None
