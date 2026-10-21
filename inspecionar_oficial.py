"""Diagnóstico opcional da página oficial, com Chrome e JavaScript ativo.

Uso (depois de instalar Playwright): python inspecionar_oficial.py
Gera HTML renderizado, links e screenshot para adaptação do scraper.
Não executa cliques automáticos nem contorna barreiras do site.
"""

import csv
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://soutransportes.com.br/sao-carlos/linhas-e-horarios/"
SAIDA = Path(__file__).resolve().parent / "saida"
SAIDA.mkdir(exist_ok=True)

with sync_playwright() as p:
    try:
        browser = p.chromium.launch(channel="chrome", headless=False)
    except Exception:
        print("Chrome não encontrado. Tentando Chromium do Playwright...")
        browser = p.chromium.launch(headless=False)

    page = browser.new_page(viewport={"width": 1366, "height": 900}, locale="pt-BR")
    try:
        page.goto(URL, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(6000)
        page.mouse.wheel(0, 3000)
        page.wait_for_timeout(1500)
        page.mouse.wheel(0, -3000)
        page.wait_for_timeout(1000)

        print("Página renderizada:", page.url)
        (SAIDA / "oficial_renderizada.html").write_text(page.content(), encoding="utf-8")
        (SAIDA / "texto_renderizado.txt").write_text(page.locator("body").inner_text(), encoding="utf-8")
        page.screenshot(path=str(SAIDA / "oficial.png"), full_page=True)

        links = []
        for quadro in page.frames:
            try:
                for item in quadro.locator("a[href]").evaluate_all(
                    "els => els.map(a => ({texto: a.innerText.trim(), url: a.href}))"
                ):
                    links.append({"quadro": quadro.url, **item})
            except Exception as erro:
                print("Quadro não disponível:", erro)

        with (SAIDA / "links_renderizados.csv").open("w", newline="", encoding="utf-8-sig") as arq:
            escritor = csv.DictWriter(arq, fieldnames=["quadro", "texto", "url"])
            escritor.writeheader()
            escritor.writerows(links)
        print(f"Links renderizados: {len(links)}")
        print("Veja os arquivos na pasta 'saida'.")
    except Exception as erro:
        print("Erro ao carregar/inspecionar a página:", erro)
    finally:
        browser.close()
