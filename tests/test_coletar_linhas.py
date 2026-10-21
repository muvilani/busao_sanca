"""Fixtures inteiramente sintéticas; não representam linhas em operação.

Nenhum teste acessa a rede ou utiliza uma lista histórica como catálogo oficial.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import requests

import coletar_linhas as coletor
from acesso_http import ErroColeta


DATA_SINTETICA = "2026-01-01T12:34:56+00:00"
HASH_SINTETICO = "TesteSintetico9"
CATALOGO_SINTETICO = f"https://bus2.info/2you/#/{HASH_SINTETICO}"
PROJETO_SINTETICO = {
    "city": "São Carlos, SP",
    "hash": HASH_SINTETICO,
    "projectId": 876543,
}
LINHA_SINTETICA = {
    "shortName": "0007-A",
    "longName": 'Linha sintética: Estação, "Árvore" & Praça; Teste',
    "routeId": 987654,
}


def resposta(
    conteudo: bytes | str,
    *,
    url: str = "https://mobilibus.com/api/exemplo-sintetico",
    tipo: str = "application/json; charset=utf-8",
    status: int = 200,
    cabecalhos: dict | None = None,
) -> requests.Response:
    """Response real sem transporte de rede, para testar bytes e cabeçalhos."""
    resultado = requests.Response()
    resultado.status_code = status
    resultado.url = url
    resultado.encoding = "utf-8"
    resultado._content = conteudo.encode("utf-8") if isinstance(conteudo, str) else conteudo
    resultado.headers["Content-Type"] = tipo
    resultado.headers.update(cabecalhos or {})
    return resultado


def resposta_json(conteudo: object, **kwargs) -> requests.Response:
    return resposta(json.dumps(conteudo, ensure_ascii=False), **kwargs)


class ClienteSintetico:
    """Servidor em memória; URLs desconhecidas fazem o teste falhar."""

    def __init__(self, *, projeto=None, linhas=None):
        self.projeto = copy.deepcopy(projeto if projeto is not None else PROJETO_SINTETICO)
        self.linhas = copy.deepcopy(linhas if linhas is not None else [LINHA_SINTETICA])
        self.urls = []
        self.regras = [{"origem": "fixture sintética offline", "permitido": True}]
        self.respostas = []

    def obter(self, url):
        self.urls.append(url)
        partes = urlsplit(url)
        parametros = parse_qs(partes.query)
        if url == coletor.OFICIAL:
            resultado = resposta(
                f'<html><iframe src="{CATALOGO_SINTETICO}"></iframe></html>',
                url=url,
                tipo="text/html",
            )
        elif url == "https://bus2.info/2you/":
            resultado = resposta("<html>Aplicação sintética</html>", url=url, tipo="text/html")
        elif partes.path == "/api/project-details":
            if parametros != {"project_hash": [HASH_SINTETICO]}:
                raise AssertionError(f"Projeto inesperado: {url}")
            resultado = resposta_json(self.projeto, url=url)
        elif partes.path == "/api/routes":
            if parametros != {"origin": ["web"], "project_id": [str(self.projeto["projectId"])]}:
                raise AssertionError(f"O projeto descoberto não foi usado: {url}")
            resultado = resposta_json(self.linhas, url=url)
        else:
            raise AssertionError(f"Requisição inesperada: {url}")
        self.respostas.append(resultado)
        return resultado

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class DescobertaCatalogoTests(unittest.TestCase):
    def test_catalogo_deve_vir_do_iframe_da_pagina(self):
        html = f'<a href="https://exemplo.invalid/">Outro link</a><iframe src="{CATALOGO_SINTETICO}"></iframe>'
        self.assertEqual(
            coletor.descobrir_catalogo(html),
            (CATALOGO_SINTETICO, HASH_SINTETICO),
        )

    def test_recusa_pagina_sem_iframe_e_dominio_imitador(self):
        for html in (
            "<html>Catálogo indisponível</html>",
            f'<a href="{CATALOGO_SINTETICO}">Catálogo</a>',
            '<iframe src="https://bus2.info.exemplo.invalid/2you/#/Teste"></iframe>',
            '<iframe src="https://bus2.info@exemplo.invalid/2you/#/Teste"></iframe>',
        ):
            with self.subTest(html=html), self.assertRaises(ErroColeta):
                coletor.descobrir_catalogo(html)

    def test_recusa_catalogos_ambiguos_ou_endereco_alterado(self):
        for html in (
            f'<iframe src="{CATALOGO_SINTETICO}"></iframe>'
            '<iframe src="https://bus2.info/2you/#/OutroTeste"></iframe>',
            '<iframe src="http://bus2.info/2you/#/Teste"></iframe>',
            '<iframe src="https://bus2.info/novo/#/Teste"></iframe>',
            '<iframe src="https://bus2.info/2you/?cidade=outra#/Teste"></iframe>',
            '<iframe src="https://bus2.info/2you/"></iframe>',
            '<iframe src="https://[bus2.info/2you/#/Teste"></iframe>',
        ):
            with self.subTest(html=html), self.assertRaises(ErroColeta):
                coletor.descobrir_catalogo(html)

    def test_iframes_repetidos_do_mesmo_catalogo_nao_sao_ambiguos(self):
        iframe = f'<iframe src="{CATALOGO_SINTETICO}"></iframe>'
        self.assertEqual(coletor.descobrir_catalogo(iframe * 2)[1], HASH_SINTETICO)


class ValidacaoProjetoTests(unittest.TestCase):
    def test_aceita_cidade_com_acentos_e_retorna_id_da_fonte(self):
        self.assertEqual(
            coletor.validar_projeto(PROJETO_SINTETICO, HASH_SINTETICO),
            PROJETO_SINTETICO["projectId"],
        )

    def test_recusa_outra_cidade_hash_divergente_e_id_invalido(self):
        invalidos = [
            None,
            [],
            {**PROJETO_SINTETICO, "city": "Outra Cidade, SP"},
            {**PROJETO_SINTETICO, "city": "São Carlos, SC"},
            {**PROJETO_SINTETICO, "hash": "OutroHash"},
        ]
        invalidos.extend(
            {**PROJETO_SINTETICO, "projectId": valor}
            for valor in (None, True, 0, -1, 1.5, "876543")
        )
        for projeto in invalidos:
            with self.subTest(projeto=projeto), self.assertRaises(ErroColeta):
                coletor.validar_projeto(projeto, HASH_SINTETICO)


class ExtracaoLinhasTests(unittest.TestCase):
    def extrair(self, payload):
        return coletor.extrair_linhas(
            payload, "https://mobilibus.com/api/routes?fixture=1",
            CATALOGO_SINTETICO, DATA_SINTETICA,
        )

    def test_preserva_codigo_textual_zeros_acentos_e_pontuacao(self):
        linha = self.extrair([LINHA_SINTETICA])[0]
        self.assertIsInstance(linha["codigo"], str)
        self.assertEqual(linha["codigo"], "0007-A")
        self.assertEqual(linha["nome"], LINHA_SINTETICA["longName"])
        self.assertEqual(linha["coletado_em"], DATA_SINTETICA)
        self.assertEqual(linha["url_origem"], "https://mobilibus.com/api/routes?fixture=1")
        self.assertEqual(linha["url_catalogo"], CATALOGO_SINTETICO)

    def test_recusa_lista_vazia_ou_mudanca_de_schema(self):
        for payload in ([], {}, {"data": [LINHA_SINTETICA]}, None, "erro"):
            with self.subTest(payload=payload), self.assertRaises(ErroColeta):
                self.extrair(payload)

    def test_um_registro_invalido_interrompe_o_catalogo_inteiro(self):
        invalidos = [None, [], {}, {"shortName": "001", "longName": "Teste"}]
        invalidos.extend(
            {**LINHA_SINTETICA, campo: valor}
            for campo in ("shortName", "longName")
            for valor in (None, 7, "", "   ", "Teste\nOutro", "Teste\ufffd")
        )
        invalidos.extend(
            {**LINHA_SINTETICA, "routeId": valor}
            for valor in (None, True, 0, -1, 1.5, "987654")
        )
        for registro in invalidos:
            with self.subTest(registro=registro), self.assertRaises(ErroColeta):
                self.extrair([LINHA_SINTETICA, registro])

    def test_recusa_duplicacao_de_codigo_ou_id_sem_descartar_silenciosamente(self):
        duplicatas = (
            {**LINHA_SINTETICA},
            {**LINHA_SINTETICA, "routeId": 111111},
            {**LINHA_SINTETICA, "shortName": "0008"},
            {**LINHA_SINTETICA, "shortName": " 0007-A ", "routeId": 111111},
        )
        for duplicata in duplicatas:
            with self.subTest(duplicata=duplicata), self.assertRaises(ErroColeta):
                self.extrair([LINHA_SINTETICA, duplicata])


class LeituraJsonTests(unittest.TestCase):
    def test_le_json_utf8_inclusive_bom(self):
        conteudo = b"\xef\xbb\xbf" + json.dumps(
            [LINHA_SINTETICA], ensure_ascii=False
        ).encode("utf-8")
        self.assertEqual(coletor.ler_json(resposta(conteudo)), [LINHA_SINTETICA])

    def test_recusa_html_json_invalido_codificacao_e_http_parcial(self):
        casos = [
            resposta("<html>Erro do servidor</html>", tipo="text/html"),
            resposta("<html>Erro com cabeçalho JSON</html>"),
            resposta('{"incompleto":'),
            resposta(b"\xff"),
            resposta("[]", status=206),
            resposta("[]", status=503),
        ]
        for caso in casos:
            with self.subTest(status=caso.status_code, conteudo=caso.content), self.assertRaises(ErroColeta):
                coletor.ler_json(caso)

    def test_recusa_indicadores_de_paginacao_ou_intervalo_parcial(self):
        for cabecalhos in (
            {"Content-Range": "items 0-9/100"},
            {"Link": '<https://exemplo.invalid/?page=2>; rel="next"'},
            {"Link": "<https://exemplo.invalid/?page=2>; rel=next"},
            {"Link": '<https://exemplo.invalid/?page=2>; REL="NEXT"'},
            {"Link": '<https://exemplo.invalid/?page=2>; rel="alternate next"'},
        ):
            with self.subTest(cabecalhos=cabecalhos), self.assertRaises(ErroColeta):
                coletor.ler_json(resposta("[]", cabecalhos=cabecalhos))


class PipelineTests(unittest.TestCase):
    def test_projeto_dinamico_e_cobertura_honesta_mesmo_com_um_registro(self):
        projeto = {**PROJETO_SINTETICO, "projectId": 7654321}
        cliente = ClienteSintetico(projeto=projeto)
        with patch.object(coletor, "agora", return_value=DATA_SINTETICA):
            linhas, metadados, fontes = coletor.coletar(cliente)

        self.assertEqual(len(linhas), 1)
        url_rotas = next(url for url in cliente.urls if urlsplit(url).path == "/api/routes")
        self.assertEqual(parse_qs(urlsplit(url_rotas).query)["project_id"], ["7654321"])
        self.assertFalse(any(urlsplit(url).fragment for url in cliente.urls))
        self.assertEqual(linhas[0]["url_origem"], url_rotas)
        self.assertEqual(metadados["total_registros"], 1)
        cobertura = metadados["cobertura"]
        self.assertEqual(cobertura["completude_municipal"], "nao_verificada")
        self.assertIsNone(cobertura["total_declarado_pela_fonte"])
        self.assertEqual(cobertura["registros_recebidos"], len(linhas))
        self.assertEqual(cobertura["registros_exportados"], len(linhas))
        self.assertEqual(metadados["coletado_em"], linhas[0]["coletado_em"])
        self.assertEqual(len(fontes), len(cliente.respostas))
        for evidencia in metadados["respostas"]:
            nome = Path(evidencia["arquivo"]).name
            original = next(r for r in cliente.respostas if r.url == evidencia["url"])
            self.assertEqual(fontes[nome], original.content)
            self.assertEqual(evidencia["sha256"], hashlib.sha256(original.content).hexdigest())

    def test_nao_completa_resposta_com_catalogo_historico_local(self):
        with tempfile.TemporaryDirectory() as temporario:
            destino = Path(temporario)
            historico = destino / "execucao-anterior"
            historico.mkdir()
            anterior = {"codigo": "HISTORICO-SINTETICO", "nome": "Somente fixture antiga"}
            (historico / "linhas.json").write_text(
                json.dumps({"linhas": [anterior]}), encoding="utf-8"
            )
            with patch.object(coletor, "SAIDA_PADRAO", destino):
                linhas, metadados, _ = coletor.coletar(ClienteSintetico())
            self.assertEqual([linha["codigo"] for linha in linhas], ["0007-A"])
            self.assertEqual(metadados["cobertura"]["registros_exportados"], 1)

    def test_projeto_de_outra_cidade_interrompe_antes_de_obter_rotas(self):
        cliente = ClienteSintetico(projeto={**PROJETO_SINTETICO, "city": "Outra Cidade, SP"})
        with self.assertRaises(ErroColeta):
            coletor.coletar(cliente)
        self.assertFalse(any(urlsplit(url).path == "/api/routes" for url in cliente.urls))


class ExportacaoTests(unittest.TestCase):
    def dados(self):
        with patch.object(coletor, "agora", return_value=DATA_SINTETICA):
            return coletor.coletar(ClienteSintetico())

    def test_csv_e_json_equivalentes_e_fontes_brutas_verificaveis(self):
        linhas, metadados, fontes = self.dados()
        with tempfile.TemporaryDirectory() as temporario:
            pasta = coletor.exportar(linhas, metadados, fontes, Path(temporario))
            with (pasta / "linhas.csv").open(encoding="utf-8-sig", newline="") as arquivo:
                csv_linhas = list(csv.DictReader(arquivo))
            json_catalogo = json.loads((pasta / "linhas.json").read_text(encoding="utf-8"))
            json_metadados = json.loads((pasta / "coleta.json").read_text(encoding="utf-8"))
            self.assertEqual(json_catalogo["linhas"], linhas)
            self.assertEqual(json_catalogo["metadados"], json_metadados)
            self.assertEqual(json_metadados, metadados)
            # O CSV é textual; converter somente o identificador permite comparar
            # todos os campos sem transformar o código e perder os zeros iniciais.
            for linha in csv_linhas:
                linha["id_linha"] = int(linha["id_linha"])
            self.assertEqual(csv_linhas, json_catalogo["linhas"])
            self.assertEqual(csv_linhas[0]["codigo"], "0007-A")
            self.assertEqual(csv_linhas[0]["nome"], LINHA_SINTETICA["longName"])
            self.assertEqual(csv_linhas[0]["coletado_em"], DATA_SINTETICA)
            for evidencia in metadados["respostas"]:
                conteudo = (pasta / evidencia["arquivo"]).read_bytes()
                self.assertEqual(conteudo, fontes[Path(evidencia["arquivo"]).name])
                self.assertEqual(hashlib.sha256(conteudo).hexdigest(), evidencia["sha256"])

    def test_falha_de_gravacao_ou_publicacao_preserva_anterior_sem_execucao_parcial(self):
        linhas, metadados, fontes = self.dados()
        gravar_real = coletor.gravar_json

        def falhar_metadados(caminho, conteudo):
            if caminho.name == "coleta.json":
                raise OSError("Falha sintética de disco")
            gravar_real(caminho, conteudo)

        for fase in ("metadados", "publicacao"):
            with self.subTest(fase=fase), tempfile.TemporaryDirectory() as temporario:
                destino = Path(temporario)
                anterior = destino / "execucao-anterior"
                anterior.mkdir()
                (anterior / "linhas.json").write_bytes(b'{"fixture": "preservar"}\n')
                estado_anterior = {
                    p.relative_to(destino): p.read_bytes()
                    for p in destino.rglob("*") if p.is_file()
                }
                alvo = "gravar_json" if fase == "metadados" else "os.replace"
                efeito = falhar_metadados if fase == "metadados" else OSError("Falha sintética de publicação")
                with patch.object(coletor, "identificador_execucao", return_value="nova-execucao"):
                    with patch(f"coletar_linhas.{alvo}", side_effect=efeito):
                        with self.assertRaises(OSError):
                            coletor.exportar(linhas, metadados, fontes, destino)
                self.assertEqual(
                    {p.relative_to(destino): p.read_bytes() for p in destino.rglob("*") if p.is_file()},
                    estado_anterior,
                )
                self.assertEqual(list(destino.iterdir()), [anterior])

    def test_exportacao_vazia_nao_cria_catalogo(self):
        with tempfile.TemporaryDirectory() as temporario:
            destino = Path(temporario) / "nova-pasta"
            with self.assertRaises(ErroColeta):
                coletor.exportar([], {}, {}, destino)
            self.assertFalse(destino.exists())

    def test_colisao_de_identificador_nao_sobrescreve_catalogo_anterior(self):
        linhas, metadados, fontes = self.dados()
        with tempfile.TemporaryDirectory() as temporario:
            destino = Path(temporario)
            anterior = destino / "mesma-execucao"
            anterior.mkdir()
            preservado = anterior / "linhas.json"
            conteudo_anterior = b'{"fixture": "anterior"}\n'
            preservado.write_bytes(conteudo_anterior)
            with patch.object(coletor, "identificador_execucao", return_value="mesma-execucao"):
                with self.assertRaises((OSError, ErroColeta)):
                    coletor.exportar(linhas, metadados, fontes, destino)
            self.assertEqual(preservado.read_bytes(), conteudo_anterior)
            self.assertEqual(list(anterior.iterdir()), [preservado])
            self.assertEqual(list(destino.iterdir()), [anterior])


class CliTests(unittest.TestCase):
    def test_falha_retorna_um_salva_diagnostico_e_nao_publica_catalogo(self):
        cliente = ClienteSintetico()
        with tempfile.TemporaryDirectory() as temporario:
            destino = Path(temporario) / "saida"
            stderr = io.StringIO()
            with patch.object(coletor, "ClientePublico", return_value=cliente):
                with patch.object(coletor, "coletar", side_effect=ErroColeta("Fixture: acesso recusado")):
                    with redirect_stderr(stderr):
                        resultado = coletor.main(["--saida", str(destino)])
            self.assertEqual(resultado, 1)
            self.assertIn("Coleta interrompida", stderr.getvalue())
            self.assertIn("acesso recusado", stderr.getvalue())
            diagnosticos = list((destino / "falhas").glob("*.json"))
            self.assertEqual(len(diagnosticos), 1)
            diagnostico = json.loads(diagnosticos[0].read_text(encoding="utf-8"))
            self.assertEqual(diagnostico["status"], "erro")
            self.assertFalse(diagnostico["catalogo_publicado"])
            self.assertEqual(diagnostico["robots"], cliente.regras)
            self.assertFalse(list(destino.rglob("linhas.csv")))
            self.assertFalse(list(destino.rglob("linhas.json")))


if __name__ == "__main__":
    unittest.main()
