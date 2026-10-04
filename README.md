# Forzy Sensor Monitoring API

Checkpoint integrado de Governança em IA e Front-end da FIAP.

## Integrantes em ordem alfabética

| Nome | RM |
|---|---|
| Bernardo Braga Perobeli | 562468 |
| Felipe Stefani Honorato | 563380 |
| Igor Paixão Sarak | 563726 |
| Lucca Phelipe Masini | 564121 |
| Luiz Henrique Poss | 562177 |

## Arquitetura

Streamlit → requests com headers de contexto → FastAPI → provider de Sensores.
Middleware → SQLite → GET /v1/observabilidade → indicadores, gráficos e exportação JSON.

O provider padrão é uma **simulação**. A aquisição ocorre ao iniciar o processo;
consultar não renova timestamps. Não há inferência de modelo de IA.
A integração com o provider original da Forzy depende do módulo do projeto construído em aula.
Este repositório contém uma interface de adaptação, não uma integração original comprovada.

## Requisitos e execução

Python 3.12. As versões diretas estão fixadas em requirements.txt.
requirements-lock.txt registra também as dependências transitivas do ambiente de teste Windows.
Execute os comandos na pasta deste README.

Terminal 1 em PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Terminal 2:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --global.developmentMode false
```

Interface: http://localhost:8501. OpenAPI: http://127.0.0.1:8000/docs.
Pacotes principais: FastAPI/Uvicorn para API, SQLite da biblioteca padrão para persistência,
requests para HTTP, Streamlit/pandas para interface, pytest/httpx para testes.

Terminal 3:

```powershell
.\.venv\Scripts\python.exe client.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\validate_http.py
```

O roteiro HTTP inicia seus próprios servidores de teste na porta 8765 e os encerra ao terminar.
Ele grava evidências em evidencias/ e arquivos intermediários em work/. Não exige a API da porta 8000.

## Endpoints e contexto

| Rota | Resposta |
|---|---|
| GET /v1/sensores/{tag}/leitura-atual | tag, timestamp, valor, unidade, severidade e origem |
| GET /v1/sensores/{tag}/historico?limit=30 | items e count; limite de 1 a 500 |
| GET /v1/observabilidade?limit=10000&window_minutes=15 | eventos, métricas, resultados por rota e saúde de persistência |

Tags da simulação: TEMP-001 e VIB-001. Na interface, a tag pode ser digitada.
Headers: X-Session-Id (sessão pseudônima, até 128 caracteres) e X-Feature
(leitura_atual, historico ou observabilidade, até 64 caracteres).
Ausência e invalidade são registradas para medir descumprimento, sem rejeitar a consulta de sensores.

Toda resposta contém X-Request-Id e X-Observability-Status.
Se o banco falhar, a leitura pode continuar disponível, mas o status de observabilidade
será unavailable e a interface sinalizará a perda. O contador de falhas vale apenas desde o início do processo.
Se a leitura do repositório de logs falhar, observabilidade retorna 503.

## Metric Contract

Contrato detalhado: METRIC_CONTRACT.json e relatório de governança.

- Latência: P50 e P95 nearest rank, em ms; meta inicial P95 <= 500 ms.
- Erros HTTP: percentual de status >= 400; meta inicial <= 1%; 4xx e 5xx separados.
- Contexto completo e válido: metas 100%; validade compara funcionalidade e limites.
- Freshness completa: respostas 200 com idade finita e não negativa / respostas 200; meta 100%.
- Atualidade: idade <= 120 s / idades válidas; meta >= 95%; monitorar P95 da idade.
- Completude de registro: contagem externa versus eventos persistidos; meta 100%, verificada pelo roteiro.

Janela padrão: 15 minutos. Limite de até 10 mil eventos pode truncar a janela;
possibly_truncated sinaliza esse risco. Métricas excluem consultas de observabilidade.
Sem denominador, taxas são null. Há resultados agregados e por rota.
O mínimo didático de 100 chamadas não comprova representatividade ou SLA de produção.
Metas são propostas do projeto; fontes conceituais não prescrevem esses valores numéricos.

Latência interna exclui persistência e transporte. O roteiro mede também ida e volta no cliente.
Freshness usa o timestamp de aquisição, não o horário em que o cliente consultou a API.
Timestamp futuro é uma falha temporal; valor não finito ou timestamp sem fuso viola o esquema e gera 502.

## Baseline e evidências

Evidências de HTTP local com requests e Uvicorn, sem aquisição física e com concorrência 1:

| Arquivo | Cenário |
|---|---|
| evidencias/normal.json | 200 chamadas, 100 por rota, sem falhas induzidas |
| evidencias/falhas_induzidas.json | 404, 422, contexto ausente e funcionalidade incorreta |
| evidencias/atraso_aquisicao.json | 100 leituras com aquisição inicial 300 s atrasada |

Oito testes automatizados passaram. A interface foi testada com AppTest usando HTTP real,
inclusive aviso de atraso, e foi conferida em navegador durante a gravação automatizada.
O baseline deve ser repetido com o provider original e com condições representativas de uso.

## Integração do provider original

Crie um módulo, por exemplo backend/provider_forzy.py, que adapte o provider do grupo:

```python
# Substitua os acessos abaixo pela implementação original do grupo.
SENSORS = {"TAG_REAL": {}}

def current(tag):
    # Retornar dicionário com os campos definidos abaixo.
    raise NotImplementedError("Conectar ao provider original")

def history(tag, limit=30):
    # Retornar lista de leituras, preferencialmente em ordem temporal.
    raise NotImplementedError("Conectar ao provider original")
```

Cada leitura: tag (str), timestamp (ISO 8601 com fuso), value (número finito), unit (str),
severity (normal, alerta ou critico) e source (origem real).
Preserve o horário de aquisição original. Converta nomes de campos e severidades no adaptador.

```powershell
$env:SENSOR_PROVIDER="backend.provider_forzy"
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

SENSOR_PROVIDER inválido impede a inicialização, em vez de retornar silenciosamente à simulação.
Para ensaiar dados antigos no provider padrão, defina SENSOR_SIMULATION_AGE_SECONDS=300 antes de iniciar a API.
API_URL configura o destino do frontend; OBS_DB configura o arquivo de persistência.

## Governança e limites

Não há autenticação, conforme o escopo. A sessão não comprova identidade pessoal.
Execute localmente. Não registre nomes, RM, IP, cookies, tokens ou informações pessoais nos headers.
Logs persistem após reinício. Há proposta de limpeza controlada após avaliação; não há retenção automática.
Os gráficos avaliam as consultas recebidas e não detectam sozinhos intervalos de indisponibilidade.
Alertas são exibidos na consulta; não há notificação em segundo plano.
Perda de registro torna a evidência incompleta, mesmo que a leitura de sensores funcione.

## Demonstração e entrega

[Vídeo da entrega no YouTube](https://youtu.be/HtlurgMkMcI).

[Demonstracao_Forzy.webm](media/Demonstracao_Forzy.webm) está no repositório: gravação automatizada,
com legendas, das telas de leitura, histórico, observabilidade e erro 404. Não é apresentação oral do grupo.
Se preferir, gravem uma apresentação usando ROTEIRO_VIDEO.md.

Para Front-end, envie o link deste repositório no Teams da disciplina junto da demonstração.
Não publique .venv/, work/, data/ ou logs pessoais. O código, o relatório e o vídeo estão disponíveis nas pastas deste repositório.
Prazo de Governança informado: 14/10/2026. Prazo de Front-end: confirmar com professor Lucas.
O relatório declara assistência de IA, inclusive na conclusão, que não cumpre a condição de escrita sem IA do enunciado.

## Fontes conceituais

- https://opentelemetry.io/docs/concepts/observability-primer/
- https://sre.google/workbook/implementing-slos/
- https://fastapi.tiangolo.com/tutorial/middleware/
- https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state

## Relatório e vídeo

- [Relatório editável em Word](docs/Relatorio_Governanca_Forzy.docx)
- [Relatório em PDF](docs/Relatorio_Governanca_Forzy.pdf)
- [Vídeo da entrega no YouTube](https://youtu.be/HtlurgMkMcI)
- [Gravação demonstrativa local](media/Demonstracao_Forzy.webm)

O sumário do Word é um campo atualizável. Confira a paginação antes de entregar; o PDF possui paginação conferida.
