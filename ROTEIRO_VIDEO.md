# Roteiro para apresentação do grupo

1. Apresentar FIAP, integrantes e objetivo: observar leitura atual e histórico de sensores.
2. Mostrar API iniciada, interface e rotas em /docs. Declarar se o provider está simulado ou integrado ao original.
3. Consultar leitura atual: valor, unidade, timestamp, severidade e idade do dado.
4. Consultar histórico: tabela e gráfico. Explicar o parâmetro limit.
5. Mostrar observabilidade: headers, request_id, status, latência e freshness.
6. Explicar um indicador e sua ação: idade >120 s exige investigar aquisição, mesmo com HTTP 200 rápido.
7. Mostrar métricas por rota, janela temporal, resultados dos limiares e exportação JSON.
8. Demonstrar tag inexistente (404), mostrar erro no front e registro no backend.
9. Mostrar resultado de pytest, evidências e README; abrir o link real do GitHub.
10. Encerrar com a limitação da demonstração: testes locais não comprovam confiabilidade de sensores físicos.

O vídeo automatizado entregue demonstra as telas. Este roteiro serve caso o grupo queira apresentar oralmente.
