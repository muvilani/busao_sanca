# Planejamento experimental da primeira viagem

Estudo realizado em 20/10/2026 para o deslocamento de 21/10/2026, entre 17h
e 18h. O resultado não é previsão em tempo real.

## Geocodificação

Foram feitas consultas pontuais ao Nominatim, identificadas pelo `User-Agent`
do projeto e abaixo do limite de uma requisição por segundo. A atribuição é
“Dados © contribuidores do OpenStreetMap, ODbL”.

| Local | Resultado | Precisão utilizável |
| --- | --- | --- |
| StepWise, Rua XV de Novembro, 2190 | O endereço e o nome não retornaram correspondência. O CEP 13560-240 retornou `-22.0124426, -47.8931462`. | Baixa: centroide de CEP com caixa delimitadora de vários quilômetros; não representa o número 2190. |
| Rua Icaraí, Vila Morumbi | Via OSM `way/88811330`, centroide `-22.0410217, -47.8860183`, caixa entre latitudes `-22.0426575/-22.0393872` e longitudes `-47.8868889/-47.8851645`. | Aproximada: centroide de uma rua, sem número residencial. |

Por causa da precisão da origem, nenhuma alternativa é classificada como rota
confirmada. As distâncias apresentadas são haversine em linha reta, não rotas
reais para pedestres.

## Resultado nos itinerários coletados

- Linha 34, sentido `Ida`, variantes com destino Novo Mundo: a parada `Rua Dona
  Alexandrina 1550` aparece antes de paradas da Avenida Morumbi.
- Distância de triagem: aproximadamente 342 m do centroide do CEP até a parada
  de embarque e 147 m da parada da Avenida Morumbi até o centroide da Rua
  Icaraí.
- Na variante `tripId 8469231`, as ordens são 33 para embarque e 54 para
  desembarque, e a geometria passou na validação de extremidades.
- Para 21/10/2026, o serviço descrito pela fonte como `Dias úteis` contém
  partidas na origem da viagem às 17:00 e 18:00, sem exceção de calendário
  explícita para essa data.

Esses horários são do início da viagem. Não foi confirmada a hora de passagem
na Rua Dona Alexandrina, pois os campos de intervalo das paradas continuam sem
semântica comprovada.

A linha 57 também foi coletada de forma controlada. Sua melhor combinação
ordenada encontrada ficou a cerca de 342 m da origem, mas mais de 2 km do
destino; portanto ela não é recomendada como alternativa direta.

## Classificações

- `confirmada`: ordem das paradas, cobertura, geometria e coordenadas precisas
  de origem/destino atendem aos limites definidos.
- `candidata_nao_verificada`: há sequência compatível, mas ao menos uma
  evidência necessária é aproximada ou inconsistente.
- sem informação suficiente: não há itinerário completo, sequência válida ou
  dados temporais dentro da vigência.
