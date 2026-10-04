import os
import sys
import json
import subprocess
import time
import platform
from pathlib import Path
from math import ceil
import requests

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
Path('work').mkdir(exist_ok=True)
BASE = 'http://127.0.0.1:8765'
EVIDENCE = ROOT/'evidencias'
EVIDENCE.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT))

def run_case(name, age, action):
    env = os.environ.copy()
    env['OBS_DB'] = str(Path(f'work/http_{name}.sqlite3').resolve())
    env['SENSOR_SIMULATION_AGE_SECONDS'] = str(age)
    db = Path(env['OBS_DB'])
    if db.exists():
        db.unlink()
    log = open(f'work/http_{name}.log', 'w', encoding='utf-8')
    proc = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', '8765'],
        cwd=ROOT, env=env, stdout=log, stderr=log,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    try:
        ready = False
        for _ in range(40):
            if proc.poll() is not None:
                raise RuntimeError(f'API nao iniciou: work/http_{name}.log')
            try:
                requests.get(BASE+'/openapi.json', timeout=1).raise_for_status()
                ready = True
                break
            except requests.RequestException:
                time.sleep(.25)
        assert ready
        return action()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
        log.close()

def send(path, feature=None, session='validacao-http'):
    headers = {} if feature is None else {'X-Session-Id':session, 'X-Feature':feature}
    return requests.get(BASE+path, headers=headers, timeout=10)

def export(name, expected, extra=None):
    data = send('/v1/observabilidade?limit=10000', 'observabilidade').json()
    data['validation'] = {'method':'requests sobre HTTP local com Uvicorn',
        'provider':'simulacao', 'scenario':name, 'expected_sensor_calls':expected,
        'python':platform.python_version(), 'concurrency':1,
        'history_limit':30, 'limitation':'Execucao local sem carga concorrente ou aquisicao fisica Forzy.'}
    if extra:
        data['validation'].update(extra)
    assert data['metrics']['sensor_requests'] == expected
    (EVIDENCE/f'{name}.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    return data

def normal():
    rtts=[]
    for i in range(200):
        suffix, feature = ('historico','historico') if i%2 else ('leitura-atual','leitura_atual')
        start=time.perf_counter()
        response=send('/v1/sensores/TEMP-001/'+suffix,feature)
        rtts.append((time.perf_counter()-start)*1000)
        assert response.status_code == 200
        assert response.headers['X-Observability-Status']=='persisted'
    data=export('normal',200,{'client_round_trip_p95_ms':sorted(rtts)[ceil(.95*len(rtts))-1],
        'record_completeness_percent':100*200/200})
    os.environ['API_URL']=BASE
    from streamlit.testing.v1 import AppTest
    for feature in ['Leitura atual','Historico','Observabilidade']:
        at=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
        at.radio[0].set_value(feature).run()
        at.button[0].click().run()
        assert not at.exception, at.exception
        assert not at.error, at.error
    return data

def invalid():
    cases=[('/v1/sensores/INVALIDO/leitura-atual','leitura_atual',404),
           ('/v1/sensores/TEMP-001/historico?limit=0','historico',422),
           ('/v1/sensores/TEMP-001/leitura-atual',None,200),
           ('/v1/sensores/TEMP-001/leitura-atual','funcionalidade_errada',200)]
    for path,feature,status in cases:
        response=send(path,feature)
        assert response.status_code==status
    data=export('falhas_induzidas',4)
    assert data['metrics']['error_rate_percent']==50
    assert data['metrics']['context_completeness_percent']==75
    assert data['metrics']['context_validity_percent']==50
    return data

def stale():
    for i in range(100):
        assert send('/v1/sensores/TEMP-001/leitura-atual','leitura_atual').status_code==200
    data=export('atraso_aquisicao',100)
    assert data['metrics']['fresh_within_120s_percent']==0
    assert data['metrics']['freshness_p95_seconds']>=300
    from streamlit.testing.v1 import AppTest
    at=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
    at.button[0].click().run()
    assert not at.exception
    assert len(at.warning)>0
    return data

normal_data=run_case('normal',5,normal)
run_case('falhas',5,invalid)
run_case('atraso',300,stale)
print('HTTP local verificado: 200 chamadas normais, 4 falhas induzidas, 100 leituras atrasadas; interface verificada com API real.')
