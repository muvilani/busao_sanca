"""Testes sintéticos do pipeline; não acessam a rede nem usam dados reais."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline_mvp import (
    ErroPipeline, executar, publicar_resultado, registrar_falha, selecionar_linhas,
)
from tests.test_processar_horarios import resposta as resposta_horarios
from tests.test_processar_itinerarios import resposta as resposta_itinerario


def catalogo():
    return {
        "metadados": {
            "projeto": {"id": 317, "hash": "sintetico", "cidade": "Cidade sintética"},
            "url_pagina_oficial": "https://example.test/oficial",
            "url_catalogo": "https://example.test/catalogo",
        },
        "linhas": [{"codigo": "T-01", "nome": "Linha sintética", "id_linha": 9001}],
    }


class Resposta:
    def __init__(self, payload):
        self.content = json.dumps(payload).encode()


class Cliente:
    def __init__(self, *, itinerario=None):
        self.urls = []
        self.itinerario = itinerario or resposta_itinerario()

    def obter(self, url):
        self.urls.append(url)
        return Resposta(self.itinerario if "trip-details" in url else resposta_horarios())


class PipelineTests(unittest.TestCase):
    def test_pipeline_completo_relaciona_e_deduplica(self):
        cliente = Cliente()
        resultado = executar(catalogo(), ["T-01", "T-01"], cliente)
        self.assertTrue(resultado["cobertura"]["completa_no_escopo_solicitado"])
        self.assertEqual(len(resultado["linhas"]), 1)
        self.assertEqual(resultado["linhas"][0]["itinerarios"][0]["id_viagem"], 701)
        self.assertEqual(sum("trip-details" in url for url in cliente.urls), 1)

    def test_linha_ausente_impede_requisicoes(self):
        cliente = Cliente()
        with self.assertRaisesRegex(ErroPipeline, "não encontradas"):
            executar(catalogo(), ["X"], cliente)
        self.assertEqual(cliente.urls, [])

    def test_identidade_divergente_e_rejeitada(self):
        cliente = Cliente()
        original = resposta_horarios
        class Divergente(Cliente):
            def obter(self, url):
                payload = self.itinerario if "trip-details" in url else original()
                if "timetable" in url:
                    payload["shortName"] = "OUTRA"
                return Resposta(payload)
        with self.assertRaisesRegex(ErroPipeline, "identidade divergente"):
            executar(catalogo(), ["T-01"], Divergente())

    def test_json_invalido_nao_e_aceito(self):
        class Invalido(Cliente):
            def obter(self, url):
                resposta = Resposta({})
                resposta.content = b"{"
                return resposta
        with self.assertRaisesRegex(ErroPipeline, "JSON UTF-8"):
            executar(catalogo(), ["T-01"], Invalido())

    def test_publicacao_preserva_execucoes_e_atualiza_web(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            dados = {"status": "sucesso"}
            primeiro = publicar_resultado(dados, raiz / "saida", raiz / "web" / "dados.json")
            segundo = publicar_resultado(dados, raiz / "saida", raiz / "web" / "dados.json")
            self.assertTrue(primeiro.exists() and segundo.exists())
            self.assertNotEqual(primeiro.parent, segundo.parent)
            self.assertEqual(json.loads((raiz / "web" / "dados.json").read_text()), dados)

    def test_selecao_vazia_e_rejeitada(self):
        with self.assertRaisesRegex(ErroPipeline, "ao menos uma"):
            selecionar_linhas(catalogo(), [])

    def test_falha_e_registrada_sem_publicar_dataset(self):
        with tempfile.TemporaryDirectory() as pasta:
            base = Path(pasta)
            destino = registrar_falha(base, ["T-01"], ErroPipeline("sintético"))
            registro = json.loads(destino.read_text(encoding="utf-8"))
            self.assertEqual(registro["status"], "falha")
            self.assertFalse(registro["dataset_publicado"])


if __name__ == "__main__":
    unittest.main()
