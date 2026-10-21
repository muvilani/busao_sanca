"""Pipeline controlado de horários e itinerários para o MVP local.

As respostas HTTP são validadas pelos parsers existentes. Uma execução somente
publica ``web/dados.json`` depois que todas as linhas e viagens solicitadas
forem obtidas; uma falha nunca substitui o último conjunto válido.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from acesso_http import ClientePublico, ErroColeta
from processar_horarios import processar_horarios
from processar_itinerarios import processar_itinerario

API = "https://mobilibus.com/api/"
RAIZ = Path(__file__).resolve().parent
CATALOGO_PADRAO = RAIZ / "saida" / "oficial"
SAIDA_PADRAO = RAIZ / "saida" / "mvp"
WEB_PADRAO = RAIZ / "web" / "dados.json"


class ErroPipeline(RuntimeError):
    """Coleta do conjunto solicitado não pôde ser concluída integralmente."""


def agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json_resposta(resposta, contexto: str) -> object:
    try:
        texto = resposta.content.decode("utf-8-sig")
        return json.loads(texto)
    except (UnicodeDecodeError, json.JSONDecodeError) as erro:
        raise ErroPipeline(f"{contexto}: resposta não contém JSON UTF-8 válido") from erro


def localizar_catalogo(base: Path = CATALOGO_PADRAO) -> Path:
    candidatos = sorted(base.glob("*/linhas.json"), reverse=True)
    if not candidatos:
        raise ErroPipeline(f"nenhum catálogo encontrado em {base}")
    return candidatos[0]


def carregar_catalogo(caminho: Path | None = None) -> dict:
    arquivo = caminho or localizar_catalogo()
    try:
        catalogo = json.loads(arquivo.read_text(encoding="utf-8-sig"))
        projeto = catalogo["metadados"]["projeto"]
        linhas = catalogo["linhas"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as erro:
        raise ErroPipeline(f"catálogo inválido: {arquivo}") from erro
    if type(projeto.get("id")) is not int or projeto["id"] <= 0 or not isinstance(linhas, list):
        raise ErroPipeline(f"catálogo inválido: {arquivo}")
    return catalogo


def selecionar_linhas(catalogo: dict, codigos: list[str]) -> list[dict]:
    indice = {item.get("codigo"): item for item in catalogo["linhas"]}
    ausentes = [codigo for codigo in codigos if codigo not in indice]
    if ausentes:
        raise ErroPipeline("linhas não encontradas no catálogo: " + ", ".join(ausentes))
    selecionadas = [indice[codigo] for codigo in dict.fromkeys(codigos)]
    if not selecionadas:
        raise ErroPipeline("selecione ao menos uma linha")
    return selecionadas


def _url(endpoint: str, **parametros: object) -> str:
    return API + endpoint + "?" + urlencode(parametros)


def coletar_linha(cliente, projeto_id: int, linha: dict) -> dict:
    route_id = linha["id_linha"]
    url_horarios = _url("timetable", origin="web", v=2, project_id=projeto_id, route_id=route_id)
    horarios = processar_horarios(_json_resposta(cliente.obter(url_horarios), "timetable"))
    identidade = horarios["linha"]
    if identidade["id_linha"] != route_id or identidade["codigo"] != linha["codigo"]:
        raise ErroPipeline(f"identidade divergente na linha {linha['codigo']}")

    ids_viagem = list(dict.fromkeys(v["id_viagem"] for v in horarios["variantes"]))
    itinerarios = []
    urls_itinerarios = []
    for trip_id in ids_viagem:
        url_itinerario = _url("trip-details", origin="web", v=2, project_id=projeto_id, trip_id=trip_id)
        try:
            item = processar_itinerario(
                _json_resposta(cliente.obter(url_itinerario), f"trip-details {trip_id}"),
                trip_id,
                permitir_extremidades_divergentes=True,
            )
        except ValueError as erro:
            raise ErroPipeline(f"trip-details {trip_id}: {erro}") from erro
        itinerarios.append(item)
        urls_itinerarios.append(url_itinerario)

    obtidos = {item["id_viagem"] for item in itinerarios}
    if obtidos != set(ids_viagem):
        raise ErroPipeline(f"cobertura de itinerários incompleta na linha {linha['codigo']}")
    geometrias_divergentes = [
        item["id_viagem"] for item in itinerarios
        if not item["geometria"]["validacao"]["extremidades_compativeis"]
    ]
    return {
        "catalogo": {"codigo": linha["codigo"], "nome": linha["nome"], "id_linha": route_id},
        "horarios": horarios,
        "itinerarios": itinerarios,
        "fontes": {"horarios": url_horarios, "itinerarios": urls_itinerarios},
        "cobertura": {
            "variantes": len(horarios["variantes"]),
            "trip_ids_unicos": len(ids_viagem),
            "itinerarios_validados": len(itinerarios),
            "completa_no_escopo_solicitado": True,
            "geometrias_com_extremidades_divergentes": geometrias_divergentes,
        },
        "erros": [],
    }


def executar(catalogo: dict, codigos: list[str], cliente) -> dict:
    selecionadas = selecionar_linhas(catalogo, codigos)
    projeto = catalogo["metadados"]["projeto"]
    linhas = [coletar_linha(cliente, projeto["id"], linha) for linha in selecionadas]
    return {
        "schema_version": 1,
        "status": "sucesso",
        "coletado_em": agora(),
        "projeto": projeto,
        "fonte": {
            "pagina_oficial": catalogo["metadados"].get("url_pagina_oficial"),
            "catalogo": catalogo["metadados"].get("url_catalogo"),
            "aviso": "Dados de terceiros para consulta privada; atualização e completude não garantidas.",
        },
        "cobertura": {
            "linhas_solicitadas": len(selecionadas),
            "linhas_concluidas": len(linhas),
            "completa_no_escopo_solicitado": True,
        },
        "limitacoes": [
            "A ordem do vetor semanal e a semântica das exceções não estão confirmadas.",
            "Partidas são horários de origem da viagem, não previsão para paradas intermediárias.",
            "O catálogo não declara sua completude municipal.",
        ],
        "linhas": linhas,
    }


def gravar_atomico(caminho: Path, dados: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conteudo = json.dumps(dados, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=caminho.parent, delete=False) as temporario:
        temporario.write(conteudo)
        nome = temporario.name
    os.replace(nome, caminho)


def publicar_resultado(dados: dict, base: Path, web: Path | None) -> Path:
    identificador = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destino = base / identificador / "dados.json"
    gravar_atomico(destino, dados)
    if web is not None:
        gravar_atomico(web, dados)
    return destino


def registrar_falha(base: Path, codigos: list[str], erro: Exception) -> Path:
    identificador = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destino = base / "falhas" / f"{identificador}.json"
    gravar_atomico(destino, {
        "schema_version": 1,
        "status": "falha",
        "coletado_em": agora(),
        "linhas_solicitadas": codigos,
        "erro": {"tipo": type(erro).__name__, "mensagem": str(erro)},
        "dataset_publicado": False,
    })
    return destino


def main() -> int:
    parser = argparse.ArgumentParser(description="Coleta controlada do dataset do MVP")
    parser.add_argument("--linhas", nargs="+", default=["34"], help="códigos das linhas (padrão: 34)")
    parser.add_argument("--catalogo", type=Path)
    parser.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    parser.add_argument("--web", type=Path, default=WEB_PADRAO)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--intervalo", type=float, default=2)
    args = parser.parse_args()
    try:
        catalogo = carregar_catalogo(args.catalogo)
        with ClientePublico(timeout=args.timeout, intervalo=args.intervalo) as cliente:
            dados = executar(catalogo, args.linhas, cliente)
        destino = publicar_resultado(dados, args.saida, args.web)
    except (ErroPipeline, ErroColeta, ValueError, OSError) as erro:
        try:
            diagnostico = registrar_falha(args.saida, args.linhas, erro)
            print(f"Coleta não publicada: {erro} (diagnóstico: {diagnostico})")
        except OSError:
            print(f"Coleta não publicada: {erro} (falha ao gravar diagnóstico)")
        return 1
    print(f"Dataset completo publicado em {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
