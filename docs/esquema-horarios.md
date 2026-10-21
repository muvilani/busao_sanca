# Esquema normalizado de horários

O módulo [`processar_horarios.py`](../processar_horarios.py) recebe um objeto
JSON já decodificado da resposta `timetable`. Ele não faz requisições e não
grava arquivos. A saída atual usa `schema_version: 1`.

As fixtures dos testes são inteiramente sintéticas. Respostas brutas do
fornecedor não são versionadas.

## Estrutura

```text
schema_version
linha
├── id_linha, codigo, nome
├── campos_origem
└── campos_extras
direcoes[]
├── id_direcao, descricao, ordem_origem?
├── servicos[]
│   ├── id_servico, descricao
│   ├── vigencia_inicio, vigencia_fim
│   ├── dias_semana_origem[7]
│   ├── ordem_dias_confirmada: false
│   └── partidas[]
│       ├── saida, chegada
│       ├── sequencia_variante_origem
│       └── id_viagem
└── campos_extras
variantes[]
├── id_viagem, id_direcao, sequencia_origem
├── destino
├── campos_origem
└── campos_extras
excecoes_calendario[]
├── data, id_servico, tipo_origem
└── semantica_tipo_confirmada: false
campos_extras_timetable
```

## Invariantes

- `routeId`, `serviceId` e `tripId` são inteiros positivos; identificadores de
  direção e tipos opacos são inteiros não negativos. Booleanos não são
  aceitos como inteiros.
- Cada direção é única e tem ao menos um serviço. Um `serviceId` não pode
  se repetir na mesma direção, mas pode existir em direções diferentes.
- Serviços com descrições iguais continuam separados por identidade e
  contexto.
- Cada variante tem `tripId` globalmente único. O par `(directionId, seq)`
  também é único e resolve as partidas daquela direção.
- Cada partida deve referenciar exatamente uma variante na mesma direção.
- Datas usam `YYYY-MM-DD`, existem no calendário e formam uma vigência em
  ordem crescente.
- `days` tem exatamente sete booleanos. A ordem é preservada sem receber
  nomes de dias, pois sua semântica ainda não foi oficialmente confirmada.
- Horários aceitam `HH:MM` ou `HH:MM:SS`, inclusive de `24:00` a `47:59:59`
  para representações operacionais após meia-noite. O parser não calcula
  duração e, portanto, não confunde `23:50–00:20` com duração negativa.
- Exceções devem referenciar um `serviceId` presente. `type` é preservado
  como valor de origem sem interpretação.

## Preservação da origem

`campos_origem` contém campos observados cuja semântica completa ainda não
está confirmada, como `wa`, `ac`, `extra` e `ckpt`. `campos_extras` contém
qualquer campo que não fazia parte do formato conhecido. A cópia mantém a
diferença entre:

- campo ausente: a chave não aparece;
- campo nulo: a chave aparece com `null`;
- booleano falso: a chave aparece com `false`.

Isso permite detectar evoluções da fonte sem inventar significados nem perder
informação.

## Limitações

- A ordem dos sete dias ainda não é declarada como oficial.
- A semântica de `exceptions.type`, `wa`, `ckpt` e outros campos opacos não é
  interpretada.
- O parser não confirma completude, atualidade ou permissão de redistribuição.
- Itinerários, paradas e geometria pertencem à Etapa 2B e não fazem parte
  deste esquema.
- O módulo processa objetos em memória; validação HTTP e limites de resposta
  continuam sendo responsabilidades separadas.
