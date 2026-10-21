# Busão Sanca

Projeto em desenvolvimento para facilitar a consulta de linhas, horários e
itinerários dos ônibus de São Carlos (SP).

> **Estado atual:** além do catálogo, o projeto possui parsers de horários e
> itinerários e um MVP web mobile-first. O MVP é uma prévia privada, não é um
> planejador de viagens e ainda não é uma PWA instalável.

## MVP privado: horários e itinerários

O [`pipeline_mvp.py`](pipeline_mvp.py) usa o catálogo local mais recente,
consulta uma lista pequena de linhas e valida horários, variantes e itinerários
com os parsers existentes. O padrão coleta somente a linha `34`. Respostas
brutas não são gravadas e o dataset normalizado fica em `saida/mvp/` e
`web/dados.json`; ambos permanecem fora do Git.

```powershell
$env:UV_CACHE_DIR = ".uv-cache"
uv run --locked python pipeline_mvp.py --linhas 34 --intervalo 2
uv run --locked python -m http.server 8000 --directory web --bind 127.0.0.1
```

Abra `http://127.0.0.1:8000`. O servidor fica restrito ao próprio computador.
Não exponha o servidor de desenvolvimento diretamente na internet. Para abrir
no Android fora da rede local, use somente uma implantação privada autenticada;
o arquivo `web/dados.json` não deve ser commitado nem publicado abertamente.

A interface permite buscar por número, nome e destino, selecionar uma data,
consultar sentidos, variantes, partidas e paradas. A data limita apenas o
intervalo de vigência declarado pelo serviço. Ela **não** confirma o dia da
semana, pois a ordem do vetor semanal e a semântica das exceções ainda não
foram estabelecidas. Partidas são exibidas explicitamente como horários na
origem da viagem, nunca como previsão em uma parada intermediária.

O módulo [`planejar_viagem.py`](planejar_viagem.py) oferece análise experimental
conservadora de origem e destino: calcula distância em linha reta, exige que o
embarque preceda o desembarque e nunca converte partida de terminal em horário
de passagem. O estudo da primeira viagem está documentado em
[`docs/planejamento-experimental.md`](docs/planejamento-experimental.md).

O pipeline só classifica como completa a cobertura do escopo solicitado quando
todas as variantes foram obtidas. Geometrias cujas extremidades divergem das
paradas podem ser preservadas para diagnóstico, ficam enumeradas em
`cobertura.geometrias_com_extremidades_divergentes` e recebem aviso na tela.

## Etapa 1: coletar o catálogo de linhas

O coletor Python parte da [página oficial da SOU](https://soutransportes.com.br/sao-carlos/linhas-e-horarios/), identifica o catálogo incorporado à página e consulta a API pública usada por esse catálogo. Exporta código, nome, URL de origem e instante da coleta, com evidências para conferir de onde vieram os dados.

**A completude municipal ainda não está verificada.** A API observada retorna um array sem declarar o total de linhas do município. O programa verifica e exporta todos os registros dessa resposta, mas isso não comprova que ela abranja todas as linhas em operação. A saída registra essa limitação explicitamente. Não há complemento automático com uma lista de referência.

A investigação da fonte, as regras de acesso observadas e suas limitações estão em [docs/fonte-sou.md](docs/fonte-sou.md).

## Preparar o ambiente

É necessário Python 3.10 ou superior. Execute os comandos na raiz deste
repositório, onde está [coletar_linhas.py](coletar_linhas.py). O ambiente
recomendado usa `uv` e o [uv.lock](uv.lock) versionado:

```powershell
$env:UV_CACHE_DIR = ".uv-cache"
uv sync --locked
```

Esse comando cria `.venv` e instala somente as dependências do coletor e dos
testes. O cache local e o ambiente virtual não são versionados. Para executar
sem alterar permanentemente `UV_CACHE_DIR`, use a atribuição apenas no terminal
atual.

As dependências de execução também estão em
[requirements.txt](requirements.txt): `requests` para HTTP e
`beautifulsoup4` para localizar o iframe no HTML.

No Windows, com PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe coletar_linhas.py
```

No Linux ou macOS:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python coletar_linhas.py
```

Os comandos com `venv` e `pip` são uma alternativa compatível, mas não usam o
lockfile do projeto.

## Executar a coleta

```sh
python coletar_linhas.py --saida saida/oficial --timeout 30 --intervalo 2
```

Com o ambiente criado pelo `uv`, prefira:

```powershell
uv run --locked python coletar_linhas.py --saida saida/oficial --timeout 30 --intervalo 2
```

Use o executável do ambiente virtual mostrado acima se ele não estiver ativado.

| Opção | Padrão | Comportamento |
| --- | --- | --- |
| `--saida` | `saida/oficial` na raiz do repositório | Diretório que receberá uma pasta por execução bem-sucedida. Um caminho fornecido explicitamente é relativo ao diretório de execução, salvo quando absoluto. |
| `--timeout` | `30` | Tempo limite, em segundos, aplicado às requisições HTTP. Deve ser positivo e finito. |
| `--intervalo` | `2` | Intervalo mínimo entre requisições, em segundos. Valores menores que 2 são recusados. Regras da fonte podem aumentar a espera. |
| `--help` | — | Mostra a ajuda da linha de comando. |

As requisições são sequenciais. O cliente identifica-se como `BusaoSanca/0.2` e consulta `robots.txt` de cada origem antes de buscar seu conteúdo. Bloqueios, redirecionamentos e falhas de verificação encerram a coleta. Consulte o [detalhamento do acesso HTTP](docs/fonte-sou.md#acesso-http).

## Arquivos gerados

Cada sucesso cria uma pasta com identificador de data e hora UTC dentro do diretório de saída:

```text
saida/oficial/<identificador-UTC>/
├── linhas.csv
├── linhas.json
├── coleta.json
└── fontes/
    ├── pagina_oficial.html
    ├── catalogo.html
    ├── projeto.json
    └── rotas.json
```

A pasta só é publicada depois que todos os arquivos foram escritos. Execuções anteriores são preservadas.

| Campo de cada linha | Significado |
| --- | --- |
| `codigo` | Código textual informado pela fonte (`shortName`); mantém zeros iniciais. |
| `nome` | Nome informado pela fonte (`longName`). |
| `url_origem` | URL da resposta da API que forneceu a linha. |
| `coletado_em` | Instante da coleta em ISO 8601, com fuso UTC explícito. Não é a data de atualização da linha pela operadora. |
| `id_linha` | Identificador numérico da linha na API (`routeId`). |
| `url_pagina_oficial` | Página da SOU que incorporou o catálogo. |
| `url_catalogo` | Endereço do catálogo Bus2, incluindo o identificador da cidade no fragmento. |

O CSV usa UTF-8 com BOM (`utf-8-sig`) e separador vírgula. O código é gravado como texto, mas o Excel pode inferir que ele é um número ao abrir o arquivo e remover zeros iniciais. Importe o CSV e defina a coluna `codigo` como **Texto**. O JSON preserva esse campo como string.

O JSON contém um objeto com duas chaves: `metadados` e `linhas`. Os metadados também são salvos separadamente no arquivo de diagnóstico da coleta e incluem:

- origem, projeto, instante da coleta e quantidade de registros;
- registros recebidos e exportados, ausência de total declarado e `completude_municipal: "nao_verificada"`;
- resultado da consulta às regras de acesso;
- URL, status HTTP, instante da consulta, alguns cabeçalhos e SHA-256 de cada resposta guardada.

Os arquivos em `fontes/` guardam os corpos recebidos, antes da extração das linhas. Seus hashes permitem conferir a integridade dessas evidências.

## Falhas e dados anteriores

Uma coleta malsucedida retorna código de saída `1`, descreve o problema na saída de erro e tenta gravar um diagnóstico JSON em `falhas/`, dentro do diretório escolhido em `--saida`. Se o diagnóstico também não puder ser salvo, o programa informa isso na saída de erro. Argumentos inválidos são recusados pela linha de comando com código `2`.

O coletor interrompe a execução quando não consegue confirmar a cidade e o projeto, quando o iframe ou formato muda, quando recebe lista vazia, campos inválidos, códigos ou identificadores duplicados, ou sinais de resposta parcial/paginação não suportada. Não descarta silenciosamente registros inválidos para produzir uma lista aparentemente completa.

Falhas temporárias de conexão, timeout e HTTP 5xx admitem até três tentativas no total por requisição. HTTP 401, 403 e 429 encerram a coleta sem repetição. Em caso de mudança da fonte, reveja o adaptador e as regras de acesso antes de executar novamente.

O arquivo local `dados/linhas_referencia.csv` é uma referência de pesquisa e
não é lido pelo coletor. Os resultados locais em `saida/` também não
completam respostas da API nem devem ser confundidos com uma coleta oficial
validada.

O diretório `saida/` e os CSVs externos em `dados/` são ignorados pelo Git.
Isso preserva localmente as evidências e referências anteriores sem publicar
dados de terceiros antes da confirmação das condições de redistribuição.

## Testes básicos

Os testes usam respostas simuladas e não precisam consultar o site. Com as dependências instaladas, execute:

```sh
python -m unittest discover -s tests -v
```

Ou, no ambiente reproduzível do projeto:

```powershell
$env:UV_CACHE_DIR = ".uv-cache"
uv run --locked python -m unittest discover -s tests -v
```

Os testes cobrem as regras de acesso HTTP e as validações do coletor. Eles verificam o comportamento do código diante dos formatos e erros previstos; não comprovam a disponibilidade atual da fonte nem a completude do catálogo municipal.

## Organização

- [coletar_linhas.py](coletar_linhas.py): descoberta do catálogo, validação, extração e exportação.
- [acesso_http.py](acesso_http.py): regras de acesso, espera entre requisições e tratamento de falhas HTTP.
- [processar_horarios.py](processar_horarios.py): parser puro e normalização das respostas de horários, sem acesso HTTP.
- [processar_itinerarios.py](processar_itinerarios.py): parser puro de itinerários, paradas e geometria, associado ao `tripId` dos horários.
- [tests/](tests/): testes automatizados com respostas simuladas.
- [docs/fonte-sou.md](docs/fonte-sou.md): evidências da investigação e decisões técnicas.
- [docs/esquema-horarios.md](docs/esquema-horarios.md): esquema normalizado, invariantes e limitações do parser de horários.
- [docs/esquema-itinerarios.md](docs/esquema-itinerarios.md): contrato normalizado, validação espacial e limitações dos itinerários.
- [inspecionar_oficial.py](inspecionar_oficial.py): utilitário de inspeção já existente no projeto; a execução documentada nesta etapa usa o coletor.

## Inspeção opcional com navegador

O utilitário `inspecionar_oficial.py` não faz parte da coleta normal. Ele exige
Playwright, navegador compatível e ambiente gráfico. Para preparar essa
dependência opcional:

```powershell
$env:UV_CACHE_DIR = ".uv-cache"
uv sync --locked --extra diagnostico
uv run playwright install chromium
```

O download do navegador é separado e não é necessário para executar o
coletor ou seus testes.
