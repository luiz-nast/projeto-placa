"""fuzz: texto sorteado e placas mutadas. Pode dar erro, mas sempre um erro de gente (ErroTxt, Falhou, Pulou), nunca um crash"""
import random
import re
import unittest

from apoio import PLACAS, apagar, copia
import gerar
import testar

LANTERNA = (PLACAS / "lanterna" / "placa.txt").read_text()
PALAVRAS = ["placa", "furos", "cantos", "peca", "liga", "R1", "D1", "SW1", "BT1", "GND", "VBAT", "N1", "R1.1", "D1.2", "SW1.3",
            "BT1.9", "resistor_axial", "led_5mm", "botao_6x6", "pilha_cr2032", "resistor", "0", "-5", "3.2", "1e9", "nan",
            "inf", "4.7k", "1M", "Ω", "#", "..", "R1..1", ".", "x.y", "ç", "\t", "100", "52", "34", "1e-9"]
TIPOS = ["resistor_axial", "led_5mm", "botao_6x6", "pilha_cr2032", "resistor", "led", "botao", "buzzer"]


def texto_sorteado(rnd):
    linhas = []
    for _ in range(rnd.randint(0, 12)):
        linhas.append(" ".join(rnd.choice(PALAVRAS) for _ in range(rnd.randint(0, 6))))
    if rnd.random() < 0.7:
        linhas.insert(rnd.randint(0, len(linhas)), f"placa {rnd.choice(['52 34', '10 10', '0 0', '-1 5', '1e6 1e6', 'nan 3'])}")
    return "\n".join(linhas)


def placa_mutada(rnd):
    linhas = LANTERNA.splitlines()
    for _ in range(rnd.randint(1, 4)):
        i = rnd.randrange(len(linhas))
        p = linhas[i].split()
        acao = rnd.random()
        if acao < 0.25 and p and p[0] == "peca":   # move a peça (às vezes pra fora da placa)
            p[3], p[4] = str(round(rnd.uniform(-5, 60), 2)), str(round(rnd.uniform(-5, 40), 2))
        elif acao < 0.4 and p and p[0] == "peca":   # troca o tipo
            p[2] = rnd.choice(TIPOS)
        elif acao < 0.55 and p and p[0] == "peca":   # mexe no valor
            p = p[:5] + [rnd.choice(["1", "10", "100", "1k", "1M", "0.001"])]
        elif acao < 0.75 and p and p[0] == "liga":   # liga noutro pino
            p[rnd.randint(1, 2)] = rnd.choice(["R1.1", "R1.2", "D1.1", "D1.2", "SW1.1", "SW1.2", "SW1.3", "SW1.4", "BT1.1", "BT1.2", "GND", "VBAT", "N7"])
        elif acao < 0.85:   # apaga a linha
            p = []
        else:   # duplica a linha
            linhas.append(linhas[i])
        linhas[i] = " ".join(p)
    return "\n".join(linhas) + "\n"


class Fuzz(unittest.TestCase):
    def test_1000_textos_sorteados_no_leitor(self):
        rnd = random.Random(1)
        for k in range(1000):
            texto = texto_sorteado(rnd)
            try:
                gerar.montar(gerar.ler(texto))
            except gerar.ErroTxt as e:
                self.assertIsInstance(e.linha, int)
            except Exception as e:   # noqa: BLE001
                self.fail(f"caso {k}: {type(e).__name__}: {e}\n---\n{texto}")

    def test_150_placas_mutadas_nas_etapas_1_a_5(self):
        rnd = random.Random(2)
        etapas = [testar.le_txt, testar.confere_pecas, testar.confere_ligacoes, testar.liga_circuito, testar.regras_fabrica]
        resultado = {}
        for k in range(150):
            texto = placa_mutada(rnd)
            pasta = copia()
            (pasta / "placa.txt").write_text(texto)
            ctx = {"pasta": pasta, "frase": None, "estado": {"versao": None}, "anterior": {}}
            fim = "passou"
            try:
                for n, etapa in enumerate(etapas, 1):
                    try:
                        etapa(ctx)
                    except testar.Pulou:
                        continue
                    except (testar.Falhou, gerar.ErroTxt):
                        fim = f"parou na {n}"
                        break
            except Exception as e:   # noqa: BLE001
                self.fail(f"caso {k}: {type(e).__name__}: {e}\n---\n{texto}")
            finally:
                apagar(pasta)
            resultado[fim] = resultado.get(fim, 0) + 1
        self.assertGreater(len(resultado), 3, f"as mutações precisam cair em etapas diferentes: {resultado}")

    def test_20_placas_com_pecas_e_valores_sorteados_nas_7_etapas(self):
        rnd = random.Random(5)
        vistos = set()
        for k in range(20):
            texto = LANTERNA
            for ref in ("SW1", "R1", "D1"):
                x, y = round(rnd.uniform(30, 49), 1), round(rnd.uniform(3, 31), 1)
                texto = re.sub(rf"(peca {ref} \S+) [\d.]+ [\d.]+", rf"\1 {x} {y}", texto)
            texto = re.sub(r"(peca R1 resistor_axial [\d.]+ [\d.]+) \S+", rf"\1 {rnd.choice(['22', '47', '100', '1k', '10k'])}", texto)
            pasta = copia()
            (pasta / "placa.txt").write_text(texto)
            try:
                e = testar.rodar(pasta)
                falha = next((x for x in e["etapas"] if x["estado"] == "falhou"), None)
                self.assertFalse(falha and "inesperado" in falha["detalhe"], f"caso {k}: {falha and falha['detalhe']}\n{texto}")
                self.assertEqual(falha is None, (pasta / "saida" / "fabrica.zip").exists(), f"caso {k}: zip só quando passa tudo")
                vistos.add(falha["nome"] if falha else "passou")
            finally:
                apagar(pasta)
        self.assertGreater(len(vistos), 1)


if __name__ == "__main__":
    unittest.main()
