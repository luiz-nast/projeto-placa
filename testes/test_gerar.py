"""o gerador (gerar.py): o que o placa.txt aceita e recusa, as nets, e o formato dos arquivos de fábrica"""
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
