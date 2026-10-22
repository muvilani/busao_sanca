"""Coleta incremental por linha, sem publicar o dataset do aplicativo."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from acesso_http import ClientePublico, ErroColeta
from pipeline_mvp import (
    ErroPipeline,
    carregar_catalogo,
    coletar_linha,
    gravar_atomico,
    localizar_catalogo,
    selecionar_linhas,
)


def agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def carregar_json(caminho: Path) -> object:
    return json.loads(caminho.read_text(encoding="utf-8-sig"))


def iter_datasets(entrada: Path) -> Iterable[Path]:
    vistos: set[Path] = set()
    candidatos = (
        sorted(entrada.rglob("dados.json"))
        + sorted(entrada.rglob("web-dados.json"))
        + sorted(entrada.rglob("linhas/*.json"))
    )
    for caminho in candidatos:
        resolvido = caminho.resolve()
        if resolvido not in vistos:
            vistos.add(resolvido)
            yield caminho


def linha_valida(linha: object) -> bool:
    """Revalida a cobertura antes de reutilizar uma linha salva."""
    if not isinstance(linha, dict):
        return False
    catalogo = linha.get("catalogo")
    horarios = linha.get("horarios")
    itinerarios = linha.get("itinerarios")
    cobertura = linha.get("cobertura")
    if not isinstance(catalogo, dict) or not isinstance(horarios, dict):
        return False
    if not isinstance(itinerarios, list) or not isinstance(cobertura, dict):
        return False
    if cobertura.get("completa_no_escopo_solicitado") is not True:
        return False
    variantes = horarios.get("variantes")
    if not isinstance(variantes, list):
        return False
    ids_esperados = [v.get("id_viagem") for v in variantes if isinstance(v, dict)]
    if len(ids_esperados) != len(variantes) or any(type(i) is not int or i <= 0 for i in ids_esperados):
        return False
    if len(set(ids_esperados)) != len(ids_esperados):
        return False
    ids_obtidos = [item.get("id_viagem") for item in itinerarios if isinstance(item, dict)]
    if len(ids_obtidos) != len(itinerarios) or set(ids_obtidos) != set(ids_esperados):
        return False
    for item in itinerarios:
        if not isinstance(item, dict) or not isinstance(item.get("paradas"), list):
            return False
        if len(item["paradas"]) < 2:
            return False
        geometria = item.get("geometria")
        if not isinstance(geometria, dict) or not isinstance(geometria.get("validacao"), dict):
            return False
    return True


def descobrir_linhas_validas(entrada: Path) -> dict[str, dict]:
    validas: dict[str, dict] = {}
    for caminho in iter_datasets(entrada):
        try:
            dados = carregar_json(caminho)
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(dados, dict) or dados.get("status") != "sucesso":
            continue
        linhas = dados.get("linhas")
        if not isinstance(linhas, list):
            continue
        for linha in linhas:
            if linha_valida(linha) and isinstance(linha["catalogo"].get("codigo"), str):
                validas[linha["catalogo"]["codigo"]] = linha
    return validas


def descobrir_falhas(entrada: Path) -> dict[str, list[dict]]:
    falhas: dict[str, list[dict]] = {}
    for caminho in entrada.rglob("falhas/*.json"):
        try:
            dados = carregar_json(caminho)
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(dados, dict):
            continue
        solicitadas = dados.get("linhas_solicitadas", [])
        # Diagnóstico antigo de lote não identifica qual linha falhou; não
        # transforma as demais linhas em falhas por inferência.
        if isinstance(solicitadas, list) and len(solicitadas) == 1 and isinstance(solicitadas[0], str):
            falhas.setdefault(solicitadas[0], []).append(dados)
        linha = dados.get("linha")
        if isinstance(linha, dict) and isinstance(linha.get("codigo"), str):
            falhas.setdefault(linha["codigo"], []).append(dados)
    return falhas


def classificar_catalogo(catalogo: dict, entrada: Path) -> dict[str, list[str]]:
    validas = descobrir_linhas_validas(entrada)
    falhas = descobrir_falhas(entrada)
    codigos = [linha["codigo"] for linha in catalogo["linhas"]]
    return {
        "validadas": [c for c in codigos if c in validas],
        "com_falhas": [c for c in codigos if c in falhas and c not in validas],
        "nao_coletadas": [c for c in codigos if c not in validas and c not in falhas],
    }


def salvar_falha(base: Path, codigo: str, erro: Exception) -> Path:
    destino = base / "falhas" / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}-{codigo}.json"
    gravar_atomico(destino, {
        "schema_version": 1,
        "status": "falha",
        "coletado_em": agora(),
        "linha": {"codigo": codigo},
        "erro": {"tipo": type(erro).__name__, "mensagem": str(erro), "trip_id": getattr(erro, "trip_id", None)},
        "dataset_publicado": False,
    })
    return destino


def coletar_pendentes(catalogo: dict, entrada: Path, cliente, destino: Path, codigos: list[str] | None = None) -> dict:
    estado = classificar_catalogo(catalogo, entrada)
    validas = set(estado["validadas"])
    alvo = codigos if codigos is not None else estado["nao_coletadas"]
    pendentes = [linha for linha in selecionar_linhas(catalogo, alvo) if linha["codigo"] not in validas]
    projeto_id = catalogo["metadados"]["projeto"]["id"]
    base = destino / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    sucesso, falhas = [], []
    for linha in pendentes:
        try:
            dados = coletar_linha(cliente, projeto_id, linha)
            gravar_atomico(base / "linhas" / f"{linha['codigo']}.json", {"schema_version": 1, "status": "sucesso", "linhas": [dados]})
            sucesso.append(linha["codigo"])
        except (ErroPipeline, ErroColeta, ValueError, OSError) as erro:
            diagnostico = salvar_falha(base, linha["codigo"], erro)
            falhas.append({"codigo": linha["codigo"], "diagnostico": str(diagnostico), "trip_id": getattr(erro, "trip_id", None), "motivo": str(erro)})
    manifesto = {
        "schema_version": 1,
        "status": "sucesso_parcial" if falhas else "sucesso",
        "coletado_em": agora(),
        "linhas_reutilizadas": estado["validadas"],
        "linhas_ignoradas_com_falha": estado["com_falhas"],
        "linhas_solicitadas": [linha["codigo"] for linha in pendentes],
        "linhas_concluidas": sucesso,
        "falhas": falhas,
    }
    gravar_atomico(base / "manifesto.json", manifesto)
    return manifesto


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, default=Path("saida"))
    parser.add_argument("--catalogo", type=Path)
    parser.add_argument("--saida", type=Path, default=Path("saida/lotes"))
    parser.add_argument("--linhas", nargs="*")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--intervalo", type=float, default=2)
    args = parser.parse_args(argv)
    catalogo = carregar_catalogo(args.catalogo or localizar_catalogo())
    estado = classificar_catalogo(catalogo, args.entrada)
    codigos = args.linhas or estado["nao_coletadas"]
    selecionadas = selecionar_linhas(catalogo, codigos)
    subcatalogo = {**catalogo, "linhas": selecionadas}
    with ClientePublico(timeout=args.timeout, intervalo=args.intervalo) as cliente:
        manifesto = coletar_pendentes(subcatalogo, args.entrada, cliente, args.saida, codigos if args.linhas else None)
    print(json.dumps(manifesto, ensure_ascii=False, indent=2))
    return 0 if not manifesto["falhas"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
