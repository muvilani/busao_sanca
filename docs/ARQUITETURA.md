# Arquitetura do Busão Sanca

## Visão geral

O Busão Sanca é dividido em aquisição, validação, consolidação e apresentação.
As respostas externas nunca são consumidas diretamente pela interface: cada
etapa valida seu contrato e uma falha impede que o resultado incompleto seja
classificado como completo.

```text
SOU / catálogo Bus2
        |
        v
coletar_linhas.py + acesso_http.py
        |
        v
catálogo local versionado somente como evidência ignorada
        |
        v
pipeline_mvp.py / coletar_lotes.py
        |
        +--> processar_horarios.py
        +--> processar_itinerarios.py
        |
        v
consolidar_datasets.py
        |
        v
web/dados.json (privado, ignorado) --> interface buildless em web/
```

## Aquisição e segurança HTTP

[`acesso_http.py`](../acesso_http.py) centraliza acesso às origens permitidas,
consulta `robots.txt`, aplica intervalo mínimo, limites de tamanho, timeout e
repetição restrita para falhas transitórias. Redirecionamentos inesperados,
bloqueios, respostas parciais e formatos não suportados falham de forma
fechada.

[`coletar_linhas.py`](../coletar_linhas.py) descobre o projeto a partir da
página oficial, valida a cidade e normaliza o catálogo. A quantidade recebida
não é tratada como prova de completude municipal.

## Contratos de horários e itinerários

[`processar_horarios.py`](../processar_horarios.py) valida identidades,
direções, serviços, vigências, variantes e partidas. O vetor semanal e as
exceções são preservados, mas não interpretados enquanto sua semântica não
estiver comprovada.

[`processar_itinerarios.py`](../processar_itinerarios.py) exige, entre outros
campos, um array `stops` com pelo menos duas paradas válidas. A geometria é
decodificada e comparada às extremidades; divergências podem ser preservadas
como diagnóstico, nunca convertidas silenciosamente em confirmação.

[`pipeline_mvp.py`](../pipeline_mvp.py) relaciona cada `tripId` dos horários ao
respectivo itinerário. Uma variante sem itinerário válido impede a cobertura
completa daquela linha. [`coletar_lotes.py`](../coletar_lotes.py) reutiliza
somente linhas que passam novamente por essas invariantes.

## Consolidação

[`consolidar_datasets.py`](../consolidar_datasets.py) reúne linhas validadas e
mantém separadas as classificações `validadas`, `com_falhas` e
`nao_coletadas`. O consolidado local e as respostas brutas ficam em `saida/`,
fora do Git.

## Interface web

`web/` é uma aplicação estática, sem framework ou etapa obrigatória de build:

- `app.js`: carregamento do dataset, busca de linhas e renderização geral;
- `planejador.js`: busca textual e rotas diretas ou com uma conexão estrutural;
- `paradas.js`: índice de paradas, busca manual, proximidade e consulta por
  parada;
- `styles.css` e `planner.css`: layout mobile-first;
- `index.html`: estrutura semântica e avisos de uso.

A geolocalização é opcional, processada no navegador e usada apenas para
ordenar distâncias em linha reta. A consulta por parada filtra pela vigência
declarada da data escolhida, mas não afirma operação naquele dia. Os horários
continuam sendo partidas na origem da viagem, não previsão de passagem.

O planejador usa `id_parada` como identidade confiável. Cada alternativa
preserva linha, sentido, variante, serviço e ordem do itinerário. Uma viagem
direta exige embarque anterior ao desembarque na mesma variante. Uma conexão
exige duas variantes válidas e exatamente o mesmo `id_parada` no ponto de
troca; igualdade de nome não basta. Os resultados são deduplicados e ordenados
por número de conexões, quantidade de paradas e identificadores estáveis. A
conexão continua marcada como candidata não verificada porque o dataset não
confirma tempo de transferência, espera, tarifa ou integração.

## Fronteira de publicação

[`preparar_publicacao.py`](../preparar_publicacao.py) é a única rotina prevista
para montar uma prévia publicável a partir do repositório principal. Ela:

1. copia uma lista fechada de assets de `web/`;
2. recusa fixture sem `demonstracao.sintetico: true`;
3. publica apenas `publicacao/dados.demo.json` como `dados.json`;
4. gera hashes dos arquivos em um manifesto local;
5. não acessa rede, não faz deploy e não lê `web/dados.json` ou `saida/`.

O diretório gerado `publicacao/dist/` é ignorado. O repositório separado
`site` não faz parte desse fluxo até existir autorização explícita para
atualizá-lo.

## Testes

A suíte cobre parsers, acesso HTTP simulado, pipelines, consolidação,
planejamento, paradas e política do pacote. O teste funcional de navegador
monta a prévia sintética em diretório temporário e abre Edge/Chrome/Chromium
headless em quatro viewports: Android e iPhone, retrato e paisagem. Também
verifica estados vazios e de erro, foco por teclado, overflow, rotas direta e
com conexão, troca de data e geolocalização simulada. Sem navegador compatível,
somente os testes dependentes dele são marcados como ignorados.

Automação headless não substitui validação em Android/iOS físico, permissões
reais do sistema, leitores de tela, condições de rede lenta ou instalação como
PWA. O roteiro seguro de validação está em
[`TESTE_MOBILE.md`](TESTE_MOBILE.md).
