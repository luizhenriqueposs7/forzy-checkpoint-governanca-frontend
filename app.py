from datetime import datetime, timezone
from uuid import uuid4
from math import ceil
import json
import pandas as pd
import requests
import streamlit as st
from client import get

def temporal_chart(frame, unit):
    data = frame.reset_index().melt(id_vars='timestamp', var_name='indicator', value_name='chart_value')
    data['timestamp'] = data['timestamp'].map(lambda value: value.isoformat())
    st.vega_lite_chart(data, {
        'mark': {'type':'line', 'point':True},
        'encoding': {
            'x': {'field':'timestamp', 'type':'temporal', 'title':'Data e hora UTC', 'scale':{'type':'utc'}, 'axis':{'format':'%d/%m %H:%M'}},
            'y': {'field':'chart_value', 'type':'quantitative', 'title':unit},
            'color': {'field':'indicator', 'type':'nominal', 'title':'Indicador'},
            'tooltip': [{'field':'timestamp','type':'temporal','title':'UTC'}, {'field':'chart_value','type':'quantitative'}]
        }
    })

st.set_page_config(page_title='Forzy Sensores', layout='wide')
st.title('Forzy Monitoramento de sensores')
st.caption('Leitura, historico e evidencias de governanca em uma unica interface.')
st.info('Provider padrao: simulacao de aquisicao congelada ao iniciar a API. Consultar nao renova a data do sensor.')
if 'session_id' not in st.session_state:
    st.session_state.session_id = str(uuid4())
tag = st.text_input('Tag do sensor', 'TEMP-001', help='Exemplos da simulacao: TEMP-001 e VIB-001.').strip()
feature = st.radio('Funcionalidade', ['Leitura atual', 'Historico', 'Observabilidade'], horizontal=True)
history_limit = st.sidebar.slider('Quantidade de leituras', 1, 500, 30)
window = st.sidebar.selectbox('Janela de observabilidade em minutos', [15, 60, 1440])
st.sidebar.caption('As metas sao propostas academicas. Uma amostra pequena nao comprova atendimento continuo.')
if st.button('Consultar', type='primary'):
    try:
        if feature == 'Leitura atual':
            data = get(f'/v1/sensores/{tag}/leitura-atual', 'leitura_atual', st.session_state.session_id)
        elif feature == 'Historico':
            data = get(f'/v1/sensores/{tag}/historico', 'historico', st.session_state.session_id, limit=history_limit)
        else:
            data = get('/v1/observabilidade', 'observabilidade', st.session_state.session_id, limit=10000, window_minutes=window)
        st.session_state['result'] = (feature, tag, data)
    except (requests.RequestException, ValueError) as error:
        st.session_state.pop('result', None)
        st.error(f'Consulta falhou. Verifique a API e a tag. {error}')

if 'result' in st.session_state:
    saved_feature, saved_tag, data = st.session_state['result']
    if saved_feature == feature and (saved_tag == tag or feature == 'Observabilidade'):
        if data.get('_observability_status') == 'unavailable':
            st.error('A resposta foi recebida, mas seu registro de observabilidade nao foi persistido. Investigue o banco.')
        if feature == 'Leitura atual':
            st.metric(data['tag'], f"{data['value']} {data['unit']}")
            st.write('Severidade:', data['severity'], 'Data UTC:', data['timestamp'], 'Origem:', data['source'])
            age = (datetime.now(timezone.utc)-datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))).total_seconds()
            st.metric('Idade do dado em segundos', f'{age:.1f}')
            if age < 0:
                st.error('Timestamp futuro: verificar sincronizacao dos relogios.')
            elif age > 120:
                st.warning('Dado atrasado: verificar aquisicao do sensor. Limiar inicial de 120 segundos excedido.')
        elif feature == 'Historico':
            df = pd.DataFrame(data['items'])
            st.dataframe(df, width='stretch')
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).astype('datetime64[ns, UTC]')
                temporal_chart(df.set_index('timestamp')[['value']], 'Valor do sensor')
        else:
            metrics = data['metrics']
            def formatted(value, suffix=''):
                return 'Sem dados' if value is None else f'{value:.2f}{suffix}'
            cols = st.columns(4)
            cols[0].metric('Chamadas de sensores', metrics['sensor_requests'])
            cols[1].metric('Latencia P95', formatted(metrics['latency_p95_ms'], ' ms'))
            cols[2].metric('Erros HTTP', formatted(metrics['error_rate_percent'], '%'))
            cols[3].metric('Dados em ate 120 s', formatted(metrics['fresh_within_120s_percent'], '%'))
            if not metrics['minimum_sample_met']:
                st.warning('Menos de 100 chamadas: resultado descritivo, insuficiente para avaliar baseline.')
            if data['possibly_truncated']:
                st.warning('O limite de registros foi atingido. A janela pode estar incompleta.')
            if data['logging_health']['persistence_failures_since_process_start']:
                st.error('Foram detectadas falhas de persistencia neste processo. A rastreabilidade esta comprometida.')
            st.subheader('Contrato e acoes por indicador')
            contract = pd.DataFrame(metrics['evaluations'])
            contract['Meta'] = contract.operator+' '+contract.target.astype(str)
            contract['Resultado'] = contract.status.map({'sem_dados':'Sem dados', 'atendido_na_amostra':'Atendido na amostra', 'violado_na_amostra':'Violado na amostra'})
            st.dataframe(contract[['indicator','value','Meta','Resultado']].rename(columns={'indicator':'Indicador','value':'Valor'}), width='stretch', hide_index=True)
            with st.expander('Acoes em caso de violacao'):
                for rule in metrics['evaluations']:
                    st.write(rule['indicator']+': '+rule['action'])
            st.subheader('Comparacao por rota')
            per_route = pd.DataFrame(metrics['by_route']).T
            if not per_route.empty:
                per_route.index = per_route.index.str.rsplit('/').str[-1]
                st.dataframe(per_route[['sensor_requests','latency_p95_ms','error_rate_percent','context_validity_percent','fresh_within_120s_percent']].rename(columns={
                    'sensor_requests':'Chamadas', 'latency_p95_ms':'P95 ms', 'error_rate_percent':'Erros %',
                    'context_validity_percent':'Contexto valido %', 'fresh_within_120s_percent':'Dados em ate 120 s %'}), width='stretch')
            st.caption(data['note'])
            if not per_route.empty:
                st.bar_chart(per_route[['client_error_rate_percent', 'server_error_rate_percent']])
            df = pd.DataFrame(data['items'])
            if not df.empty:
                sensors = df[df.path.str.startswith('/v1/sensores/')].copy()
                if not sensors.empty:
                    sensors['timestamp'] = pd.to_datetime(sensors['timestamp'], utc=True).astype('datetime64[ns, UTC]')
                    evaluated_at = pd.to_datetime(metrics['window_evaluated_at'], utc=True)
                    sensors = sensors[(sensors.timestamp <= evaluated_at) & (sensors.timestamp >= evaluated_at-pd.Timedelta(minutes=metrics['window_minutes']))]
                    sensors['minute'] = sensors['timestamp'].dt.floor('min')
                    evolution = []
                    for minute, rows in sensors.groupby('minute'):
                        valid = rows[(rows.status_code == 200) & rows.freshness_seconds.notna() & (rows.freshness_seconds >= 0)]
                        evolution.append({'timestamp': minute,
                            'latencia_p95_ms': sorted(rows.latency_ms)[ceil(.95*len(rows))-1],
                            'contexto_completo_percent': 100*((rows.session_id.str.strip() != '') & (rows.feature.str.strip() != '')).mean(),
                            'freshness_completo_percent': 100*len(valid)/sum(rows.status_code == 200) if sum(rows.status_code == 200) else None,
                            'idade_p95_segundos': sorted(valid.freshness_seconds)[ceil(.95*len(valid))-1] if len(valid) else None})
                    if evolution:
                        evolution = pd.DataFrame(evolution).set_index('timestamp')
                        evolution.index = evolution.index.astype('datetime64[ns, UTC]')
                        st.subheader('Evolucao por minuto')
                        st.caption('Cada ponto e uma janela de um minuto. Minutos sem chamadas nao comprovam disponibilidade.')
                        temporal_chart(evolution[['latencia_p95_ms']], 'P95 em ms')
                        temporal_chart(evolution[['contexto_completo_percent', 'freshness_completo_percent']], 'Completude em %')
                        temporal_chart(evolution[['idade_p95_segundos']], 'P95 da idade em segundos')
            with st.expander('Registros e contrato completo'):
                st.dataframe(df, width='stretch')
                st.json(metrics)
            st.download_button('Exportar evidencia JSON', json.dumps(data, ensure_ascii=False, indent=2),
                               file_name='evidencia.json', mime='application/json')
