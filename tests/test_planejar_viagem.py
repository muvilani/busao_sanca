"""Testes inteiramente sintéticos para o planejador conservador."""

from __future__ import annotations

import unittest

from planejar_viagem import analisar_linha, distancia_linha_reta, melhor_par_ordenado, origem_itinerario, partidas_de_terminal, planejar_texto, relatorio_origens, sugerir_locais


def parada(ordem, lat, lon, nome, id_parada=None):
    return {
        "ordem": ordem,
        "latitude": lat,
        "longitude": lon,
        "nome": nome,
        "id_parada": ordem if id_parada is None else id_parada,
    }


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
    linha["itinerarios"][0]["paradas"] = [parada(1, 0, 0, "São João", 101), parada(2, 0, .01, "Centro", 102), parada(3, 0, .02, "Vila Sul", 103)]
    linha["itinerarios"][1]["paradas"] = [parada(1, 0, .02, "Vila Sul", 103), parada(2, 0, .01, "Centro", 102), parada(3, 0, 0, "São João", 101)]
    return {"linhas": [linha]}


def adicionar_linha_conexao(dados, *, parada_compartilhada=103, codigo="11", repetida=False):
    segunda = linha_sintetica()
    segunda["catalogo"] = {"codigo": codigo, "nome": "Sul x Norte"}
    segunda["cobertura"] = {"completa_no_escopo_solicitado": True}
    paradas = [
        parada(1, 0, .02, "Vila Sul", parada_compartilhada),
        parada(2, 0, .03, "Norte", 104),
    ]
    segunda["itinerarios"] = [{
        "id_viagem": 30,
        "paradas": paradas,
        "geometria": {"validacao": {"extremidades_compativeis": True}},
    }]
    if repetida:
        segunda["itinerarios"].append({
            "id_viagem": 31,
            "paradas": [dict(item) for item in paradas],
            "geometria": {"validacao": {"extremidades_compativeis": True}},
        })
    segunda["horarios"]["variantes"] = [
        {"id_viagem": 30, "id_direcao": 0, "destino": "Norte", "sequencia": 1}
    ]
    if repetida:
        segunda["horarios"]["variantes"].append(
            {"id_viagem": 31, "id_direcao": 0, "destino": "Norte", "sequencia": 2}
        )
    dados["linhas"].append(segunda)
    return segunda


class PlanejamentoTests(unittest.TestCase):
    def test_busca_textual_tolera_acentos_e_caixa(self):
        sugestoes = sugerir_locais(dataset_textual(), "sao joao")
        self.assertEqual(sugestoes[0]["nome"], "São João")

    def test_planejamento_textual_respeita_sentido_e_ordem(self):
        resultado = planejar_texto(dataset_textual(), "SÃO JOÃO", "vila sul")
        self.assertEqual(resultado["status"], "sucesso")
        self.assertEqual(resultado["resultados"][0]["sentido"], "Ida")
        self.assertLess(resultado["resultados"][0]["embarque"]["ordem"], resultado["resultados"][0]["desembarque"]["ordem"])

    def test_sentido_inverso_escolhe_variante_de_volta(self):
        resultado = planejar_texto(dataset_textual(), "Vila Sul", "São João")
        self.assertEqual(resultado["status"], "sucesso")
        self.assertEqual(resultado["resultados"][0]["sentido"], "Volta")

    def test_origem_e_destino_iguais_tem_estado_especifico(self):
        resultado = planejar_texto(dataset_textual(), "Centro", "Centro")
        self.assertEqual(resultado["status"], "origem_destino_iguais")
        self.assertEqual(resultado["resultados"], [])

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
        adicionar_linha_conexao(dados)
        resultado = planejar_texto(dados, "São João", "Norte")
        self.assertEqual(resultado["status"], "sucesso")
        self.assertEqual(resultado["resultados"][0]["tipo"], "conexao")
        self.assertEqual(resultado["resultados"][0]["transferencia"]["nome"], "Vila Sul")
        self.assertEqual(resultado["resultados"][0]["transferencia"]["id_parada"], 103)

    def test_nome_igual_com_ids_diferentes_nao_cria_conexao(self):
        dados = dataset_textual()
        adicionar_linha_conexao(dados, parada_compartilhada=999)
        resultado = planejar_texto(dados, "São João", "Norte")
        self.assertEqual(resultado["status"], "sem_rota")

    def test_conexao_impossivel_por_ordem_inversa(self):
        dados = dataset_textual()
        segunda = adicionar_linha_conexao(dados)
        segunda["itinerarios"][0]["paradas"].reverse()
        for indice, item in enumerate(segunda["itinerarios"][0]["paradas"], 1):
            item["ordem"] = indice
        resultado = planejar_texto(dados, "São João", "Norte")
        self.assertEqual(resultado["status"], "sem_rota")

    def test_itinerario_com_ordem_invalida_e_ignorado(self):
        dados = dataset_textual()
        dados["linhas"][0]["itinerarios"][0]["paradas"][1]["ordem"] = 1
        resultado = planejar_texto(dados, "São João", "Vila Sul")
        self.assertEqual(resultado["status"], "sem_rota")

    def test_resultados_diretos_precedem_conexoes_e_menor_percurso(self):
        dados = dataset_textual()
        adicionar_linha_conexao(dados)
        resultado = planejar_texto(dados, "São João", "Vila Sul")
        self.assertEqual(resultado["resultados"][0]["tipo"], "direto")
        self.assertEqual(resultado["resultados"][0]["paradas_percorridas"], 2)

    def test_resultados_repetidos_sao_deduplicados(self):
        dados = dataset_textual()
        adicionar_linha_conexao(dados)
        dados["linhas"].append(dados["linhas"][1])
        resultado = planejar_texto(dados, "São João", "Norte")
        self.assertEqual(len(resultado["resultados"]), 1)

    def test_dataset_ausente_retorna_sem_rota(self):
        resultado = planejar_texto({}, "Origem", "Destino")
        self.assertEqual(resultado["status"], "sem_rota")

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
