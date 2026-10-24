"""blocos.py: o começo de toda placa, na ordem em que a gente pensa.

1. objetivo: o que a placa faz e as perguntas de gente ("quanta luz você quer?")
2. blocos: o tipo de cada peça, sem número ainda (pilha -> botão -> resistor -> LED)
3. carrinho: pra cada bloco, uma peça de verdade da loja (loja.py); o resistor sai da conta do brilho
4. só então a placa: o placa.txt usa o código da peça da loja como tipo (peca R1 C119304 43 15)

Fica tudo em placas/<nome>/projeto.json; as peças importadas, em placas/<nome>/pecas/.
"""
import json
import math
import re
from datetime import datetime
from pathlib import Path

import catalogo

# cada bloco: o que ele faz, em uma frase, e como procurar a peca dele na loja (sempre de furo: a gente solda).
# a busca da JLCPCB e por palavra exata: "CR2032 Plugin" acha, "CR2032 battery holder through hole" nao
BLOCOS = {
    "pilha": {"nome": "Pilha", "funcao": "Energia", "ref": "BT",
              "por_que": "É de onde vem a força que empurra a corrente pelo circuito.",
              "explica": "Segura a pilha. O + e o − dela viram dois furos na placa; o − é o GND, o 0 V de referência.",
              "busca": "CR2032 Plugin"},
    "botao": {"nome": "Botão", "funcao": "Liga e desliga", "ref": "SW",
              "por_que": "Apertou, a corrente passa; soltou, ela para e a pilha não gasta.",
              "explica": "Apertou, liga; soltou, desliga. Tem o lado A (dois pinos, ligados por dentro) e o lado B (os outros dois). "
                         "Só faz alguma coisa se cada lado for pra um lugar diferente.",
              "busca": "6x6mm tactile"},
    "resistor": {"nome": "Resistor", "funcao": "Freio", "ref": "R",
                 "por_que": "Segura a corrente no tanto certo: é ele que decide o brilho e protege o LED.",
                 "explica": "Freia a corrente: quanto mais ohms, menos corrente passa. É o cilindrinho com faixas coloridas. "
                            "Não tem lado certo.",
                 "busca": "{valor} 250mW metal film through hole resistor"},
    "led": {"nome": "LED", "funcao": "Luz", "ref": "D",
            "por_que": "Transforma corrente em luz: mais corrente, mais brilho, até o limite dele.",
            "explica": "Só acende com a corrente no sentido certo: entra pelo + (a perna comprida) e sai pelo − "
                       "(a perna curta; na placa é o pad quadrado). Sempre com um resistor na frente.",
            "busca": "LED 5mm red", "atributo": ("Illumination Color", "Red")},
}

# fracao = parte do brilho que o fabricante anuncia (o brilho medido na corrente de teste do datasheet)
PERGUNTAS = {
    "brilho": {"texto": "Quanta luz você quer?", "precisa": "led",
               "opcoes": {"fraca": {"nome": "Fraca", "fracao": 0.25, "explica": "Um quarto do brilho que o fabricante anuncia. A pilha dura mais."},
                          "media": {"nome": "Média", "fracao": 0.5, "explica": "Metade do brilho do anúncio."},
                          "forte": {"nome": "Forte", "fracao": 1.0, "explica": "O brilho do anúncio. Gasta a pilha bem mais rápido."}}},
}

E24 = [10, 11, 12, 13, 15, 16, 18, 20, 22, 24, 27, 30, 33, 36, 39, 43, 47, 51, 56, 62, 68, 75, 82, 91]


# ---------- números que a loja escreve como texto ----------
def numero_com_unidade(txt, unidade):
    """'4.7kΩ' -> 4700; '250mW' -> 0.25; '20mA' -> 0.02"""
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*([pnuµmkM]?)" + unidade, txt or "")
    if not m:
        return None
    return float(m[1]) * {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "k": 1e3, "M": 1e6, "": 1}[m[2]]


def ohms_txt(o):
    if o is None:
        return "?"
    if o >= 1000:
        return f"{o / 1000:g} kΩ".replace(".", ",")
    return f"{o:g} Ω"


def watts_txt(w):
    return f"{w:g} W".replace(".", ",") if w >= 1 else f"{w * 1000:g} mW"


def mais_perto(ohms):
    """o valor comercial (série E24) mais perto, olhando a proporção"""
    valores = [v * 10 ** d for d in range(0, 6) for v in E24]
    return min(valores, key=lambda v: abs(math.log(v / ohms)))


def tamanho(pacote):
    """'Plugin,D2.3xL6.5mm' -> 'corpo de 6,5 × 2,3 mm'"""
    num = lambda s: s.replace(".", ",")
    if m := re.search(r"D(\d+(?:\.\d+)?)xL(\d+(?:\.\d+)?)mm", pacote):
        return f"corpo de {num(m[2])} × {num(m[1])} mm"
    if m := re.search(r"D=(\d+(?:\.\d+)?)mm", pacote):
        return f"{num(m[1])} mm de diâmetro"
    if m := re.search(r"(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)mm", pacote):
        return f"{num(m[1])} × {num(m[2])} mm"
    return pacote


def de_furo(i):
    """peca de furo passante (a gente solda na mao); SMD fica de fora por enquanto"""
    return i["pacote"].startswith(("Plugin", "Through Hole")) or "Through Hole" in i["categoria"]


# ---------- a peca da loja vira um tipo da placa ----------
def nome_da_loja(bloco, d):
    """nome de gente de uma peca da loja, so com o que a loja diz"""
    at = d["atributos"]
    if bloco == "resistor":
        ohms, w = numero_com_unidade(at.get("Resistance"), "Ω"), numero_com_unidade(at.get("Power(Watts)"), "W")
        return f"Resistor {ohms_txt(ohms)}, {watts_txt(w)}" if ohms and w else "Resistor"
    if bloco == "led":
        cor = catalogo.CORES.get(at.get("Illumination Color"), "")
        return f"LED {cor} {tamanho(d['pacote'])}".replace("  ", " ").replace(" de diâmetro", "").strip()
    if bloco == "botao":
        return f"Botão {tamanho(d['pacote'])}"
    if bloco == "pilha":
        return f"Suporte de pilha {at.get('Battery Type', '')}".strip()
    return BLOCOS[bloco]["nome"]


def pad(p):
    if p["forma"] == "C" and abs(p["w"] - p["h"]) < 1e-6:
        return {"forma": "C", "d": p["w"]}
    return {"forma": "O" if p["forma"] in ("C", "O") else "R", "w": p["w"], "h": p["h"]}


def tipo_da_loja(bloco, d, des):
    """d = ficha da loja (loja.item), des = desenho do EasyEDA (loja.desenho)"""
    b, at, codigo = BLOCOS[bloco], d["atributos"], d["codigo"]
    medida = tamanho(d["pacote"])
    if medida == d["pacote"] and des["corpo"]:   # o pacote nao diz a medida: usa o contorno do desenho
        medida = f"{des['corpo'][0]:.1f} × {des['corpo'][1]:.1f} mm".replace(".", ",")
    tipo = {
        "nome": nome_da_loja(bloco, d), "bloco": bloco, "explica": b["explica"],
        "fonte": f"desenho {des['pacote']} do EasyEDA; ficha LCSC {codigo}; datasheet {d['datasheet']}",
        "corpo": des["corpo"] or [2 * max(abs(p["x"]) + p["w"] / 2 for p in des["pads"]),
                                  2 * max(abs(p["y"]) + p["h"] / 2 for p in des["pads"])],
        "redondo": bloco == "led", "desenho": des["silk"],
        "pinos": {p["n"]: {"x": p["x"], "y": p["y"], "pad": pad(p), "furo": p["furo"]} for p in des["pads"]},
        "eletrica": None, "pendente": [],
        "compra": f"{d['marca']} {d['modelo']} (LCSC {codigo})",
        "loja": {k: d[k] for k in ("codigo", "modelo", "marca", "pacote", "preco", "minimo", "estoque", "datasheet", "link", "atributos")}
                | {"tamanho": medida, "quando": datetime.now().strftime("%Y-%m-%d")},
    }
    if bloco == "resistor":
        ohms, w = numero_com_unidade(at.get("Resistance"), "Ω"), numero_com_unidade(at.get("Power(Watts)"), "W")
        tipo["nomes"] = {"1": "lado 1", "2": "lado 2"}
        tipo["valor"] = ohms
        if ohms and w:
            tipo["eletrica"] = {"modelo": "resistor", "potencia_max": w}
        else:
            tipo["pendente"].append("o valor e a potência do resistor")
    elif bloco == "led":
        tipo["nomes"] = {n: {"A": "+", "K": "−"}.get(nome, nome) for n, nome in des["simbolo"].items()}
        tipo["pendente"].append("o + e o −, a corrente máxima e a curva de brilho do LED")
    elif bloco == "botao":
        tipo["pendente"].append("quais pinos do botão são o mesmo lado")
    elif bloco == "pilha":
        tipo["pendente"].append("qual furo é o + e qual pilha vai nele")
    conferido = catalogo.conferido(codigo)
    if conferido:   # o que o Claude ja conferiu no datasheet
        for chave in ("nomes", "juntos", "eletrica", "pinos_fixos", "extras"):
            if chave in conferido:
                tipo[chave] = conferido[chave]
        tipo["fonte"] += f"; conferido: {conferido['fonte']}"
        tipo["pendente"] = [p for p in tipo["pendente"] if bloco == "resistor"]
    return tipo


def carregar_pecas(pasta):
    """codigo -> tipo, das pecas que vieram da loja pra esta placa"""
    pecas = {}
    for arq in sorted((Path(pasta) / "pecas").glob("C*.json")):
        pecas[arq.stem] = json.loads(arq.read_text())
    return pecas


# ---------- brilho, corrente e o resistor ----------
def corrente_do_brilho(e, fracao):
    """corrente que da essa parte do brilho do anuncio, pela curva do datasheet (None sem curva)"""
    pts = e.get("brilho") or []
    for (i0, b0), (i1, b1) in zip(pts, pts[1:]):
        if b0 <= fracao <= b1:
            return i0 + (i1 - i0) * (fracao - b0) / (b1 - b0)
    return None


def brilho_da_corrente(e, i):
    """parte do brilho do anuncio que essa corrente da (1,0 = o anuncio)"""
    pts = e.get("brilho") or []
    if not pts:
        return None
    if i <= pts[0][0]:
        return 0.0
    for (i0, b0), (i1, b1) in zip(pts, pts[1:]):
        if i0 <= i <= i1:
            return b0 + (b1 - b0) * (i - i0) / (i1 - i0)
    return pts[-1][1]   # acima da curva: nao inventa, fica no ultimo ponto medido


def nivel_do_brilho(fracao):
    """fracao -> 'fraca' | 'media' | 'forte' (o mais perto)"""
    ops = PERGUNTAS["brilho"]["opcoes"]
    return min(ops, key=lambda k: abs(ops[k]["fracao"] - fracao))


def conta_do_freio(pilha, led, fracao):
    """pilha -> botao -> resistor -> LED, tudo em serie: que resistor da esse brilho?
    I = (pilha − joelho do LED) / (R + r_s do LED + resistencia interna da pilha)"""
    i = corrente_do_brilho(led, fracao)
    if i is None:
        return None
    joelho = led["vf"] - led["r_s"] * led["i_teste"]
    resto = led["r_s"] + pilha.get("r_interna", 0)
    ohms = (pilha["v"] - joelho) / i - resto
    if ohms <= 0:
        return {"i": i, "impossivel": True, "joelho": joelho}
    padrao = mais_perto(ohms)
    i_padrao = (pilha["v"] - joelho) / (padrao + resto)
    return {"i": i, "ohms": ohms, "padrao": padrao, "i_padrao": i_padrao, "joelho": joelho,
            "brilho": brilho_da_corrente(led, i_padrao), "r_interna": pilha.get("r_interna", 0), "r_s": led["r_s"],
            "v": pilha["v"]}


# ---------- projeto.json ----------
def ler_projeto(pasta):
    arq = Path(pasta) / "projeto.json"
    return json.loads(arq.read_text()) if arq.exists() else None


def salvar_projeto(pasta, proj):
    arq = Path(pasta) / "projeto.json"
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(proj, ensure_ascii=False, indent=1))
    tmp.replace(arq)


def bloco_do_ref(proj, ref):
    return next((b for b in proj["blocos"] if b["ref"] == ref), None)


def eletrica_do_bloco(proj, pecas, bloco):
    b = next((b for b in proj["blocos"] if b["bloco"] == bloco), None)
    return (pecas.get(b.get("peca")) or {}).get("eletrica") if b else None


def conta_do_projeto(proj, pecas):
    """a conta do freio, quando o projeto e uma pilha, um resistor e um LED (a lanterninha)"""
    resposta = proj.get("perguntas", {}).get("brilho", {}).get("resposta")
    pilha, led = eletrica_do_bloco(proj, pecas, "pilha"), eletrica_do_bloco(proj, pecas, "led")
    if not resposta or not pilha or not led:
        falta = [] if resposta else ["responder quanta luz você quer"]
        falta += [] if pilha else ["escolher a pilha"]
        falta += [] if led else ["escolher o LED (e conferir o datasheet dele)"]
        return {"falta": falta}
    conta = conta_do_freio(pilha, led, PERGUNTAS["brilho"]["opcoes"][resposta]["fracao"])
    if conta is None:
        return {"falta": ["a curva de brilho do LED (datasheet)"]}
    conta["resposta"] = resposta
    conta["i_testada"] = pilha.get("i_testada")
    conta["mah"] = pilha.get("mah")
    return conta


def tipos_no_txt(pasta):
    """REF -> tipo, direto do placa.txt (sem montar a placa)"""
    arq = Path(pasta) / "placa.txt"
    tipos = {}
    if arq.exists():
        for linha in arq.read_text().splitlines():
            p = linha.split("#")[0].split()
            if len(p) >= 3 and p[0] == "peca":
                tipos[p[1]] = p[2]
    return tipos


def estado(pasta):
    """tudo que a aba Processo mostra dos passos 1 a 3"""
    proj = ler_projeto(pasta)
    if not proj:
        return None
    pecas = carregar_pecas(pasta)
    tem = {b["bloco"] for b in proj["blocos"]}
    perguntas = []
    for pid, p in PERGUNTAS.items():
        if p["precisa"] in tem:
            r = proj.get("perguntas", {}).get(pid, {})
            perguntas.append({"id": pid, "texto": p["texto"], "resposta": r.get("resposta"), "quem": r.get("quem"),
                              "opcoes": [{"id": k, **o} for k, o in p["opcoes"].items()]})
    conta = conta_do_projeto(proj, pecas)
    no_txt = tipos_no_txt(pasta)
    blocos, total = [], 0.0
    for b in proj["blocos"]:
        info = BLOCOS[b["bloco"]]
        tipo = pecas.get(b.get("peca"))
        item = {"ref": b["ref"], "bloco": b["bloco"], "nome": info["nome"], "funcao": info["funcao"],
                "por_que": info["por_que"], "quem": b.get("quem"), "peca": None,
                "na_placa": no_txt.get(b["ref"]) == b.get("peca") if b.get("peca") else None}
        if tipo:
            loja = tipo["loja"]
            item["peca"] = {"codigo": loja["codigo"], "nome": tipo["nome"], "modelo": loja["modelo"], "marca": loja["marca"],
                            "tamanho": loja["tamanho"], "preco": loja["preco"], "minimo": loja["minimo"],
                            "estoque": loja["estoque"], "datasheet": loja["datasheet"], "link": loja["link"],
                            "foto": loja.get("foto"), "pendente": tipo.get("pendente", []), "valor": tipo.get("valor"),
                            "extras": tipo.get("extras", [])}
            total += (loja["preco"] or 0) * max(1, loja["minimo"] or 1)
        if b["bloco"] == "resistor":
            item["conta"] = conta
            if conta.get("padrao") and tipo:
                item["conta"]["bate"] = tipo.get("valor") == conta["padrao"]
        blocos.append(item)
    return {"objetivo": proj.get("objetivo", ""), "frase": proj.get("frase", ""), "perguntas": perguntas,
            "blocos": blocos, "total": round(total, 4),
            "pronto": all(b["peca"] and not b["peca"]["pendente"] and b["na_placa"] for b in blocos)
                      and all(p["resposta"] for p in perguntas)
                      and all(b.get("conta", {}).get("bate", True) for b in blocos)}


# ---------- o que o app muda ----------
def opcoes(pasta, ref, online=False):
    """o mundo de pecas que servem pra esse bloco: primeiro o catalogo (na hora, sem internet); online=True
    (ou catalogo sem nada pra esse caso) busca na loja e poe o que achar no catalogo.
    Resistor so com o valor da conta; LED da mesma cor do escolhido."""
    import loja
    proj = ler_projeto(pasta)
    b = proj and bloco_do_ref(proj, ref)
    if not b:
        raise ValueError(f"{ref} não é um bloco deste projeto")
    bloco, atual, pecas = b["bloco"], b.get("peca"), carregar_pecas(pasta)
    busca, alvo, cor = BLOCOS[bloco]["busca"], None, None
    if bloco == "resistor":
        conta = conta_do_projeto(proj, pecas)
        alvo = conta.get("padrao") or (pecas.get(atual) or {}).get("valor")
        if not alvo:
            raise ValueError("primeiro a conta do brilho: " + ", ".join(conta.get("falta", [])))
        busca = busca.format(valor=catalogo.ohms_busca(alvo))
    if bloco == "led":
        cor = ((pecas.get(atual) or {}).get("loja", {}).get("atributos") or {}).get("Illumination Color")

    def servem(cat):
        lista = catalogo.do_bloco(cat, bloco)
        if alvo:
            lista = [e for e in lista if numero_com_unidade(e["atributos"].get("Resistance"), "Ω") == alvo]
        if cor:
            lista = [e for e in lista if e["atributos"].get("Illumination Color") == cor]
        return lista

    cat = catalogo.ler()
    novas = 0
    if online or not servem(cat):
        if cor:
            busca = f"LED {'3mm' if '3' in (pecas.get(atual) or {}).get('loja', {}).get('pacote', '') else '5mm'} {cor.lower()}"
        achadas = [i for i in loja.buscar(busca, 30, validade=0 if online else loja.UM_DIA) if catalogo.serve(bloco, i)]
        novas = catalogo.adicionar(cat, bloco, sorted(achadas, key=lambda i: -i["estoque"])[:12])
        catalogo.salvar(cat)
    lista = servem(cat)
    for e in lista:
        e["bloco"] = bloco
        e["escolhida"] = e["codigo"] == atual
        e["conferida"] = bool(e.get("conferido")) or bloco == "resistor"   # resistor: a loja ja diz tudo
        e.pop("conferido", None)
    lista.sort(key=lambda e: (not e["escolhida"], e["situacao"] != "ok", not e["conferida"], -e["estoque"]))
    return {"ref": ref, "bloco": bloco, "busca": busca, "alvo": alvo, "cor": catalogo.CORES.get(cor), "novas": novas,
            "itens": lista}


def trocar_no_txt(pasta, ref, codigo, nome):
    """peca REF TIPO X Y [VALOR] -> peca REF CODIGO X Y   # nome (o valor vem da peca; o comentario velho sai). False se REF nao esta na placa"""
    arq = Path(pasta) / "placa.txt"
    linhas, achou = arq.read_text().splitlines(keepends=True), False
    for i, linha in enumerate(linhas):
        codigo_txt, _, comentario = linha.partition("#")
        p = codigo_txt.split()
        if len(p) >= 5 and p[0] == "peca" and p[1] == ref and p[2] != codigo:
            fim = "\n" if linha.endswith("\n") else ""
            linhas[i] = f"peca {ref} {codigo} {p[3]} {p[4]}   # {nome}, escolhido no carrinho{fim}"
            achou = True
    if achou:
        arq.write_text("".join(linhas))
    return achou


def escolher(pasta, ref, codigo, quem="Luiz"):
    import loja
    proj = ler_projeto(pasta)
    b = proj and bloco_do_ref(proj, ref)
    if not b:
        raise ValueError(f"{ref} não é um bloco deste projeto")
    tipo = loja.importar(codigo, b["bloco"], pasta)
    b.update(peca=codigo, quem=quem, quando=datetime.now().strftime("%Y-%m-%d %H:%M"))
    salvar_projeto(pasta, proj)
    trocar_no_txt(pasta, ref, codigo, tipo["nome"])
    return {"tipo": tipo["nome"], "na_placa": tipos_no_txt(pasta).get(ref) == codigo, "pendente": tipo["pendente"],
            "frase": f"trocou {ref} por {tipo['nome']} ({codigo}), no carrinho"}


def responder(pasta, pergunta, resposta, quem="Luiz"):
    if pergunta not in PERGUNTAS or resposta not in PERGUNTAS[pergunta]["opcoes"]:
        raise ValueError("pergunta ou resposta desconhecida")
    proj = ler_projeto(pasta)
    if not proj:
        raise ValueError("esta placa não tem projeto.json")
    proj.setdefault("perguntas", {})[pergunta] = {"resposta": resposta, "quem": quem,
                                                  "quando": datetime.now().strftime("%Y-%m-%d %H:%M")}
    salvar_projeto(pasta, proj)
