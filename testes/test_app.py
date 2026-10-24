"""o app (app.py): só serve o que deve, só pra esta máquina, e só aceita pedido que veio dele mesmo"""
import http.client
import json
import threading
import unittest
from functools import partial
from http.server import ThreadingHTTPServer

from apoio import PLACAS, RAIZ
import app

HOST = "127.0.0.1:8765"   # o app confere o cabeçalho Host; a porta de verdade aqui é outra


class App(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.placas_de_verdade, app.PLACAS = app.PLACAS, PLACAS   # só a placa de teste (o clone limpo não tem placas/)
        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 0), partial(app.Bancada, directory=str(RAIZ)))
        cls.porta = cls.servidor.server_address[1]
        threading.Thread(target=cls.servidor.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        app.PLACAS = cls.placas_de_verdade

    def pedir(self, metodo, caminho, corpo=None, cabecalhos=None):
        c = http.client.HTTPConnection("127.0.0.1", self.porta, timeout=20)
        c.putrequest(metodo, caminho, skip_host=True, skip_accept_encoding=True)   # caminho cru, sem normalizar
        for k, v in {"Host": HOST, **(cabecalhos or {})}.items():
            c.putheader(k, v)
        dado = corpo.encode() if isinstance(corpo, str) else corpo
        if dado is not None:
            c.putheader("Content-Length", str(len(dado)))
        c.endheaders(dado)
        r = c.getresponse()
        texto = r.read()
        c.close()
        return r.status, texto

    def test_pagina_e_api(self):
        self.assertEqual(self.pedir("GET", "/")[0], 302)
        self.assertEqual(self.pedir("GET", "/bancada/index.html")[0], 200)
        status, texto = self.pedir("GET", "/api/placas")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(texto)["raiz"], str(RAIZ))
        self.assertEqual(json.loads(texto)["placas"], ["lanterna"])
        status, texto = self.pedir("GET", "/api/catalogo")
        d = json.loads(texto)
        self.assertGreater(len(d["pecas"]), 1000)
        self.assertEqual(d["grupos"][0], "Passivos")

    def test_nao_sai_da_bancada_e_das_placas(self):
        for caminho in ("/bancada/../.git/HEAD", "/bancada/%2e%2e/.git/HEAD", "/placas/../ferramenta/app.py",
                        "/placas/%2e%2e/%2e%2e/etc/passwd", "/.git/HEAD", "/ferramenta/app.py", "/bancada/../../../etc/passwd"):
            self.assertEqual(self.pedir("GET", caminho)[0], 404, caminho)
            self.assertEqual(self.pedir("HEAD", caminho)[0], 404, f"HEAD {caminho}")

    def test_host_de_outro_site_e_barrado(self):
        for metodo in ("GET", "POST"):
            self.assertEqual(self.pedir(metodo, "/api/placas", cabecalhos={"Host": "evil.com"})[0], 403)
        self.assertEqual(self.pedir("GET", "/api/placas", cabecalhos={"Host": "127.0.0.1:8765.evil.com"})[0], 403)

    def test_post_so_com_o_cabecalho_do_app(self):
        self.assertEqual(self.pedir("POST", "/api/testar?placa=lanterna", "{}")[0], 404)
        self.assertEqual(self.pedir("POST", "/api/qualquer", "{}", {"X-Bancada": "1"})[0], 404)

    def test_post_com_dado_ruim(self):
        x = {"X-Bancada": "1"}
        self.assertEqual(self.pedir("POST", "/api/testar?placa=nao_existe", "{}", x)[0], 404)
        self.assertEqual(self.pedir("POST", "/api/testar?placa=..", "{}", x)[0], 404)
        self.assertEqual(self.pedir("POST", "/api/escolher?placa=lanterna", "isto não é json", x)[0], 400)
        self.assertEqual(self.pedir("POST", "/api/escolher?placa=lanterna", "[1, 2]", x)[0], 400)
        self.assertEqual(self.pedir("POST", "/api/escolher?placa=lanterna", "{" + " " * 20000 + "}", x)[0], 400)
        self.assertEqual(self.pedir("POST", "/api/escolher?placa=lanterna", json.dumps({"ref": "R1", "codigo": "../x"}), x)[0], 400)
        self.assertEqual(self.pedir("POST", "/api/escolher?placa=lanterna", json.dumps({"ref": "R1;rm", "codigo": "C1"}), x)[0], 400)
        self.assertEqual(self.pedir("POST", "/api/catalogo/buscar", json.dumps({"bloco": "../../etc", "texto": "x"}), x)[0], 400)

    def test_get_com_dado_ruim(self):
        self.assertEqual(self.pedir("GET", "/api/foto?codigo=../../etc/passwd")[0], 400)
        self.assertEqual(self.pedir("GET", "/api/projeto?placa=%00")[0], 404)
        self.assertEqual(self.pedir("GET", "/api/opcoes?placa=..&ref=R1")[0], 404)

    def test_placa_so_dentro_de_placas(self):
        self.assertIsNone(app.placa(".."))
        self.assertIsNone(app.placa("../ferramenta"))
        self.assertIsNone(app.placa("\x00"))
        self.assertIsNone(app.placa(""))


if __name__ == "__main__":
    unittest.main()
