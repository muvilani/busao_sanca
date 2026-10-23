"""Monta um pacote estático seguro usando somente dados sintéticos versionados."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


RAIZ = Path(__file__).resolve().parent
WEB = RAIZ / "web"
FIXTURE = RAIZ / "publicacao" / "dados.demo.json"
DESTINO_PADRAO = RAIZ / "publicacao" / "dist"
ASSETS = (
    "index.html",
    "styles.css",
    "planner.css",
    "app.js",
    "planejador.js",
    "paradas.js",
)


class ErroPublicacao(ValueError):
    """Pacote não pode ser preparado sem comprovar que os dados são sintéticos."""


def carregar_fixture(caminho: Path = FIXTURE) -> dict:
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as erro:
        raise ErroPublicacao(f"fixture sintético inválido: {caminho}") from erro
    if not isinstance(dados, dict) or dados.get("demonstracao", {}).get("sintetico") is not True:
        raise ErroPublicacao("o pacote aceita somente fixture marcado como sintético")
    if dados.get("status") != "sucesso" or not isinstance(dados.get("linhas"), list):
        raise ErroPublicacao("fixture sintético não respeita o contrato mínimo do aplicativo")
    return dados


def preparar(destino: Path = DESTINO_PADRAO) -> dict:
    """Copia assets permitidos e grava o fixture sintético como ``dados.json``."""
    dados = carregar_fixture()
    destino = destino.resolve()
    proibidos = tuple((RAIZ / nome).resolve() for nome in ("web", "saida", "dados", "site"))
    if any(destino == raiz or raiz in destino.parents for raiz in proibidos):
        raise ErroPublicacao(f"destino protegido contra publicação: {destino}")
    esperados = set(ASSETS) | {"dados.json", "manifesto.json"}
    if destino.exists():
        inesperados = [item.name for item in destino.iterdir() if item.name not in esperados]
        if inesperados:
            raise ErroPublicacao("destino contém arquivos inesperados: " + ", ".join(sorted(inesperados)))
        dados_existentes = destino / "dados.json"
        if dados_existentes.exists():
            try:
                anterior = json.loads(dados_existentes.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as erro:
                raise ErroPublicacao("dados.json preexistente não é um fixture sintético válido") from erro
            if anterior.get("demonstracao", {}).get("sintetico") is not True:
                raise ErroPublicacao("recusa sobrescrever dados.json sem marcação sintética")
    destino.mkdir(parents=True, exist_ok=True)
    arquivos = {}
    for nome in ASSETS:
        origem = WEB / nome
        alvo = destino / nome
        shutil.copyfile(origem, alvo)
        arquivos[nome] = hashlib.sha256(alvo.read_bytes()).hexdigest()
    conteudo = json.dumps(dados, ensure_ascii=False, indent=2) + "\n"
    (destino / "dados.json").write_text(conteudo, encoding="utf-8")
    arquivos["dados.json"] = hashlib.sha256(conteudo.encode("utf-8")).hexdigest()
    manifesto = {
        "schema_version": 1,
        "dados_sinteticos": True,
        "origem_fixture": "publicacao/dados.demo.json",
        "arquivos": arquivos,
    }
    (destino / "manifesto.json").write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifesto


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destino", type=Path, default=DESTINO_PADRAO)
    args = parser.parse_args()
    manifesto = preparar(args.destino)
    print(json.dumps(manifesto, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
