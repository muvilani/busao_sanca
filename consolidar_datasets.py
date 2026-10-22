"""Consolida somente linhas cuja cobertura e itinerários foram validados."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from coletar_lotes import descobrir_falhas, descobrir_linhas_validas, linha_valida
from planejar_viagem import relatorio_origens
from pipeline_mvp import carregar_catalogo, gravar_atomico, localizar_catalogo


def consolidar(catalogo: dict, entrada: Path, destino: Path, codigos: list[str] | None = None, exigir_completa: bool = False) -> dict:
    validas = descobrir_linhas_validas(entrada)
    falhas = descobrir_falhas(entrada)
    alvo = codigos or [linha["codigo"] for linha in catalogo["linhas"]]
    linhas = [validas[codigo] for codigo in alvo if codigo in validas and linha_valida(validas[codigo])]
    validadas = {linha["catalogo"]["codigo"] for linha in linhas}
    com_falhas = [codigo for codigo in alvo if codigo not in validadas and codigo in falhas]
    nao_coletadas = [codigo for codigo in alvo if codigo not in validadas and codigo not in falhas]
    completa = len(validadas) == len(set(alvo))
    if exigir_completa and not completa:
        raise ValueError("consolidação incompleta: existem linhas com falha ou não coletadas")
    resultado = {
        "schema_version": 1,
        "status": "sucesso" if linhas else "incompleto",
        "consolidado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "projeto": catalogo["metadados"]["projeto"],
        "cobertura": {"linhas_solicitadas": len(set(alvo)), "linhas_validadas": len(linhas), "completa": completa},
        "classificacao": {"validadas": [c for c in alvo if c in validadas], "com_falhas": com_falhas, "nao_coletadas": nao_coletadas},
        "linhas": linhas,
    }
    resultado["cobertura_origens"] = relatorio_origens(resultado)
    gravar_atomico(destino, resultado)
    return resultado


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, default=Path("saida"))
    parser.add_argument("--catalogo", type=Path)
    parser.add_argument("--saida", type=Path, default=Path("saida/consolidado/dados.json"))
    parser.add_argument("--linhas", nargs="*")
    parser.add_argument("--exigir-completa", action="store_true")
    args = parser.parse_args(argv)
    resultado = consolidar(carregar_catalogo(args.catalogo or localizar_catalogo()), args.entrada, args.saida, args.linhas, args.exigir_completa)
    print(json.dumps(resultado["cobertura"] | resultado["classificacao"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
