# Relatório de estabilização

Data da rodada: **23 de outubro de 2026**.

## Escopo

Esta rodada partiu do commit `cc76a1a`, que já continha filtro de vigência na
consulta por parada. O trabalho seguinte investigou a linha 54, separou uma
prévia publicável sintética, acrescentou teste funcional headless e consolidou
a documentação técnica. Nenhum push, deploy ou alteração no repositório
separado `site` foi realizado.

## Diagnóstico da linha 54

Há duas evidências locais independentes, ambas de 21 de outubro de 2026:

- `saida/teste_lote_6/falhas/...` registra que `trip-details 8477734` falhou em
  `$.stops` por não ser um array com pelo menos duas paradas;
- `saida/lotes/20261021T225823025277Z/...` repete a mesma falha, associa-a
  explicitamente à linha 54 e não publica dataset para essa linha.

Esses diagnósticos não guardaram a resposta bruta, portanto não é possível
distinguir retrospectivamente entre lista vazia, lista unitária ou tipo
incorreto sem inventar evidência.

Uma consulta diagnóstica somente leitura em 23 de outubro de 2026 mostrou que:

- o quadro de horários atual da linha 54 não referencia mais o `tripId
  8477734`;
- o endpoint do itinerário antigo responde HTTP 404.

Conclusão: o erro decorre de referência inconsistente ou obsoleta na fonte
observada, não de um payload válido rejeitado indevidamente pelo parser. Aceitar
menos de duas paradas criaria um itinerário sem utilidade e quebraria as
invariantes de ordem, origem/destino e geometria. A linha 54 permanece excluída
até nova coleta completa e validada. O dataset original não foi modificado.

## Pacote de publicação

Foi criado um fluxo no repositório principal:

- `preparar_publicacao.py` copia apenas assets permitidos;
- `publicacao/dados.demo.json` contém uma linha inteiramente fictícia;
- `publicacao/dist/` é gerado localmente e ignorado pelo Git;
- o pacote exibe aviso destacado de demonstração sintética;
- o experimento antigo com coordenadas e referências reais foi removido do
  bundle; o planejador textual genérico foi preservado;
- nenhuma leitura de `web/dados.json`, `saida/` ou do repositório `site` ocorre
  durante a montagem.

O fixture sintético passou a conter duas linhas fictícias conectadas pelo mesmo
identificador de parada, exclusivamente para exercitar o planejador. O pacote
está pronto para revisão local, não para publicação. A hospedagem
continua inalterada e desatualizada em relação ao repositório principal.

## Testes automatizados

Além da suíte unitária existente, foram adicionadas verificações para:

- marcação obrigatória de dados sintéticos;
- lista fechada de assets e ausência de cópia do dataset privado;
- igualdade entre assets web e pacote montado;
- busca de linha no navegador;
- busca manual e seleção de parada;
- atualização da consulta após mudança de data;
- geolocalização simulada permitida, negada e indisponível;
- Android e iPhone simulados, em retrato e paisagem;
- rota direta, conexão, inversão, limpeza e origem igual ao destino;
- estados vazios, dataset ausente e foco programático por teclado;
- ausência de overflow horizontal;
- ausência de erros e rejeições JavaScript não tratadas.

O teste funcional usa Edge, Chrome ou Chromium real em modo headless. Os estados
de geolocalização são simulados de forma determinística; nenhuma localização
real é coletada.

## Testes ainda necessários em dispositivo físico

- Android e iOS em orientação vertical;
- prompt real de geolocalização e retorno após negar permissão;
- navegação por teclado e leitor de tela;
- contraste, zoom e fontes ampliadas;
- rede lenta, cache e retomada após suspensão;
- abertura de mapas e comportamento de voltar ao aplicativo.

Esses testes não devem ser descritos como concluídos pela automação headless.
O roteiro executável e os cuidados de acesso estão em `docs/TESTE_MOBILE.md`.

## Política de dados

- `saida/`, `web/dados.json`, CSVs externos e respostas brutas permanecem fora
  do Git;
- dados reais não entram no pacote sintético;
- horários, calendário e itinerários não são inferidos;
- publicação de dados reais depende de autorização de redistribuição;
- geolocalização do usuário permanece local e efêmera.

## Riscos e pendências

1. Licença de redistribuição ainda não confirmada.
2. Completude municipal não comprovada.
3. Calendário semanal e exceções sem semântica confirmada.
4. Linha 54 sem itinerário local válido.
5. Ausência de validação em dispositivo físico.
6. Repositório `site` permanece separado e não deve ser atualizado
   automaticamente.

## Recomendação

Validar o pacote sintético em aparelhos físicos e, em paralelo, obter
autorização formal e documentação do calendário. Somente depois deve ser
planejada uma prévia privada com dados reais minimizados.
