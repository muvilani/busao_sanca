"""Índice e consultas locais de paradas do Busão Sanca.

Este módulo não acessa a API. Ele trabalha apenas sobre um dataset já validado.
"""

from __future__ import annotations

import unicodedata
from datetime import date
from math import asin, cos, isfinite, radians, sin, sqrt
from typing import Any


RAIO_TERRA_METROS = 6_371_000


def coordenada_valida(latitude: Any, longitude: Any) -> bool:
    """Retorna se latitude/longitude são números finitos dentro dos limites."""
    return (
        isinstance(latitude, (int, float))
        and isinstance(longitude, (int, float))
        and not isinstance(latitude, bool)
        and not isinstance(longitude, bool)
        and isfinite(latitude)
        and isfinite(longitude)
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
    )


def distancia_em_linha_reta(latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float) -> float:
    """Calcula distância geográfica aproximada em metros (Haversine)."""
    if not all(coordenada_valida(a, b) for a, b in ((latitude_a, longitude_a), (latitude_b, longitude_b))):
        raise ValueError("coordenadas inválidas")
    dlat = radians(latitude_b - latitude_a)
    dlon = radians(longitude_b - longitude_a)
    a = sin(dlat / 2) ** 2 + cos(radians(latitude_a)) * cos(radians(latitude_b)) * sin(dlon / 2) ** 2
    return 2 * RAIO_TERRA_METROS * asin(min(1, sqrt(a)))


def _chave_parada(parada: dict[str, Any]) -> str:
    """Usa o ID da fonte; sem ID, usa a ocorrência para não unir paradas."""
    identificador = parada.get("id_parada")
    if identificador is not None:
        return f"id:{identificador}"
    return f"ocorrencia:{id(parada)}"


def construir_indice_paradas(dataset: dict[str, Any]) -> dict[str, Any]:
    """Cria um índice serializável de paradas e suas associações de serviço."""
    registros: dict[str, dict[str, Any]] = {}
    ocorrencias = 0
    for linha in dataset.get("linhas", []):
        catalogo = linha.get("catalogo", {})
        horarios = linha.get("horarios", {})
        codigo = str(catalogo.get("codigo", horarios.get("linha", {}).get("codigo", "")))
        nome_linha = horarios.get("linha", {}).get("nome", catalogo.get("nome", ""))
        direcoes = {str(d.get("id_direcao")): d for d in horarios.get("direcoes", [])}
        variantes = {str(v.get("id_viagem")): v for v in horarios.get("variantes", [])}
        for itinerario in linha.get("itinerarios", []):
            trip_id = str(itinerario.get("id_viagem"))
            variante = variantes.get(trip_id, {})
            direcao = direcoes.get(str(variante.get("id_direcao")), {})
            associado = {
                "codigo_linha": codigo,
                "nome_linha": nome_linha,
                "sentido": direcao.get("descricao", ""),
                "destino": variante.get("destino", ""),
                "variante": variante.get("sequencia_origem"),
                "id_viagem": itinerario.get("id_viagem"),
                "ordem": None,
                "partidas": [],
            }
            for servico in direcao.get("servicos", []):
                associado["partidas"].extend(
                    {
                        "saida": partida.get("saida"),
                        "id_viagem": partida.get("id_viagem"),
                        "servico": servico.get("descricao", ""),
                        "vigencia_inicio": servico.get("vigencia_inicio"),
                        "vigencia_fim": servico.get("vigencia_fim"),
                    }
                    for partida in servico.get("partidas", [])
                    if str(partida.get("id_viagem")) == trip_id
                )
            for ordem, parada in enumerate(itinerario.get("paradas", []), start=1):
                ocorrencias += 1
                chave = _chave_parada(parada)
                if chave not in registros:
                    registros[chave] = {
                        "chave": chave,
                        "id_parada": parada.get("id_parada"),
                        "nome": parada.get("nome", ""),
                        "latitude": parada.get("latitude"),
                        "longitude": parada.get("longitude"),
                        "atendimentos": [],
                    }
                atendimento = {**associado, "ordem": ordem}
                if atendimento not in registros[chave]["atendimentos"]:
                    registros[chave]["atendimentos"].append(atendimento)
    paradas = sorted(registros.values(), key=lambda p: (str(p.get("nome", "")).casefold(), p["chave"]))
    for parada in paradas:
        parada["linhas"] = sorted({a["codigo_linha"] for a in parada["atendimentos"]})
    return {
        "schema_version": 1,
        "paradas": paradas,
        "estatisticas": {
            "ocorrencias": ocorrencias,
            "paradas_unicas": len(paradas),
            "paradas_com_coordenadas": sum(coordenada_valida(p.get("latitude"), p.get("longitude")) for p in paradas),
            "linhas_associadas": len({linha for p in paradas for linha in p["linhas"]}),
        },
    }


def paradas_proximas(indice: dict[str, Any], latitude: float, longitude: float, limite: int = 10) -> list[dict[str, Any]]:
    """Ordena paradas com coordenadas válidas pela distância em linha reta."""
    if not coordenada_valida(latitude, longitude):
        raise ValueError("localização do usuário inválida")
    if limite < 1:
        return []
    resultados = []
    for parada in indice.get("paradas", []):
        if not coordenada_valida(parada.get("latitude"), parada.get("longitude")):
            continue
        item = dict(parada)
        item["distancia_metros"] = distancia_em_linha_reta(latitude, longitude, parada["latitude"], parada["longitude"])
        resultados.append(item)
    return sorted(resultados, key=lambda p: (p["distancia_metros"], p["chave"]))[:limite]


def atendimentos_da_parada(indice: dict[str, Any], chave: str) -> list[dict[str, Any]]:
    """Retorna as associações de linha/sentido/variante da parada selecionada."""
    for parada in indice.get("paradas", []):
        if parada.get("chave") == chave:
            return list(parada.get("atendimentos", []))
    return []


def normalizar_busca(valor: Any) -> str:
    """Normaliza caixa, acentos e separadores sem alterar o dado original."""
    decomposto = unicodedata.normalize("NFKD", str(valor or ""))
    sem_acentos = "".join(caractere for caractere in decomposto if not unicodedata.combining(caractere))
    return " ".join("".join(caractere if caractere.isalnum() else " " for caractere in sem_acentos.casefold()).split())


def buscar_paradas(indice: dict[str, Any], termo: Any, limite: int = 10) -> list[dict[str, Any]]:
    """Busca por nome ou ID com a mesma normalização usada na interface."""
    if limite < 1:
        return []
    consulta = normalizar_busca(termo)
    return [
        parada
        for parada in indice.get("paradas", [])
        if not consulta or consulta in normalizar_busca(f"{parada.get('nome', '')} {parada.get('id_parada', '')}")
    ][:limite]


def _data_iso_valida(valor: Any) -> bool:
    if not isinstance(valor, str) or len(valor) != 10:
        return False
    try:
        return date.fromisoformat(valor).isoformat() == valor
    except ValueError:
        return False


def partidas_na_vigencia(atendimento: dict[str, Any], data_selecionada: Any) -> dict[str, Any]:
    """Filtra somente pela vigência conhecida, sem inferir calendário semanal."""
    if not _data_iso_valida(data_selecionada):
        return {"partidas": [], "data_valida": False, "vigencia_desconhecida": False}
    compativeis = []
    vigencia_desconhecida = False
    for partida in atendimento.get("partidas", []):
        inicio = partida.get("vigencia_inicio")
        fim = partida.get("vigencia_fim")
        if not _data_iso_valida(inicio) or not _data_iso_valida(fim):
            vigencia_desconhecida = True
            continue
        if inicio <= data_selecionada <= fim:
            compativeis.append(partida)
    return {
        "partidas": compativeis,
        "data_valida": True,
        "vigencia_desconhecida": vigencia_desconhecida,
    }


def resumo_indice(indice: dict[str, Any]) -> dict[str, int]:
    """Extrai métricas úteis para auditoria."""
    return {
        "paradas_unicas": len(indice.get("paradas", [])),
        "paradas_com_coordenadas": sum(coordenada_valida(p.get("latitude"), p.get("longitude")) for p in indice.get("paradas", [])),
        "linhas_associadas": len({a["codigo_linha"] for p in indice.get("paradas", []) for a in p.get("atendimentos", [])}),
    }
