"""管理后台 API 测试"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from main import app

    return TestClient(app)


def test_admin_page(client):
    res = client.get("/api/admin/page")
    assert res.status_code == 200
    assert "成分库管理后台" in res.text


def test_admin_stats(client):
    res = client.get("/api/admin/stats")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["total_ingredients"] >= 400


def test_admin_crud_ingredient(client):
    name = "测试成分AdminXYZ"
    payload = {
        "name": name,
        "ingredient_type": "additive",
        "category": "测试类",
        "safety_level": "safe",
        "description": "测试描述",
        "aliases": ["测试别名XYZ"],
        "tags": ["测试"],
        "potential_risks": [],
        "common_products": ["测试食品"],
    }
    create = client.post("/api/admin/ingredients", json=payload)
    assert create.status_code == 200

    get_res = client.get(f"/api/admin/ingredients/{name}")
    assert get_res.status_code == 200
    assert get_res.json()["data"]["aliases"] == ["测试别名XYZ"]

    search = client.get("/api/admin/ingredients", params={"q": "AdminXYZ"})
    assert search.status_code == 200
    assert search.json()["data"]["total"] >= 1

    delete = client.delete(f"/api/admin/ingredients/{name}")
    assert delete.status_code == 200

    get_after = client.get(f"/api/admin/ingredients/{name}")
    assert get_after.status_code == 404


def test_admin_unknown_candidates(client):
    res = client.get("/api/admin/unknown-candidates")
    assert res.status_code == 200
    assert "items" in res.json()["data"]


def test_admin_reload_requires_token_when_configured(client, monkeypatch):
    from config.settings import get_settings

    monkeypatch.setenv("ADMIN_TOKEN", "test-secret-token")
    get_settings.cache_clear()

    res = client.post("/api/admin/reload-database")
    assert res.status_code == 401

    res_ok = client.post(
        "/api/admin/reload-database",
        headers={"X-Admin-Token": "test-secret-token"},
    )
    assert res_ok.status_code == 200

    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    get_settings.cache_clear()


def test_admin_export_yaml(client):
    res = client.get("/api/admin/export-yaml")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["total"] >= 500
    assert "files" in data


def test_legacy_analyze_text_route(client):
    # 无 body 应 422，说明路由存在（非 404）
    res = client.post("/api/food/analyze_text")
    assert res.status_code == 422


def test_analyze_text_with_text_result_field(client):
    res = client.post(
        "/api/food/analyze_text",
        data={"text_result": "配料：水、苯甲酸钠", "user_notes": "测试"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["code"] == 1
    assert "苯甲酸钠" in str(data["data"]["analysis_result"]["matched_ingredients"])

