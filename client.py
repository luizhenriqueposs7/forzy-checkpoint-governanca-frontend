import os
from uuid import uuid4
import requests

BASE_URL = os.getenv('API_URL', 'http://127.0.0.1:8000').rstrip('/')

def get(path, feature, session_id, **params):
    response = requests.get(BASE_URL+path,
        headers={'X-Session-Id': session_id, 'X-Feature': feature}, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()
    data['_observability_status'] = response.headers.get('X-Observability-Status', 'unknown')
    data['_request_id'] = response.headers.get('X-Request-Id')
    return data

if __name__ == '__main__':
    session = str(uuid4())
    for path, feature in [('/v1/sensores/TEMP-001/leitura-atual', 'leitura_atual'),
                          ('/v1/sensores/TEMP-001/historico', 'historico'),
                          ('/v1/observabilidade', 'observabilidade')]:
        print(feature, get(path, feature, session))
