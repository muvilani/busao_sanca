"""Valida e normaliza respostas do endpoint ``timetable`` do Bus2.

Este módulo não faz acesso HTTP. Campos de semântica ainda não confirmada
são preservados em ``campos_origem``; campos não conhecidos pelo esquema
observado são copiados para ``campos_extras``.
"""

from __future__ import annotations

import copy
import re
from datetime import date

SCHEMA_VERSION = 1
_HORARIO = re.compile(r"([0-9]{2}):([0-9]{2})(?::([0-9]{2}))?")


class ErroHorario(ValueError):
    """Resposta de horários inválida, inconsistente ou ambígua."""


def _erro(caminho: str, mensagem: str) -> None:
    raise ErroHorario(f"{caminho}: {mensagem}")


def _objeto(valor: object, caminho: str) -> dict:
    if not isinstance(valor, dict):
        _erro(caminho, "esperado objeto JSON")
    return valor


def _lista(valor: object, caminho: str, *, vazia: bool = True) -> list:
    if not isinstance(valor, list) or (not vazia and not valor):
        detalhe = "array não vazio" if not vazia else "array"
        _erro(caminho, f"esperado {detalhe}")
    return valor


def _obrigatorio(objeto: dict, campo: str, caminho: str) -> object:
    if campo not in objeto:
        _erro(caminho, f"campo obrigatório {campo!r} ausente")
    return objeto[campo]


def _inteiro(valor: object, caminho: str, *, positivo: bool = False) -> int:
    limite = 1 if positivo else 0
    if type(valor) is not int or valor < limite:
        regra = "inteiro positivo" if positivo else "inteiro não negativo"
        _erro(caminho, f"esperado {regra}")
    return valor


def _inteiro_assinado(valor: object, caminho: str) -> int:
    """Valida um inteiro opaco sem inventar limites para sua semântica."""
    if type(valor) is not int:
        _erro(caminho, "esperado inteiro")
    return valor


def _texto(valor: object, caminho: str, *, vazio: bool = False) -> str:
    if not isinstance(valor, str) or (not vazio and not valor.strip()):
        regra = "texto" if vazio else "texto não vazio"
        _erro(caminho, f"esperado {regra}")
    if any(ord(caractere) < 32 for caractere in valor):
        _erro(caminho, "texto contém caractere de controle")
    return valor.strip() if not vazio else valor


def _data(valor: object, caminho: str) -> str:
    texto = _texto(valor, caminho)
    try:
        analisada = date.fromisoformat(texto)
    except ValueError as erro:
        raise ErroHorario(f"{caminho}: data inválida; esperado YYYY-MM-DD") from erro
    if analisada.isoformat() != texto:
        _erro(caminho, "data deve usar exatamente YYYY-MM-DD")
    return texto


def _horario(valor: object, caminho: str) -> str:
    texto = _texto(valor, caminho)
    correspondencia = _HORARIO.fullmatch(texto)
    if correspondencia is None:
        _erro(caminho, "horário inválido; esperado HH:MM ou HH:MM:SS")
    hora, minuto, segundo = (int(item or 0) for item in correspondencia.groups())
    # GTFS e sistemas de transporte podem representar viagens após meia-noite
    # com horas superiores a 23. O limite evita aceitar valores arbitrários.
    if hora > 47 or minuto > 59 or segundo > 59:
        _erro(caminho, "horário fora do intervalo aceito (00:00 a 47:59:59)")
    return texto


def _campos(objeto: dict, nomes: set[str]) -> dict:
    """Copia somente campos presentes; assim null, false e ausente não se confundem."""
    return {nome: copy.deepcopy(objeto[nome]) for nome in nomes if nome in objeto}


def _extras(objeto: dict, conhecidos: set[str]) -> dict:
    return {
        chave: copy.deepcopy(valor)
        for chave, valor in objeto.items()
        if chave not in conhecidos
    }


def _variante(item: object, indice: int, direcoes: set[int]) -> dict:
    caminho = f"$.timetable.trips[{indice}]"
    origem = _objeto(item, caminho)
    trip_id = _inteiro(_obrigatorio(origem, "tripId", caminho), f"{caminho}.tripId", positivo=True)
    direcao = _inteiro(
        _obrigatorio(origem, "directionId", caminho), f"{caminho}.directionId"
    )
    if direcao not in direcoes:
        _erro(f"{caminho}.directionId", "direção inexistente")
    sequencia = _inteiro(_obrigatorio(origem, "seq", caminho), f"{caminho}.seq", positivo=True)

    campos_origem = _campos(
        origem, {"tripDesc", "shortName", "headsign", "description"}
    )
    destinos = [
        origem.get("headsign"),
        origem.get("tripDesc"),
    ]
    destino = next(
        (valor.strip() for valor in destinos if isinstance(valor, str) and valor.strip()),
        None,
    )
    if destino is None:
        _erro(caminho, "variante sem headsign ou tripDesc utilizável")

    conhecidos = {"tripId", "directionId", "seq"} | set(campos_origem)
    return {
        "id_viagem": trip_id,
        "id_direcao": direcao,
        "sequencia_origem": sequencia,
        "destino": destino,
        "campos_origem": campos_origem,
        "campos_extras": _extras(origem, conhecidos),
    }


def _servico(
    item: object,
    caminho: str,
    direcao: int,
    variantes: dict[tuple[int, int], dict],
) -> dict:
    origem = _objeto(item, caminho)
    service_id = _inteiro(
        _obrigatorio(origem, "serviceId", caminho),
        f"{caminho}.serviceId",
        positivo=True,
    )
    descricao = _texto(_obrigatorio(origem, "desc", caminho), f"{caminho}.desc")
    inicio = _data(_obrigatorio(origem, "start", caminho), f"{caminho}.start")
    fim = _data(_obrigatorio(origem, "end", caminho), f"{caminho}.end")
    if date.fromisoformat(inicio) > date.fromisoformat(fim):
        _erro(caminho, "início da vigência posterior ao fim")

    dias = _lista(_obrigatorio(origem, "days", caminho), f"{caminho}.days")
    if len(dias) != 7 or any(type(valor) is not bool for valor in dias):
        _erro(f"{caminho}.days", "esperado vetor de sete booleanos")

    partidas_origem = _lista(
        _obrigatorio(origem, "departures", caminho),
        f"{caminho}.departures",
        vazia=False,
    )
    partidas = []
    for indice, item_partida in enumerate(partidas_origem):
        caminho_partida = f"{caminho}.departures[{indice}]"
        partida = _objeto(item_partida, caminho_partida)
        sequencia = _inteiro(
            _obrigatorio(partida, "seq", caminho_partida),
            f"{caminho_partida}.seq",
            positivo=True,
        )
        chave = (direcao, sequencia)
        if chave not in variantes:
            _erro(
                f"{caminho_partida}.seq",
                "não referencia uma variante única na mesma direção",
            )
        campos_origem = _campos(partida, {"wa", "ac", "extra", "ckpt"})
        conhecidos = {"dep", "arr", "seq"} | set(campos_origem)
        partidas.append(
            {
                "saida": _horario(
                    _obrigatorio(partida, "dep", caminho_partida),
                    f"{caminho_partida}.dep",
                ),
                "chegada": _horario(
                    _obrigatorio(partida, "arr", caminho_partida),
                    f"{caminho_partida}.arr",
                ),
                "sequencia_variante_origem": sequencia,
                "id_viagem": variantes[chave]["id_viagem"],
                "campos_origem": campos_origem,
                "campos_extras": _extras(partida, conhecidos),
            }
        )

    conhecidos = {"serviceId", "desc", "start", "end", "days", "departures"}
    return {
        "id_servico": service_id,
        "descricao": descricao,
        "vigencia_inicio": inicio,
        "vigencia_fim": fim,
        "dias_semana_origem": copy.deepcopy(dias),
        "ordem_dias_confirmada": False,
        "partidas": partidas,
        "campos_extras": _extras(origem, conhecidos),
    }


def processar_horarios(payload: object) -> dict:
    """Valida uma resposta ``timetable`` e retorna o esquema normalizado v1."""
    raiz = _objeto(payload, "$")
    route_id = _inteiro(_obrigatorio(raiz, "routeId", "$"), "$.routeId", positivo=True)
    codigo = _texto(_obrigatorio(raiz, "shortName", "$"), "$.shortName")
    nome = _texto(_obrigatorio(raiz, "longName", "$"), "$.longName")
    timetable = _objeto(_obrigatorio(raiz, "timetable", "$"), "$.timetable")

    direcoes_origem = _lista(
        _obrigatorio(timetable, "directions", "$.timetable"),
        "$.timetable.directions",
        vazia=False,
    )
    ids_direcao: set[int] = set()
    for indice, item in enumerate(direcoes_origem):
        caminho = f"$.timetable.directions[{indice}]"
        direcao = _objeto(item, caminho)
        identificador = _inteiro(
            _obrigatorio(direcao, "directionId", caminho), f"{caminho}.directionId"
        )
        if identificador in ids_direcao:
            _erro(f"{caminho}.directionId", "direção duplicada")
        ids_direcao.add(identificador)

    trips = _lista(
        _obrigatorio(timetable, "trips", "$.timetable"),
        "$.timetable.trips",
        vazia=False,
    )
    variantes_lista = [_variante(item, indice, ids_direcao) for indice, item in enumerate(trips)]
    ids_viagem: set[int] = set()
    variantes: dict[tuple[int, int], dict] = {}
    for indice, variante in enumerate(variantes_lista):
        if variante["id_viagem"] in ids_viagem:
            _erro(f"$.timetable.trips[{indice}].tripId", "tripId duplicado")
        ids_viagem.add(variante["id_viagem"])
        chave = (variante["id_direcao"], variante["sequencia_origem"])
        if chave in variantes:
            _erro(
                f"$.timetable.trips[{indice}].seq",
                "seq ambíguo dentro da mesma direção",
            )
        variantes[chave] = variante

    direcoes = []
    servicos_existentes: set[int] = set()
    for indice, item in enumerate(direcoes_origem):
        caminho = f"$.timetable.directions[{indice}]"
        origem = _objeto(item, caminho)
        identificador = _inteiro(origem["directionId"], f"{caminho}.directionId")
        descricao = _texto(_obrigatorio(origem, "desc", caminho), f"{caminho}.desc")
        servicos_origem = _lista(
            _obrigatorio(origem, "services", caminho),
            f"{caminho}.services",
            vazia=False,
        )
        servicos = []
        ids_no_contexto: set[int] = set()
        for indice_servico, item_servico in enumerate(servicos_origem):
            caminho_servico = f"{caminho}.services[{indice_servico}]"
            servico = _servico(item_servico, caminho_servico, identificador, variantes)
            if servico["id_servico"] in ids_no_contexto:
                _erro(f"{caminho_servico}.serviceId", "serviço duplicado na direção")
            ids_no_contexto.add(servico["id_servico"])
            servicos_existentes.add(servico["id_servico"])
            servicos.append(servico)
        conhecidos = {"directionId", "desc", "order", "services"}
        direcao_normalizada = {
            "id_direcao": identificador,
            "descricao": descricao,
            "servicos": servicos,
            "campos_extras": _extras(origem, conhecidos),
        }
        if "order" in origem:
            direcao_normalizada["ordem_origem"] = copy.deepcopy(origem["order"])
        direcoes.append(direcao_normalizada)

    excecoes_origem = _lista(
        _obrigatorio(timetable, "exceptions", "$.timetable"),
        "$.timetable.exceptions",
    )
    excecoes = []
    for indice, item in enumerate(excecoes_origem):
        caminho = f"$.timetable.exceptions[{indice}]"
        origem = _objeto(item, caminho)
        service_id = _inteiro(
            _obrigatorio(origem, "serviceId", caminho),
            f"{caminho}.serviceId",
            positivo=True,
        )
        # A fonte usa também valores negativos (observado: -1). Como a
        # semântica ainda não foi confirmada, validamos somente o tipo.
        tipo = _inteiro_assinado(
            _obrigatorio(origem, "type", caminho), f"{caminho}.type"
        )
        conhecidos = {"date", "serviceId", "type"}
        excecoes.append(
            {
                "data": _data(_obrigatorio(origem, "date", caminho), f"{caminho}.date"),
                "id_servico": service_id,
                "referencia_servico_presente": service_id in servicos_existentes,
                "tipo_origem": tipo,
                "semantica_tipo_confirmada": False,
                "campos_extras": _extras(origem, conhecidos),
            }
        )

    linha_origem = {"desc", "type", "color", "textColor", "ac", "price"}
    conhecidos_raiz = {"routeId", "shortName", "longName", "timetable"} | linha_origem
    conhecidos_timetable = {"directions", "trips", "exceptions"}
    return {
        "schema_version": SCHEMA_VERSION,
        "linha": {
            "id_linha": route_id,
            "codigo": codigo,
            "nome": nome,
            "campos_origem": _campos(raiz, linha_origem),
            "campos_extras": _extras(raiz, conhecidos_raiz),
        },
        "direcoes": direcoes,
        "variantes": variantes_lista,
        "excecoes_calendario": excecoes,
        "campos_extras_timetable": _extras(timetable, conhecidos_timetable),
    }
