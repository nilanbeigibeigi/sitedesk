"""Tests with FastAPI's TestClient and a fake AI (no Ollama needed)."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SITEDESK_DB", str(tmp_path / "t.db"))
    import importlib, app.db, app.ai, app.main
    importlib.reload(app.db); importlib.reload(app.ai); importlib.reload(app.main)
    with TestClient(app.main.app) as c:
        yield c


def test_pages_load(client):
    for url in ["/", "/reports", "/certs", "/rfis", "/reports/1"]:
        assert client.get(url).status_code == 200, url


def test_dashboard_flags_seeded_problems(client):
    html = client.get("/").text
    assert "Daniel Okafor" in html          # expired WHMIS -> not cleared / to renew
    assert "days late" in html              # RFI-002 is overdue
    assert "without a harness" in html      # safety issue from a recent report


def test_rule_check_catches_safety_even_without_ai():
    from app import ai
    def broken(*a): raise ConnectionError("Ollama is off")
    r = ai.structure_report("5 guys. saw a worker on the roof with no harness. also a near miss with the forklift", chat=broken)
    assert not r["ai_ok"] and "Fall protection not used" in r["safety"] and "Near miss" in r["safety"]


def test_preview_then_save_report(client, monkeypatch):
    from app import ai
    fake = json.dumps({"crew_count": 6, "weather": "Sunny", "work_done": ["Framed unit 4"],
                       "delays": [{"reason": "Concrete truck late", "hours": 2}], "safety_issues": [],
                       "materials_needed": ["Nails"], "summary": "Unit 4 framed; 2 h concrete delay."})
    monkeypatch.setattr(ai, "_chat", lambda s, u: fake)
    r = client.post("/reports/preview", data={"site_id": 1, "date": "2026-09-28", "author": "Test",
                                               "raw_notes": "6 guys, sunny, framed unit 4, concrete 2 hrs late"})
    assert "Framed unit 4" in r.text and 'value="2.0"' in r.text
    s = client.post("/reports", data={"site_id": 1, "date": "2026-09-28", "author": "Test", "raw_notes": "x",
                                      "crew_count": "6", "delay_hours": "2", "summary": "Unit 4 framed"})
    assert s.status_code == 204 and s.headers["HX-Redirect"].startswith("/reports/")
    assert "Unit 4 framed" in client.get(s.headers["HX-Redirect"]).text


def test_rfi_create_and_answer(client):
    client.post("/rfis", data={"site_id": 3, "subject": "Tile layout", "question": "Which pattern?",
                               "to_party": "Designer", "due_on": "2026-12-01"}, follow_redirects=False)
    html = client.get("/rfis").text
    assert "RFI-002" in html and "Tile layout" in html
    r = client.post("/rfis/2/answer", data={"answer": "Use 4-ply"})
    assert "Answered" in r.text


def test_renewing_cert_clears_worker(client):
    assert "Not cleared" in client.get("/certs").text
    client.post("/certs", data={"worker_id": 3, "cert_type": "WHMIS", "expires_on": "2030-01-01"})
    client.post("/certs", data={"worker_id": 8, "cert_type": "WHMIS", "expires_on": "2030-01-01"})
    from app import main
    assert next(w for w in main.workers_with_certs() if w["id"] == 3)["cleared"]
