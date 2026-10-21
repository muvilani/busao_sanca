# Esquema normalizado de itinerários

O módulo [`processar_itinerarios.py`](../processar_itinerarios.py) valida um
objeto JSON já decodificado de `trip-details`. Ele não realiza HTTP nem grava
arquivos. A saída atual usa `schema_version: 1`.

O identificador da viagem não foi observado no corpo de `trip-details`; por
isso ele deve ser informado pelo contexto da requisição:

```python
from processar_itinerarios import processar_itinerario

normalizado = processar_itinerario(payload, trip_id=123456)  # ID sintético
```

O `trip_id` é o mesmo `id_viagem` produzido por
[`processar_horarios.py`](../processar_horarios.py). Essa identidade, e não o
nome do destino, liga horário e itinerário.

Por padrão, extremidades da geometria distantes das paradas terminais são
rejeitadas. O pipeline controlado pode preservá-las para diagnóstico com
`permitir_extremidades_divergentes=True`; nesse caso,
`geometria.validacao.extremidades_compativeis` fica `false` e a interface não
deve tratar a geometria como confirmada.

## Entrada observada

```text
tripName
routeName
shape
tzOffset
price?
stops[]
├── stopId
├── lat
├── lng
├── name
├── int?
└── wait?
```

## Saída normalizada

```text
schema_version
id_viagem
nome_viagem
nome_linha_origem
fuso_utc_origem_horas
paradas[]
├── ordem
├── id_parada
├── nome
├── latitude, longitude
├── campos_origem
└── campos_extras
geometria
├── formato: google_encoded_polyline_5
├── codificacao_origem
├── geojson
│   ├── type: LineString
│   └── coordinates: [[longitude, latitude], ...]
└── validacao
campos_origem
campos_extras
```

## Regras de validação

- `trip_id` e `stopId` são inteiros positivos; booleanos não são aceitos
  como inteiros.
- `tripName`, `routeName` e nomes de parada são textos não vazios e sem
  caracteres de controle.
- `tzOffset` é numérico, finito e fica entre -14 e +14 horas.
- O itinerário tem pelo menos duas paradas.
- Latitude e longitude são números finitos nos intervalos `[-90, 90]` e
  `[-180, 180]`.
- A ordem do array de origem é preservada explicitamente em `ordem`, iniciada
  em 1. IDs repetidos não são rejeitados, pois uma linha circular pode passar
  novamente pela mesma parada.
- Campos obrigatórios ausentes, objetos trocados por outros tipos e
  geometrias inconsistentes interrompem o processamento.

## Geometria

A conversão para GeoJSON não é feita apenas por aparência. Para cada resposta,
`shape` precisa:

1. ser texto não vazio dentro do limite defensivo de tamanho;
2. decodificar integralmente como Google Encoded Polyline com precisão 5;
3. produzir ao menos dois pontos, todos em intervalos geográficos válidos;
4. ter início e fim a no máximo 500 metros das paradas terminais.

Somente depois dessas verificações a saída recebe
`formato: google_encoded_polyline_5` e uma `LineString`. A codificação original
e as distâncias calculadas permanecem registradas. Uma codificação truncada,
inválida ou espacialmente incompatível é rejeitada; não há fallback que
invente uma geometria.

O limite de 500 metros tolera terminais cujo desenho comece ou termine em uma
via próxima, mas é uma decisão defensiva do projeto, não um valor declarado
pela fonte.

## Campos opacos e evolução do formato

`int` e `wait` são copiados para `campos_origem` sem conversão ou significado
atribuído. Chaves ausentes continuam ausentes; `null` e `false` permanecem
distintos. Campos novos são copiados para `campos_extras` na raiz ou na parada.

O parser não presume que itinerários com o mesmo `tripName` tenham o mesmo
trajeto. Cada `trip_id` é processado e armazenado independentemente.

## Limitações

- A semântica de `int`, `wait` e `price` continua não confirmada.
- A tolerância espacial deverá ser reavaliada com fixtures autorizadas se a
  fonte apresentar terminais mais afastados da geometria.
- O parser não verifica completude, vigência, atualidade ou permissão de
  redistribuição.
- A integração HTTP, deduplicação de requisições e publicação atômica ficam
  para uma etapa posterior.
