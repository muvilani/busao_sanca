from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from coletar_lotes import classificar_catalogo, descobrir_linhas_validas, linha_valida
from consolidar_datasets import consolidar


def linha(codigo="01", trip=10, completa=True):
    return {
        "catalogo": {"codigo": codigo, "nome": "Sintética", "id_linha": 1},
        "horarios": {"variantes": [{"id_viagem": trip}]},
        "itinerarios": [{"id_viagem": trip, "paradas": [{}, {}], "geometria": {"validacao": {}}}],
        "cobertura": {"completa_no_escopo_solicitado": completa},
    }


class LotesTests(unittest.TestCase):
    def test_linha_com_itinerario_invalido_nao_e_reutilizada(self):
        self.assertFalse(linha_valida(linha(completa=False)))
        quebrada = {**linha(), "itinerarios": [{"id_viagem": 10, "paradas": [{}], "geometria": {"validacao": {}}}]}
        self.assertFalse(linha_valida(quebrada))

    def test_classificacao_distingue_validada_falha_e_pendente(self):
        with tempfile.TemporaryDirectory() as pasta:
            base = Path(pasta)
            (base / "ok").mkdir()
            (base / "ok" / "dados.json").write_text(json.dumps({"status": "sucesso", "linhas": [linha("01")] }))
            (base / "falhas").mkdir()
            (base / "falhas" / "x.json").write_text(json.dumps({"linhas_solicitadas": ["02"], "status": "falha"}))
            catalogo = {"linhas": [{"codigo": c} for c in ["01", "02", "03"]]}
            esperado = {"validadas": ["01"], "com_falhas": ["02"], "nao_coletadas": ["03"]}
            self.assertEqual(classificar_catalogo(catalogo, base), esperado)

    def test_consolidacao_preserva_cobertura_incompleta(self):
        with tempfile.TemporaryDirectory() as pasta:
            base = Path(pasta)
            (base / "ok").mkdir()
            (base / "ok" / "dados.json").write_text(json.dumps({"status": "sucesso", "linhas": [linha("01")] }))
            catalogo = {"metadados": {"projeto": {"id": 1}}, "linhas": [{"codigo": "01"}, {"codigo": "02"}]}
            destino = base / "consolidado.json"
            resultado = consolidar(catalogo, base, destino)
            self.assertFalse(resultado["cobertura"]["completa"])
            self.assertEqual(resultado["classificacao"]["nao_coletadas"], ["02"])
            self.assertTrue(destino.exists())

    def test_falha_de_lote_antiga_nao_inventa_falhas_por_linha(self):
        with tempfile.TemporaryDirectory() as pasta:
            base = Path(pasta)
            (base / "falhas").mkdir()
            (base / "falhas" / "lote.json").write_text(json.dumps({"linhas_solicitadas": ["52", "53", "54"]}))
            catalogo = {"linhas": [{"codigo": c} for c in ["52", "53", "54"]]}
            self.assertEqual(classificar_catalogo(catalogo, base)["com_falhas"], [])
            self.assertEqual(classificar_catalogo(catalogo, base)["nao_coletadas"], ["52", "53", "54"])

    def test_reconhece_arquivo_por_linha_produzido_pela_coleta_incremental(self):
        with tempfile.TemporaryDirectory() as pasta:
            base = Path(pasta) / "lotes" / "execucao" / "linhas"
            base.mkdir(parents=True)
            (base / "52.json").write_text(json.dumps({"status": "sucesso", "linhas": [linha("52")] }))
            self.assertEqual(sorted(descobrir_linhas_validas(Path(pasta))), ["52"])


if __name__ == "__main__":
    unittest.main()
