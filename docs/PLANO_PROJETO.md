# Plano do projeto Busão Sanca

## Princípios de evolução

- Dados externos só avançam quando origem, contrato e permissão estão claros.
- Incertezas são mostradas ao usuário, não preenchidas por inferência.
- Dataset privado e respostas brutas permanecem fora do Git.
- Cada fase precisa de testes reproduzíveis e critério explícito de saída.
- Publicação técnica não antecede autorização de redistribuição.

## Fase 1 — Descoberta e catálogo

**Estado:** concluída para o escopo observado.

- descobrir a fonte incorporada à página oficial;
- validar cidade e identidade do projeto;
- coletar e auditar o catálogo sem assumir completude municipal;
- preservar evidências e hashes apenas localmente.

**Pendência:** obter confirmação oficial da relação completa de linhas ativas.

## Fase 2 — Contratos e normalização

**Estado:** concluída com limitações documentadas.

- validar horários, serviços, vigências e variantes;
- validar paradas, ordem e geometria dos itinerários;
- preservar campos desconhecidos sem interpretá-los;
- rejeitar respostas incompletas, como itinerário com menos de duas paradas.

**Pendência:** confirmar a ordem do calendário semanal e a semântica das
exceções.

## Fase 3 — Dataset incremental privado

**Estado:** operacional.

- coletar linhas em lotes respeitando limites da fonte;
- reutilizar apenas linhas integralmente revalidadas;
- registrar falhas por linha e viagem;
- consolidar cobertura parcial de forma honesta.

**Pendência prioritária:** reavaliar a linha 54 somente após uma nova coleta
controlada mostrar variantes atuais com itinerários válidos. O `tripId`
histórico `8477734` não pode ser reconstruído.

## Fase 4 — MVP mobile local

**Estado:** estabilizado para prévia.

- busca por linha, nome e destino;
- horários na origem e itinerários;
- busca manual e proximidade de paradas;
- geolocalização opcional;
- consulta por parada com filtro de vigência;
- planejador textual experimental;
- avisos de cobertura, calendário e ausência de previsão em tempo real.

**Critério para avançar:** suíte completa verde, teste headless mobile verde e
nenhuma regressão com o dataset privado local.

## Fase 5 — Prévia publicável sintética

**Estado:** preparada, não publicada.

- pacote reproduzível em `publicacao/dist/`;
- fixture explicitamente sintético;
- nenhum dado real, resposta bruta ou coordenada do experimento antigo;
- teste funcional automatizado do pacote montado.

**Critério para avançar:** revisão manual do pacote e teste em pelo menos um
Android e um iPhone físicos. Não é necessário usar localização real: a revisão
deve confirmar também os fluxos de permissão negada e indisponível.

## Fase 6 — Autorização e prévia privada

**Estado:** pendente.

- esclarecer licença e condições de redistribuição;
- definir responsável, política de atualização e retenção;
- decidir quais linhas/dados podem compor uma prévia autenticada;
- revisar privacidade, atribuições e termos de uso;
- atualizar o repositório de hospedagem somente após autorização explícita.

## Fase 7 — Beta público

**Estado:** futuro.

- fonte autorizada e atualização monitorada;
- observabilidade sem coletar localização do usuário;
- acessibilidade e compatibilidade em dispositivos reais;
- tratamento de indisponibilidade e dados desatualizados;
- comunicação clara de que o serviço não substitui a fonte oficial.

## Fase 8 — Produto operacional

**Estado:** futuro e condicionado a fontes adequadas.

- PWA instalável e estratégia de cache segura;
- atualização automatizada com rollback;
- eventual GTFS autorizado;
- rotas reais a pé e tempo real somente com fontes licenciadas;
- métricas de qualidade, incidentes e revisão periódica de cobertura.

## Próxima ação recomendada

Executar a prévia sintética em dispositivos físicos e registrar evidências de
layout, acessibilidade e permissões. Em paralelo, solicitar confirmação formal
da licença de redistribuição e do calendário. Nenhum dataset real deve avançar
para hospedagem antes dessas duas frentes.
