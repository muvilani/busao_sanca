"""Verificações estruturais da interface buildless do MVP."""

from __future__ import annotations

import unittest
from pathlib import Path


WEB = Path(__file__).resolve().parents[1] / "web"


class WebMvpTests(unittest.TestCase):
    def test_arquivos_essenciais_existem(self):
        for nome in ("index.html", "styles.css", "app.js"):
            self.assertTrue((WEB / nome).is_file(), nome)

    def test_interface_esta_em_portugues_e_mobile_first(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn('lang="pt-BR"', html)
        self.assertIn('name="viewport"', html)
        self.assertIn("Linha, nome ou destino", html)

    def test_interface_nao_confunde_partida_com_chegada_na_parada(self):
        js = (WEB / "app.js").read_text(encoding="utf-8")
        self.assertIn("não são previsão de chegada às paradas", js)
        self.assertIn("ordem do vetor semanal", (WEB / "index.html").read_text(encoding="utf-8"))

    def test_dados_reais_nao_estao_versionados(self):
        ignore = (WEB.parent / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("web/dados.json", ignore)


if __name__ == "__main__":
    unittest.main()
