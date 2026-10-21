"""Valida e normaliza respostas do endpoint ``trip-details`` do Bus2.

O ``tripId`` vem do contexto da requisição e é obrigatório porque a resposta
observada não o repete. Este módulo não realiza acesso HTTP nem grava arquivos.
"""

from __future__ import annotations

import copy
import math

SCHEMA_VERSION = 1
LIMITE_SHAPE_CARACTERES = 200_000
LIMITE_PONTOS_GEOMETRIA = 100_000
TOLERANCIA_EXTREMIDADE_METROS = 500.0


class ErroItinerario(ValueError):
    """Resposta de itinerário inválida ou incompatível com seu contexto."""


def _erro(caminho: str, mensagem: str) -> None:
    raise ErroItinerario(f"{caminho}: {mensagem}")


def _objeto(valor: object, caminho: str) -> dict:
    if not isinstance(valor, dict):
        _erro(caminho, "esperado objeto JSON")
    return valor


def _obrigatorio(objeto: dict, campo: str, caminho: str) -> object:
    if campo not in objeto:
        _erro(caminho, f"campo obrigatório {campo!r} ausente")
    return objeto[campo]


def _inteiro_positivo(valor: object, caminho: str) -> int:
    if type(valor) is not int or valor <= 0:
        _erro(caminho, "esperado inteiro positivo")
    return valor


def _texto(valor: object, caminho: str) -> str:
    if not isinstance(valor, str) or not valor.strip():
        _erro(caminho, "esperado texto não vazio")
    if any(ord(caractere) < 32 for caractere in valor):
        _erro(caminho, "texto contém caractere de controle")
    return valor.strip()


def _numero(valor: object, caminho: str, minimo: float, maximo: float) -> int | float:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        _erro(caminho, "esperado número")
    if not math.isfinite(valor) or not minimo <= valor <= maximo:
        _erro(caminho, f"valor fora do intervalo [{minimo}, {maximo}]")
    return valor


def _campos(objeto: dict, nomes: set[str]) -> dict:
    """Copia apenas chaves presentes, preservando null, false e ausência."""
    return {nome: copy.deepcopy(objeto[nome]) for nome in nomes if nome in objeto}


def _extras(objeto: dict, conhecidos: set[str]) -> dict:
    return {
        chave: copy.deepcopy(valor)
        for chave, valor in objeto.items()
        if chave not in conhecidos
    }


def _decodificar_valor(shape: str, indice: int) -> tuple[int, int]:
    resultado = 0
    deslocamento = 0
    while True:
        if indice >= len(shape):
            _erro("$.shape", "codificação truncada")
        codigo = ord(shape[indice])
        indice += 1
        if codigo < 63 or codigo > 126:
            _erro("$.shape", "caractere incompatível com encoded polyline")
        parte = codigo - 63
        resultado |= (parte & 0x1F) << deslocamento
        deslocamento += 5
        if deslocamento > 35:
            _erro("$.shape", "valor codificado excede o limite suportado")
        if parte < 0x20:
            break
    delta = ~(resultado >> 1) if resultado & 1 else resultado >> 1
    return delta, indice


def _decodificar_polyline(shape: str) -> list[list[float]]:
    if len(shape) > LIMITE_SHAPE_CARACTERES:
        _erro("$.shape", "geometria excede o limite de caracteres")
    latitude = 0
    longitude = 0
    indice = 0
    coordenadas = []
    while indice < len(shape):
        delta_latitude, indice = _decodificar_valor(shape, indice)
        delta_longitude, indice = _decodificar_valor(shape, indice)
        latitude += delta_latitude
        longitude += delta_longitude
        lat = latitude / 100_000
        lng = longitude / 100_000
        if not -90 <= lat <= 90 or not -180 <= lng <= 180:
            _erro("$.shape", "coordenada decodificada fora do intervalo geográfico")
        coordenadas.append([lng, lat])
        if len(coordenadas) > LIMITE_PONTOS_GEOMETRIA:
            _erro("$.shape", "geometria excede o limite de pontos")
    if len(coordenadas) < 2:
        _erro("$.shape", "geometria deve conter pelo menos dois pontos")
    return coordenadas


def _distancia_metros(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lng1 = (math.radians(valor) for valor in a)
    lat2, lng2 = (math.radians(valor) for valor in b)
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    haversine = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * 6_371_000 * math.asin(min(1.0, math.sqrt(haversine)))


def _validar_geometria(shape: object, paradas: list[dict]) -> dict:
    texto = _texto(shape, "$.shape")
    coordenadas = _decodificar_polyline(texto)
    primeira_shape = (coordenadas[0][1], coordenadas[0][0])
    ultima_shape = (coordenadas[-1][1], coordenadas[-1][0])
    primeira_parada = (paradas[0]["latitude"], paradas[0]["longitude"])
    ultima_parada = (paradas[-1]["latitude"], paradas[-1]["longitude"])
    distancias = [
        _distancia_metros(primeira_shape, primeira_parada),
        _distancia_metros(ultima_shape, ultima_parada),
    ]
    if any(distancia > TOLERANCIA_EXTREMIDADE_METROS for distancia in distancias):
        _erro(
            "$.shape",
            "extremidades da geometria não correspondem às paradas terminais",
        )
    return {
        "formato": "google_encoded_polyline_5",
        "codificacao_origem": texto,
        "geojson": {"type": "LineString", "coordinates": coordenadas},
        "validacao": {
            "tolerancia_extremidade_metros": TOLERANCIA_EXTREMIDADE_METROS,
            "distancia_inicio_metros": distancias[0],
            "distancia_fim_metros": distancias[1],
        },
    }


def processar_itinerario(payload: object, trip_id: object) -> dict:
    """Valida ``trip-details`` e normaliza o itinerário associado a ``trip_id``."""
    identificador = _inteiro_positivo(trip_id, "trip_id")
    raiz = _objeto(payload, "$")
    nome_viagem = _texto(_obrigatorio(raiz, "tripName", "$"), "$.tripName")
    nome_linha = _texto(_obrigatorio(raiz, "routeName", "$"), "$.routeName")
    fuso = _numero(_obrigatorio(raiz, "tzOffset", "$"), "$.tzOffset", -14, 14)

    paradas_origem = _obrigatorio(raiz, "stops", "$")
    if not isinstance(paradas_origem, list) or len(paradas_origem) < 2:
        _erro("$.stops", "esperado array com pelo menos duas paradas")
    paradas = []
    for indice, item in enumerate(paradas_origem):
        caminho = f"$.stops[{indice}]"
        origem = _objeto(item, caminho)
        stop_id = _inteiro_positivo(
            _obrigatorio(origem, "stopId", caminho), f"{caminho}.stopId"
        )
        latitude = _numero(
            _obrigatorio(origem, "lat", caminho), f"{caminho}.lat", -90, 90
        )
        longitude = _numero(
            _obrigatorio(origem, "lng", caminho), f"{caminho}.lng", -180, 180
        )
        nome = _texto(_obrigatorio(origem, "name", caminho), f"{caminho}.name")
        campos_origem = _campos(origem, {"int", "wait"})
        conhecidos = {"stopId", "lat", "lng", "name", "int", "wait"}
        paradas.append(
            {
                "ordem": indice + 1,
                "id_parada": stop_id,
                "nome": nome,
                "latitude": latitude,
                "longitude": longitude,
                "campos_origem": campos_origem,
                "campos_extras": _extras(origem, conhecidos),
            }
        )

    geometria = _validar_geometria(_obrigatorio(raiz, "shape", "$"), paradas)
    campos_origem = _campos(raiz, {"price"})
    conhecidos = {"tripName", "routeName", "shape", "tzOffset", "stops", "price"}
    return {
        "schema_version": SCHEMA_VERSION,
        "id_viagem": identificador,
        "nome_viagem": nome_viagem,
        "nome_linha_origem": nome_linha,
        "fuso_utc_origem_horas": fuso,
        "paradas": paradas,
        "geometria": geometria,
        "campos_origem": campos_origem,
        "campos_extras": _extras(raiz, conhecidos),
    }
