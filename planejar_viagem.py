"""Análise geográfica conservadora sobre datasets normalizados do MVP.

Não calcula rotas de pedestre nem estima passagem do ônibus. Distâncias são
geodésicas em linha reta e horários são sempre partidas na origem da viagem.
"""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import date
from difflib import SequenceMatcher

RAIO_TERRA_METROS = 6_371_000
PRECISOES_CONFIRMAVEIS = {"endereco", "edificio"}


class ErroPlanejamento(ValueError):
    pass


def normalizar_local(texto: object) -> str:
    """Normaliza acentos, caixa e pontuação para busca local."""
    base = unicodedata.normalize("NFD", str(texto or "")).casefold()
    sem_acentos = "".join(c for c in base if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", sem_acentos).strip()


def _pontuacao_busca(consulta: str, nome: str) -> float:
    if not consulta or not nome:
        return 0.0
    if consulta == nome:
        return 1.0
    if nome.startswith(consulta):
        return 0.94
    if consulta in nome:
        return 0.88
    consulta_tokens = set(consulta.split())
    nome_tokens = set(nome.split())
    if consulta_tokens and consulta_tokens <= nome_tokens:
        return 0.84
    return SequenceMatcher(None, consulta, nome).ratio()


def _registros_locais(dataset: dict) -> list[dict]:
    registros = []
    for linha in dataset.get("linhas", []):
        catalogo = linha.get("catalogo", {})
        codigo = catalogo.get("codigo")
        if codigo == "54" or linha.get("cobertura", {}).get("completa_no_escopo_solicitado") is False:
            continue
        horarios = linha.get("horarios", {})
        variantes = {v.get("id_viagem"): v for v in horarios.get("variantes", [])}
        direcoes = {d.get("id_direcao"): d for d in horarios.get("direcoes", [])}
        for itinerario in linha.get("itinerarios", []):
            variante = variantes.get(itinerario.get("id_viagem"))
            direcao = direcoes.get(variante.get("id_direcao")) if variante else None
            if not variante or not direcao:
                continue
            for parada in itinerario.get("paradas", []):
                nome = parada.get("nome")
                chave = normalizar_local(nome)
                if chave:
                    registros.append({
                        "chave": chave,
                        "nome": nome,
                        "parada": parada,
                        "linha": linha,
                        "codigo": codigo,
                        "nome_linha": catalogo.get("nome", ""),
                        "itinerario": itinerario,
                        "variante": variante,
                        "direcao": direcao,
                    })
    return registros


def sugerir_locais(dataset: dict, consulta: str, limite: int = 8) -> list[dict]:
    """Sugere nomes de paradas existentes no dataset, sem consultar a rede."""
    consulta_normalizada = normalizar_local(consulta)
    agrupados: dict[str, dict] = {}
    for registro in _registros_locais(dataset):
        chave = registro["chave"]
        item = agrupados.setdefault(chave, {"nome": registro["nome"], "ocorrencias": 0})
        item["ocorrencias"] += 1
    resultados = []
    for chave, item in agrupados.items():
        score = _pontuacao_busca(consulta_normalizada, chave) if consulta_normalizada else 0.1
        if score >= 0.52 or not consulta_normalizada:
            resultados.append({**item, "score": round(score, 3)})
    return sorted(resultados, key=lambda item: (-item["score"], -item["ocorrencias"], normalizar_local(item["nome"])))[:limite]


def _partidas_textuais(horarios: dict, trip_id: int, data_consulta: str | None) -> list[dict]:
    resultados = []
    for direcao in horarios.get("direcoes", []):
        for servico in direcao.get("servicos", []):
            if data_consulta:
                try:
                    dia = date.fromisoformat(data_consulta)
                    inicio = date.fromisoformat(servico["vigencia_inicio"])
                    fim = date.fromisoformat(servico["vigencia_fim"])
                except (KeyError, TypeError, ValueError):
                    continue
                if not inicio <= dia <= fim:
                    continue
            for partida in servico.get("partidas", []):
                if partida.get("id_viagem") == trip_id:
                    resultados.append({
                        "saida_terminal": partida.get("saida"),
                        "descricao_servico": servico.get("descricao"),
                        "horario_passagem_confirmado": False,
                    })
    return sorted({(item["saida_terminal"], item["descricao_servico"]): item for item in resultados}.values(), key=lambda item: item["saida_terminal"] or "")


def origem_itinerario(itinerario: dict, horarios: dict) -> dict:
    """Descreve a primeira parada sem afirmar que ela é o terminal oficial."""
    paradas = itinerario.get("paradas")
    primeira = paradas[0] if isinstance(paradas, list) and paradas else {}
    latitude = primeira.get("latitude")
    longitude = primeira.get("longitude")
    coordenadas_validas = (
        isinstance(latitude, (int, float)) and not isinstance(latitude, bool)
        and isinstance(longitude, (int, float)) and not isinstance(longitude, bool)
        and math.isfinite(latitude) and math.isfinite(longitude)
        and -90 <= latitude <= 90 and -180 <= longitude <= 180
    )
    trip_id = itinerario.get("id_viagem")
    partidas = _partidas_textuais(horarios, trip_id, None) if isinstance(trip_id, int) else []
    return {
        "status": "primeira_parada_cadastrada" if primeira.get("nome") else "origem_nao_identificada",
        "id_parada": primeira.get("id_parada"),
        "nome": primeira.get("nome"),
        "latitude": latitude if coordenadas_validas else None,
        "longitude": longitude if coordenadas_validas else None,
        "coordenadas_validas": coordenadas_validas,
        "partidas_vinculadas_por_id_viagem": len(partidas),
        "associacao_horario_id_viagem_confirmada": bool(partidas),
        "ponto_oficial_partida_confirmado": False,
        "observacao": "A fonte vincula a partida ao id_viagem, mas não confirma que a primeira parada cadastrada seja o ponto oficial de partida.",
    }


def relatorio_origens(dataset: dict) -> dict:
    """Calcula cobertura das origens dos itinerários válidos do consolidado."""
    itinerarios = 0
    identificadas = 0
    com_coordenadas = 0
    com_partida_vinculada = 0
    for linha in dataset.get("linhas", []):
        for itinerario in linha.get("itinerarios", []):
            itinerarios += 1
            origem = origem_itinerario(itinerario, linha.get("horarios", {}))
            identificadas += origem["status"] == "primeira_parada_cadastrada"
            com_coordenadas += origem["coordenadas_validas"]
            com_partida_vinculada += origem["associacao_horario_id_viagem_confirmada"]
    return {
        "itinerarios": itinerarios,
        "origens_identificadas": identificadas,
        "origens_com_coordenadas": com_coordenadas,
        "variantes_com_partida_vinculada_por_id_viagem": com_partida_vinculada,
        "correspondencias_confirmadas_com_ponto_oficial": 0,
        "criterio_correspondencia": "não existe campo da fonte que confirme a equivalência entre primeira parada cadastrada e ponto oficial de partida",
    }


def planejar_texto(dataset: dict, origem: str, destino: str, *, data_consulta: str | None = None, limite_caminhada_m: float = 800) -> dict:
    """Encontra trajetos diretos por nomes de paradas, respeitando a ordem."""
    sugestoes_origem = sugerir_locais(dataset, origem)
    sugestoes_destino = sugerir_locais(dataset, destino)
    if not sugestoes_origem or not sugestoes_destino or sugestoes_origem[0]["score"] < 0.52 or sugestoes_destino[0]["score"] < 0.52:
        return {"status": "sem_rota", "motivo": "Não encontrei paradas suficientemente semelhantes aos locais informados.", "sugestoes": {"origem": sugestoes_origem, "destino": sugestoes_destino}, "resultados": []}
    origem_chaves = {item["nome"] for item in sugestoes_origem if item["score"] >= sugestoes_origem[0]["score"] - 0.12}
    destino_chaves = {item["nome"] for item in sugestoes_destino if item["score"] >= sugestoes_destino[0]["score"] - 0.12}
    resultados = []
    for registro in _registros_locais(dataset):
        if registro["nome"] not in origem_chaves:
            continue
        paradas = registro["itinerario"].get("paradas", [])
        for destino_registro in _registros_locais({"linhas": [registro["linha"]]}):
            if destino_registro["itinerario"].get("id_viagem") != registro["itinerario"].get("id_viagem") or destino_registro["nome"] not in destino_chaves:
                continue
            if registro["parada"].get("ordem", 0) >= destino_registro["parada"].get("ordem", 0):
                continue
            itinerario = registro["itinerario"]
            geometria_ok = itinerario.get("geometria", {}).get("validacao", {}).get("extremidades_compativeis", True)
            resultados.append({
                "tipo": "direto",
                "status": "candidata_nao_verificada" if not geometria_ok else "candidata",
                "codigo_linha": registro["codigo"],
                "nome_linha": registro["nome_linha"],
                "sentido": registro["direcao"].get("descricao"),
                "embarque": registro["parada"],
                "desembarque": destino_registro["parada"],
                "id_viagem": itinerario.get("id_viagem"),
                "geometria_confirmada": geometria_ok,
                "partidas": _partidas_textuais(registro["linha"]["horarios"], itinerario.get("id_viagem"), data_consulta),
            })
    if not resultados:
        registros = _registros_locais(dataset)
        for primeira in registros:
            if primeira["nome"] not in origem_chaves:
                continue
            for transferencia in registros:
                if transferencia["itinerario"].get("id_viagem") != primeira["itinerario"].get("id_viagem"):
                    continue
                if transferencia["parada"].get("ordem", 0) <= primeira["parada"].get("ordem", 0):
                    continue
                if transferencia["chave"] in {normalizar_local(nome) for nome in destino_chaves}:
                    continue
                for segunda in registros:
                    if segunda["codigo"] == primeira["codigo"] or segunda["chave"] != transferencia["chave"]:
                        continue
                    for destino_registro in registros:
                        if destino_registro["itinerario"].get("id_viagem") != segunda["itinerario"].get("id_viagem") or destino_registro["nome"] not in destino_chaves:
                            continue
                        if segunda["parada"].get("ordem", 0) >= destino_registro["parada"].get("ordem", 0):
                            continue
                        resultados.append({
                            "tipo": "conexao",
                            "status": "candidata_nao_verificada",
                            "transferencia": transferencia["parada"],
                            "pernas": [
                                {"codigo_linha": primeira["codigo"], "nome_linha": primeira["nome_linha"], "sentido": primeira["direcao"].get("descricao"), "embarque": primeira["parada"], "desembarque": transferencia["parada"], "id_viagem": primeira["itinerario"].get("id_viagem"), "partidas": _partidas_textuais(primeira["linha"]["horarios"], primeira["itinerario"].get("id_viagem"), data_consulta)},
                                {"codigo_linha": segunda["codigo"], "nome_linha": segunda["nome_linha"], "sentido": segunda["direcao"].get("descricao"), "embarque": segunda["parada"], "desembarque": destino_registro["parada"], "id_viagem": segunda["itinerario"].get("id_viagem"), "partidas": _partidas_textuais(segunda["linha"]["horarios"], segunda["itinerario"].get("id_viagem"), data_consulta)},
                            ],
                        })
    resultados = sorted({(r.get("tipo"), r["pernas"][0]["codigo_linha"] if r.get("tipo") == "conexao" else r["codigo_linha"], r["pernas"][0]["id_viagem"] if r.get("tipo") == "conexao" else r["id_viagem"]): r for r in resultados}.values(), key=lambda r: (r.get("tipo") != "direto", r.get("codigo_linha", r.get("pernas", [{}])[0].get("codigo_linha"))))
    return {"status": "sucesso" if resultados else "sem_rota", "motivo": "Não encontrei uma rota direta validada para a ordem informada." if not resultados else "", "sugestoes": {"origem": sugestoes_origem, "destino": sugestoes_destino}, "resultados": resultados}


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
