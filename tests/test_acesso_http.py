"""Testes offline da política HTTP; nenhuma chamada real de rede."""

import hashlib
import unittest
from unittest.mock import patch

import requests

from acesso_http import ClientePublico, ErroColeta, USER_AGENT


URL = "https://mobilibus.com/api/routes?origin=web&project_id=317"
ROBOTS = "https://mobilibus.com/robots.txt"


def resposta(status=200, corpo="", headers=None):
    resultado = requests.Response()
    resultado.status_code = status
    resultado._content = corpo.encode("utf-8")
    resultado._content_consumed = True
    resultado.encoding = "utf-8"
    resultado.headers.update(headers or {})
    return resultado


class SessaoFalsa:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = []
        self.fechada = False

    def get(self, url, **kwargs):
        self.chamadas.append((url, kwargs))
        if not self.respostas:
            raise AssertionError("Requisição além das respostas previstas.")
        proxima = self.respostas.pop(0)
        if isinstance(proxima, BaseException):
            raise proxima
        return proxima

    def close(self):
        self.fechada = True


class RelogioFalso:
    def __init__(self):
        self.agora = 0.0
        self.esperas = []

    def monotonic(self):
        return self.agora

    def sleep(self, duracao):
        if duracao < 0:
            raise AssertionError("Espera negativa.")
        self.esperas.append(duracao)
        self.agora += duracao


class ClientePublicoTests(unittest.TestCase):
    def setUp(self):
        self.relogio = RelogioFalso()
        self.patch_tempo = patch("acesso_http.time.monotonic", self.relogio.monotonic)
        self.patch_sleep = patch("acesso_http.time.sleep", self.relogio.sleep)
        self.patch_tempo.start()
        self.patch_sleep.start()
        self.addCleanup(self.patch_tempo.stop)
        self.addCleanup(self.patch_sleep.stop)

    def test_consulta_robots_primeiro_e_reutiliza_regras(self):
        sessao = SessaoFalsa(
            [
                resposta(corpo="User-agent: *\nAllow: /\n"),
                resposta(corpo='{"routes": []}'),
                resposta(corpo='{"routes": []}'),
            ]
        )
        with ClientePublico(session=sessao, intervalo=0) as cliente:
            self.assertEqual(cliente.obter(URL).json(), {"routes": []})
            cliente.obter(URL)
            self.assertEqual([c[0] for c in sessao.chamadas], [ROBOTS, URL, URL])
            self.assertEqual(len(cliente.regras), 1)
            self.assertEqual(cliente.regras[0]["politica"], "robots_txt")
            self.assertEqual(
                cliente.regras[0]["sha256"],
                hashlib.sha256(b"User-agent: *\nAllow: /\n").hexdigest(),
            )
            self.assertEqual(self.relogio.esperas, [2.0, 2.0])
            for _, argumentos in sessao.chamadas:
                self.assertFalse(argumentos["allow_redirects"])
                self.assertEqual(argumentos["headers"]["User-Agent"], USER_AGENT)
            self.assertTrue(all("?" not in r["url"] for r in cliente.requisicoes))
        self.assertTrue(sessao.fechada)

    def test_disallow_impede_requisicao_de_conteudo(self):
        sessao = SessaoFalsa([resposta(corpo="User-agent: *\nDisallow: /api/\n")])
        with ClientePublico(session=sessao) as cliente:
            with self.assertRaisesRegex(ErroColeta, "proíbe"):
                cliente.obter(URL)
        self.assertEqual([c[0] for c in sessao.chamadas], [ROBOTS])

    def test_regra_especifica_do_agente_tem_precedencia(self):
        sessao = SessaoFalsa(
            [
                resposta(
                    corpo="User-agent: BusaoSanca\nDisallow: /api/\n\n"
                    "User-agent: *\nAllow: /\n"
                )
            ]
        )
        with ClientePublico(session=sessao) as cliente:
            with self.assertRaisesRegex(ErroColeta, "proíbe"):
                cliente.obter(URL)
        self.assertEqual(len(sessao.chamadas), 1)

    def test_robots_ausente_e_registrado(self):
        for status in (404, 410):
            with self.subTest(status=status):
                sessao = SessaoFalsa([resposta(status), resposta(corpo="ok")])
                with ClientePublico(session=sessao) as cliente:
                    self.assertEqual(cliente.obter(URL).text, "ok")
                    regra = cliente.regras[0]
                    self.assertEqual(regra["status_http"], status)
                    self.assertEqual(regra["politica"], "ausente_acesso_permitido")

    def test_bloqueios_no_robots_falham_sem_nova_tentativa(self):
        for status in (401, 403, 429):
            with self.subTest(status=status):
                sessao = SessaoFalsa([resposta(status, headers={"Retry-After": "120"})])
                with ClientePublico(session=sessao) as cliente:
                    with self.assertRaisesRegex(ErroColeta, str(status)):
                        cliente.obter(URL)
                    self.assertEqual(cliente.regras[0]["status_http"], status)
                    self.assertEqual(
                        cliente.regras[0]["politica"], "falha_acesso_nao_verificado"
                    )
                self.assertEqual(len(sessao.chamadas), 1)

    def test_429_no_conteudo_reporta_retry_after_sem_repetir(self):
        sessao = SessaoFalsa(
            [resposta(404), resposta(429, headers={"Retry-After": "120"})]
        )
        with ClientePublico(session=sessao) as cliente:
            with self.assertRaisesRegex(ErroColeta, "Retry-After: 120"):
                cliente.obter(URL)
        self.assertEqual(len(sessao.chamadas), 2)

    def test_5xx_com_retry_after_encerra_sem_antecipar_prazo(self):
        for no_robots in (True, False):
            with self.subTest(no_robots=no_robots):
                indisponivel = resposta(503, headers={"Retry-After": "120"})
                resultados = [indisponivel] if no_robots else [resposta(404), indisponivel]
                sessao = SessaoFalsa(resultados)
                with ClientePublico(session=sessao) as cliente:
                    with self.assertRaisesRegex(ErroColeta, "Retry-After: 120"):
                        cliente.obter(URL)
                self.assertEqual(len(sessao.chamadas), 1 if no_robots else 2)

    def test_timeout_e_5xx_admitem_retry_limitado_no_robots(self):
        sessao = SessaoFalsa(
            [
                requests.Timeout("timeout simulado"),
                resposta(503),
                resposta(corpo="User-agent: *\nAllow: /\n"),
                resposta(corpo="ok"),
            ]
        )
        with ClientePublico(session=sessao, tentativas=3) as cliente:
            self.assertEqual(cliente.obter(URL).text, "ok")
            self.assertEqual(len(cliente.requisicoes), 4)
        self.assertEqual([c[0] for c in sessao.chamadas], [ROBOTS, ROBOTS, ROBOTS, URL])
        self.assertGreaterEqual(self.relogio.agora, 6)

    def test_retry_esgotado_nao_busca_conteudo(self):
        for resultados in (
            [resposta(503), resposta(503), resposta(503)],
            [requests.Timeout(), requests.Timeout(), requests.Timeout()],
        ):
            with self.subTest(tipo=type(resultados[0]).__name__):
                sessao = SessaoFalsa(resultados)
                with ClientePublico(session=sessao, tentativas=3) as cliente:
                    with self.assertRaisesRegex(ErroColeta, "após 3 tentativa"):
                        cliente.obter(URL)
                self.assertEqual(len(sessao.chamadas), 3)
                self.assertTrue(all(c[0] == ROBOTS for c in sessao.chamadas))

    def test_erro_nao_transitorio_nao_admite_retry(self):
        sessao = SessaoFalsa([requests.exceptions.InvalidURL("URL inválida simulada")])
        with ClientePublico(session=sessao) as cliente:
            with self.assertRaisesRegex(ErroColeta, "Falha HTTP"):
                cliente.obter(URL)
        self.assertEqual(len(sessao.chamadas), 1)

    def test_redirecionamentos_de_robots_e_conteudo_sao_recusados(self):
        for no_robots in (True, False):
            with self.subTest(no_robots=no_robots):
                redirecionamento = resposta(
                    302, headers={"Location": "https://outro.example/arquivo"}
                )
                resultados = [redirecionamento] if no_robots else [resposta(404), redirecionamento]
                sessao = SessaoFalsa(resultados)
                with ClientePublico(session=sessao) as cliente:
                    with self.assertRaisesRegex(ErroColeta, "Redirecionamento recusado"):
                        cliente.obter(URL)
                self.assertEqual(len(sessao.chamadas), 1 if no_robots else 2)

    def test_crawl_delay_e_request_rate(self):
        sessao = SessaoFalsa(
            [
                resposta(
                    corpo="User-agent: *\nAllow: /\nCrawl-delay: 5\nRequest-rate: 2/20\n"
                ),
                resposta(corpo="ok"),
                resposta(corpo="ok"),
            ]
        )
        with ClientePublico(session=sessao) as cliente:
            cliente.obter(URL)
            cliente.obter(URL)
            regra = cliente.regras[0]
            self.assertEqual(regra["crawl_delay"], 5)
            self.assertEqual(regra["request_rate"], {"requests": 2, "seconds": 20})
            self.assertEqual(regra["intervalo_aplicado_segundos"], 10)
        self.assertEqual(self.relogio.esperas, [10, 10])

    def test_intervalo_global_entre_origens(self):
        sessao = SessaoFalsa(
            [resposta(404), resposta(corpo="ok"), resposta(404), resposta(corpo="ok")]
        )
        with ClientePublico(session=sessao) as cliente:
            cliente.obter(URL)
            cliente.obter("https://bus2.info/41r5p")
            self.assertEqual(len(cliente.regras), 2)
        self.assertEqual(self.relogio.esperas, [2, 2, 2])

    def test_url_recusada_antes_de_qualquer_requisicao(self):
        invalidas = (
            "http://mobilibus.com/api/routes",
            "https://falsomobilibus.com/api/routes",
            "https://mobilibus.com.outro.example/",
            "https://usuario:segredo@mobilibus.com/",
            "https://mobilibus.com:444/",
            "https://mobilibus.com:invalida/",
            "https://mobilibus.com/#fragmento",
            "https://mobilibus.com/a b",
        )
        for url in invalidas:
            with self.subTest(url=url):
                sessao = SessaoFalsa([])
                with ClientePublico(session=sessao) as cliente:
                    with self.assertRaises(ErroColeta):
                        cliente.obter(url)
                self.assertEqual(sessao.chamadas, [])

    def test_html_ou_resposta_parcial_em_robots_nao_autoriza_acesso(self):
        for robot in (
            resposta(corpo="<html>erro</html>", headers={"Content-Type": "text/html"}),
            resposta(206, corpo="User-agent: *\nAllow: /\n"),
        ):
            with self.subTest(status=robot.status_code):
                sessao = SessaoFalsa([robot])
                with ClientePublico(session=sessao) as cliente:
                    with self.assertRaises(ErroColeta):
                        cliente.obter(URL)
                self.assertEqual(len(sessao.chamadas), 1)

    def test_robots_utf8_invalido_falha_fechado(self):
        robot = resposta()
        robot._content = b"User-agent: *\nDisallow: /\xffapi/\n"
        sessao = SessaoFalsa([robot])
        with ClientePublico(session=sessao) as cliente:
            with self.assertRaisesRegex(ErroColeta, "UTF-8"):
                cliente.obter(URL)
            self.assertIsNotNone(cliente.regras[0]["sha256"])
        self.assertEqual(len(sessao.chamadas), 1)

    def test_sintaxe_robots_nao_suportada_falha_fechado(self):
        for regra in (
            "Disallow: /api/*",
            "Disallow: /api/routes$",
            "Allow: /api/*",
            "Crawl-delay: 0.5",
            "Crawl-delay: desconhecido",
            "Request-rate: 1/0",
            "Request-rate: 10/60 0800-2000",
        ):
            with self.subTest(regra=regra):
                sessao = SessaoFalsa([resposta(corpo=f"User-agent: *\n{regra}\n")])
                with ClientePublico(session=sessao) as cliente:
                    with self.assertRaises(ErroColeta):
                        cliente.obter(URL)
                self.assertEqual(len(sessao.chamadas), 1)

    def test_allow_antes_de_disallow_nao_libera_caminho_proibido(self):
        sessao = SessaoFalsa(
            [resposta(corpo="User-agent: *\nAllow: /\nDisallow: /api/\n")]
        )
        with ClientePublico(session=sessao) as cliente:
            with self.assertRaisesRegex(ErroColeta, "sobrepostas"):
                cliente.obter(URL)
        self.assertEqual(len(sessao.chamadas), 1)

    def test_disallow_de_outro_caminho_nao_bloqueia_api(self):
        sessao = SessaoFalsa(
            [
                resposta(
                    corpo="User-agent: *\nDisallow: /wp-admin/\n"
                    "Allow: /wp-admin/admin-ajax.php\n"
                ),
                resposta(corpo="ok"),
            ]
        )
        with ClientePublico(session=sessao) as cliente:
            self.assertEqual(cliente.obter(URL).text, "ok")

    def test_limite_de_tamanho_declarado_e_real(self):
        for grande in (
            resposta(corpo="ok", headers={"Content-Length": "11"}),
            resposta(corpo="12345678901"),
        ):
            with self.subTest(headers=dict(grande.headers)):
                sessao = SessaoFalsa([resposta(404), grande])
                with patch("acesso_http.LIMITE_RESPOSTA", 10):
                    with ClientePublico(session=sessao) as cliente:
                        with self.assertRaisesRegex(ErroColeta, "limite"):
                            cliente.obter(URL)

    def test_cliente_fechado_nao_faz_requisicoes(self):
        sessao = SessaoFalsa([])
        cliente = ClientePublico(session=sessao)
        cliente.close()
        cliente.close()
        with self.assertRaisesRegex(ErroColeta, "fechado"):
            cliente.obter(URL)
        self.assertTrue(sessao.fechada)
        self.assertEqual(sessao.chamadas, [])


if __name__ == "__main__":
    unittest.main()
