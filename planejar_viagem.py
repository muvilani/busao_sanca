"""Análise geográfica conservadora sobre datasets normalizados do MVP.

Não calcula rotas de pedestre nem estima passagem do ônibus. Distâncias são
geodésicas em linha reta e horários são sempre partidas na origem da viagem.
"""

from __future__ import annotations

import math
from datetime import date

RAIO_TERRA_METROS = 6_371_000
PRECISOES_CONFIRMAVEIS = {"endereco", "edificio"}


class ErroPlanejamento(ValueError):
    pass


def distancia_linha_reta(a: dict, b: dict) -> float:
    """Distância haversine; não representa caminho real de pedestre."""
    try:
        lat1, lon1 = float(a["latitude"]), float(a["longitude"])
        lat2, lon2 = float(b["latitude"]), float(b["longitude"])
    except (KeyError, TypeError, ValueError) as erro:
        raise ErroPlanejamento("coordenadas ausentes ou inválidas") from erro
    if not all(math.isfinite(v) for v in (lat1, lon1, lat2, lon2)):
        raise ErroPlanejamento("coordenadas não finitas")
    if not (-90 <= lat1 <= 90 and -90 <= lat2 <= 90 and -180 <= lon1 <= 180 and -180 <= lon2 <= 180):
        raise ErroPlanejamento("coordenadas fora do intervalo")
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * RAIO_TERRA_METROS * math.asin(min(1, math.sqrt(h)))


def melhor_par_ordenado(itinerario: dict, origem: dict, destino: dict) -> dict:
    """Escolhe embarque anterior ao desembarque minimizando as caminhadas."""
    paradas = itinerario.get("paradas")
    if not isinstance(paradas, list) or len(paradas) < 2:
        raise ErroPlanejamento("itinerário sem paradas suficientes")
    candidatos = []
    for indice, embarque in enumerate(paradas[:-1]):
        for desembarque in paradas[indice + 1:]:
            de = distancia_linha_reta(origem, embarque)
            dd = distancia_linha_reta(destino, desembarque)
            candidatos.append((de + dd, de, dd, embarque, desembarque))
    _, de, dd, embarque, desembarque = min(candidatos, key=lambda item: item[0])
    return {
        "embarque": embarque,
        "desembarque": desembarque,
        "caminhada_origem_linha_reta_m": round(de),
        "caminhada_destino_linha_reta_m": round(dd),
        "ordem_valida": embarque["ordem"] < desembarque["ordem"],
    }


def analisar_linha(
    linha: dict, origem: dict, destino: dict, *, limite_caminhada_m: float = 800
) -> list[dict]:
    horarios = linha["horarios"]
    variantes = {v["id_viagem"]: v for v in horarios["variantes"]}
    direcoes = {d["id_direcao"]: d for d in horarios["direcoes"]}
    resultados = []
    for itinerario in linha["itinerarios"]:
        variante = variantes.get(itinerario["id_viagem"])
        if variante is None or variante["id_direcao"] not in direcoes:
            continue
        par = melhor_par_ordenado(itinerario, origem, destino)
        dentro = par["caminhada_origem_linha_reta_m"] <= limite_caminhada_m and par["caminhada_destino_linha_reta_m"] <= limite_caminhada_m
        preciso = origem.get("precisao") in PRECISOES_CONFIRMAVEIS and destino.get("precisao") in PRECISOES_CONFIRMAVEIS
        geometria_ok = itinerario["geometria"]["validacao"].get("extremidades_compativeis", True)
        status = "confirmada" if dentro and preciso and geometria_ok else "candidata_nao_verificada"
        resultados.append({
            "status": status,
            "id_viagem": itinerario["id_viagem"],
            "direcao": direcoes[variante["id_direcao"]]["descricao"],
            "destino_variante": variante["destino"],
            "geometria_confirmada": geometria_ok,
            **par,
        })
    return sorted(resultados, key=lambda r: (
        r["caminhada_origem_linha_reta_m"] + r["caminhada_destino_linha_reta_m"],
        r["id_viagem"],
    ))


def partidas_de_terminal(
    horarios: dict,
    trip_id: int,
    data_consulta: str,
    inicio: str,
    fim: str,
    *,
    descricao_servico: str | None = None,
) -> list[dict]:
    try:
        dia = date.fromisoformat(data_consulta)
    except (TypeError, ValueError) as erro:
        raise ErroPlanejamento("data inválida") from erro
    saidas = []
    for direcao in horarios["direcoes"]:
        for servico in direcao["servicos"]:
            if not (date.fromisoformat(servico["vigencia_inicio"]) <= dia <= date.fromisoformat(servico["vigencia_fim"])):
                continue
            if descricao_servico is not None and servico["descricao"] != descricao_servico:
                continue
            for partida in servico["partidas"]:
                if partida["id_viagem"] == trip_id and inicio <= partida["saida"] <= fim:
                    saidas.append({
                        "saida_terminal": partida["saida"],
                        "chegada_final_origem": partida["chegada"],
                        "id_servico": servico["id_servico"],
                        "descricao_servico": servico["descricao"],
                        "horario_passagem_confirmado": False,
                    })
    return saidas
