"""Fixtures sintéticas do parser de itinerários; não contêm dados reais."""

from __future__ import annotations

import math
import unittest

from processar_itinerarios import ErroItinerario, processar_itinerario


PONTOS = [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]
SHAPE_CONHECIDA = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"


def _codificar_valor(valor):
    valor = ~(valor << 1) if valor < 0 else valor << 1
    caracteres = []
    while valor >= 0x20:
        caracteres.append(chr((0x20 | (valor & 0x1F)) + 63))
        valor >>= 5
    caracteres.append(chr(valor + 63))
    return "".join(caracteres)


def codificar_polyline(pontos):
    anterior_lat = 0
    anterior_lng = 0
    partes = []
    for latitude, longitude in pontos:
        lat = round(latitude * 100_000)
        lng = round(longitude * 100_000)
        partes.append(_codificar_valor(lat - anterior_lat))
        partes.append(_codificar_valor(lng - anterior_lng))
        anterior_lat, anterior_lng = lat, lng
    return "".join(partes)


def parada(stop_id, latitude, longitude, nome, **extras):
    return {
        "stopId": stop_id,
        "lat": latitude,
        "lng": longitude,
        "name": nome,
        **extras,
    }


def resposta(*, pontos=None, paradas=None, trip_name="Destino sintético"):
    pontos = pontos if pontos is not None else PONTOS
    if paradas is None:
        paradas = [
            parada(101, pontos[0][0], pontos[0][1], "Parada inicial sintética", int=0, wait=0),
            parada(102, pontos[1][0], pontos[1][1], "Parada intermediária sintética", int=600, wait=0),
            parada(103, pontos[-1][0], pontos[-1][1], "Parada final sintética", int=1200, wait=0),
        ]
    return {
        "tripName": trip_name,
        "routeName": "T-01 - Linha sintética",
        "shape": codificar_polyline(pontos),
        "tzOffset": -3,
        "price": None,
        "stops": paradas,
    }


class ItinerarioValidoTests(unittest.TestCase):
    def test_itinerario_valido_e_geojson_com_polyline_conhecida(self):
        entrada = resposta()
        self.assertEqual(entrada["shape"], SHAPE_CONHECIDA)
        resultado = processar_itinerario(entrada, 7001)
        self.assertEqual(resultado["schema_version"], 1)
        self.assertEqual(resultado["id_viagem"], 7001)
        self.assertEqual(resultado["geometria"]["formato"], "google_encoded_polyline_5")
        self.assertEqual(
            resultado["geometria"]["geojson"],
            {
                "type": "LineString",
                "coordinates": [[-120.2, 38.5], [-120.95, 40.7], [-126.453, 43.252]],
            },
        )

    def test_multiplas_paradas_preservam_ordem(self):
        resultado = processar_itinerario(resposta(), 7001)
        self.assertEqual([item["ordem"] for item in resultado["paradas"]], [1, 2, 3])
        self.assertEqual([item["id_parada"] for item in resultado["paradas"]], [101, 102, 103])

    def test_int_e_wait_sao_preservados_sem_interpretacao(self):
        entrada = resposta()
        entrada["stops"][0]["int"] = None
        entrada["stops"][0]["wait"] = False
        entrada["stops"][1].pop("wait")
        resultado = processar_itinerario(entrada, 7001)
        self.assertEqual(resultado["paradas"][0]["campos_origem"], {"int": None, "wait": False})
        self.assertEqual(resultado["paradas"][1]["campos_origem"], {"int": 600})

    def test_nulos_e_campos_desconhecidos_sao_preservados(self):
        entrada = resposta()
        entrada["atributoNovo"] = {"ativo": False}
        entrada["stops"][0]["novoNaParada"] = None
        resultado = processar_itinerario(entrada, 7001)
        self.assertIsNone(resultado["campos_origem"]["price"])
        self.assertEqual(resultado["campos_extras"], {"atributoNovo": {"ativo": False}})
        self.assertEqual(resultado["paradas"][0]["campos_extras"], {"novoNaParada": None})

    def test_itinerarios_com_mesmo_destino_continuam_distintos(self):
        primeiro = processar_itinerario(resposta(), 7001)
        outros_pontos = [(38.5, -120.2), (39.0, -121.0), (43.252, -126.453)]
        segundo = processar_itinerario(resposta(pontos=outros_pontos), 7002)
        self.assertEqual(primeiro["nome_viagem"], segundo["nome_viagem"])
        self.assertNotEqual(primeiro["id_viagem"], segundo["id_viagem"])
        self.assertNotEqual(
            primeiro["geometria"]["codificacao_origem"],
            segundo["geometria"]["codificacao_origem"],
        )


class IdentificadoresInvalidosTests(unittest.TestCase):
    def test_trip_id_invalido(self):
        for trip_id in (0, -1, True, "7001", None):
            with self.subTest(trip_id=trip_id), self.assertRaisesRegex(ErroItinerario, "inteiro positivo"):
                processar_itinerario(resposta(), trip_id)

    def test_stop_id_invalido(self):
        for stop_id in (0, -1, False, "101", None):
            entrada = resposta()
            entrada["stops"][0]["stopId"] = stop_id
            with self.subTest(stop_id=stop_id), self.assertRaisesRegex(ErroItinerario, "inteiro positivo"):
                processar_itinerario(entrada, 7001)


class CoordenadasInvalidasTests(unittest.TestCase):
    def test_latitude_invalida(self):
        for latitude in (-91, 91, math.nan, math.inf, True, "38.5", None):
            entrada = resposta()
            entrada["stops"][0]["lat"] = latitude
            with self.subTest(latitude=latitude), self.assertRaises(ErroItinerario):
                processar_itinerario(entrada, 7001)

    def test_longitude_invalida(self):
        for longitude in (-181, 181, math.nan, -math.inf, False, "-120.2", None):
            entrada = resposta()
            entrada["stops"][0]["lng"] = longitude
            with self.subTest(longitude=longitude), self.assertRaises(ErroItinerario):
                processar_itinerario(entrada, 7001)


class ParadasInvalidasTests(unittest.TestCase):
    def test_lista_vazia_ou_com_menos_de_duas_paradas(self):
        for paradas in ([], [parada(101, 38.5, -120.2, "Única")]):
            with self.subTest(paradas=paradas), self.assertRaisesRegex(ErroItinerario, "pelo menos duas"):
                processar_itinerario(resposta(paradas=paradas), 7001)

    def test_parada_deve_ser_objeto(self):
        entrada = resposta()
        entrada["stops"][1] = "parada"
        with self.assertRaisesRegex(ErroItinerario, "objeto JSON"):
            processar_itinerario(entrada, 7001)

    def test_nome_da_parada_deve_ser_texto_nao_vazio(self):
        for nome in (None, "", "   ", False):
            entrada = resposta()
            entrada["stops"][0]["name"] = nome
            with self.subTest(nome=nome), self.assertRaisesRegex(ErroItinerario, "texto não vazio"):
                processar_itinerario(entrada, 7001)


class GeometriaInvalidaTests(unittest.TestCase):
    def test_shape_truncada_ou_com_caractere_invalido(self):
        for shape in ("_", "abc\n", ""):
            entrada = resposta()
            entrada["shape"] = shape
            with self.subTest(shape=shape), self.assertRaises(ErroItinerario):
                processar_itinerario(entrada, 7001)

    def test_shape_com_menos_de_dois_pontos(self):
        entrada = resposta()
        entrada["shape"] = codificar_polyline([PONTOS[0]])
        with self.assertRaisesRegex(ErroItinerario, "pelo menos dois pontos"):
            processar_itinerario(entrada, 7001)

    def test_extremidades_devem_corresponder_as_paradas(self):
        entrada = resposta()
        entrada["stops"][0]["lat"] = 0
        entrada["stops"][0]["lng"] = 0
        with self.assertRaisesRegex(ErroItinerario, "extremidades"):
            processar_itinerario(entrada, 7001)

    def test_divergencia_pode_ser_preservada_e_marcada_para_diagnostico(self):
        entrada = resposta()
        entrada["stops"][-1]["lat"] = 0
        resultado = processar_itinerario(
            entrada, 7001, permitir_extremidades_divergentes=True
        )
        self.assertFalse(
            resultado["geometria"]["validacao"]["extremidades_compativeis"]
        )


class EsquemaInvalidoTests(unittest.TestCase):
    def test_resposta_deve_ser_objeto(self):
        for entrada in (None, [], "json", 4):
            with self.subTest(entrada=entrada), self.assertRaisesRegex(ErroItinerario, "objeto JSON"):
                processar_itinerario(entrada, 7001)

    def test_campos_raiz_obrigatorios(self):
        for campo in ("tripName", "routeName", "shape", "tzOffset", "stops"):
            entrada = resposta()
            del entrada[campo]
            with self.subTest(campo=campo), self.assertRaisesRegex(ErroItinerario, "obrigatório"):
                processar_itinerario(entrada, 7001)

    def test_campos_obrigatorios_da_parada(self):
        for campo in ("stopId", "lat", "lng", "name"):
            entrada = resposta()
            del entrada["stops"][0][campo]
            with self.subTest(campo=campo), self.assertRaisesRegex(ErroItinerario, "obrigatório"):
                processar_itinerario(entrada, 7001)

    def test_metadados_invalidos(self):
        casos = [
            ("tripName", None),
            ("routeName", ""),
            ("tzOffset", 15),
            ("tzOffset", True),
        ]
        for campo, valor in casos:
            entrada = resposta()
            entrada[campo] = valor
            with self.subTest(campo=campo, valor=valor), self.assertRaises(ErroItinerario):
                processar_itinerario(entrada, 7001)


if __name__ == "__main__":
    unittest.main()
