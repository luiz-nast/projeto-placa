"""o simulador existe em duas línguas (circuito.py e simular() no app); elas têm que dar o mesmo número"""
import json
import random
import re
import shutil
import subprocess
import unittest

from apoio import LED, PILHA, RAIZ, RESISTOR, CHAVE, peca
import circuito

NODE = shutil.which("node")


def js_do_app():
    """o pedaço do index.html com o simulador (de 'const GMIN' até antes de 'const mA')"""
    html = (RAIZ / "bancada" / "index.html").read_text()
    return html[html.index("const GMIN"):html.index("const mA =")]


def sortear(rnd):
    nets = ["GND"] + [f"N{i}" for i in range(1, rnd.randint(2, 6))]
    pilha = {**PILHA, "r_interna": rnd.choice([0, 5, 12])}
    pecas = [peca("BT1", pilha, {"1": nets[1], "2": "GND"})]
    for i in range(rnd.randint(2, 9)):
        a, b = rnd.sample(nets, 2)
        sorteio = rnd.random()
        if sorteio < 0.25:
            led = LED if rnd.random() < 0.5 else {**LED, "mais": "2", "menos": "1"}
            pecas.append(peca(f"D{i}", led, {"1": a, "2": b}))
        elif sorteio < 0.35:
            pecas.append(peca(f"SW{i}", CHAVE, {"1": a, "2": a, "3": b, "4": b}))
        else:
            pecas.append(peca(f"R{i}", RESISTOR, {"1": a, "2": b}, valor=rnd.choice([10, 47, 100, 220, 1000, 4700])))
    aj = {"pilha": {"BT1": rnd.uniform(1.5, 3.3)}, "resistor": {},
          "chave": {p["ref"]: rnd.random() < 0.6 for p in pecas if p["ref"].startswith("SW")}}
    return {"pecas": pecas}, aj


@unittest.skipUnless(NODE, "precisa do node (brew install node)")
class MesmaConta(unittest.TestCase):
    def test_300_circuitos_sorteados(self):
        rnd = random.Random(7)
        casos = [sortear(rnd) for _ in range(300)]
        programa = js_do_app() + """
const casos = JSON.parse(require('fs').readFileSync(0, 'utf8'));
console.log(JSON.stringify(casos.map(([m, aj]) => simular(m, aj))));"""
        r = subprocess.run([NODE, "-e", programa], input=json.dumps(casos), capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        js = json.loads(r.stdout)
        for k, ((m, aj), s_js) in enumerate(zip(casos, js)):
            s_py = circuito.resolver(m, aj)
            for ref, p_py in s_py["pecas"].items():
                p_js = s_js["pecas"][ref]
                for campo in ("i", "p", "v"):
                    if campo in p_py:
                        self.assertAlmostEqual(p_py[campo], p_js[campo], delta=1e-9 + 1e-7 * abs(p_py[campo]),
                                               msg=f"caso {k}, {ref}.{campo}")
                for campo in ("acende", "queima", "forte", "apertada"):
                    if campo in p_py:
                        self.assertEqual(p_py[campo], p_js[campo], f"caso {k}, {ref}.{campo}")

    def test_brilho_igual_nas_duas(self):
        import blocos
        led = {"brilho": [[0.001, 0], [0.005, 0.32], [0.010, 0.60], [0.020, 1.0], [0.030, 1.36]]}
        correntes = [0, 0.0005, 0.001, 0.003, 0.0075, 0.012, 0.02, 0.025, 0.05]
        programa = js_do_app() + f"\nconsole.log(JSON.stringify({json.dumps(correntes)}.map(i => brilhoDaCorrente({json.dumps(led)}, i))));"
        r = subprocess.run([NODE, "-e", programa], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr[-1000:])
        for i, b_js in zip(correntes, json.loads(r.stdout)):
            self.assertAlmostEqual(blocos.brilho_da_corrente(led, i), b_js, places=9, msg=str(i))


if __name__ == "__main__":
    unittest.main()
