from fastapi.testclient import TestClient
from backend.main import app
from backend import store

def test_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path/"events.db")
    with TestClient(app) as client:
        headers = {"X-Session-Id": "test-session", "X-Feature": "leitura_atual"}
        r = client.get("/v1/sensores/TEMP-001/leitura-atual", headers=headers)
        assert r.status_code == 200 and r.json()["source"] == "simulacao"
        assert r.headers["X-Request-Id"]
        assert client.get("/v1/sensores/TEMP-001/historico?limit=5", headers=headers).json()["count"] == 5
        assert client.get("/v1/sensores/INVALIDO/leitura-atual", headers=headers).status_code == 404
        assert client.get("/v1/sensores/TEMP-001/historico?limit=0", headers=headers).status_code == 422
        data = client.get("/v1/observabilidade", headers=headers).json()
        assert data["metrics"]["sensor_requests"] == 4
        assert data["metrics"]["error_rate_percent"] == 50
        assert data["metrics"]["context_completeness_percent"] == 100
        assert data["metrics"]["freshness_completeness_percent"] == 100
        assert all(r["latency_ms"] >= 0 for r in data["items"])
        assert len(store.read()) == 5

def test_missing_context_and_exception(tmp_path, monkeypatch):
    from backend import provider
    monkeypatch.setattr(store, "DB", tmp_path/"events.db")
    with TestClient(app) as client:
        client.get("/v1/sensores/TEMP-001/leitura-atual")
        def fail(tag):
            raise RuntimeError("provider failed")
        monkeypatch.setattr(provider, "current", fail)
        assert client.get("/v1/sensores/TEMP-001/leitura-atual").status_code == 500
        data = client.get("/v1/observabilidade").json()
        assert data["metrics"]["context_completeness_percent"] == 0
        assert data["metrics"]["error_rate_percent"] == 50
