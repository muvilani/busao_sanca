"""Fixtures sintéticas do parser de horários; nenhuma resposta real é incluída."""

from __future__ import annotations

import unittest

from processar_horarios import ErroHorario, processar_horarios


def partida(seq=1, dep="06:30", arr="07:15", **extras):
    return {"dep": dep, "arr": arr, "seq": seq, **extras}


def servico(service_id=501, *, partidas=None, descricao="Dias sintéticos"):
    return {
        "serviceId": service_id,
        "desc": descricao,
        "start": "2026-01-01",
        "end": "2026-12-31",
        "days": [False, True, True, True, True, True, False],
        "departures": partidas if partidas is not None else [partida()],
    }


def direcao(direction_id=0, *, servicos=None, descricao="Ida sintética"):
    return {
        "directionId": direction_id,
        "desc": descricao,
        "order": 255,
        "services": servicos if servicos is not None else [servico()],
    }


def viagem(trip_id=701, *, direction_id=0, seq=1, destino="Terminal sintético"):
    return {
        "tripId": trip_id,
        "tripDesc": destino,
        "shortName": None,
        "headsign": destino,
        "description": None,
        "directionId": direction_id,
        "seq": seq,
    }


def resposta(*, direcoes=None, viagens=None, excecoes=None):
    return {
        "routeId": 9001,
        "shortName": "T-01",
        "longName": "Linha inteiramente sintética",
        "desc": "",
        "type": 3,
        "color": "#123456",
        "textColor": "#FFFFFF",
        "ac": False,
        "price": None,
        "timetable": {
            "directions": direcoes if direcoes is not None else [direcao()],
            "trips": viagens if viagens is not None else [viagem()],
            "exceptions": excecoes if excecoes is not None else [],
        },
    }


class ProcessamentoValidoTests(unittest.TestCase):
    def test_resposta_valida_com_uma_direcao(self):
        resultado = processar_horarios(resposta())
        self.assertEqual(resultado["schema_version"], 1)
        self.assertEqual(resultado["linha"]["id_linha"], 9001)
        self.assertEqual(len(resultado["direcoes"]), 1)
        self.assertEqual(resultado["direcoes"][0]["servicos"][0]["dias_semana_origem"],
                         [False, True, True, True, True, True, False])
        self.assertFalse(resultado["direcoes"][0]["servicos"][0]["ordem_dias_confirmada"])

    def test_linha_com_duas_direcoes_e_seq_contextual(self):
        entrada = resposta(
            direcoes=[
                direcao(0, servicos=[servico(501, partidas=[partida(seq=1)])]),
                direcao(1, servicos=[servico(501, partidas=[partida(seq=1)])], descricao="Volta sintética"),
            ],
            viagens=[
                viagem(701, direction_id=0, seq=1, destino="Norte sintético"),
                viagem(702, direction_id=1, seq=1, destino="Sul sintético"),
            ],
        )
        resultado = processar_horarios(entrada)
        ids = [d["servicos"][0]["partidas"][0]["id_viagem"] for d in resultado["direcoes"]]
        self.assertEqual(ids, [701, 702])

    def test_multiplos_servicos_com_mesma_descricao_nao_sao_mesclados(self):
        entrada = resposta(
            direcoes=[direcao(servicos=[servico(501), servico(502)])]
        )
        resultado = processar_horarios(entrada)
        servicos = resultado["direcoes"][0]["servicos"]
        self.assertEqual([item["id_servico"] for item in servicos], [501, 502])
        self.assertEqual(len(servicos), 2)

    def test_mesmo_service_id_em_direcoes_diferentes_permanece_contextual(self):
        entrada = resposta(
            direcoes=[
                direcao(0, servicos=[servico(501, partidas=[partida(seq=1)])]),
                direcao(1, servicos=[servico(501, partidas=[partida(seq=2)])]),
            ],
            viagens=[viagem(701, seq=1), viagem(702, direction_id=1, seq=2)],
        )
        resultado = processar_horarios(entrada)
        self.assertEqual(
            [(d["id_direcao"], d["servicos"][0]["id_servico"]) for d in resultado["direcoes"]],
            [(0, 501), (1, 501)],
        )

    def test_diferentes_variantes_em_uma_direcao(self):
        entrada = resposta(
            direcoes=[direcao(servicos=[servico(partidas=[partida(1), partida(2)])])],
            viagens=[viagem(701, seq=1), viagem(702, seq=2, destino="Bairro sintético")],
        )
        resultado = processar_horarios(entrada)
        self.assertEqual([v["id_viagem"] for v in resultado["variantes"]], [701, 702])
        self.assertEqual(
            [p["id_viagem"] for p in resultado["direcoes"][0]["servicos"][0]["partidas"]],
            [701, 702],
        )

    def test_excecao_preserva_tipo_sem_interpretar(self):
        resultado = processar_horarios(
            resposta(excecoes=[{"date": "2026-05-01", "serviceId": 501, "type": 7}])
        )
        excecao = resultado["excecoes_calendario"][0]
        self.assertEqual(excecao["tipo_origem"], 7)
        self.assertFalse(excecao["semantica_tipo_confirmada"])

    def test_excecao_preserva_tipo_negativo_sem_interpretar(self):
        resultado = processar_horarios(
            resposta(excecoes=[{"date": "2026-05-01", "serviceId": 501, "type": -1}])
        )
        self.assertEqual(resultado["excecoes_calendario"][0]["tipo_origem"], -1)

    def test_campos_desconhecidos_e_estados_null_false_ausente_sao_preservados(self):
        entrada = resposta()
        entrada["campoNovo"] = {"valor": 4}
        entrada["timetable"]["novoTimetable"] = False
        entrada["timetable"]["directions"][0]["services"][0]["novoServico"] = None
        entrada["timetable"]["directions"][0]["services"][0]["departures"][0].update(
            {"wa": 0, "ac": None, "extra": False, "novoPartida": "x"}
        )
        resultado = processar_horarios(entrada)
        linha = resultado["linha"]
        self.assertIsNone(linha["campos_origem"]["price"])
        self.assertFalse(linha["campos_origem"]["ac"])
        self.assertNotIn("campoAusente", linha["campos_origem"])
        self.assertEqual(linha["campos_extras"]["campoNovo"], {"valor": 4})
        self.assertFalse(resultado["campos_extras_timetable"]["novoTimetable"])
        servico_normalizado = resultado["direcoes"][0]["servicos"][0]
        self.assertIsNone(servico_normalizado["campos_extras"]["novoServico"])
        partida_normalizada = servico_normalizado["partidas"][0]
        self.assertEqual(partida_normalizada["campos_origem"], {"wa": 0, "ac": None, "extra": False})
        self.assertEqual(partida_normalizada["campos_extras"], {"novoPartida": "x"})

    def test_horario_que_atravessa_meia_noite_nao_tem_duracao_inferida(self):
        entrada = resposta(
            direcoes=[direcao(servicos=[servico(partidas=[partida(dep="23:50", arr="00:20")])])]
        )
        normalizada = processar_horarios(entrada)["direcoes"][0]["servicos"][0]["partidas"][0]
        self.assertEqual((normalizada["saida"], normalizada["chegada"]), ("23:50", "00:20"))
        self.assertNotIn("duracao", normalizada)

    def test_horario_operacional_acima_de_24_horas_e_aceito(self):
        entrada = resposta(
            direcoes=[direcao(servicos=[servico(partidas=[partida(dep="24:10", arr="25:00:30")])])]
        )
        processar_horarios(entrada)


class ReferenciasInvalidasTests(unittest.TestCase):
    def test_seq_inexistente(self):
        entrada = resposta(direcoes=[direcao(servicos=[servico(partidas=[partida(seq=99)])])])
        with self.assertRaisesRegex(ErroHorario, "não referencia"):
            processar_horarios(entrada)

    def test_seq_ambiguo_na_mesma_direcao(self):
        entrada = resposta(viagens=[viagem(701, seq=1), viagem(702, seq=1)])
        with self.assertRaisesRegex(ErroHorario, "ambíguo"):
            processar_horarios(entrada)

    def test_trip_id_duplicado(self):
        entrada = resposta(viagens=[viagem(701, seq=1), viagem(701, seq=2)])
        with self.assertRaisesRegex(ErroHorario, "tripId duplicado"):
            processar_horarios(entrada)

    def test_variante_referencia_direcao_inexistente(self):
        entrada = resposta(viagens=[viagem(direction_id=8)])
        with self.assertRaisesRegex(ErroHorario, "direção inexistente"):
            processar_horarios(entrada)

    def test_excecao_preserva_referencia_a_servico_nao_listado(self):
        entrada = resposta(excecoes=[{"date": "2026-05-01", "serviceId": 999, "type": 1}])
        resultado = processar_horarios(entrada)
        excecao = resultado["excecoes_calendario"][0]
        self.assertEqual(excecao["id_servico"], 999)
        self.assertFalse(excecao["referencia_servico_presente"])


class CalendarioInvalidoTests(unittest.TestCase):
    def alterar_servico(self, campo, valor):
        entrada = resposta()
        entrada["timetable"]["directions"][0]["services"][0][campo] = valor
        return entrada

    def test_vetor_semanal_deve_ter_sete_booleanos(self):
        for dias in ([True] * 6, [True] * 6 + [1], "0111110"):
            with self.subTest(dias=dias), self.assertRaises(ErroHorario):
                processar_horarios(self.alterar_servico("days", dias))

    def test_data_invalida(self):
        for valor in ("2026-02-30", "01/02/2026", None):
            with self.subTest(valor=valor), self.assertRaises(ErroHorario):
                processar_horarios(self.alterar_servico("start", valor))

    def test_inicio_posterior_ao_fim(self):
        entrada = self.alterar_servico("start", "2027-01-01")
        with self.assertRaisesRegex(ErroHorario, "posterior"):
            processar_horarios(entrada)

    def test_service_id_duplicado_na_mesma_direcao(self):
        entrada = resposta(direcoes=[direcao(servicos=[servico(501), servico(501)])])
        with self.assertRaisesRegex(ErroHorario, "duplicado na direção"):
            processar_horarios(entrada)


class HorarioInvalidoTests(unittest.TestCase):
    def test_horarios_invalidos(self):
        for horario in ("7:00", "12:60", "48:00", "24:00:60", None, False):
            entrada = resposta(
                direcoes=[direcao(servicos=[servico(partidas=[partida(dep=horario)])])]
            )
            with self.subTest(horario=horario), self.assertRaises(ErroHorario):
                processar_horarios(entrada)


class EsquemaInvalidoTests(unittest.TestCase):
    def test_respostas_vazias_ou_de_tipo_incorreto(self):
        for entrada in (None, [], {}, "json"):
            with self.subTest(entrada=entrada), self.assertRaises(ErroHorario):
                processar_horarios(entrada)

    def test_campos_estruturais_ausentes_ou_alterados(self):
        casos = []
        for campo in ("routeId", "shortName", "longName", "timetable"):
            entrada = resposta()
            del entrada[campo]
            casos.append(entrada)
        entrada = resposta()
        entrada["timetable"]["directions"] = {}
        casos.append(entrada)
        entrada = resposta()
        entrada["timetable"]["trips"] = []
        casos.append(entrada)
        entrada = resposta()
        del entrada["timetable"]["exceptions"]
        casos.append(entrada)
        for entrada in casos:
            with self.subTest(entrada=entrada), self.assertRaises(ErroHorario):
                processar_horarios(entrada)

    def test_booleano_nao_e_aceito_como_id(self):
        entrada = resposta()
        entrada["routeId"] = True
        with self.assertRaisesRegex(ErroHorario, "inteiro positivo"):
            processar_horarios(entrada)

    def test_array_de_partidas_nao_pode_ser_vazio(self):
        entrada = resposta(direcoes=[direcao(servicos=[servico(partidas=[])])])
        with self.assertRaisesRegex(ErroHorario, "array não vazio"):
            processar_horarios(entrada)


if __name__ == "__main__":
    unittest.main()
