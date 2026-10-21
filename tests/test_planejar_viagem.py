"""Testes inteiramente sintéticos para o planejador conservador."""

from __future__ import annotations

import unittest

from planejar_viagem import analisar_linha, distancia_linha_reta, melhor_par_ordenado, partidas_de_terminal


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


class PlanejamentoTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
