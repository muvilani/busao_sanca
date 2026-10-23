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


def _chave_parada(parada: dict, fallback: str) -> tuple[str, bool]:
    identificador = parada.get("id_parada")
    if type(identificador) is int and identificador > 0:
        return f"id:{identificador}", True
    return f"ocorrencia:{fallback}", False


def _segmentos(dataset: dict) -> list[dict]:
    segmentos = []
    linhas = dataset.get("linhas", []) if isinstance(dataset, dict) else []
    for linha in linhas if isinstance(linhas, list) else []:
        if not isinstance(linha, dict):
            continue
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
            paradas = itinerario.get("paradas")
            if not variante or not direcao or not isinstance(paradas, list) or len(paradas) < 2:
                continue
            ordens = [parada.get("ordem") for parada in paradas if isinstance(parada, dict)]
            if len(ordens) != len(paradas) or any(type(ordem) is not int for ordem in ordens):
                continue
            if any(atual >= seguinte for atual, seguinte in zip(ordens, ordens[1:])):
                continue
            paradas_indexadas = []
            for indice, parada in enumerate(paradas):
                nome = parada.get("nome") if isinstance(parada, dict) else None
                chave = normalizar_local(nome)
                if not chave:
                    break
                chave_parada, confiavel = _chave_parada(
                    parada, f"{codigo}:{itinerario.get('id_viagem')}:{indice}"
                )
                paradas_indexadas.append({
                    "chave": chave_parada,
                    "chave_nome": chave,
                    "confiavel": confiavel,
                    "nome": nome,
                    "parada": parada,
                    "indice": indice,
                })
            if len(paradas_indexadas) != len(paradas):
                continue
            segmentos.append({
                "linha": linha,
                "codigo": str(codigo or ""),
                "nome_linha": catalogo.get("nome", ""),
                "itinerario": itinerario,
                "variante": variante,
                "direcao": direcao,
                "paradas": paradas_indexadas,
            })
    return segmentos


def _registros_locais(dataset: dict) -> list[dict]:
    registros = []
    for segmento in _segmentos(dataset):
        for parada in segmento["paradas"]:
            registros.append({**parada, **segmento})
    return registros


def sugerir_locais(dataset: dict, consulta: str, limite: int = 8) -> list[dict]:
    """Sugere nomes de paradas existentes no dataset, sem consultar a rede."""
    consulta_normalizada = normalizar_local(consulta)
    agrupados: dict[str, dict] = {}
    for registro in _registros_locais(dataset):
        chave = registro["chave"]
        identificador = registro["parada"].get("id_parada")
        rotulo = f"{registro['nome']} · parada {identificador}" if registro["confiavel"] else registro["nome"]
        item = agrupados.setdefault(chave, {
            "chave": chave,
            "nome": registro["nome"],
            "rotulo": rotulo,
            "id_parada": identificador,
            "ocorrencias": 0,
        })
        item["ocorrencias"] += 1
    resultados = []
    for chave, item in agrupados.items():
        score = max(
            _pontuacao_busca(consulta_normalizada, normalizar_local(item["nome"])),
            _pontuacao_busca(consulta_normalizada, normalizar_local(item["rotulo"])),
        ) if consulta_normalizada else 0.1
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
                        "id_servico": servico.get("id_servico"),
                        "descricao_servico": servico.get("descricao"),
                        "vigencia_inicio": servico.get("vigencia_inicio"),
                        "vigencia_fim": servico.get("vigencia_fim"),
                        "horario_passagem_confirmado": False,
                    })
    return sorted(
        {
            (item["saida_terminal"], item["id_servico"], item["descricao_servico"]): item
            for item in resultados
        }.values(),
        key=lambda item: item["saida_terminal"] or "",
    )


def _resolver_chaves(dataset: dict, valor: str) -> tuple[set[str], list[dict]]:
    sugestoes = sugerir_locais(dataset, valor, limite=20)
    texto = str(valor or "").strip()
    if not texto:
        return set(), sugestoes

    por_chave = [item for item in sugestoes if item["chave"] == texto]
    if por_chave:
        return {por_chave[0]["chave"]}, sugestoes

    consulta = normalizar_local(texto)
    por_rotulo = [item for item in sugestoes if normalizar_local(item["rotulo"]) == consulta]
    if por_rotulo:
        return {item["chave"] for item in por_rotulo}, sugestoes
    por_nome = [item for item in sugestoes if normalizar_local(item["nome"]) == consulta]
    if por_nome:
        return {item["chave"] for item in por_nome}, sugestoes
    if not sugestoes or sugestoes[0]["score"] < 0.52:
        return set(), sugestoes
    melhor = sugestoes[0]["score"]
    return {item["chave"] for item in sugestoes if item["score"] >= melhor - 0.12}, sugestoes


def _montar_perna(segmento: dict, inicio: int, fim: int, data_consulta: str | None) -> dict:
    itinerario = segmento["itinerario"]
    variante = segmento["variante"]
    embarque = segmento["paradas"][inicio]
    desembarque = segmento["paradas"][fim]
    geometria_ok = itinerario.get("geometria", {}).get("validacao", {}).get(
        "extremidades_compativeis", True
    )
    partidas = _partidas_textuais(
        segmento["linha"].get("horarios", {}), itinerario.get("id_viagem"), data_consulta
    )
    servicos = {
        (str(partida.get("id_servico")), str(partida.get("descricao_servico"))): {
            "id_servico": partida.get("id_servico"),
            "descricao": partida.get("descricao_servico"),
        }
        for partida in partidas
    }
    return {
        "codigo_linha": segmento["codigo"],
        "nome_linha": segmento["nome_linha"],
        "sentido": segmento["direcao"].get("descricao"),
        "destino_variante": variante.get("destino"),
        "sequencia_variante": variante.get("sequencia"),
        "embarque": embarque["parada"],
        "desembarque": desembarque["parada"],
        "chave_embarque": embarque["chave"],
        "chave_desembarque": desembarque["chave"],
        "id_viagem": itinerario.get("id_viagem"),
        "geometria_confirmada": geometria_ok,
        "paradas_intermediarias": max(0, fim - inicio - 1),
        "paradas_percorridas": fim - inicio,
        "servicos": [servicos[chave] for chave in sorted(servicos)],
        "partidas": partidas,
    }


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


def planejar_texto(
    dataset: dict,
    origem: str,
    destino: str,
    *,
    data_consulta: str | None = None,
    limite_caminhada_m: float = 800,
    limite_resultados: int = 8,
) -> dict:
    """Encontra viagens diretas e com uma conexão por paradas do dataset.

    Uma conexão só é criada quando as duas variantes compartilham o mesmo
    ``id_parada``. Coincidência de nomes, isoladamente, não prova integração.
    ``limite_caminhada_m`` é mantido por compatibilidade; esta busca textual
    não estima caminhada.
    """
    del limite_caminhada_m
    origem_chaves, sugestoes_origem = _resolver_chaves(dataset, origem)
    destino_chaves, sugestoes_destino = _resolver_chaves(dataset, destino)
    resposta_base = {
        "sugestoes": {"origem": sugestoes_origem, "destino": sugestoes_destino},
        "resultados": [],
    }
    if not origem_chaves or not destino_chaves:
        return {
            **resposta_base,
            "status": "sem_rota",
            "motivo": "Não encontrei paradas suficientemente semelhantes aos locais informados.",
        }
    if origem_chaves & destino_chaves:
        return {
            **resposta_base,
            "status": "origem_destino_iguais",
            "motivo": "Origem e destino representam a mesma parada.",
        }

    segmentos = _segmentos(dataset)
    diretos = []
    for segmento in segmentos:
        origens = [p["indice"] for p in segmento["paradas"] if p["chave"] in origem_chaves]
        destinos = [p["indice"] for p in segmento["paradas"] if p["chave"] in destino_chaves]
        for inicio in origens:
            for fim in destinos:
                if inicio >= fim:
                    continue
                perna = _montar_perna(segmento, inicio, fim, data_consulta)
                diretos.append({
                    "tipo": "direto",
                    "status": "candidata" if perna["geometria_confirmada"] else "candidata_nao_verificada",
                    "conexoes": 0,
                    **perna,
                })

    conexoes = []
    for primeiro in segmentos:
        origens = [p["indice"] for p in primeiro["paradas"] if p["chave"] in origem_chaves]
        for inicio in origens:
            for indice_transferencia in range(inicio + 1, len(primeiro["paradas"])):
                transferencia = primeiro["paradas"][indice_transferencia]
                if (
                    not transferencia["confiavel"]
                    or transferencia["chave"] in origem_chaves
                    or transferencia["chave"] in destino_chaves
                ):
                    continue
                for segundo in segmentos:
                    if segundo["itinerario"].get("id_viagem") == primeiro["itinerario"].get("id_viagem"):
                        continue
                    embarques = [
                        p["indice"] for p in segundo["paradas"]
                        if p["confiavel"] and p["chave"] == transferencia["chave"]
                    ]
                    destinos = [p["indice"] for p in segundo["paradas"] if p["chave"] in destino_chaves]
                    for embarque_segundo in embarques:
                        for fim in destinos:
                            if embarque_segundo >= fim:
                                continue
                            primeira_perna = _montar_perna(
                                primeiro, inicio, indice_transferencia, data_consulta
                            )
                            segunda_perna = _montar_perna(
                                segundo, embarque_segundo, fim, data_consulta
                            )
                            conexoes.append({
                                "tipo": "conexao",
                                "status": "candidata_nao_verificada",
                                "conexoes": 1,
                                "transferencia": transferencia["parada"],
                                "paradas_ate_transferencia": primeira_perna["paradas_percorridas"],
                                "paradas_percorridas": (
                                    primeira_perna["paradas_percorridas"]
                                    + segunda_perna["paradas_percorridas"]
                                ),
                                "pernas": [primeira_perna, segunda_perna],
                                "aviso_conexao": (
                                    "Conexão estrutural pelo mesmo identificador de parada; "
                                    "tempo de transferência, tarifa e espera não foram confirmados."
                                ),
                            })

    diretos_unicos = {
        (item["id_viagem"], item["chave_embarque"], item["chave_desembarque"]): item
        for item in diretos
    }
    conexoes_unicas = {
        (
            item["pernas"][0]["id_viagem"],
            item["pernas"][1]["id_viagem"],
            item["pernas"][0]["chave_embarque"],
            item["transferencia"].get("id_parada"),
            item["pernas"][1]["chave_desembarque"],
        ): item
        for item in conexoes
    }
    resultados = [*diretos_unicos.values(), *conexoes_unicas.values()]

    def chave_ordenacao(item: dict) -> tuple:
        primeira = item["pernas"][0] if item["tipo"] == "conexao" else item
        segunda = item["pernas"][1] if item["tipo"] == "conexao" else {}
        return (
            item["conexoes"],
            item["paradas_percorridas"],
            primeira["paradas_percorridas"],
            primeira["codigo_linha"],
            str(primeira.get("sentido") or ""),
            primeira.get("sequencia_variante") or 0,
            str(segunda.get("codigo_linha") or ""),
            segunda.get("sequencia_variante") or 0,
        )

    resultados = sorted(resultados, key=chave_ordenacao)[:max(0, limite_resultados)]
    if not resultados:
        return {
            **resposta_base,
            "status": "sem_rota",
            "motivo": (
                "Não encontrei uma sequência válida, direta ou com uma conexão confirmável, "
                "entre as paradas informadas."
            ),
        }
    return {
        **resposta_base,
        "status": "sucesso",
        "motivo": "",
        "resultados": resultados,
    }


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
