"""o simulador (circuito.py): contas que dá pra fazer à mão, e leis que valem pra qualquer circuito (sorteado)"""
import random
import unittest

from apoio import CHAVE, LED, PILHA, RESISTOR, peca
import circuito


def resolver(pecas, ajustes=None):
    return circuito.resolver({"pecas": pecas}, ajustes)


class ContasAMao(unittest.TestCase):
    def serie(self, v=3.0, ohms=100.0, led=LED, pilha=PILHA, invertido=False):
        a, k = ("N2", "GND") if not invertido else ("GND", "N2")
        return resolver([peca("BT1", pilha, {"1": "N1", "2": "GND"}),
                         peca("R1", RESISTOR, {"1": "N1", "2": "N2"}, valor=ohms),
                         peca("D1", led, {"1": a, "2": k})], {"pilha": {"BT1": v}})

    def test_lanterninha_da_conta_do_papel(self):
        # I = (pilha − joelho) / (R + r_s + a resistência mínima da pilha); joelho = vf − r_s·i_teste = 1,9 − 0,2 = 1,7 V
        s = self.serie()
        esperado = (3.0 - 1.7) / (100 + 20 + circuito.R_PILHA)
        self.assertAlmostEqual(s["pecas"]["D1"]["i"], esperado, delta=1e-6)
        self.assertAlmostEqual(s["pecas"]["R1"]["i"], esperado, delta=1e-6)
        self.assertAlmostEqual(s["pecas"]["R1"]["p"], esperado ** 2 * 100, delta=1e-7)
        self.assertTrue(s["pecas"]["D1"]["acende"])
        self.assertFalse(s["pecas"]["D1"]["queima"])

    def test_resistencia_interna_da_pilha_entra_na_conta(self):
        s = self.serie(pilha={**PILHA, "r_interna": 10})
        self.assertAlmostEqual(s["pecas"]["D1"]["i"], (3.0 - 1.7) / (100 + 20 + 10), delta=1e-6)

    def test_pilha_abaixo_do_joelho_nao_acende(self):
        s = self.serie(v=1.6)
        self.assertEqual(s["pecas"]["D1"]["i"], 0.0)
        self.assertFalse(s["pecas"]["D1"]["acende"])

    def test_led_ao_contrario_nao_passa_corrente(self):
        s = self.serie(invertido=True)
        self.assertEqual(s["pecas"]["D1"]["i"], 0.0)
        self.assertAlmostEqual(s["pecas"]["R1"]["i"], 0.0, delta=1e-6)

    def test_resistor_pequeno_queima_o_led(self):
        s = self.serie(v=3.3, ohms=10)
        self.assertTrue(s["pecas"]["D1"]["queima"])

    def test_led_da_loja_com_mais_e_menos_trocados(self):
        led = {**LED, "mais": "2", "menos": "1"}   # como o C779439: pino 2 é o +
        s = resolver([peca("BT1", PILHA, {"1": "N1", "2": "GND"}), peca("R1", RESISTOR, {"1": "N1", "2": "N2"}, valor=100),
                      peca("D1", led, {"2": "N2", "1": "GND"})])
        self.assertGreater(s["pecas"]["D1"]["i"], 0.01)

    def test_chave_solta_abre_e_apertada_fecha(self):
        pecas = [peca("BT1", PILHA, {"1": "N1", "2": "GND"}), peca("SW1", CHAVE, {"1": "N1", "2": "N1", "3": "N2", "4": "N2"}),
                 peca("R1", RESISTOR, {"1": "N2", "2": "N3"}, valor=100), peca("D1", LED, {"1": "N3", "2": "GND"})]
        self.assertEqual(resolver(pecas, {"chave": {"SW1": False}})["pecas"]["D1"]["i"], 0.0)
        self.assertGreater(resolver(pecas, {"chave": {"SW1": True}})["pecas"]["D1"]["i"], 0.01)

    def test_pino_sem_net_nao_quebra(self):
        s = resolver([peca("BT1", PILHA, {"1": "N1", "2": "GND"}), peca("R1", RESISTOR, {"1": "N1", "2": None}, valor=100)])
        self.assertEqual(s["pecas"]["R1"]["i"], 0.0)

    def test_duas_pilhas_em_paralelo(self):
        s = resolver([peca("BT1", PILHA, {"1": "N1", "2": "GND"}), peca("BT2", PILHA, {"1": "N1", "2": "GND"}),
                      peca("R1", RESISTOR, {"1": "N1", "2": "GND"}, valor=300)])
        self.assertAlmostEqual(s["pecas"]["BT1"]["i"] + s["pecas"]["BT2"]["i"], 3.0 / 300, delta=1e-6)

    def test_sem_pilha_nao_tem_o_que_ligar(self):
        self.assertIsNone(resolver([peca("R1", RESISTOR, {"1": "N1", "2": "GND"}, valor=100)]))


class LeisComCircuitoSorteado(unittest.TestCase):
    """200 circuitos sorteados: a corrente que entra numa net sai dela, e a pilha entrega o que as peças gastam"""

    def sortear(self, rnd):
        nets = ["GND"] + [f"N{i}" for i in range(1, rnd.randint(2, 6))]
        pecas = [peca("BT1", {**PILHA, "r_interna": rnd.choice([0, 5, 12])}, {"1": nets[1], "2": "GND"})]
        for i in range(rnd.randint(2, 9)):
            a, b = rnd.sample(nets, 2)
            if rnd.random() < 0.3:
                pecas.append(peca(f"D{i}", LED, {"1": a, "2": b}))
            else:
                pecas.append(peca(f"R{i}", RESISTOR, {"1": a, "2": b}, valor=rnd.choice([47, 100, 220, 1000, 4700])))
        return pecas, rnd.uniform(2.0, 3.3)

    def test_kirchhoff_e_energia(self):
        rnd = random.Random(2026)
        for _ in range(200):
            pecas, v = self.sortear(rnd)
            s = resolver(pecas, {"pilha": {"BT1": v}})
            soma = {}
            for p in pecas:
                for pino in p["pinos"]:
                    soma[pino["net"]] = soma.get(pino["net"], 0) + s["entra"].get(f"{p['ref']}.{pino['n']}", 0)
            for net, i in soma.items():
                self.assertAlmostEqual(i, 0, delta=1e-5, msg=f"net {net} não fecha: {i}")
            entregue = s["pecas"]["BT1"]["i"] * s["pecas"]["BT1"]["v"]
            gasto = sum(r.get("p", 0) for r in s["pecas"].values())
            gasto += sum(r["i"] * r["v"] for ref, r in s["pecas"].items() if ref.startswith("D"))
            gasto += s["pecas"]["BT1"]["i"] ** 2 * circuito.r_pilha(pecas[0]["eletrica"])
            self.assertAlmostEqual(entregue, gasto, delta=1e-4 + 1e-3 * abs(entregue))
            for ref, r in s["pecas"].items():
                if ref.startswith("D"):
                    self.assertGreaterEqual(r["i"], 0, "LED não conduz ao contrário")


if __name__ == "__main__":
    unittest.main()
