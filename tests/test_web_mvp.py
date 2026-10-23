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

    def test_planejador_experimental_expoe_limitacoes(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        js = (WEB / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="planejador"', html)
        self.assertIn("candidata não verificada", js)
        self.assertIn("Não há horário confirmado de passagem", js)
        self.assertIn("linha reta", js)

    def test_interface_aceita_dataset_parcial_e_sinaliza_falhas(self):
        js = (WEB / "app.js").read_text(encoding="utf-8")
        self.assertIn("Dados locais parciais; linhas indisponíveis não são exibidas", js)
        self.assertIn("dataset.classificacao?.com_falhas", js)
        self.assertIn("Array.isArray(dataset.linhas)", js)

    def test_interface_usa_data_do_consolidado_sem_invalid_date(self):
        js = (WEB / "app.js").read_text(encoding="utf-8")
        self.assertIn("dataset.coletado_em || dataset.consolidado_em", js)
        self.assertIn("data não informada", js)
        self.assertNotIn("new Date(dataset.coletado_em).toLocaleString", js)

    def test_interface_expoe_planejador_textual(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        planner = (WEB / "planejador.js").read_text(encoding="utf-8")
        self.assertIn('id="origem-rota"', html)
        self.assertIn('id="destino-rota"', html)
        self.assertIn('id="buscar-rota"', html)
        self.assertIn("window.BusaoPlanner", planner)
        self.assertIn("horario_passagem_confirmado: false", planner)
        self.assertIn('catalogo.codigo === "54"', planner)

    def test_interface_exibe_primeira_parada_e_mapa(self):
        js = (WEB / "app.js").read_text(encoding="utf-8")
        css = (WEB / "planner.css").read_text(encoding="utf-8")
        self.assertIn("Primeira parada cadastrada", js)
        self.assertIn("O ponto oficial de partida não foi confirmado", js)
        self.assertIn("openstreetmap.org", js)
        self.assertIn("origem-viagem", css)

    def test_interface_expoe_consulta_de_paradas_e_geolocalizacao(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        js = (WEB / "paradas.js").read_text(encoding="utf-8")
        self.assertIn('id="usar-localizacao"', html)
        self.assertIn('id="busca-parada"', html)
        self.assertIn("navigator.geolocation", js)
        self.assertIn("Permissão negada", js)
        self.assertIn("linha reta", html)
        self.assertIn("window.BusaoStops", js)

    def test_consulta_preserva_distincao_de_partida_e_passagem(self):
        js = (WEB / "paradas.js").read_text(encoding="utf-8")
        self.assertIn("saídas na origem da viagem", js)
        self.assertIn("não horários de passagem nesta parada", js)

    def test_consulta_de_parada_filtra_vigencia_e_mantem_incerteza(self):
        js = (WEB / "paradas.js").read_text(encoding="utf-8")
        self.assertIn("function partidasNaVigencia", js)
        self.assertIn("vigencia_inicio <= dataSelecionada", js)
        self.assertIn("dataSelecionada <= partida.vigencia_fim", js)
        self.assertIn("A data considera somente a vigência declarada", js)
        self.assertIn("A operação nesse dia não pode ser confirmada", js)
        self.assertIn("nenhuma partida com vigência compatível", js)

    def test_selecao_de_parada_e_atualizada_quando_data_muda(self):
        js = (WEB / "paradas.js").read_text(encoding="utf-8")
        self.assertIn("let paradaSelecionada = null", js)
        self.assertIn("paradaSelecionada = parada", js)
        self.assertIn('data?.addEventListener("change"', js)
        self.assertIn("selecionar(paradaSelecionada)", js)

    def test_geolocalizacao_permitida_ordena_e_exibe_resultados(self):
        js = (WEB / "paradas.js").read_text(encoding="utf-8")
        self.assertIn("navigator.geolocation.getCurrentPosition", js)
        self.assertIn("pos.coords.latitude", js)
        self.assertIn("pos.coords.longitude", js)
        self.assertIn("Localização usada somente nesta tela", js)
        self.assertIn("enableHighAccuracy: false", js)

    def test_geolocalizacao_negada_oferece_busca_manual(self):
        js = (WEB / "paradas.js").read_text(encoding="utf-8")
        self.assertIn('1: "Permissão negada."', js)
        self.assertIn("Use a busca manual", js)

    def test_geolocalizacao_indisponivel_oferece_busca_manual(self):
        js = (WEB / "paradas.js").read_text(encoding="utf-8")
        self.assertIn("if (!navigator.geolocation)", js)
        self.assertIn("Este navegador não oferece geolocalização", js)
        self.assertIn('2: "Localização indisponível."', js)


if __name__ == "__main__":
    unittest.main()
