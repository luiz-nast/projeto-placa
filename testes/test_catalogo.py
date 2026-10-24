"""o catálogo inteiro (ferramenta/catalogo/): formato, categorias, peças, lojas e as regras do código"""
import json
import re
import unittest

from apoio import RAIZ
import catalogo

PASTA = RAIZ / "ferramenta" / "catalogo"
ARQUIVOS = sorted(PASTA.glob("*.json"))
MONTAGENS = {"furo", "superfície", "módulo", "fio", "não informado"}
SITUACOES = {"ok", "sem estoque", "sumiu"}
CAMPOS_PECA = ("nome", "marca", "modelo", "pacote", "montagem", "atributos", "loja", "link", "preco", "moeda", "visto", "situacao")
NA_LANTERNINHA = {"C5365915": "pilha", "C393938": "botao", "C119310": "resistor", "C779439": "led"}


class Formato(unittest.TestCase):
    def test_cada_arquivo_e_uma_categoria_valida(self):
        self.assertGreater(len(ARQUIVOS), 50)
        for arq in ARQUIVOS:
            d = json.loads(arq.read_text())
            self.assertEqual(d["categoria"], arq.stem, arq.name)
            self.assertRegex(d["categoria"], r"^[a-z0-9_]+$")
            self.assertIn(d["grupo"], catalogo.GRUPOS, arq.name)
            for campo in ("nome", "explica"):
                self.assertTrue(d.get(campo), f"{arq.name}: falta {campo}")
            self.assertLess(len(d["explica"]), 900, f"{arq.name}: explica comprido demais pro Luiz")
            self.assertTrue(set(d) <= set(catalogo.CAMPOS_SPEC) | {"pecas"}, f"{arq.name}: campo estranho {set(d) - set(catalogo.CAMPOS_SPEC)}")
            for s in d.get("sementes", []):
                self.assertTrue(s.get("busca"), arq.name)

    def test_codigo_nao_aparece_em_duas_categorias(self):
        visto = {}
        for arq in ARQUIVOS:
            for codigo in json.loads(arq.read_text()).get("pecas", {}):
                self.assertNotIn(codigo, visto, f"{codigo} em {arq.stem} e em {visto.get(codigo)}")
                visto[codigo] = arq.stem

    def test_cada_peca_tem_o_que_o_app_mostra(self):
        cat = catalogo.ler()
        for codigo, e in cat["pecas"].items():
            onde = f"{e['categoria']}/{codigo}"
            for campo in CAMPOS_PECA:
                self.assertIn(campo, e, f"{onde}: falta {campo}")
            self.assertIn(e["montagem"], MONTAGENS, onde)
            self.assertIn(e["situacao"], SITUACOES, onde)
            self.assertIn(e["moeda"], ("USD", "BRL"), onde)
            self.assertRegex(e["link"], r"^https://\S+$", f"{onde}: link")
            self.assertRegex(e["visto"], r"^\d{4}-\d{2}-\d{2}$", onde)
            self.assertTrue(e["preco"] is None or e["preco"] > 0, onde)
            self.assertTrue(e.get("apelido") or e["nome"], onde)
            if e["loja"] == "LCSC":
                self.assertRegex(codigo, r"^C\d+$", onde)
                self.assertEqual(e["moeda"], "USD", onde)
            else:
                self.assertIn(":", codigo, f"{onde}: peça de outra loja tem chave loja:pedaço")
                self.assertTrue(e.get("foto", "").startswith("https://") or not e.get("foto"), onde)
            for oferta in e.get("outras_lojas", []):
                self.assertRegex(oferta.get("link", ""), r"^https://", f"{onde}: outra loja sem link")

    def test_codigo_barrado_nao_esta_na_categoria(self):
        cat = catalogo.ler()
        for cid, spec in cat["categorias"].items():
            for codigo in spec.get("filtro", {}).get("fora", []):
                e = cat["pecas"].get(codigo)
                self.assertFalse(e and e["categoria"] == cid, f"{codigo} está barrado em {cid} mas continua lá")

    def test_conferido_tem_o_que_o_simulador_precisa(self):
        precisa = {"led": ("vf", "i_teste", "i_max", "r_s"), "pilha": ("mais", "menos", "v", "v_min", "v_max", "mah"),
                   "chave": ("lados",), "resistor": ("potencia_max",)}
        for codigo, e in catalogo.ler()["pecas"].items():
            el = (e.get("conferido") or {}).get("eletrica")
            if el:
                for campo in precisa[el["modelo"]]:
                    self.assertIn(campo, el, f"{codigo}: conferido sem {campo}")
                self.assertTrue(e["conferido"].get("fonte"), f"{codigo}: conferido sem fonte")


class AsPecasDasPlacas(unittest.TestCase):
    def test_lanterninha_continua_no_lugar(self):
        cat = catalogo.ler()
        for codigo, categoria in NA_LANTERNINHA.items():
            self.assertEqual(cat["pecas"][codigo]["categoria"], categoria, codigo)
        for codigo in ("C5365915", "C393938", "C779439"):
            self.assertTrue(cat["pecas"][codigo].get("conferido"), f"{codigo} perdeu o conferido")


class Regras(unittest.TestCase):
    def test_montagem_pelos_pacotes(self):
        casos = {"Plugin,D=5mm": "furo", "DIP-8": "furo", "PDIP-28": "furo", "TO-92": "furo", "TO-220F": "furo", "DO-41": "furo",
                 "HC-49S": "furo", "插件,D9xL4mm": "furo", "SIP-3-2.5mm": "furo", "KBP": "furo", "TO-39-4": "furo",
                 "SOIC-8": "superfície", "TO-252": "superfície", "HC-49S-SMD": "superfície", "DO-214AC": "superfície",
                 "DBS": "superfície", "0805": "superfície", "-": "não informado"}
        for pacote, esperado in casos.items():
            self.assertEqual(catalogo.montagem({"pacote": pacote, "categoria": "x", "atributos": {}}), esperado, pacote)
        self.assertEqual(catalogo.montagem({"pacote": "-", "categoria": "Development Boards & Kits", "atributos": {}}), "módulo")
        self.assertEqual(catalogo.montagem({"pacote": "-", "categoria": "Thyristors (SCR)/Modules", "atributos": {}}), "não informado")
        self.assertEqual(catalogo.montagem({"pacote": "x", "categoria": "Housings (Wire To Board)", "atributos": {}}), "fio")
        self.assertEqual(catalogo.montagem({"pacote": "-", "categoria": "x", "atributos": {}, "montagem_manual": "furo"}), "furo")

    def test_atributo_com_dois_nomes(self):
        self.assertEqual(catalogo.atributo({"type": "-", "Type": "NPN"}, "type|Type"), "NPN")
        self.assertIsNone(catalogo.atributo({}, "a|b"))

    def test_nome_em_lista_de_modelos_e_traducao(self):
        cat = {"categorias": {"x": {"nome": "Coisa", "nome_peca": ["{A} {B}", "{@categoria_loja} {@modelo}"],
                                    "traducoes": {"Timers": "Timer"}}}}
        self.assertEqual(catalogo.nome_da_peca(cat, "x", {"atributos": {"A": "1", "B": "Right Angle"}, "categoria": "", "modelo": "M"}),
                         "1 a 90°")
        self.assertEqual(catalogo.nome_da_peca(cat, "x", {"atributos": {"A": "1"}, "categoria": "Timers", "modelo": "NE555"}),
                         "Timer NE555")
        self.assertEqual(catalogo.nome_da_peca(cat, "x", {"atributos": {}, "categoria": "", "modelo": "Z1"}), "Coisa Z1")

    def test_filtro(self):
        cat = {"categorias": {"x": {"filtro": {"montagem": ["furo"], "estoque_minimo": 50, "fora": ["C2"],
                                               "pacotes_fora": ["SMD"], "valores_fora": {"T": ["ruim"]}}}}}
        base = {"codigo": "C1", "pacote": "Plugin", "categoria": "", "atributos": {}, "estoque": 100}
        self.assertTrue(catalogo.serve(cat, "x", base))
        self.assertFalse(catalogo.serve(cat, "x", {**base, "estoque": 10}))
        self.assertFalse(catalogo.serve(cat, "x", {**base, "codigo": "C2"}))
        self.assertFalse(catalogo.serve(cat, "x", {**base, "pacote": "Plugin SMD"}))
        self.assertFalse(catalogo.serve(cat, "x", {**base, "atributos": {"T": "ruim"}}))
        self.assertFalse(catalogo.serve(cat, "x", {**base, "pacote": "SOIC-8"}))

    def test_recalcular_nao_muda_nada_num_catalogo_ja_recalculado(self):
        cat = catalogo.ler()
        antes = {c: json.dumps(e, sort_keys=True) for c, e in cat["pecas"].items()}
        catalogo.recalcular(cat)
        mudou = [c for c, e in cat["pecas"].items() if json.dumps(e, sort_keys=True) != antes[c]]
        self.assertEqual(mudou[:10], [], f"{len(mudou)} peças estão diferentes do que as regras de agora dão")

    def test_salvar_e_ler_de_volta_e_igual(self):
        cat = catalogo.ler()
        for arq in ARQUIVOS[:5]:
            original = arq.read_text()
            catalogo.salvar(cat, [arq.stem])
            self.assertEqual(arq.read_text(), original, f"{arq.name} mudou só de ler e salvar")


if __name__ == "__main__":
    unittest.main()
