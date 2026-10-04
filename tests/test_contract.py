from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from backend.main import app
from backend import store
from backend.metrics import summary
import pytest

def event(**changes):
    row = dict(path='/v1/sensores/TEMP-001/leitura-atual', timestamp=datetime.now(timezone.utc).isoformat(),
        latency_ms=10, status_code=200, session_id='session', feature='leitura_atual', freshness_seconds=5)
    return dict(row, **changes)

def test_empty_and_temporal_window():
    assert summary([])['latency_p95_ms'] is None
    old = event(timestamp=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat())
    assert summary([old])['sensor_requests'] == 0
    assert summary([old], 120)['sensor_requests'] == 1

def test_routes_percentiles_context_and_future():
    rows = [event(latency_ms=i) for i in range(1, 101)]
    rows += [event(path='/v1/sensores/TEMP-001/historico', feature='historico', latency_ms=700)]
    m = summary(rows)
    assert m['by_route']['/v1/sensores/{tag}/leitura-atual']['latency_p95_ms'] == 95
    assert m['by_route']['/v1/sensores/{tag}/historico']['latency_p95_ms'] == 700
    m = summary([event(session_id='   '), event(feature='desconhecida'), event(freshness_seconds=-10)])
    assert m['context_validity_percent'] == pytest.approx(33.333)
    assert m['future_timestamp_count'] == 1
    assert m['freshness_completeness_percent'] == pytest.approx(66.667)

def test_logging_failure_preserves_response(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DB', tmp_path/'events.db')
    def fail(event):
        raise OSError('disk unavailable')
    monkeypatch.setattr(store, 'save', fail)
    before = app.state.persistence_failures
    with TestClient(app) as client:
        response = client.get('/v1/sensores/TEMP-001/leitura-atual')
        assert response.status_code == 200
        assert response.headers['X-Observability-Status'] == 'unavailable'
        assert app.state.persistence_failures == before+1

def test_provider_bad_timestamp_and_stale_data(tmp_path, monkeypatch):
    from backend.main import provider
    monkeypatch.setattr(store, 'DB', tmp_path/'events.db')
    reading = provider.current('TEMP-001')
    with TestClient(app) as client:
        monkeypatch.setattr(provider, 'current', lambda tag: dict(reading, timestamp='2026-01-01T00:00:00'))
        assert client.get('/v1/sensores/TEMP-001/leitura-atual').status_code == 502
        stale = datetime.now(timezone.utc)-timedelta(seconds=300)
        monkeypatch.setattr(provider, 'current', lambda tag: dict(reading, timestamp=stale.isoformat()))
        client.get('/v1/sensores/TEMP-001/leitura-atual')
        m = client.get('/v1/observabilidade').json()['metrics']
        assert m['fresh_within_120s_percent'] == 0
        assert m['server_error_rate_percent'] == 50

def test_simulation_does_not_refresh_on_query():
    from backend import provider
    assert provider.current('TEMP-001')['timestamp'] == provider.history('TEMP-001', 2)[-1]['timestamp']

def test_store_survives_connections_and_read_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DB', tmp_path/'persistent.db')
    store.save(event(request_id='a'))
    store.save(event(request_id='b'))
    assert [row['request_id'] for row in store.read()] == ['b', 'a']
    def fail(limit):
        raise OSError('unavailable')
    monkeypatch.setattr(store, 'read', fail)
    with TestClient(app) as client:
        assert client.get('/v1/observabilidade').status_code == 503
