"""blocos.py: números da loja, a conta do brilho e o projeto (perguntas, carrinho, placa.txt)"""
import json
import unittest

from apoio import LED, PILHA, apagar, copia
import blocos

LED_LOJA = {**LED, "vf": 1.97, "r_s": 3.5, "i_teste": 0.020,
            "brilho": [[0.001, 0], [0.005, 0.32], [0.010, 0.60], [0.015, 0.83], [0.020, 1.0], [0.025, 1.2], [0.030, 1.36]]}
CR2032 = {**PILHA, "r_interna": 10}


class NumerosDaLoja(unittest.TestCase):
    def test_numero_com_unidade(self):
        casos = [("100Ω", "Ω", 100), ("4.7kΩ", "Ω", 4700), ("1MΩ", "Ω", 1e6), ("250mW", "W", 0.25), ("1W", "W", 1),
                 ("20mA", "A", 0.02), ("100nF", "F", 1e-7), ("abc", "Ω", None), (None, "Ω", None)]
        for txt, u, esperado in casos:
            v = blocos.numero_com_unidade(txt, u)
            if esperado is None:
                self.assertIsNone(v, txt)
            else:
                self.assertAlmostEqual(v, esperado, msg=txt)

    def test_ohms_txt(self):
        for o, txt in ((0, "0 Ω (jumper)"), (2.2, "2,2 Ω"), (240, "240 Ω"), (4700, "4,7 kΩ"), (1e6, "1 MΩ"), (None, "?")):
            self.assertEqual(blocos.ohms_txt(o), txt)

    def test_valor_comercial_mais_perto(self):
        for pedido, e24 in ((253, 240), (131, 130), (41.5, 43), (1000, 1000), (11.6, 12), (95, 91)):
            self.assertEqual(blocos.mais_perto(pedido), e24)

    def test_tamanho_do_pacote(self):
        self.assertEqual(blocos.tamanho("Plugin,D2.3xL6.5mm"), "corpo de 6,5 × 2,3 mm")
        self.assertEqual(blocos.tamanho("Plugin-4P,6x6mm"), "6 × 6 mm")
        self.assertEqual(blocos.tamanho("Plugin,D=5mm"), "5 mm de diâmetro")
        self.assertEqual(blocos.tamanho("-"), "")


class ContaDoBrilho(unittest.TestCase):
    def test_curva_ida_e_volta(self):
        for fracao in (0.1, 0.25, 0.5, 0.75, 1.0, 1.3):
            i = blocos.corrente_do_brilho(LED_LOJA, fracao)
            self.assertAlmostEqual(blocos.brilho_da_corrente(LED_LOJA, i), fracao, places=6)
        self.assertEqual(blocos.brilho_da_corrente(LED_LOJA, 0.0005), 0)
        self.assertEqual(blocos.brilho_da_corrente(LED_LOJA, 0.050), 1.36, "acima da curva não inventa")
        self.assertIsNone(blocos.corrente_do_brilho(LED, 0.5), "LED sem curva não tem conta")

    def test_nivel_mais_perto(self):
        self.assertEqual(blocos.nivel_do_brilho(0.27), "fraca")
        self.assertEqual(blocos.nivel_do_brilho(0.40), "media")
        self.assertEqual(blocos.nivel_do_brilho(0.80), "forte")

    def test_lanterninha_fraca_media_forte(self):
        esperado = {"fraca": 240, "media": 120, "forte": 43}
        for nivel, ohms in esperado.items():
            c = blocos.conta_do_freio(CR2032, LED_LOJA, blocos.PERGUNTAS["brilho"]["opcoes"][nivel]["fracao"])
            self.assertEqual(c["padrao"], ohms, nivel)
            self.assertEqual(blocos.nivel_do_brilho(c["brilho"]), nivel, f"{nivel}: o resistor de loja ainda dá o nível pedido")
            i = (CR2032["v"] - c["joelho"]) / (c["padrao"] + LED_LOJA["r_s"] + 10)
            self.assertAlmostEqual(c["i_padrao"], i)

    def test_pilha_fraca_demais(self):
        c = blocos.conta_do_freio({**CR2032, "v": 1.5}, LED_LOJA, 0.5)
        self.assertTrue(c["impossivel"])


class Projeto(unittest.TestCase):
    def setUp(self):
        self.pasta = copia()
        (self.pasta / "projeto.json").write_text(json.dumps({
            "objetivo": "teste", "perguntas": {},
            "blocos": [{"ref": "BT1", "bloco": "pilha"}, {"ref": "R1", "bloco": "resistor"}, {"ref": "D1", "bloco": "led"}]}))

    def tearDown(self):
        apagar(self.pasta)

    def test_responder_valida(self):
        blocos.responder(self.pasta, "brilho", "media")
        self.assertEqual(blocos.ler_projeto(self.pasta)["perguntas"]["brilho"]["resposta"], "media")
        with self.assertRaises(ValueError):
            blocos.responder(self.pasta, "brilho", "cegante")
        with self.assertRaises(ValueError):
            blocos.responder(self.pasta, "volume", "alto")

    def test_estado_sem_pecas_pede_o_que_falta(self):
        e = blocos.estado(self.pasta)
        self.assertFalse(e["pronto"])
        conta = next(b for b in e["blocos"] if b["ref"] == "R1")["conta"]
        self.assertIn("responder quanta luz você quer", conta["falta"])

    def test_trocar_no_txt_so_mexe_na_linha_certa(self):
        antes = (self.pasta / "placa.txt").read_text()
        self.assertTrue(blocos.trocar_no_txt(self.pasta, "R1", "C119310", "Resistor 240 Ω"))
        depois = (self.pasta / "placa.txt").read_text()
        self.assertIn("peca R1 C119310 43 15   # Resistor 240 Ω, escolhido no carrinho", depois)
        self.assertEqual([l for l in antes.splitlines() if "R1 " not in l or not l.startswith("peca")],
                         [l for l in depois.splitlines() if "R1 " not in l or not l.startswith("peca")])
        self.assertFalse(blocos.trocar_no_txt(self.pasta, "R9", "C1", "x"), "ref que não está na placa")

    def test_tipos_no_txt(self):
        self.assertEqual(blocos.tipos_no_txt(self.pasta)["D1"], "led_5mm")


if __name__ == "__main__":
    unittest.main()
