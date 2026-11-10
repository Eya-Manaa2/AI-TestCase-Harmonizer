from fastapi.testclient import TestClient

from harmonizer.api import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_analyze_returns_pairs_clusters_and_readiness():
    response = client.post(
        "/analyze",
        json={
            "threshold": 0.9,
            "cases": [
                {"id": "A", "title": "Login", "steps": "Click Login"},
                {"id": "B", "title": " login ", "steps": "Click Login"},
            ],
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["case_count"] == 2
    assert result["pairs"][0]["exact_duplicate"] is True
    assert result["pairs"][0]["left_id"] == "A"
    assert result["readiness"][0]["score"] >= 0
    assert result["standardizations"][0]["id"] == "A"


def test_analyze_rejects_duplicate_ids():
    response = client.post(
        "/analyze",
        json={"cases": [{"id": "A", "title": "One"}, {"id": "A", "title": "Two"}]},
    )
    assert response.status_code == 422


def test_standardization_requires_human_approval_before_export():
    standardized = client.post(
        "/standardize",
        json={"cases": [{"id": "A", "title": "Login", "steps": "Click Login"}]},
    )
    assert standardized.status_code == 200
    case = standardized.json()["cases"][0]
    assert case["approved"] is False
    rejected = client.post("/export", json={"cases": [case], "format": "json"})
    assert rejected.status_code == 422


def test_exports_approved_json_and_csv():
    case = {
        "id": "A",
        "title": "Login",
        "steps": "1. CLICK — Login.",
        "approved": True,
    }
    json_response = client.post("/export", json={"cases": [case], "format": "json"})
    assert json_response.status_code == 200
    assert json_response.json()[0]["id"] == "A"
    csv_response = client.post("/export", json={"cases": [case], "format": "csv"})
    assert csv_response.status_code == 200
    assert "text/csv" in csv_response.headers["content-type"]
    assert "Login" in csv_response.text


def test_exports_excel():
    response = client.post(
        "/export",
        json={
            "cases": [{"id": "A", "title": "Login", "approved": True}],
            "format": "xlsx",
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response.content.startswith(b"PK")


def test_analysis_validates_threshold_range():
    response = client.post("/analyze", json={"cases": [{"title": "Case"}], "threshold": 1.1})
    assert response.status_code == 422
