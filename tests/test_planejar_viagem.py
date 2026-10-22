"""Testes inteiramente sintéticos para o planejador conservador."""

from __future__ import annotations

import unittest

from planejar_viagem import analisar_linha, distancia_linha_reta, melhor_par_ordenado, origem_itinerario, partidas_de_terminal, planejar_texto, relatorio_origens, sugerir_locais


def parada(ordem, lat, lon, nome):
    return {"ordem": ordem, "latitude": lat, "longitude": lon, "nome": nome, "id_parada": ordem}


def linha_sintetica():
    servico = {"id_servico": 1, "descricao": "Dias sintéticos", "vigencia_inicio": "2026-10-01", "vigencia_fim": "2026-10-31", "partidas": [{"id_viagem": 10, "saida": "17:30", "chegada": "18:30"}]}
    return {
        "horarios": {
            "variantes": [{"id_viagem": 10, "id_direcao": 0, "destino": "Sul"}, {"id_viagem": 20, "id_direcao": 1, "destino": "Norte"}],
            "direcoes": [{"id_direcao": 0, "descricao": "Ida", "servicos": [servico]}, {"id_direcao": 1, "descricao": "Volta", "servicos": []}],
        },
        "itinerarios": [
            {"id_viagem": 10, "paradas": [parada(1, 0, 0, "A"), parada(2, 0, .01, "B")], "geometria": {"validacao": {"extremidades_compativeis": True}}},
            {"id_viagem": 20, "paradas": [parada(1, 0, .01, "B"), parada(2, 0, 0, "A")], "geometria": {"validacao": {"extremidades_compativeis": True}}},
        ],
    }


def dataset_textual():
    linha = linha_sintetica()
    linha["catalogo"] = {"codigo": "10", "nome": "Centro x Sul"}
    linha["cobertura"] = {"completa_no_escopo_solicitado": True}
    linha["itinerarios"][0]["paradas"] = [parada(1, 0, 0, "São João"), parada(2, 0, .01, "Centro"), parada(3, 0, .02, "Vila Sul")]
    linha["itinerarios"][1]["paradas"] = [parada(1, 0, .02, "Vila Sul"), parada(2, 0, .01, "Centro"), parada(3, 0, 0, "São João")]
    return {"linhas": [linha]}


class PlanejamentoTests(unittest.TestCase):
    def test_busca_textual_tolera_acentos_e_caixa(self):
        sugestoes = sugerir_locais(dataset_textual(), "sao joao")
        self.assertEqual(sugestoes[0]["nome"], "São João")

    def test_planejamento_textual_respeita_sentido_e_ordem(self):
        resultado = planejar_texto(dataset_textual(), "SÃO JOÃO", "vila sul")
        self.assertEqual(resultado["status"], "sucesso")
        self.assertEqual(resultado["resultados"][0]["sentido"], "Ida")
        self.assertLess(resultado["resultados"][0]["embarque"]["ordem"], resultado["resultados"][0]["desembarque"]["ordem"])

    def test_linha_54_incompleta_e_excluida(self):
        dados = dataset_textual()
        linha = dict(dados["linhas"][0])
        linha["catalogo"] = {"codigo": "54", "nome": "Indisponível"}
        dados["linhas"] = [linha]
        self.assertEqual(planejar_texto(dados, "São João", "Vila Sul")["status"], "sem_rota")

    def test_sem_rota_explica_limitacao(self):
        resultado = planejar_texto(dataset_textual(), "Aeroporto", "Vila Sul")
        self.assertEqual(resultado["status"], "sem_rota")
        self.assertTrue(resultado["motivo"])

    def test_conexao_so_usa_parada_compartilhada_e_ordem_valida(self):
        dados = dataset_textual()
        segunda = linha_sintetica()
        segunda["catalogo"] = {"codigo": "11", "nome": "Sul x Norte"}
        segunda["cobertura"] = {"completa_no_escopo_solicitado": True}
        segunda["itinerarios"] = [{"id_viagem": 30, "paradas": [parada(1, 0, .02, "Vila Sul"), parada(2, 0, .03, "Norte")], "geometria": {"validacao": {"extremidades_compativeis": True}}}]
        segunda["horarios"]["variantes"] = [{"id_viagem": 30, "id_direcao": 0, "destino": "Norte"}]
        dados["linhas"].append(segunda)
        resultado = planejar_texto(dados, "São João", "Norte")
        self.assertEqual(resultado["status"], "sucesso")
        self.assertEqual(resultado["resultados"][0]["tipo"], "conexao")
        self.assertEqual(resultado["resultados"][0]["transferencia"]["nome"], "Vila Sul")

    def test_embarque_sempre_precede_desembarque(self):
        rota = linha_sintetica()["itinerarios"][0]
        resultado = melhor_par_ordenado(rota, {"latitude": 0, "longitude": 0}, {"latitude": 0, "longitude": .01})
        self.assertLess(resultado["embarque"]["ordem"], resultado["desembarque"]["ordem"])

    def test_sentidos_nao_sao_confundidos(self):
        ponto_a = {"latitude": 0, "longitude": 0, "precisao": "endereco"}
        ponto_b = {"latitude": 0, "longitude": .01, "precisao": "endereco"}
        resultados = analisar_linha(linha_sintetica(), ponto_a, ponto_b, limite_caminhada_m=100)
        self.assertEqual(resultados[0]["id_viagem"], 10)
        self.assertEqual(resultados[0]["direcao"], "Ida")

    def test_distancia_geografica_haversine(self):
        distancia = distancia_linha_reta({"latitude": 0, "longitude": 0}, {"latitude": 0, "longitude": 1})
        self.assertAlmostEqual(distancia, 111_195, delta=100)

    def test_baixa_precisao_nao_e_confirmada(self):
        origem = {"latitude": 0, "longitude": 0, "precisao": "centroide_cep"}
        destino = {"latitude": 0, "longitude": .01, "precisao": "via"}
        self.assertEqual(analisar_linha(linha_sintetica(), origem, destino)[0]["status"], "candidata_nao_verificada")

    def test_horario_fora_da_vigencia_nao_e_exibido(self):
        horarios = linha_sintetica()["horarios"]
        self.assertEqual(partidas_de_terminal(horarios, 10, "2026-11-01", "17:00", "18:00"), [])
        validos = partidas_de_terminal(horarios, 10, "2026-10-21", "17:00", "18:00")
        self.assertEqual(validos[0]["saida_terminal"], "17:30")
        self.assertFalse(validos[0]["horario_passagem_confirmado"])

    def test_origem_e_a_primeira_parada_sem_confirmar_terminal(self):
        dados = dataset_textual()["linhas"][0]
        origem = origem_itinerario(dados["itinerarios"][0], dados["horarios"])
        self.assertEqual(origem["nome"], "São João")
        self.assertTrue(origem["coordenadas_validas"])
        self.assertFalse(origem["ponto_oficial_partida_confirmado"])

    def test_relatorio_de_origens_diferencia_vinculo_e_confirmacao(self):
        relatorio = relatorio_origens(dataset_textual())
        self.assertEqual(relatorio["itinerarios"], 2)
        self.assertEqual(relatorio["origens_identificadas"], 2)
        self.assertEqual(relatorio["origens_com_coordenadas"], 2)
        self.assertEqual(relatorio["correspondencias_confirmadas_com_ponto_oficial"], 0)


if __name__ == "__main__":
    unittest.main()
