"""Acesso sequencial às fontes públicas autorizadas do Busão Sanca.

O cliente verifica robots.txt antes do conteúdo, não segue redirecionamentos
e encerra em bloqueios de acesso. Uma resposta permitida por robots.txt não
constitui autorização para usos que contrariem os termos do fornecedor.
"""

from __future__ import annotations

import hashlib
import math
import re
import threading
import time
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import requests

USER_AGENT = "BusaoSanca/0.2 (+https://github.com/muvilani/busao_sanca)"
HOSTS_PERMITIDOS = frozenset(
    {"soutransportes.com.br", "bus2.info", "mobilibus.com"}
)
LIMITE_RESPOSTA = 10 * 1024 * 1024


class ErroColeta(Exception):
    """Falha explícita que impede tratar uma resposta como coleta válida."""


def _validar_url(url: str) -> tuple[str, str]:
    """Retorna a origem e a URL sem query para evidências sem credenciais."""
    try:
        partes = urlsplit(url)
        porta = partes.port
    except (TypeError, ValueError) as erro:
        raise ErroColeta("URL inválida para a coleta.") from erro
    if (
        partes.scheme != "https"
        or partes.hostname not in HOSTS_PERMITIDOS
        or partes.username is not None
        or partes.password is not None
        or porta not in (None, 443)
        or partes.fragment
        or any(caractere.isspace() for caractere in url)
    ):
        raise ErroColeta(
            "URL recusada: use HTTPS, host autorizado, sem credenciais ou fragmento."
        )
    origem = f"https://{partes.hostname}"
    evidencia = urlunsplit(("https", partes.hostname, partes.path or "/", "", ""))
    return origem, evidencia


def _validar_sintaxe_robots(conteudo: str) -> None:
    """Recusa extensões que RobotFileParser poderia ignorar silenciosamente."""
    for linha in conteudo.splitlines():
        sem_comentario = linha.split("#", 1)[0].strip()
        if ":" not in sem_comentario:
            continue
        campo, valor = sem_comentario.split(":", 1)
        campo, valor = campo.strip().lower(), valor.strip()
        if campo in ("allow", "disallow") and ("*" in valor or "$" in valor):
            raise ErroColeta(
                "robots.txt contém caminho com * ou $ não suportado; "
                "a política precisa de revisão antes da coleta."
            )
        if campo == "crawl-delay" and not re.fullmatch(r"[0-9]+", valor):
            raise ErroColeta(
                "Crawl-delay não inteiro ou inválido no robots.txt; "
                "a política precisa de revisão antes da coleta."
            )
        if campo == "request-rate":
            taxa = re.fullmatch(r"([0-9]+)/([0-9]+)", valor)
            if taxa is None or int(taxa[1]) <= 0 or int(taxa[2]) <= 0:
                raise ErroColeta(
                    "Request-rate não suportado no robots.txt; "
                    "a política precisa de revisão antes da coleta."
                )


def _verificar_sobreposicao(parser: RobotFileParser, url: str) -> None:
    """Não aceita um Allow que o parser priorize sobre um Disallow aplicável."""
    grupos = [grupo for grupo in parser.entries if grupo.applies_to(USER_AGENT)]
    if not grupos and parser.default_entry is not None:
        grupos = [parser.default_entry]
    regras_negadas = [
        f"Disallow: {regra.path}"
        for grupo in grupos
        for regra in grupo.rulelines
        if not regra.allowance
    ]
    restritivo = RobotFileParser()
    restritivo.parse(["User-agent: *", *regras_negadas])
    if not restritivo.can_fetch(USER_AGENT, url):
        raise ErroColeta(
            "Regras Allow/Disallow sobrepostas no robots.txt; "
            "a política precisa de revisão antes de acessar este caminho."
        )


class ClientePublico:
    """Cliente HTTP com regras e evidências consultáveis após a execução.

    ``tentativas`` inclui a primeira chamada. Falhas temporárias de conexão,
    timeout e HTTP 5xx admitem novas tentativas; 429 encerra imediatamente.
    ``regras`` guarda uma entrada por origem e ``requisicoes`` uma por tentativa.
    """

    def __init__(
        self,
        timeout: float = 30.0,
        intervalo: float = 2.0,
        tentativas: int = 3,
        session=None,
    ) -> None:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout deve ser um número positivo e finito.")
        if not math.isfinite(intervalo) or intervalo < 0:
            raise ValueError("intervalo deve ser um número não negativo e finito.")
        if isinstance(tentativas, bool) or not isinstance(tentativas, int) or tentativas < 1:
            raise ValueError("tentativas deve ser um inteiro positivo.")
        self.timeout = timeout
        self.intervalo = max(2.0, intervalo)
        self.tentativas = tentativas
        self.session = session if session is not None else requests.Session()
        self.regras: list[dict] = []
        self.requisicoes: list[dict] = []
        self._robots: dict[str, RobotFileParser | None] = {}
        self._intervalos: dict[str, float] = {}
        self._ultima_global: float | None = None
        self._ultimas_origem: dict[str, float] = {}
        self._lock = threading.Lock()
        self._fechado = False

    def __enter__(self) -> ClientePublico:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def close(self) -> None:
        """Fecha a sessão, inclusive quando recebida por injeção."""
        with self._lock:
            if not self._fechado:
                self.session.close()
                self._fechado = True

    def _aguardar(self, origem: str) -> None:
        agora = time.monotonic()
        proxima = agora
        if self._ultima_global is not None:
            proxima = max(proxima, self._ultima_global + self.intervalo)
        if origem in self._ultimas_origem:
            proxima = max(
                proxima,
                self._ultimas_origem[origem]
                + self._intervalos.get(origem, self.intervalo),
            )
        if proxima > agora:
            time.sleep(proxima - agora)
        momento = time.monotonic()
        self._ultima_global = momento
        self._ultimas_origem[origem] = momento

    def _carregar_corpo(self, resposta: requests.Response) -> None:
        tamanho_declarado = resposta.headers.get("Content-Length")
        if tamanho_declarado:
            try:
                if int(tamanho_declarado) > LIMITE_RESPOSTA:
                    raise ErroColeta("Resposta excede o limite de 10 MiB.")
            except ValueError as erro:
                raise ErroColeta("Content-Length inválido na resposta.") from erro
        partes = []
        total = 0
        for parte in resposta.iter_content(chunk_size=64 * 1024):
            total += len(parte)
            if total > LIMITE_RESPOSTA:
                raise ErroColeta("Resposta excede o limite de 10 MiB.")
            partes.append(parte)
        # Response mantém as APIs .text/.json após o fechamento do socket.
        resposta._content = b"".join(partes)
        resposta._content_consumed = True

    def _solicitar(self, url: str, *, robots: bool = False) -> requests.Response:
        origem, evidencia_url = _validar_url(url)
        for tentativa in range(1, self.tentativas + 1):
            if tentativa > 1:
                time.sleep(min(2 ** (tentativa - 2), 30))
            self._aguardar(origem)
            evidencia = {
                "url": evidencia_url,
                "tentativa": tentativa,
                "status_http": None,
            }
            self.requisicoes.append(evidencia)
            resposta = None
            try:
                resposta = self.session.get(
                    url,
                    headers={"User-Agent": USER_AGENT},
                    timeout=self.timeout,
                    allow_redirects=False,
                    stream=True,
                )
                status = resposta.status_code
                evidencia["status_http"] = status
                if 300 <= status < 400:
                    raise ErroColeta(
                        f"Redirecionamento recusado (HTTP {status}) em {evidencia_url}."
                    )
                if status == 429:
                    espera = resposta.headers.get("Retry-After")
                    detalhe = (
                        f" Retry-After: {' '.join(espera.split())[:120]}."
                        if espera
                        else ""
                    )
                    raise ErroColeta(
                        f"Limite de acesso (HTTP 429) em {evidencia_url}.{detalhe} "
                        "Coleta encerrada; não há tentativa de contornar o bloqueio."
                    )
                if status in (401, 403):
                    raise ErroColeta(
                        f"Acesso recusado (HTTP {status}) em {evidencia_url}."
                    )
                if 500 <= status < 600:
                    espera = resposta.headers.get("Retry-After")
                    if espera:
                        detalhe = " ".join(espera.split())[:120]
                        raise ErroColeta(
                            f"Servidor indisponível (HTTP {status}) em {evidencia_url}. "
                            f"Retry-After: {detalhe}. Coleta encerrada para respeitar "
                            "o prazo solicitado pelo servidor."
                        )
                    if tentativa < self.tentativas:
                        continue
                    raise ErroColeta(
                        f"Servidor indisponível (HTTP {status}) em {evidencia_url} "
                        f"após {tentativa} tentativa(s)."
                    )
                if robots and status in (404, 410):
                    resposta._content = b""
                    resposta._content_consumed = True
                    return resposta
                if not 200 <= status < 300:
                    raise ErroColeta(
                        f"Resposta HTTP {status} inesperada em {evidencia_url}."
                    )
                self._carregar_corpo(resposta)
                return resposta
            except (requests.Timeout, requests.ConnectionError) as erro:
                evidencia["erro"] = type(erro).__name__
                if tentativa == self.tentativas:
                    raise ErroColeta(
                        f"Falha de conexão ou timeout em {evidencia_url} "
                        f"após {tentativa} tentativa(s)."
                    ) from erro
            except requests.RequestException as erro:
                evidencia["erro"] = type(erro).__name__
                raise ErroColeta(f"Falha HTTP em {evidencia_url}.") from erro
            finally:
                if resposta is not None:
                    resposta.close()
        raise ErroColeta("A requisição terminou sem resposta válida.")

    def _verificar_robots(self, origem: str, url: str) -> None:
        if origem not in self._robots:
            robots_url = origem + "/robots.txt"
            evidencia = {
                "url": robots_url,
                "status_http": None,
                "politica": "nao_verificada",
                "sha256": None,
                "crawl_delay": None,
                "request_rate": None,
                "intervalo_aplicado_segundos": self.intervalo,
            }
            self.regras.append(evidencia)
            try:
                resposta = self._solicitar(robots_url, robots=True)
                evidencia["status_http"] = resposta.status_code
                if resposta.status_code in (404, 410):
                    evidencia["politica"] = "ausente_acesso_permitido"
                    self._robots[origem] = None
                else:
                    if resposta.status_code != 200:
                        raise ErroColeta("robots.txt deve responder HTTP 200, 404 ou 410.")
                    evidencia["sha256"] = hashlib.sha256(resposta.content).hexdigest()
                    try:
                        conteudo = resposta.content.decode("utf-8-sig")
                    except UnicodeDecodeError as erro:
                        raise ErroColeta(
                            "robots.txt não contém UTF-8 válido; política não verificada."
                        ) from erro
                    tipo = resposta.headers.get("Content-Type", "").lower()
                    if "text/html" in tipo or "<html" in conteudo.lower() or "<!doctype html" in conteudo.lower():
                        raise ErroColeta("robots.txt retornou HTML; política de acesso não verificada.")
                    _validar_sintaxe_robots(conteudo)
                    parser = RobotFileParser(robots_url)
                    parser.parse(conteudo.splitlines())
                    atraso = parser.crawl_delay(USER_AGENT)
                    taxa = parser.request_rate(USER_AGENT)
                    intervalo = self.intervalo
                    if atraso is not None:
                        intervalo = max(intervalo, atraso)
                    if taxa is not None:
                        if taxa.requests <= 0 or taxa.seconds <= 0:
                            raise ErroColeta("Request-rate inválido no robots.txt.")
                        intervalo = max(intervalo, taxa.seconds / taxa.requests)
                        evidencia["request_rate"] = {
                            "requests": taxa.requests,
                            "seconds": taxa.seconds,
                        }
                    evidencia.update(
                        politica="robots_txt",
                        crawl_delay=atraso,
                        intervalo_aplicado_segundos=intervalo,
                    )
                    self._intervalos[origem] = intervalo
                    self._robots[origem] = parser
            except ErroColeta:
                evidencia["politica"] = "falha_acesso_nao_verificado"
                if self.requisicoes and self.requisicoes[-1]["url"] == robots_url:
                    evidencia["status_http"] = self.requisicoes[-1]["status_http"]
                raise
        parser = self._robots[origem]
        if parser is not None and not parser.can_fetch(USER_AGENT, url):
            raise ErroColeta(f"robots.txt proíbe acesso ao caminho em {origem}.")
        if parser is not None:
            _verificar_sobreposicao(parser, url)

    def obter(self, url: str) -> requests.Response:
        """Obtém uma URL permitida, após verificar as regras de sua origem."""
        origem, _ = _validar_url(url)
        with self._lock:
            if self._fechado:
                raise ErroColeta("O cliente HTTP já foi fechado.")
            self._verificar_robots(origem, url)
            return self._solicitar(url)
