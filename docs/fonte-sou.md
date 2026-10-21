# Fonte de linhas da SOU São Carlos

## O que foi observado

Investigação realizada em **20 de outubro de 2026** a partir da [página de linhas e horários da SOU São Carlos](https://soutransportes.com.br/sao-carlos/linhas-e-horarios/).

A página incorpora o catálogo por um iframe para [Bus2 São Carlos](https://bus2.info/2you/#/41r5p). A lista é carregada por JavaScript na aplicação incorporada; extrair apenas os links do HTML da SOU não fornece o catálogo.

Durante a navegação foram observadas estas requisições públicas, sem autenticação:

| Recurso | Papel |
| --- | --- |
| [Detalhes do projeto](https://mobilibus.com/api/project-details?project_hash=41r5p) | Relaciona o identificador do iframe ao projeto. Na resposta observada, `city` era `São Carlos, SP` e `projectId` era `317`. |
| [Linhas do projeto](https://mobilibus.com/api/routes?origin=web&project_id=317) | Retorna os registros de linhas usados pelo catálogo. |

A resposta de linhas observada continha **40 registros**. Esse é um retrato daquela consulta, não um total oficial declarado nem uma quantidade fixada no código.

O coletor lê o identificador do iframe em cada execução, consulta os detalhes do projeto e valida a cidade antes de buscar as linhas. Não fixa o identificador numérico do projeto nem o total esperado de registros. O host e os caminhos da API fazem parte de um adaptador para a integração observada; não foi identificada documentação que garanta sua estabilidade.

## Limite da cobertura

No formato observado, a API retorna um array sem total declarado. Também não foi identificado um mecanismo de paginação nessa resposta. Isso permite verificar se todos os elementos recebidos foram exportados, mas não confirmar que a fonte inclua todas as linhas em operação no município.

Por isso, os metadados registram:

- o escopo como os registros retornados pelo catálogo incorporado à página oficial;
- as quantidades recebida e exportada;
- `todos_os_registros_da_resposta_exportados: true` somente após validar todos os registros;
- `total_declarado_pela_fonte: null`;
- `completude_municipal: "nao_verificada"`.

Uma confirmação de cobertura municipal exige uma evidência adicional da fonte, como um total declarado, documentação de cobertura ou uma relação oficial reconciliável. Uma lista de referência local não serve como substituto dessa confirmação.

Se aparecer indicação de paginação no cabeçalho `Link`, `Content-Range`, um formato diferente de array ou qualquer registro inválido, o coletor falha. Não tenta adivinhar páginas nem publica apenas os registros que conseguiu entender.

## Acesso HTTP

As observações de `robots.txt` durante a investigação foram:

| Origem | Resultado observado |
| --- | --- |
| [SOU Transportes](https://soutransportes.com.br/robots.txt) | As regras consultadas permitiam o caminho da página de linhas e horários. |
| [Bus2](https://bus2.info/robots.txt) | Regra `Allow: /`. |
| [Mobilibus](https://mobilibus.com/robots.txt) | HTTP 404: arquivo de regras ausente. |

Essas observações não substituem uma verificação futura. O [cliente HTTP](../acesso_http.py) consulta as regras novamente em cada execução e verifica cada caminho antes de buscar seu conteúdo.

O comportamento implementado é:

- usar apenas HTTPS nos hosts `soutransportes.com.br`, `bus2.info` e `mobilibus.com`, sem credenciais na URL;
- identificar as requisições pelo `User-Agent` `BusaoSanca/0.2 (+https://github.com/muvilani/busao_sanca)`;
- fazer requisições sequenciais, separadas por pelo menos dois segundos, respeitando esperas maiores indicadas por `Crawl-delay` e `Request-rate`;
- tratar HTTP 404 ou 410 **de `robots.txt`** como ausência de regras desse arquivo; esses status em conteúdo exigido pela coleta são erros;
- interromper quando as regras proíbem o caminho, quando a consulta às regras falha ou quando o suposto arquivo de regras retorna HTML;
- interromper diante de regras que o adaptador não consegue avaliar com segurança, como padrões com `*` ou `$`, esperas em formato não suportado e regras `Allow`/`Disallow` sobrepostas;
- não seguir redirecionamentos automaticamente;
- encerrar imediatamente em HTTP 401, 403 ou 429, informando `Retry-After` quando disponível;
- permitir no máximo três tentativas por requisição em erros de conexão, timeout e HTTP 5xx, com espera entre tentativas;
- aplicar timeout e limite de 10 MiB por resposta.

Não são usados login, proxies para contornar restrições, resolução de CAPTCHA ou outro mecanismo para superar bloqueios.

### Termos lidos; condições de reutilização ainda não confirmadas

Em 20/10/2026, após autorização para retomar a consulta, foram lidas as seis páginas dos [termos de uso do Bus2](https://static.mobilibus.com/legal/app/bus2_terms_of_use_pt_br.pdf). O PDF respondeu HTTP 200 e declara atualização em 27/06/2024. O robots.txt de static.mobilibus.com respondeu 404.

SHA-256 do PDF consultado: `6011d6316b56e7f81df7c319ed5a3635dabc89ae37f67ccc55d9476b06b4c715`.

- Item 3.3, página 2: prevê consultas básicas sem cadastro, incluindo trajetos e horários.
- Itens 4.1–4.3, páginas 2–3: licença limitada para usar os serviços, reserva de direitos sobre conteúdo e exigência de consentimento escrito para marcas e logotipos.
- Item 6.1.1, página 4: recomenda exportar e baixar periodicamente dados em GTFS para preservar histórico.

Não foi identificada nesses termos uma licença explícita para coletar a API e republicar seus dados em um PWA independente. A recomendação de exportação GTFS não confirma essa permissão nem indica um endereço público de download para São Carlos. O resultado é **leitura realizada; condições de reutilização pendentes de esclarecimento**, e não uma conclusão de proibição ou autorização jurídica.

Os metadados da coleta anterior permanecem inalterados: descrevem o conhecimento no instante daquela execução. O coletor não consulta nem interpreta termos automaticamente; seu campo `termos_adicionais_fornecedor` não substitui esta revisão manual. Robots.txt também não estabelece licença de redistribuição.

### Conferência municipal complementar — 20/10/2026

Foram consultados o portal da Prefeitura, resultados de busca restritos ao domínio municipal e dois comunicados oficiais. A tentativa de abrir o portal de mobilidade vinculado pela Prefeitura não concluiu o carregamento. Esta foi uma pesquisa pontual, não uma varredura exaustiva dos documentos municipais.

| Fonte municipal | Conferência com a coleta de 20/10/2026 às 18:35 UTC | Limitação |
| --- | --- | --- |
| [Comunicado de 28/05/2025](https://saocarlos.sp.gov.br/index.php/noticias-2025/179499-comunicado-.html) | Cita a linha 52, Santa Eudóxia–Estação. O código 52 consta na coleta como Estação Fepasa X Santa Eudóxia. | Confirma uma referência histórica à linha e indica o app SOU para consultas; não fornece lista completa atual. |
| [Ampliação do atendimento de 30/04/2026](https://saocarlos.sp.gov.br/index.php/noticias-2026/180807-netto-donato-amplia-tarifa-zero-e-leva-transporte-gratuito-ate-a-babilonia-e-novo-horizonte-aos-finais-de-semana-e-feriados.html) | Anuncia operação regular da linha 74, Estação–Babilônia, e viagens adicionais da 63, Estação–Novo Horizonte. Ambas constam na coleta. | Não enumera todas as linhas; o nome da 63 na API especifica Estação Norte, detalhe que a notícia não esclarece. |

Essas fontes corroboram três códigos presentes na coleta, mas não validam todos os nomes, sentidos, horários ou a vigência de todas as 40 linhas. **A completude municipal continua não verificada.** Não foram acrescentadas linhas ou horários extraídos dessas notícias aos arquivos de produção.

Para encerrar as pendências, solicitar à SOU/Bus2 e ao órgão municipal responsável:

1. Relação completa de linhas ativas, com data de vigência e indicação de linhas especiais, temporárias e rurais.
2. Confirmação do escopo do projeto 317 e de eventuais linhas fora do catálogo.
3. Disponibilidade de GTFS oficial, endereço de distribuição e condições de uso.
4. Condições para consulta automatizada, cache e redistribuição no Busão Sanca, incluindo atribuição e frequência permitida.

Nenhuma solicitação foi enviada a terceiros nesta etapa.

## Decisões de extração e validação

O [coletor](../coletar_linhas.py) usa `requests` para as consultas HTTP e `BeautifulSoup` para localizar o iframe no HTML oficial. Como o navegador revelou as consultas públicas que alimentam esse iframe, a coleta não precisa iniciar um navegador a cada execução.

O adaptador aceita um único iframe no formato observado e valida que os detalhes do projeto correspondam ao identificador encontrado e à cidade São Carlos, SP. Uma mudança nesses pontos exige revisão explícita.

Os campos da API são mapeados assim:

| API | Saída | Validação |
| --- | --- | --- |
| `shortName` | `codigo` | Texto não vazio; preserva zeros iniciais e remove espaços nas extremidades. |
| `longName` | `nome` | Texto não vazio; remove espaços nas extremidades. |
| `routeId` | `id_linha` | Inteiro positivo. |

Caracteres de controle e de substituição de texto inválido são recusados. Código e identificador devem ser únicos dentro da resposta. A ordem dos registros recebidos é preservada.

Cada registro recebe a URL exata da consulta de linhas, o endereço da página oficial, o endereço do catálogo e um instante de coleta em UTC. Esse instante informa quando o coletor obteve os dados, sem atribuir uma data de atualização que a fonte não tenha fornecido.

## Evidência e publicação

Cada execução bem-sucedida guarda os corpos recebidos da página da SOU, da página do catálogo, dos detalhes do projeto e da resposta de linhas. Os metadados associam cada corpo a sua URL, instante de consulta, status HTTP, cabeçalhos disponíveis e hash SHA-256.

O CSV usa UTF-8 com BOM. O JSON usa UTF-8 e inclui `metadados` e `linhas`; o arquivo `coleta.json` repete os metadados para inspeção independente. A gravação é preparada em um diretório temporário e só depois publicada sob um identificador UTC próprio. Execuções anteriores não são substituídas.

Em caso de erro, nenhum catálogo daquela tentativa é publicado. O programa retorna código `1` e tenta salvar um diagnóstico separado no subdiretório `falhas` do destino. O diagnóstico não representa uma coleta de linhas bem-sucedida.

Os dados locais anteriores em `dados/linhas_referencia.csv`, `saida/linhas.csv`
e `saida/linhas.json` são mantidos como histórico e não participam desse
processo. Esses arquivos são ignorados pelo Git enquanto as condições de
redistribuição não estiverem esclarecidas.

As instruções de instalação, execução e testes estão no [README](../README.md).
