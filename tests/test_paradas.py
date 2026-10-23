import unittest

from paradas import (
    atendimentos_da_parada,
    buscar_paradas,
    construir_indice_paradas,
    coordenada_valida,
    normalizar_busca,
    paradas_proximas,
    partidas_na_vigencia,
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
                            "descricao": "Dias úteis",
                            "vigencia_inicio": "2026-10-01",
                            "vigencia_fim": "2026-10-31",
                            "partidas": [{"id_viagem": 100, "saida": "07:00"}],
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

    def test_proximidade_tem_ordem_crescente_estavel(self):
        indice = construir_indice_paradas(dataset_teste())
        proximas = paradas_proximas(indice, -22.0101, -47.8901, limite=3)
        distancias = [parada["distancia_metros"] for parada in proximas]
        self.assertEqual(distancias, sorted(distancias))
        self.assertEqual([parada["id_parada"] for parada in proximas], [1, 2, 3])

    def test_busca_manual_por_nome_id_acentos_caixa_e_separadores(self):
        indice = construir_indice_paradas(dataset_teste())
        parada = next(item for item in indice["paradas"] if item["id_parada"] == 2)
        parada["nome"] = "Praça São João — Centro"
        self.assertEqual(buscar_paradas(indice, "praca sao joao")[0]["id_parada"], 2)
        self.assertEqual(buscar_paradas(indice, "SÃO-JOÃO")[0]["id_parada"], 2)
        self.assertEqual(buscar_paradas(indice, "2")[0]["id_parada"], 2)
        self.assertEqual(normalizar_busca("  Praça—SÃO  "), "praca sao")

    def test_partidas_na_data_dentro_e_fora_da_vigencia(self):
        atendimento = atendimentos_da_parada(construir_indice_paradas(dataset_teste()), "id:2")[0]
        dentro = partidas_na_vigencia(atendimento, "2026-10-15")
        fora = partidas_na_vigencia(atendimento, "2026-11-01")
        self.assertEqual([partida["saida"] for partida in dentro["partidas"]], ["07:00"])
        self.assertEqual(fora["partidas"], [])
        self.assertTrue(dentro["data_valida"])

    def test_multiplos_servicos_e_vigencia_desconhecida(self):
        atendimento = {
            "partidas": [
                {"saida": "07:00", "servico": "A", "vigencia_inicio": "2026-10-01", "vigencia_fim": "2026-10-31"},
                {"saida": "08:00", "servico": "B", "vigencia_inicio": "2026-11-01", "vigencia_fim": "2026-11-30"},
                {"saida": "09:00", "servico": "Sem vigência", "vigencia_inicio": None, "vigencia_fim": None},
            ]
        }
        resultado = partidas_na_vigencia(atendimento, "2026-11-15")
        self.assertEqual([partida["saida"] for partida in resultado["partidas"]], ["08:00"])
        self.assertTrue(resultado["vigencia_desconhecida"])

    def test_data_sem_resultados_e_data_invalida(self):
        atendimento = atendimentos_da_parada(construir_indice_paradas(dataset_teste()), "id:2")[0]
        self.assertEqual(partidas_na_vigencia(atendimento, "2027-01-01")["partidas"], [])
        invalida = partidas_na_vigencia(atendimento, "2026-02-30")
        self.assertFalse(invalida["data_valida"])
        self.assertEqual(invalida["partidas"], [])

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
