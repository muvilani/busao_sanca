import json
import tempfile
import unittest
from pathlib import Path

import preparar_publicacao


class PublicacaoTests(unittest.TestCase):
    def test_fixture_e_exclusivamente_sintetico(self):
        dados = preparar_publicacao.carregar_fixture()
        self.assertIs(dados["demonstracao"]["sintetico"], True)
        self.assertEqual([linha["catalogo"]["codigo"] for linha in dados["linhas"]], ["D1"])
        self.assertIn("fict", json.dumps(dados, ensure_ascii=False).casefold())
        serializado = json.dumps(dados, ensure_ascii=False)
        self.assertNotIn("São Carlos", serializado)
        self.assertNotIn("StepWise", serializado)

    def test_prepara_assets_atuais_sem_copiar_dataset_privado(self):
        with tempfile.TemporaryDirectory() as temporario:
            destino = Path(temporario) / "dist"
            manifesto = preparar_publicacao.preparar(destino)
            self.assertIs(manifesto["dados_sinteticos"], True)
            self.assertEqual(set(preparar_publicacao.ASSETS), {p.name for p in destino.iterdir()} - {"dados.json", "manifesto.json"})
            self.assertEqual((destino / "paradas.js").read_bytes(), (preparar_publicacao.WEB / "paradas.js").read_bytes())
            dados = json.loads((destino / "dados.json").read_text(encoding="utf-8"))
            self.assertIs(dados["demonstracao"]["sintetico"], True)
            self.assertEqual(dados, preparar_publicacao.carregar_fixture())

    def test_recusa_fixture_sem_marcacao_sintetica(self):
        with tempfile.TemporaryDirectory() as temporario:
            fixture = Path(temporario) / "dados.json"
            fixture.write_text('{"status":"sucesso","linhas":[]}', encoding="utf-8")
            with self.assertRaisesRegex(preparar_publicacao.ErroPublicacao, "somente fixture"):
                preparar_publicacao.carregar_fixture(fixture)

    def test_lista_de_assets_nao_inclui_dados_reais(self):
        self.assertNotIn("dados.json", preparar_publicacao.ASSETS)
        self.assertFalse(any("saida" in nome or "dados" in nome for nome in preparar_publicacao.ASSETS))

    def test_recusa_destinos_de_dados_locais(self):
        for destino in (
            preparar_publicacao.WEB,
            preparar_publicacao.RAIZ / "saida" / "publicacao",
            preparar_publicacao.RAIZ / "dados" / "publicacao",
            preparar_publicacao.RAIZ / "site" / "dist",
        ):
            with self.subTest(destino=destino), self.assertRaisesRegex(
                preparar_publicacao.ErroPublicacao, "destino protegido"
            ):
                preparar_publicacao.preparar(destino)

    def test_recusa_residuos_inesperados_no_destino(self):
        with tempfile.TemporaryDirectory() as temporario:
            destino = Path(temporario) / "dist"
            destino.mkdir()
            (destino / "privado.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(preparar_publicacao.ErroPublicacao, "arquivos inesperados"):
                preparar_publicacao.preparar(destino)

    def test_recusa_sobrescrever_dados_sem_marcacao_sintetica(self):
        with tempfile.TemporaryDirectory() as temporario:
            destino = Path(temporario) / "dist"
            destino.mkdir()
            (destino / "dados.json").write_text('{"status":"sucesso"}', encoding="utf-8")
            with self.assertRaisesRegex(preparar_publicacao.ErroPublicacao, "recusa sobrescrever"):
                preparar_publicacao.preparar(destino)


if __name__ == "__main__":
    unittest.main()
