from __future__ import annotations

import functools
import http.server
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

import preparar_publicacao


RAIZ = Path(__file__).resolve().parents[1]


def localizar_navegador() -> str | None:
    candidatos = [
        os.environ.get("BUSAO_BROWSER"),
        shutil.which("msedge"),
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    return next((item for item in candidatos if item and Path(item).is_file()), None)


class HandlerSilencioso(http.server.SimpleHTTPRequestHandler):
    def log_message(self, formato, *args):
        pass


class BrowserFuncionalTests(unittest.TestCase):
    @unittest.skipUnless(localizar_navegador(), "Edge/Chrome/Chromium não disponível")
    def test_fluxos_mobile_no_navegador_real(self):
        navegador = localizar_navegador()
        with tempfile.TemporaryDirectory() as temporario:
            base = Path(temporario)
            dist = base / "dist"
            perfil = base / "perfil"
            preparar_publicacao.preparar(dist)
            shutil.copyfile(RAIZ / "tests" / "browser_harness.js", dist / "browser_harness.js")
            indice = dist / "index.html"
            html = indice.read_text(encoding="utf-8")
            html = html.replace(
                '<script src="planejador.js" defer></script>',
                '<script src="browser_harness.js"></script>\n  <script src="planejador.js" defer></script>',
            )
            indice.write_text(html, encoding="utf-8")

            servidor = http.server.ThreadingHTTPServer(
                ("127.0.0.1", 0),
                functools.partial(HandlerSilencioso, directory=str(dist)),
            )
            thread = threading.Thread(target=servidor.serve_forever)
            thread.start()
            try:
                resultado = subprocess.run(
                    [
                        navegador,
                        "--headless=new",
                        "--disable-gpu",
                        "--no-first-run",
                        f"--user-data-dir={perfil}",
                        "--dump-dom",
                        "--virtual-time-budget=10000",
                        "--window-size=390,844",
                        f"http://127.0.0.1:{servidor.server_port}",
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                    check=False,
                )
            finally:
                servidor.shutdown()
                servidor.server_close()
                thread.join()

            self.assertEqual(resultado.returncode, 0, resultado.stderr[-2000:])
            self.assertIn('id="browser-test-results"', resultado.stdout)
            self.assertIn('data-status="ok"', resultado.stdout)
            self.assertIn('data-falhas=""', resultado.stdout)
            self.assertIn('data-erros=""', resultado.stdout)


if __name__ == "__main__":
    unittest.main()
