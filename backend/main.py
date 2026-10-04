import importlib
import logging
import os
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4
from typing import Literal
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, AwareDatetime, FiniteFloat, ValidationError
from starlette.concurrency import run_in_threadpool
from . import store
from .metrics import summary

provider = importlib.import_module(os.getenv('SENSOR_PROVIDER', 'backend.provider'))
logger = logging.getLogger('forzy.observabilidade')
app = FastAPI(title='Forzy Sensor Monitoring API', version='2.0.0')
app.state.persistence_failures = 0

class Reading(BaseModel):
    tag: str
    timestamp: AwareDatetime
    value: FiniteFloat
    unit: str
    severity: Literal['normal', 'alerta', 'critico']
    source: str

@app.middleware('http')
async def observe(request: Request, call_next):
    started = perf_counter()
    request_id = str(uuid4())
    session = request.headers.get('X-Session-Id', '')
    feature = request.headers.get('X-Feature', '')
    event = dict(request_id=request_id, timestamp=datetime.now(timezone.utc).isoformat(),
        session_id=session[:128], feature=feature[:64],
        context_bounds_valid=len(session) <= 128 and len(feature) <= 64,
        method=request.method, path=request.url.path, status_code=500,
        freshness_seconds=None, records_count=None)
    try:
        response = await call_next(request)
        event['status_code'] = response.status_code
    except Exception:
        logger.error('request_failed request_id=%s', request_id)
        response = JSONResponse(status_code=500, content={'detail': 'Erro interno', 'request_id': request_id})
    event['latency_ms'] = round((perf_counter()-started)*1000, 3)
    event['freshness_seconds'] = getattr(request.state, 'freshness_seconds', None)
    event['records_count'] = getattr(request.state, 'records_count', None)
    try:
        await run_in_threadpool(store.save, event)
        response.headers['X-Observability-Status'] = 'persisted'
    except Exception:
        app.state.persistence_failures += 1
        logger.error('persistence_failed request_id=%s', request_id)
        response.headers['X-Observability-Status'] = 'unavailable'
    response.headers['X-Request-Id'] = request_id
    return response

def check(tag):
    if tag not in provider.SENSORS:
        raise HTTPException(404, 'Sensor inexistente')

def validate_rows(request, data):
    try:
        rows = [Reading.model_validate(row) for row in data]
    except ValidationError:
        raise HTTPException(502, 'Provider retornou leitura fora do contrato')
    request.state.records_count = len(rows)
    if rows:
        latest = max(row.timestamp for row in rows)
        request.state.freshness_seconds = (datetime.now(timezone.utc)-latest).total_seconds()
    return [row.model_dump(mode='json') for row in rows]

@app.get('/v1/sensores/{tag}/leitura-atual', response_model=Reading)
def current(tag: str, request: Request):
    check(tag)
    return validate_rows(request, [provider.current(tag)])[0]

@app.get('/v1/sensores/{tag}/historico')
def history(tag: str, request: Request, limit: int = Query(30, ge=1, le=500)):
    check(tag)
    rows = validate_rows(request, provider.history(tag, limit))
    return {'items': rows, 'count': len(rows)}

@app.get('/v1/observabilidade')
def observability(limit: int = Query(1000, ge=1, le=10000), window_minutes: int = Query(15, ge=1, le=1440)):
    try:
        rows = store.read(limit)
    except Exception:
        raise HTTPException(503, 'Repositorio de observabilidade indisponivel')
    return {'items': rows, 'count': len(rows), 'metrics': summary(rows, window_minutes),
        'sample_limit': limit, 'possibly_truncated': len(rows) == limit,
        'logging_health': {'persistence_failures_since_process_start': app.state.persistence_failures},
        'note': 'A chamada atual aparece na proxima consulta. Falhas de persistencia sao contadas apenas desde o inicio do processo.'}
