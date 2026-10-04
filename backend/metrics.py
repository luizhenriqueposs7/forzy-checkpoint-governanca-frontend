from datetime import datetime, timezone
from math import ceil, isfinite

EXPECTED_FEATURE = {'leitura-atual': 'leitura_atual', 'historico': 'historico'}

def route_of(row):
    suffix = row['path'].rsplit('/', 1)[-1]
    return '/v1/sensores/{tag}/'+suffix if suffix in EXPECTED_FEATURE else row['path']

def context_valid(row):
    session, feature = row.get('session_id', ''), row.get('feature', '')
    suffix = row['path'].rsplit('/', 1)[-1]
    return (row.get('context_bounds_valid', True) and bool(session.strip()) and
            1 <= len(session) <= 128 and feature == EXPECTED_FEATURE.get(suffix))

def percentile(values, fraction=.95):
    return sorted(values)[ceil(fraction*len(values))-1] if values else None

def aggregate(rows):
    total = len(rows)
    latencies = [r['latency_ms'] for r in rows]
    ok = [r for r in rows if r['status_code'] == 200]
    fresh = [r['freshness_seconds'] for r in ok if isinstance(r.get('freshness_seconds'), (int, float))
             and isfinite(r['freshness_seconds']) and r['freshness_seconds'] >= 0]
    pct = lambda count, denominator: round(100*count/denominator, 3) if denominator else None
    return {
        'sensor_requests': total,
        'success_responses': len(ok),
        'valid_freshness_responses': len(fresh),
        'latency_p50_ms': percentile(latencies, .5),
        'latency_p95_ms': percentile(latencies),
        'error_rate_percent': pct(sum(r['status_code'] >= 400 for r in rows), total),
        'client_error_rate_percent': pct(sum(400 <= r['status_code'] < 500 for r in rows), total),
        'server_error_rate_percent': pct(sum(r['status_code'] >= 500 for r in rows), total),
        'context_completeness_percent': pct(sum(bool(r.get('session_id', '').strip() and r.get('feature', '').strip()) for r in rows), total),
        'context_validity_percent': pct(sum(context_valid(r) for r in rows), total),
        'freshness_completeness_percent': pct(len(fresh), len(ok)),
        'future_timestamp_count': sum(isinstance(r.get('freshness_seconds'), (int, float)) and r['freshness_seconds'] < 0 for r in ok),
        'fresh_within_120s_percent': pct(sum(f <= 120 for f in fresh), len(fresh)),
        'freshness_p95_seconds': percentile(fresh),
        'minimum_sample_met': total >= 100,
    }

def evaluations(metrics):
    rules = [
        ('Latencia P95', 'latency_p95_ms', 500, '<=', 'Backend: investigar I/O, provider e volume do historico.'),
        ('Erros HTTP', 'error_rate_percent', 1, '<=', 'Separar 4xx do cliente e 5xx do backend; investigar responsavel.'),
        ('Completude de contexto', 'context_completeness_percent', 100, '>=', 'Front-end: corrigir envio dos dois headers.'),
        ('Validade do contexto', 'context_validity_percent', 100, '>=', 'Front-end: conferir funcionalidade e limites dos headers.'),
        ('Completude de freshness', 'freshness_completeness_percent', 100, '>=', 'Provider: verificar timestamp e sincronizacao dos relogios.'),
        ('Atualidade', 'fresh_within_120s_percent', 95, '>=', 'Provider: verificar atraso na aquisicao; sinalizar dado antigo.'),
    ]
    result = []
    for name, key, target, operator, action in rules:
        value = metrics[key]
        passed = None if value is None else (value <= target if operator == '<=' else value >= target)
        status = 'sem_dados' if value is None else ('atendido_na_amostra' if passed else 'violado_na_amostra')
        result.append(dict(indicator=name, metric=key, value=value, target=target,
                           operator=operator, status=status, action=action,
                           sufficient_sample=metrics['minimum_sample_met']))
    return result

def summary(events, window_minutes=15):
    now = datetime.now(timezone.utc)
    rows = []
    for row in events:
        if row['path'].startswith('/v1/sensores/'):
            age = (now-datetime.fromisoformat(row['timestamp'])).total_seconds()
            if 0 <= age <= window_minutes*60:
                rows.append(row)
    metrics = aggregate(rows)
    routes = {route_of(r) for r in rows}
    metrics['by_route'] = {route: aggregate([r for r in rows if route_of(r) == route]) for route in sorted(routes)}
    metrics['evaluations'] = evaluations(metrics)
    metrics['window_minutes'] = window_minutes
    metrics['window_evaluated_at'] = now.isoformat()
    metrics['scope'] = 'Chamadas de sensores na janela temporal e dentro da amostra retornada; limite pode truncar janela.'
    return metrics
