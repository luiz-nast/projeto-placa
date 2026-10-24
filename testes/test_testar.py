"""a bateria de 7 etapas (testar.py) de ponta a ponta: a placa boa passa, e cada defeito para na etapa certa"""
import json
import unittest
import zipfile

from apoio import apagar, copia
import testar


def rodar(troca=None, requisitos=None):
    pasta = copia(troca=troca)
    if requisitos is not None:
        (pasta / "requisitos.md").write_text(requisitos)
    try:
        estado = testar.rodar(pasta, "teste")
        salvo = json.loads((pasta / "testes.json").read_text())
        zip_ = (pasta / "saida" / "fabrica.zip")
        return estado, salvo, zipfile.ZipFile(zip_).namelist() if zip_.exists() else None
    finally:
        apagar(pasta)


def parou(estado):
    falha = next((e for e in estado["etapas"] if e["estado"] == "falhou"), None)
    return (estado["etapas"].index(falha) + 1, falha) if falha else (None, None)


class PlacaBoa(unittest.TestCase):
    def test_passa_inteira_e_gera_o_zip(self):
        estado, salvo, zip_ = rodar()
        estados = [e["estado"] for e in estado["etapas"]]
        if not _tem_gerbonara():
            self.skipTest("gerbonara só no .venv")
        self.assertEqual(estados, ["ok"] * 7, [(e["nome"], e["detalhe"]) for e in estado["etapas"]])
        self.assertEqual(estado["requisitos"], {"R1": "ok", "R2": "ok", "R3": "ok"})
        self.assertIn("11 mA", estado["etapas"][3]["detalhe"])
        self.assertEqual(len(zip_), 8)
        self.assertFalse(salvo["rodando"], "o testes.json nunca fica 'rodando'")
        self.assertEqual(salvo["versao"], 1)


def _tem_gerbonara():
    try:
        import gerbonara  # noqa: F401
        return True
    except ImportError:
        return False


class CadaDefeitoNaSuaEtapa(unittest.TestCase):
    def confere(self, etapa, trecho, troca=None, requisitos=None, rotulo=None):
        estado, salvo, zip_ = rodar(troca, requisitos)
        n, falha = parou(estado)
        self.assertEqual(n, etapa, [(e["nome"], e["estado"], e["detalhe"]) for e in estado["etapas"]])
        self.assertIn(trecho, falha["detalhe"])
        if rotulo:
            self.assertIn(rotulo, falha.get("rotulos", {}).values())
        self.assertIsNone(zip_, "com falha não sai fabrica.zip")
        self.assertTrue(all(e["estado"] == "nao_rodou" for e in estado["etapas"][n:]))
        self.assertFalse(salvo["rodando"])
        return falha

    def test_erro_de_digitacao_para_na_1_com_a_linha(self):
        falha = self.confere(1, "comando desconhecido", {"liga D1.2 GND": "ligar D1.2 GND"})
        self.assertEqual(falha["codigo"], "ligar D1.2 GND")

    def test_peca_que_nao_existe_para_na_2(self):
        self.confere(2, "não existe na biblioteca", {"led_5mm": "led_9mm"})

    def test_peca_sem_ligacao_para_na_3(self):
        self.confere(3, "sem ligação", {"liga R1.2 D1.1\nliga D1.2 GND\n": ""}, rotulo="sem ligação")

    def test_pino_solto_para_na_3(self):
        self.confere(3, "pino solto", {"liga D1.2 GND\n": ""}, rotulo="pino solto")

    def test_pecas_encostadas_dao_curto_na_3(self):
        self.confere(3, "curto", {"D1 led_5mm 43 7": "D1 led_5mm 43 15"})

    def test_led_queima_para_na_4(self):
        self.confere(4, "queima", {"43 15 100": "43 15 10"}, rotulo="queima")

    def test_peca_na_borda_para_na_5(self):
        self.confere(5, "da borda", {"R1 resistor_axial 43 15": "R1 resistor_axial 47 15"}, rotulo="perto da borda")

    def test_requisito_quebrado_aparece_sem_parar_a_rodada(self):
        req = "# Objetivo: x\n## R1 Botão dos dois lados\npecas: SW1\nverifica: separado BT1.1 SW1.1\n"
        estado, _, _ = rodar(requisitos=req)
        self.assertEqual(estado["requisitos"], {"R1": "falha"})
        self.assertEqual(estado["objetivo"]["itens"][0]["motivo"], "em curto")

    def test_requisito_com_checagem_inventada(self):
        estado, _, _ = rodar(requisitos="# Objetivo: x\n## R1 a\nverifica: brilha_muito D1\n")
        self.assertIn("checagem desconhecida", estado["objetivo"]["erro"])

    def test_erro_inesperado_nao_trava_o_testes_json(self):
        original = testar.regras_fabrica
        testar.regras_fabrica = lambda ctx: 1 / 0
        try:
            # rodar() usa a lista de funções montada na hora, então troca dentro do módulo
            estado, salvo, _ = rodar()
        finally:
            testar.regras_fabrica = original
        n, falha = parou(estado)
        self.assertEqual(n, 5)
        self.assertIn("erro inesperado", falha["detalhe"])
        self.assertFalse(salvo["rodando"])


if __name__ == "__main__":
    unittest.main()
