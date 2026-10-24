"""o gerador (gerar.py): o que o placa.txt aceita e recusa, as nets, e o formato dos arquivos de fábrica"""
import math
import re
import tempfile
import unittest
import warnings
from pathlib import Path

from apoio import PLACAS, modelo
import gerar

LANTERNA = (PLACAS / "lanterna" / "placa.txt").read_text()


class LeOTxt(unittest.TestCase):
    def erro(self, texto, trecho, linha=None):
        with self.assertRaises(gerar.ErroTxt) as c:
            gerar.ler(texto)
        self.assertIn(trecho, c.exception.msg)
        if linha:
            self.assertEqual(c.exception.linha, linha)

    def test_comando_desconhecido_diz_a_linha(self):
        self.erro("placa 10 10\npeça R1 resistor 1 1", "comando desconhecido", 2)

    def test_quantidade_de_valores(self):
        self.erro("placa 10", "espera 2 valores")
        self.erro("placa 10 10\npeca R1 resistor 1", "espera 4 ou 5 valores")
        self.erro("placa 10 10\nliga R1.1", "espera 2 valores")

    def test_sem_placa(self):
        self.erro("peca R1 resistor 1 1", "falta a linha 'placa")

    def test_ref_repetida_e_nome_ruim(self):
        self.erro("placa 10 10\npeca R1 resistor 1 1\npeca R1 resistor 2 2", "já existe na linha 2", 3)
        self.erro("placa 10 10\npeca 1R resistor 1 1", "não serve de nome")
        self.erro("placa 10 10\npeca R-1 resistor 1 1", "não serve de nome")
        self.erro("placa 10 10\nliga R1.1.2 GND", "devia ser REF.PINO")

    def test_numero_e_valor(self):
        self.erro("placa dez 10", "devia ser um número")
        self.erro("placa 10 10\npeca R1 resistor 1 1 abc", "devia ser um valor")
        self.erro("placa 10 10\npeca R1 resistor 1 1 0", "maior que zero")
        for txt, ohms in (("100", 100), ("4.7k", 4700), ("10k", 10000), ("1M", 1e6), ("220R", 220), ("330Ω", 330)):
            self.assertAlmostEqual(gerar.valor(txt, 1), ohms, msg=txt)

    def test_comentario_e_linha_vazia(self):
        lido = gerar.ler("# só comentário\n\nplaca 10 10   # fim de linha\n")
        self.assertEqual(lido["placa"]["w"], 10)


class Monta(unittest.TestCase):
    def test_lanterninha(self):
        m = modelo(LANTERNA)
        self.assertEqual([p["ref"] for p in m["pecas"]], ["BT1", "SW1", "R1", "D1"])
        nets = {f"{p['ref']}.{q['n']}": q["net"] for p in m["pecas"] for q in p["pinos"]}
        self.assertEqual(nets["BT1.1"], "VBAT")
        self.assertEqual(nets["BT1.2"], "GND")
        self.assertEqual(nets["D1.2"], "GND")
        self.assertEqual(nets["SW1.1"], nets["SW1.2"], "lado A do botão é um só por dentro")
        self.assertEqual(nets["SW1.3"], nets["R1.1"])
        self.assertNotEqual(nets["SW1.1"], nets["SW1.3"])
        self.assertEqual(len(m["trilhas"]), 4)
        self.assertTrue(m["simulacao"]["pode"])
        self.assertTrue(m["fabrica"]["pronta"])

    def test_tipo_que_nao_existe(self):
        with self.assertRaises(gerar.ErroTxt) as c:
            modelo("placa 10 10\npeca R1 resistor_de_ouro 1 1")
        self.assertEqual(c.exception.onde, ["R1"])

    def test_pino_que_nao_existe(self):
        with self.assertRaises(gerar.ErroTxt) as c:
            modelo(LANTERNA + "\nliga R1.9 GND")
        self.assertIn("não tem pino 9", c.exception.msg)

    def test_curto_entre_nets_com_nome(self):
        with self.assertRaises(gerar.ErroTxt) as c:
            modelo(LANTERNA + "\nliga BT1.1 GND")
        self.assertIn("curto", c.exception.msg)

    def test_nome_automatico_nao_pisa_no_do_luiz(self):
        m = modelo(LANTERNA + "\nliga SW1.4 N1")   # o Luiz chamou uma net de N1
        nomes = {q["net"] for p in m["pecas"] for q in p["pinos"] if q["net"]}
        self.assertIn("N1", nomes)
        self.assertEqual(len([n for n in nomes if n.startswith("N")]), len({n for n in nomes if n.startswith("N")}))

    def test_resistor_sem_valor_nao_simula(self):
        m = modelo(LANTERNA.replace("43 15 100", "43 15"))
        self.assertFalse(m["simulacao"]["pode"])
        self.assertEqual(m["simulacao"]["sem_valor"], ["R1"])

    def test_peca_de_exemplo_trava_a_fabrica(self):
        m = modelo("placa 30 20\npeca R1 resistor 10 10 100\npeca D1 led 20 10\nliga R1.2 D1.1")
        self.assertFalse(m["fabrica"]["pronta"])
        self.assertEqual(sorted(m["fabrica"]["falta_datasheet"]), ["D1", "R1"])


class ArquivosDeFabrica(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saida = Path(tempfile.mkdtemp(prefix="sianvolt-gerber-"))
        cls.m = modelo(LANTERNA)
        cls.nomes = gerar.escrever(cls.m, cls.saida)

    def test_os_8_arquivos_no_padrao_do_kicad(self):
        self.assertEqual(sorted(self.nomes), sorted([
            "placa-Edge_Cuts.gbr", "placa-F_Cu.gbr", "placa-B_Cu.gbr", "placa-F_Mask.gbr", "placa-B_Mask.gbr",
            "placa-F_Silkscreen.gbr", "placa-PTH.drl", "placa-NPTH.drl"]))

    def test_gerber_bem_formado(self):
        for nome in self.nomes:
            if not nome.endswith(".gbr"):
                continue
            t = (self.saida / nome).read_text()
            self.assertIn("%FSLAX46Y46*%", t, nome)
            self.assertIn("%MOMM*%", t, nome)
            self.assertTrue(t.rstrip().endswith("M02*"), nome)
            definidas = set(re.findall(r"%ADD(\d+)", t))
            usadas = set(re.findall(r"^D(\d+)\*$", t, re.M))
            self.assertTrue(usadas <= definidas, f"{nome}: abertura usada sem definir {usadas - definidas}")
            self.assertTrue(all(int(d) >= 10 for d in definidas), nome)
            for x, y in re.findall(r"X(-?\d+)Y(-?\d+)D0[123]", t):
                self.assertTrue(0 <= int(x) <= 52e6 and 0 <= int(y) <= 34e6, f"{nome}: ponto fora da placa")
        self.assertIn("Negative", (self.saida / "placa-F_Mask.gbr").read_text())

    def test_excellon_bem_formado(self):
        for nome in ("placa-PTH.drl", "placa-NPTH.drl"):
            linhas = (self.saida / nome).read_text().split("\n")
            self.assertEqual(linhas[0], "M48")
            self.assertIn("METRIC,TZ", linhas)
            self.assertLess(linhas.index("G90"), linhas.index("%"), "G90 tem que vir antes do %")
            self.assertEqual([l for l in linhas if l][-1], "M30")
        pth = (self.saida / "placa-PTH.drl").read_text()
        self.assertEqual(len(re.findall(r"^X", pth, re.M)), sum(len(p["pinos"]) for p in self.m["pecas"]))

    def test_gerbonara_le_sem_aviso(self):
        try:
            from gerbonara import LayerStack
        except ImportError:
            self.skipTest("gerbonara só no .venv")
        import testar
        with warnings.catch_warnings(record=True) as avisos:
            warnings.simplefilter("always")
            LayerStack.open_dir(self.saida, autoguess=False, overrides=testar.MAPA_GERBER)
        self.assertEqual(avisos, [])


class Roteador(unittest.TestCase):
    """o caminho das trilhas: reta quando dá, desvio (L, Z) ou troca de camada por via quando não dá"""

    def pino(self, x, y, net, furo=0.8, d=1.6):
        return {"x": x, "y": y, "net": net, "furo": furo, "pad": {"forma": "C", "d": d}}

    def folga_minima(self, trilhas, vias, pinos):
        import geometria
        menor = 99
        for t in trilhas:
            c = (("seg", (t["x1"], t["y1"]), (t["x2"], t["y2"])), t["largura"] / 2)
            for nome, p in pinos.items():
                if p["net"] != t["net"] and (p["furo"] or t["lado"] == "cima"):
                    menor = min(menor, geometria.distancia(c, geometria.do_pad(p["x"], p["y"], p["pad"])))
        return menor

    def test_lanterninha_continua_reta_e_em_cima(self):
        m = modelo(LANTERNA)
        self.assertEqual([(t["de"], t["ate"], t["lado"]) for t in m["trilhas"]],
                         [("BT1.1", "SW1.1", "cima"), ("SW1.3", "R1.1", "cima"), ("R1.2", "D1.1", "cima"), ("D1.2", "BT1.2", "cima")])
        self.assertEqual(m["vias"], [])

    def test_pad_de_furo_no_caminho_faz_desviar(self):
        pinos = {"A.1": self.pino(5, 10, "N1"), "B.1": self.pino(25, 10, "N1"), "X.1": self.pino(15, 10, "N2", d=2)}
        trilhas, vias = gerar.rotear([("A.1", "B.1", 1)], pinos, [], 30, 20)
        self.assertGreater(len(trilhas), 1)
        self.assertGreaterEqual(self.folga_minima(trilhas, vias, pinos), gerar.FOLGA_ROTA - 1e-9)
        self.assertEqual((trilhas[0]["x1"], trilhas[0]["y1"]), (5, 10))
        self.assertEqual((trilhas[-1]["x2"], trilhas[-1]["y2"]), (25, 10))

    def test_pad_de_superficie_no_caminho_passa_por_baixo(self):
        pinos = {"A.1": self.pino(5, 10, "N1"), "B.1": self.pino(25, 10, "N1"), "X.1": self.pino(15, 10, "N2", furo=None, d=2)}
        trilhas, vias = gerar.rotear([("A.1", "B.1", 1)], pinos, [], 30, 20)
        self.assertEqual([(t["lado"], t["y1"], t["y2"]) for t in trilhas], [("baixo", 10, 10)], "reta por baixo, sem via")

    def test_ponta_de_superficie_nao_comeca_embaixo(self):
        pinos = {"A.1": self.pino(5, 10, "N1", furo=None), "B.1": self.pino(25, 10, "N1"), "X.1": self.pino(15, 10, "N2", furo=None, d=2)}
        trilhas, vias = gerar.rotear([("A.1", "B.1", 1)], pinos, [], 30, 20)
        self.assertEqual(trilhas[0]["lado"], "cima")
        self.assertGreaterEqual(self.folga_minima(trilhas, vias, pinos), gerar.FOLGA_ROTA - 1e-9)
        for v in vias:
            self.assertGreaterEqual(math.dist((v["x"], v["y"]), (15, 10)), 1 + gerar.VIA_PAD / 2)

    def test_parede_sem_saida_fica_a_reta(self):
        pinos = {"A.1": self.pino(5, 10, "N1"), "B.1": self.pino(25, 10, "N1")}
        for i, y in enumerate(range(0, 21)):   # uma parede de pads de outra net de cima a baixo
            pinos[f"X.{i}"] = self.pino(15, y, "N2", d=1.4)
        trilhas, _, falhas = gerar.rotear_uma_vez([("A.1", "B.1", 1)], pinos, [], 30, 20)
        self.assertEqual(len(falhas), 1)
        self.assertEqual([(t["x1"], t["x2"], t["lado"]) for t in trilhas], [(5, 25, "cima")])

    def test_parede_de_superficie_faz_trocar_de_lado_e_o_gerber_mostra(self):
        # A e B são de superfície (só têm cobre em cima) e uma parede de pads de superfície fecha o lado de cima inteiro:
        # o único caminho é descer por uma via, passar por baixo da parede e subir por outra
        linhas = ["placa 30 20", "peca A resistor 5 10", "peca B resistor 25 10", "liga A.2 B.1"]
        linhas += [f"peca W{i} resistor 15 {1.5 + 1.6 * i:.1f}" for i in range(11)]
        m = modelo("\n".join(linhas))
        self.assertEqual(len(m["vias"]), 2)
        self.assertEqual([t["lado"] for t in m["trilhas"]][0], "cima")
        self.assertEqual([t["lado"] for t in m["trilhas"]][-1], "cima")
        self.assertIn("baixo", [t["lado"] for t in m["trilhas"]])
        import testar
        self.assertEqual(testar.pares_perto(m, testar.ESPACO_MIN), [], "nada perto demais em nenhuma camada")
        saida = Path(tempfile.mkdtemp(prefix="sianvolt-via-"))
        gerar.escrever(m, saida)
        embaixo = (saida / "placa-B_Cu.gbr").read_text()
        self.assertGreaterEqual(embaixo.count("D01*"), sum(1 for t in m["trilhas"] if t["lado"] == "baixo"))
        furos = (saida / "placa-PTH.drl").read_text()
        for v in m["vias"]:
            self.assertIn(f"X{v['x']:.3f}Y{v['y']:.3f}", furos)
            self.assertIn(f"X{round(v['x'] * 1e6)}Y{round(v['y'] * 1e6)}D03", embaixo)
            self.assertNotIn(f"X{round(v['x'] * 1e6)}Y{round(v['y'] * 1e6)}D03", (saida / "placa-F_Mask.gbr").read_text(),
                             "via fica coberta pela máscara")
        try:
            from gerbonara import LayerStack
            import warnings
            with warnings.catch_warnings(record=True) as avisos:
                warnings.simplefilter("always")
                LayerStack.open_dir(saida, autoguess=False, overrides=testar.MAPA_GERBER)
            self.assertEqual(avisos, [])
        except ImportError:
            pass


class Versoes(unittest.TestCase):
    def test_frases_do_que_mudou(self):
        self.assertEqual(gerar.o_que_mudou(None, LANTERNA), "primeira versão")
        self.assertEqual(gerar.o_que_mudou(LANTERNA, LANTERNA + "\n# oi"), "só comentários")
        self.assertIn("moveu R1", gerar.o_que_mudou(LANTERNA, LANTERNA.replace("R1 resistor_axial 43 15", "R1 resistor_axial 40 15")))
        self.assertIn("trocou R1 pra 220 Ω", gerar.o_que_mudou(LANTERNA, LANTERNA.replace("43 15 100", "43 15 220")))
        self.assertIn("tirou o valor de R1", gerar.o_que_mudou(LANTERNA, LANTERNA.replace("43 15 100", "43 15")))
        self.assertIn("adicionou R2", gerar.o_que_mudou(LANTERNA, LANTERNA + "\npeca R2 resistor_axial 10 5 1k"))
        self.assertIn("desligou", gerar.o_que_mudou(LANTERNA, LANTERNA.replace("liga D1.2 GND\n", "")))
        self.assertEqual(gerar.o_que_mudou(LANTERNA, LANTERNA.replace("liga R1.2 D1.1", "liga D1.1 R1.2")), "só comentários",
                         "liga A B é o mesmo que liga B A")


if __name__ == "__main__":
    unittest.main()
