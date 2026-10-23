# Relatório da Missão 4

Data: **23 de outubro de 2026**.

## Validação mobile automatizada

O pacote sintético foi exercitado em Edge headless com quatro viewports:
Android e iPhone, em retrato e paisagem. A automação cobre busca, seleção de
parada, troca de data, três estados de geolocalização simulada, planejador,
estados vazios, dataset ausente, foco e overflow. Nenhum servidor permanece em
execução depois dos testes.

O teste não equivale a Android ou iPhone físicos. Prompts reais, teclado
virtual, gestos, leitores de tela e particularidades do Safari/Chrome móvel
continuam pendentes. `TESTE_MOBILE.md` descreve o procedimento sem expor dados
ou abrir serviços externos.

## Planejador experimental

O núcleo Python e o navegador agora compartilham as seguintes regras:

- seleção de paradas normalizada, com identificador visível quando disponível;
- embarque estritamente anterior ao desembarque na mesma variante;
- rota direta antes das candidatas com uma conexão;
- conexão somente por `id_parada` igual nas duas variantes;
- rejeição de itinerários incompletos ou com ordem inválida;
- deduplicação e ordenação determinística por conexões e paradas percorridas;
- serviços e partidas filtrados apenas por vigência conhecida;
- aviso explícito de que partida na origem não é passagem na parada.

A conexão é uma candidata estrutural: tempo de espera, caminhada, tarifa,
integração, calendário semanal e operação no dia não estão confirmados. O
planejador não calcula tempo real nem inventa essas informações.

## Dados e publicação

O fixture de publicação ganhou uma segunda linha fictícia para demonstrar uma
conexão. Códigos, identificadores, nomes, coordenadas e horários continuam
sintéticos e marcados como tal. O dataset original, `web/dados.json`, `saida/`
e o repositório `site` não foram modificados ou copiados. Não houve push,
deploy ou publicação.

## Critério de avanço

A frente está pronta para revisão local automatizada. Antes de qualquer prévia
com dados reais ainda são necessários teste físico registrado, autorização de
redistribuição, confirmação do calendário e uma nova coleta válida da linha
54. A próxima ação técnica é executar o checklist físico em um Android e um
iPhone controlados.
