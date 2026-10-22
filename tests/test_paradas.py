import unittest

from paradas import (
    atendimentos_da_parada,
    construir_indice_paradas,
    coordenada_valida,
    paradas_proximas,
)


def dataset_teste():
    return {
        "linhas": [
            {
                "catalogo": {"codigo": "10", "nome": "Centro"},
                "horarios": {
                    "linha": {"codigo": "10", "nome": "Centro"},
                    "direcoes": [{
                        "id_direcao": 1, "descricao": "Centro", "servicos": [{
                            "descricao": "Dias úteis", "partidas": [{"id_viagem": 100, "saida": "07:00"}]
                        }]
                    }],
                    "variantes": [{"id_viagem": 100, "id_direcao": 1, "sequencia_origem": 1, "destino": "Centro"}],
                },
                "itinerarios": [{"id_viagem": 100, "paradas": [
                    {"id_parada": 1, "nome": "Terminal", "latitude": -22.01, "longitude": -47.89},
                    {"id_parada": 2, "nome": "Centro", "latitude": -22.02, "longitude": -47.89},
                ]}],
            },
            {
                "catalogo": {"codigo": "20", "nome": "Bairro"},
                "horarios": {
                    "linha": {"codigo": "20", "nome": "Bairro"},
                    "direcoes": [{"id_direcao": 2, "descricao": "Bairro", "servicos": []}],
                    "variantes": [{"id_viagem": 200, "id_direcao": 2, "sequencia_origem": 1, "destino": "Bairro"}],
                },
                "itinerarios": [{"id_viagem": 200, "paradas": [
                    {"id_parada": 1, "nome": "Terminal", "latitude": -22.01, "longitude": -47.89},
                    {"id_parada": 3, "nome": "Terminal", "latitude": -22.03, "longitude": -47.90},
                ]}],
            },
        ]
    }


class ParadasTests(unittest.TestCase):
    def test_deduplica_por_id_sem_unir_nomes_iguais(self):
        indice = construir_indice_paradas(dataset_teste())
        self.assertEqual(len(indice["paradas"]), 3)
        terminal = [p for p in indice["paradas"] if p["id_parada"] == 1][0]
        self.assertEqual(set(terminal["linhas"]), {"10", "20"})

    def test_associa_linha_sentido_variante_trip_e_partida(self):
        indice = construir_indice_paradas(dataset_teste())
        atendimento = atendimentos_da_parada(indice, "id:2")[0]
        self.assertEqual((atendimento["codigo_linha"], atendimento["sentido"], atendimento["variante"]), ("10", "Centro", 1))
        self.assertEqual(atendimento["id_viagem"], 100)
        self.assertEqual(atendimento["partidas"][0]["saida"], "07:00")
        self.assertEqual(atendimento["ordem"], 2)

    def test_proximidade_ignora_coordenada_invalida_e_ordena(self):
        indice = construir_indice_paradas(dataset_teste())
        indice["paradas"].append({"chave": "invalida", "nome": "Invalida", "latitude": 999, "longitude": 999, "atendimentos": []})
        proximas = paradas_proximas(indice, -22.0101, -47.8901, limite=3)
        self.assertEqual(proximas[0]["id_parada"], 1)
        self.assertTrue(proximas[0]["distancia_metros"] < proximas[-1]["distancia_metros"])

    def test_coordenadas_invalidas_e_localizacao_invalidas(self):
        self.assertFalse(coordenada_valida(None, -47.8))
        self.assertFalse(coordenada_valida(-91, -47.8))
        with self.assertRaises(ValueError):
            paradas_proximas(construir_indice_paradas(dataset_teste()), 999, 0)

    def test_parada_sem_atendimento_retorna_vazio(self):
        indice = construir_indice_paradas({"linhas": []})
        self.assertEqual(atendimentos_da_parada(indice, "ausente"), [])


if __name__ == "__main__":
    unittest.main()
