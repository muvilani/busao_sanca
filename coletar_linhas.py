"""Coleta o catálogo público incorporado à página da SOU São Carlos."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup
from requests.utils import parse_header_links

from acesso_http import ClientePublico, ErroColeta

OFICIAL = "https://soutransportes.com.br/sao-carlos/linhas-e-horarios/"
API = "https://mobilibus.com/api/"
SAIDA_PADRAO = Path(__file__).resolve().parent / "saida" / "oficial"
CAMPOS = (
    "codigo", "nome", "url_origem", "coletado_em", "id_linha",
    "url_pagina_oficial", "url_catalogo",
)


def agora() -> str:
    """UTC explícito, sem depender da base de fusos horários do Windows."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def identificador_execucao() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def descobrir_catalogo(html: str) -> tuple[str, str]:
    """Usa somente o iframe público observado; mudanças exigem revisão."""
    soup = BeautifulSoup(html, "html.parser")
    candidatos = set()
    for iframe in soup.select("iframe[src]"):
        try:
            url = urljoin(OFICIAL, iframe["src"])
            partes = urlsplit(url)
        except ValueError as erro:
            raise ErroColeta("Endereço de iframe inválido na página oficial.") from erro
        if partes.hostname != "bus2.info":
            continue
        if (
            partes.scheme != "https"
            or partes.netloc != "bus2.info"
            or partes.path != "/2you/"
            or partes.query
            or not re.fullmatch(r"/[a-zA-Z0-9]+", partes.fragment)
        ):
            raise ErroColeta("O endereço do catálogo Bus2 mudou; revise o adaptador.")
        candidatos.add((url, partes.fragment[1:]))
    if len(candidatos) != 1:
        raise ErroColeta(
            "Esperado um único catálogo Bus2 na página oficial; "
            f"encontrados {len(candidatos)}. Nenhum fallback foi utilizado."
        )
    return candidatos.pop()


def texto_normalizado(valor: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", valor.casefold())
        if unicodedata.category(c) != "Mn"
    )


def validar_projeto(projeto: object, project_hash: str) -> int:
    if not isinstance(projeto, dict):
        raise ErroColeta("Os detalhes do projeto não são um objeto JSON.")
    cidade = projeto.get("city")
    if not isinstance(cidade, str) or texto_normalizado(cidade) != "sao carlos, sp":
        raise ErroColeta("O catálogo não confirmou a cidade São Carlos, SP.")
    if projeto.get("hash") != project_hash:
        raise ErroColeta("O identificador do projeto diverge do iframe oficial.")
    project_id = projeto.get("projectId")
    if type(project_id) is not int or project_id <= 0:
        raise ErroColeta("projectId ausente ou inválido.")
    return project_id


def validar_resposta(resposta, tipo: str) -> None:
    if resposta.status_code != 200:
        raise ErroColeta(f"Resposta incompleta ou inesperada: HTTP {resposta.status_code}.")
    links = parse_header_links(resposta.headers.get("Link", ""))
    tem_proxima = any(
        chave.lower() == "rel" and "next" in valor.lower().split()
        for link in links for chave, valor in link.items()
    )
    if resposta.headers.get("Content-Range") or tem_proxima:
        raise ErroColeta("A resposta indica conteúdo parcial ou paginação não suportada.")
    mime = resposta.headers.get("Content-Type", "").split(";")[0].strip().lower()
    aceitos = {"application/json"} if tipo == "json" else {"text/html", "application/xhtml+xml"}
    if mime not in aceitos:
        raise ErroColeta(f"Content-Type inesperado: {mime!r}; esperado {tipo}.")


def ler_json(resposta) -> object:
    validar_resposta(resposta, "json")
    try:
        return json.loads(resposta.content.decode("utf-8-sig"))
    except (UnicodeError, ValueError) as erro:
        raise ErroColeta(f"JSON inválido recebido de {resposta.url}.") from erro


def extrair_linhas(
    payload: object, url_origem: str, url_catalogo: str, coletado_em: str
) -> list[dict]:
    if not isinstance(payload, list) or not payload:
        raise ErroColeta(
            "O catálogo deve retornar um array não vazio. "
            "Lista vazia ou novo formato exige revisão; nada será publicado."
        )
    codigos: set[str] = set()
    identificadores: set[int] = set()
    linhas = []
    for indice, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ErroColeta(f"Registro {indice} não é um objeto.")
        codigo, nome, route_id = (item.get(k) for k in ("shortName", "longName", "routeId"))
        for campo, valor in (("shortName", codigo), ("longName", nome)):
            if (
                not isinstance(valor, str) or not valor.strip()
                or "\ufffd" in valor
                or any(unicodedata.category(c) == "Cc" for c in valor)
            ):
                raise ErroColeta(f"Registro {indice}: {campo} ausente ou inválido.")
        if type(route_id) is not int or route_id <= 0:
            raise ErroColeta(f"Registro {indice}: routeId ausente ou inválido.")
        codigo, nome = codigo.strip(), nome.strip()
        if codigo in codigos or route_id in identificadores:
            raise ErroColeta(
                f"Código ou routeId duplicado ({codigo!r}, {route_id}); "
                "nenhum registro será descartado silenciosamente."
            )
        codigos.add(codigo)
        identificadores.add(route_id)
        linhas.append({
            "codigo": codigo,
            "nome": nome,
            "url_origem": url_origem,
            "coletado_em": coletado_em,
            "id_linha": route_id,
            "url_pagina_oficial": OFICIAL,
            "url_catalogo": url_catalogo,
        })
    return linhas


def coletar(cliente: ClientePublico) -> tuple[list[dict], dict, dict[str, bytes]]:
    fontes: dict[str, bytes] = {}
    respostas = []

    def buscar(url: str, nome: str):
        resposta = cliente.obter(url)
        fontes[nome] = resposta.content
        respostas.append({
            "url": resposta.url,
            "arquivo": f"fontes/{nome}",
            "sha256": hashlib.sha256(resposta.content).hexdigest(),
            "consultado_em": agora(),
            "http_status": resposta.status_code,
            "http_date": resposta.headers.get("Date"),
            "cache_control": resposta.headers.get("Cache-Control"),
            "age": resposta.headers.get("Age"),
        })
        return resposta

    oficial = buscar(OFICIAL, "pagina_oficial.html")
    validar_resposta(oficial, "html")
    catalogo, project_hash = descobrir_catalogo(oficial.text)
    # O fragmento identifica a cidade na aplicação; não vai na requisição HTTP.
    pagina_catalogo = buscar(catalogo.split("#", 1)[0], "catalogo.html")
    validar_resposta(pagina_catalogo, "html")
    url_projeto = API + "project-details?" + urlencode({"project_hash": project_hash})
    projeto = ler_json(buscar(url_projeto, "projeto.json"))
    project_id = validar_projeto(projeto, project_hash)
    url_rotas = API + "routes?" + urlencode({"origin": "web", "project_id": project_id})
    payload = ler_json(buscar(url_rotas, "rotas.json"))
    instante = agora()
    linhas = extrair_linhas(payload, url_rotas, catalogo, instante)
    metadados = {
        "schema_version": 1,
        "status": "sucesso",
        "coletado_em": instante,
        "url_pagina_oficial": OFICIAL,
        "url_catalogo": catalogo,
        "url_origem": url_rotas,
        "projeto": {"hash": project_hash, "id": project_id, "cidade": projeto["city"]},
        "total_registros": len(linhas),
        "cobertura": {
            "escopo": "registros retornados pelo catálogo incorporado à página oficial",
            "registros_recebidos": len(payload),
            "registros_exportados": len(linhas),
            "todos_os_registros_da_resposta_exportados": True,
            "total_declarado_pela_fonte": None,
            "paginacao": "não indicada no formato observado",
            "completude_municipal": "nao_verificada",
            "limitacao": (
                "A API retorna um array sem total declarado. A coleta integral "
                "dessa resposta não comprova todas as linhas em operação no município."
            ),
        },
        "acesso": {
            "robots": cliente.regras,
            "termos_adicionais_fornecedor": "nao_verificados",
        },
        "respostas": respostas,
    }
    return linhas, metadados, fontes


def gravar_json(caminho: Path, conteudo: object) -> None:
    caminho.write_text(json.dumps(conteudo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def exportar(
    linhas: list[dict], metadados: dict, fontes: dict[str, bytes], destino: Path
) -> Path:
    if not linhas:
        raise ErroColeta("Recusada exportação de catálogo vazio.")
    destino = destino.resolve()
    destino.mkdir(parents=True, exist_ok=True)
    pasta_final = destino / identificador_execucao()
    # Publica o diretório só após todos os arquivos serem gravados com sucesso.
    # O temporário fica dentro do destino; execuções anteriores são preservadas.
    with tempfile.TemporaryDirectory(prefix=".coleta-", dir=destino) as temporario:
        pasta = Path(temporario)
        with (pasta / "linhas.csv").open("w", encoding="utf-8-sig", newline="") as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=CAMPOS)
            escritor.writeheader()
            escritor.writerows(linhas)
        gravar_json(pasta / "linhas.json", {"metadados": metadados, "linhas": linhas})
        gravar_json(pasta / "coleta.json", metadados)
        (pasta / "fontes").mkdir()
        for nome, conteudo in fontes.items():
            if Path(nome).name != nome:
                raise ErroColeta("Nome inválido de arquivo de evidência.")
            (pasta / "fontes" / nome).write_bytes(conteudo)
        os.replace(pasta, pasta_final)
    return pasta_final


def positivo(valor: str) -> float:
    numero = float(valor)
    if not math.isfinite(numero) or numero <= 0:
        raise argparse.ArgumentTypeError("informe um número finito maior que zero")
    return numero


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saida", type=Path, default=SAIDA_PADRAO, help="diretório das execuções")
    parser.add_argument("--timeout", type=positivo, default=30.0, help="timeout HTTP em segundos")
    parser.add_argument("--intervalo", type=positivo, default=2.0, help="intervalo mínimo (>= 2 s)")
    args = parser.parse_args(argv)
    if args.intervalo < 2:
        parser.error("--intervalo deve ser pelo menos 2 segundos")
    cliente = ClientePublico(timeout=args.timeout, intervalo=args.intervalo)
    try:
        with cliente:
            linhas, metadados, fontes = coletar(cliente)
        pasta = exportar(linhas, metadados, fontes, args.saida)
    except (ErroColeta, OSError) as erro:
        print(f"Coleta interrompida: {erro}", file=sys.stderr)
        falha = {
            "status": "erro", "tentativa_em": agora(), "erro": str(erro),
            "url_pagina_oficial": OFICIAL, "robots": cliente.regras,
            "catalogo_publicado": False,
        }
        try:
            falhas = args.saida / "falhas"
            falhas.mkdir(parents=True, exist_ok=True)
            gravar_json(falhas / f"{identificador_execucao()}.json", falha)
        except OSError as erro_gravacao:
            print(f"Não foi possível salvar o diagnóstico: {erro_gravacao}", file=sys.stderr)
        return 1
    print(f"Coletados {len(linhas)} registros da resposta oficial.")
    print("Completude municipal: NÃO VERIFICADA (a fonte não declara um total).")
    print(f"CSV, JSON, metadados e respostas de origem: {pasta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
