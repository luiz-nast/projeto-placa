"""testar.py: gera a placa e roda a bateria de 7 etapas, escrevendo testes.json a cada etapa.

uso: python ferramenta/testar.py placas/estudo [-m "o que mudou"]
     python ferramenta/testar.py placas/estudo --resumo "texto do Claude no fim da rodada"
"""
import json
import math
import re
import shutil
import subprocess
import sys
import warnings
from datetime import datetime
from pathlib import Path

import blocos
import catalogo
import circuito
import gerar

# regras da fabrica: https://jlcpcb.com/capabilities/pcb-capabilities (1-2 camadas, 1 oz, lido em 2026-10-23)
TRILHA_MIN = 0.10      # largura minima da trilha
ESPACO_MIN = 0.10      # distancia minima entre cobres de nets diferentes
FURO_MIN = 0.15        # menor furo (broca mecanica)
FURO_MAX = 6.3         # maior furo
FURO_NPTH_MIN = 0.50   # menor furo sem cobre
ANEL_MIN = 0.18        # anel de cobre em volta do furo passante (minimo absoluto; recomendado 0,25)
BORDA_MIN = 0.2        # cobre ate a borda cortada (furo sem cobre conta como borda)
FURO_FURO_MIN = 0.45   # entre furos de pad, de borda a borda
PONTE_MIN = 0.10       # mascara entre dois pads (cor verde, 1 oz)
SILK_MIN = 0.15        # linha da serigrafia
LETRA_MIN = 1.0        # altura da letra da serigrafia

ETAPAS = ["Lê o txt", "Confere peças", "Confere ligações", "Liga o circuito",
          "Regras da fábrica", "Relê o Gerber", "Tira foto da placa"]


class Falhou(Exception):
    """etapa falhou; rotulos diz, pra cada peca, a etiqueta vermelha que a bancada desenha nela"""

    def __init__(self, detalhe, onde=(), rotulo=None, rotulos=None):
        super().__init__(detalhe)
        self.detalhe = detalhe
        self.rotulos = rotulos or {ref: rotulo for ref in onde}
        self.onde = list(self.rotulos)


class Pulou(Exception):
    """etapa que nao se aplica a esta placa; nao e falha"""


def mm(v):
    return f"{v:.2f}".replace(".", ",")


def ma(amp):
    return f"{amp * 1000:.0f}" if amp >= 0.0095 else f"{amp * 1000:.1f}".replace(".", ",")


def mw(watt):
    return f"{watt * 1000:.0f}"


# liga o circuito no papel, com as chaves apertadas, pra pilha fraca, nominal e nova
def ligar(modelo, pilha="v", apertadas=True):
    chaves = {p["ref"]: apertadas for p in modelo["pecas"] if (p.get("eletrica") or {}).get("modelo") == "chave"}
    pilhas = {p["ref"]: p["eletrica"][pilha] for p in modelo["pecas"] if (p.get("eletrica") or {}).get("modelo") == "pilha"}
    return circuito.resolver(modelo, {"pilha": pilhas, "chave": chaves})


# geometria do cobre: cada coisa e um "miolo" (segmentos ou retangulo) mais um raio em volta
def cobres(modelo):
    """(nome, net, miolo, raio); miolo = ("seg", a, b) ou ("ret", x0, y0, x1, y1)"""
    lista = []
    for peca in modelo["pecas"]:
        for p in peca["pinos"]:
            nome = f"{peca['ref']}.{p['n']}"
            net = p["net"] or nome   # pino solto e uma net sozinho
            if p["pad"]["forma"] == "C":
                lista.append((nome, net, ("seg", (p["x"], p["y"]), (p["x"], p["y"])), p["pad"]["d"] / 2))
            elif p["pad"]["forma"] == "O":   # oblongo: segmento no meio, raio = metade do lado curto
                w, h = p["pad"]["w"], p["pad"]["h"]
                meio = abs(w - h) / 2
                a, b = ((p["x"] - meio, p["y"]), (p["x"] + meio, p["y"])) if w >= h else ((p["x"], p["y"] - meio), (p["x"], p["y"] + meio))
                lista.append((nome, net, ("seg", a, b), min(w, h) / 2))
            else:
                w, h = p["pad"]["w"] / 2, p["pad"]["h"] / 2
                lista.append((nome, net, ("ret", p["x"] - w, p["y"] - h, p["x"] + w, p["y"] + h), 0))
    for t in modelo["trilhas"]:
        nome = f"trilha {t['de']} → {t['ate']}"
        lista.append((nome, t["net"], ("seg", (t["x1"], t["y1"]), (t["x2"], t["y2"])), t["largura"] / 2))
    return lista


def dist_ponto_seg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = 0 if dx == dy == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def cruza(a, b, c, d):
    def lado(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return lado(a, b, c) * lado(a, b, d) < 0 and lado(c, d, a) * lado(c, d, b) < 0


def dist_seg_seg(a, b, c, d):
    if cruza(a, b, c, d):
        return 0
    return min(dist_ponto_seg(a, c, d), dist_ponto_seg(b, c, d), dist_ponto_seg(c, a, b), dist_ponto_seg(d, a, b))


def segmentos(miolo):
    if miolo[0] == "seg":
        return [(miolo[1], miolo[2])]
    _, x0, y0, x1, y1 = miolo
    q = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return [(q[i], q[(i + 1) % 4]) for i in range(4)]


def dentro(p, miolo):
    return miolo[0] == "ret" and miolo[1] <= p[0] <= miolo[3] and miolo[2] <= p[1] <= miolo[4]


def distancia(c1, c2):
    """distancia entre as bordas de dois cobres (negativa = um entra no outro)"""
    (m1, r1), (m2, r2) = c1, c2
    s1, s2 = segmentos(m1), segmentos(m2)
    if any(dentro(s[0], m2) for s in s1) or any(dentro(s[0], m1) for s in s2):
        d = 0
    else:
        d = min(dist_seg_seg(a, b, c, e) for a, b in s1 for c, e in s2)
    return d - r1 - r2


def caixa(miolo, raio):
    pts = [p for s in segmentos(miolo) for p in s]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs) - raio, min(ys) - raio, max(xs) + raio, max(ys) + raio


def pares_perto(modelo, limite):
    """pares de cobre de nets diferentes mais perto que `limite` (o pior primeiro)"""
    cs = cobres(modelo)
    achados = []
    for i, (n1, net1, m1, r1) in enumerate(cs):
        for n2, net2, m2, r2 in cs[i + 1:]:
            if net1 != net2:
                d = distancia((m1, r1), (m2, r2))
                if d < limite:
                    achados.append((d, n1, n2))
    return sorted(achados)


def refs(*nomes):
    """'trilha R1.2–D1.1' / 'R1.2' -> ['R1', 'D1']"""
    saida = []
    for nome in nomes:
        for ref in re.findall(r"([A-Za-z_][\w]*)\.\w+", nome):
            if ref not in saida:
                saida.append(ref)
    return saida


def nets_partidas(modelo, bib):
    """nets cujo cobre ficou em mais de um pedaco (ex: dois GND que nao se encontram)"""
    pai = {}

    def raiz(a):
        while pai.setdefault(a, a) != a:
            a = pai[a]
        return a

    for t in modelo["trilhas"]:
        pai[raiz(t["de"])] = raiz(t["ate"])
    for peca in modelo["pecas"]:   # pinos da mesma peca com net fixa ja vem ligados por dentro (GND do DevKit)
        fixos = {}
        for n, *_, net in gerar.pinos_do_tipo(bib[peca["tipo"]]):
            if net:
                pai[raiz(f"{peca['ref']}.{n}")] = raiz(fixos.setdefault(net, f"{peca['ref']}.{n}"))
        for a, b in bib[peca["tipo"]].get("juntos", []):
            pai[raiz(f"{peca['ref']}.{a}")] = raiz(f"{peca['ref']}.{b}")
    pedacos = {}   # net -> {raiz: [pinos]}
    for peca in modelo["pecas"]:
        for p in peca["pinos"]:
            nome = f"{peca['ref']}.{p['n']}"
            if p["net"]:
                pedacos.setdefault(p["net"], {}).setdefault(raiz(nome), []).append(nome)
    return {net: list(ps.values()) for net, ps in pedacos.items() if len(ps) > 1}


# as 6 etapas; cada uma devolve o detalhe ou levanta Falhou
def le_txt(ctx):
    ctx["texto"] = (ctx["pasta"] / "placa.txt").read_text()
    ctx["lido"] = gerar.ler(ctx["texto"])
    n = sum(1 for linha in ctx["lido"]["linhas"] if linha.split("#")[0].strip())
    return f"{n} linhas, nenhum erro de digitação"


def confere_pecas(ctx):
    bib = ctx["bib"] = gerar.biblioteca(ctx["pasta"])
    gerar.conferir_tipos(ctx["lido"], bib)
    pecas = ctx["lido"]["pecas"].values()
    exemplo = sorted({p["ref"] for p in pecas if bib[p["tipo"]]["fonte"] is None})
    da_loja = [p["ref"] for p in pecas if bib[p["tipo"]].get("loja")]
    pendente = {p["ref"]: bib[p["tipo"]]["pendente"] for p in pecas if bib[p["tipo"]].get("pendente")}
    detalhe = f"{len(pecas)} peças" + (f", {len(da_loja)} da loja com o desenho oficial" if da_loja else ", todas existem na biblioteca")
    if exemplo:
        detalhe += f" · medidas de exemplo (sem datasheet): {', '.join(exemplo)}"
    for ref, falta in pendente.items():
        detalhe += f" · falta conferir no datasheet de {ref}: {'; '.join(falta)}"
    lista = catalogo.ler()["pecas"]   # a loja como o catalogo viu da ultima vez
    for p in pecas:
        e = lista.get(p["tipo"]) if bib[p["tipo"]].get("loja") else None
        if e and e["situacao"] != "ok":
            detalhe += f" · {p['ref']}: {e['situacao']} na loja (visto em {e['visto']})"
    return detalhe


def confere_ligacoes(ctx):
    modelo = gerar.montar(ctx["lido"], ctx["bib"])
    ctx["estado"]["versao"] = gerar.salvar_versao(ctx["pasta"], ctx["texto"], modelo, ctx["frase"])
    ctx["arquivos"] = gerar.escrever(modelo, ctx["pasta"] / "saida")
    ctx["modelo"] = modelo
    ligados = {t[p] for t in modelo["trilhas"] for p in ("de", "ate")}
    sem, solto = [], []
    for peca in modelo["pecas"]:
        usados = [p for p in peca["pinos"] if f"{peca['ref']}.{p['n']}" in ligados]
        if not usados:
            sem.append(peca["ref"])
        elif len(peca["pinos"]) == 2 and len(usados) == 1:
            livre = next(p["n"] for p in peca["pinos"] if p not in usados)
            solto.append(f"{peca['ref']}.{livre}")
        elif len(peca["pinos"]) <= 4:   # peca pequena com um lado sem net (ex: so um lado do botao ligado)
            lados = set()
            for p in peca["pinos"]:
                if p["net"] is None and (p["nome"] or p["n"]) not in lados:
                    lados.add(p["nome"] or p["n"])
                    solto.append(f"{peca['ref']}.{p['n']}")
    if sem:
        raise Falhou(f"{' e '.join(sem)} sem ligação", sem, "sem ligação")
    if solto:
        raise Falhou(f"pino solto: {', '.join(solto)}", refs(*solto), "pino solto")
    for peca in modelo["pecas"]:   # resistor, LED, pilha: os dois pinos na mesma net = a peca esta em curto
        if len(peca["pinos"]) == 2 and peca["pinos"][0]["net"] and peca["pinos"][0]["net"] == peca["pinos"][1]["net"]:
            raise Falhou(f"{peca['ref']} em curto: os dois pinos estão na net {peca['pinos'][0]['net']}", [peca["ref"]], "curto")
    partidas = nets_partidas(modelo, ctx["bib"])
    if partidas:
        net, pedacos = next(iter(partidas.items()))
        soltos = [p for pedaco in pedacos[1:] for p in pedaco]
        raise Falhou(f"{net} ficou partida em {len(pedacos)} pedaços: {', '.join(soltos)} não chega no resto",
                     refs(*soltos), "net partida")
    curtos = pares_perto(modelo, 0)
    if curtos:
        _, a, b = curtos[0]
        raise Falhou(f"curto: {a} encosta em {b}" + (f" (e mais {len(curtos) - 1})" if len(curtos) > 1 else ""),
                     refs(a, b), "curto")
    return f"{len(modelo['trilhas'])} ligações, nenhum pino solto, nenhum curto"


def liga_circuito(ctx):
    modelo = ctx["modelo"]
    sim = modelo["simulacao"]
    if not sim["pode"]:
        pendente = {p["ref"] for p in modelo["pecas"] if p["pendente"]}
        sem_modelo = [r for r in sim["falta_modelo"] if r not in pendente]
        motivo = []
        if pendente & set(sim["falta_modelo"]):
            motivo.append("falta conferir no datasheet: " + ", ".join(sorted(pendente & set(sim["falta_modelo"]))))
        if sem_modelo:
            motivo.append("sem modelo elétrico: " + ", ".join(sem_modelo))
        if sim["sem_valor"]:
            motivo.append("sem o valor em ohms no placa.txt: " + ", ".join(sim["sem_valor"]))
        raise Pulou("não dá pra ligar no papel ainda · " + " · ".join(motivo))
    try:
        nominal, fraca, nova = ligar(modelo, "v"), ligar(modelo, "v_min"), ligar(modelo, "v_max")
    except (ZeroDivisionError, KeyError) as e:
        raise Falhou(f"não consegui resolver o circuito: {e}")
    if nominal is None:
        raise Pulou("sem pilha na placa, nada pra ligar")
    ctx["sim"] = {"nominal": nominal, "nova": nova}   # as checagens acende/nao_queima usam isto
    problemas, frases = [], []
    for p in modelo["pecas"]:
        e, ref = p["eletrica"], p["ref"]
        r_nom, r_fraca, r_nova = nominal["pecas"][ref], fraca["pecas"][ref], nova["pecas"][ref]
        if e["modelo"] == "led":
            if r_nova["i"] > e["i_max"]:
                problemas.append((f"{ref} queima: recebe {ma(r_nova['i'])} mA com a pilha nova, o limite é {ma(e['i_max'])} mA", [ref], "queima"))
            brilho = blocos.brilho_da_corrente(e, r_nom["i"])
            quanto = f", ≈ {brilho * 100:.0f}% do brilho do anúncio" if brilho is not None else ""
            frases.append(f"{ref}: {ma(r_nom['i'])} mA{quanto} (de {ma(r_fraca['i'])} a {ma(r_nova['i'])} mA entre pilha fraca e nova; o limite é {ma(e['i_max'])} mA)")
        elif e["modelo"] == "resistor":
            if r_nova["p"] > e["potencia_max"]:
                problemas.append((f"{ref} esquenta demais: {mw(r_nova['p'])} mW, aguenta {mw(e['potencia_max'])} mW", [ref], "esquenta"))
            frases.append(f"{ref}: esquenta {mw(r_nova['p'])} mW, aguenta {mw(e['potencia_max'])} mW")
        elif e["modelo"] == "chave" and e.get("i_max") and abs(r_nova["i"]) > e["i_max"]:
            problemas.append((f"{ref} passa {ma(abs(r_nova['i']))} mA, o limite dele é {ma(e['i_max'])} mA", [ref], "corrente alta"))
        elif e["modelo"] == "pilha":
            horas = e["mah"] / (r_nom["i"] * 1000) if r_nom["i"] > 1e-6 else None
            frase = f"{ref}: {ma(r_nom['i'])} mA" + (f", dura no máximo ≈ {horas:.0f} h apertado" if horas and horas < 1e5 else "")
            if e.get("i_testada") and r_nom["i"] > e["i_testada"]:   # funciona, mas fora do que o fabricante da pilha mediu
                frase += f" (acima dos {ma(e['i_testada'])} mA que o fabricante da pilha testou: ela rende menos)"
            frases.append(frase)
    if problemas:
        problemas.sort(key=lambda p: p[2] != "queima")   # o LED queimando e o que importa, vem primeiro
        raise Falhou(" · ".join(p[0] for p in problemas), rotulos={ref: rot for _, onde, rot in problemas for ref in onde})
    return " · ".join(frases)


def regras_fabrica(ctx):
    modelo = ctx["modelo"]
    w, h = modelo["placa"]["w"], modelo["placa"]["h"]
    problemas = []   # (texto, onde, rotulo)
    for t in modelo["trilhas"]:
        if t["largura"] < TRILHA_MIN:
            problemas.append((f"trilha {t['de']}–{t['ate']} com {mm(t['largura'])} mm (mínimo {mm(TRILHA_MIN)})",
                              refs(t["de"], t["ate"]), "trilha fina"))
    for d, a, b in pares_perto(modelo, ESPACO_MIN):
        problemas.append((f"{a} a {mm(max(d, 0))} mm de {b} (mínimo {mm(ESPACO_MIN)})", refs(a, b), "perto demais"))
    furos_pad = []
    for peca in modelo["pecas"]:
        for p in peca["pinos"]:
            if not p["furo"]:
                continue
            nome = f"{peca['ref']}.{p['n']}"
            furos_pad.append((nome, p["x"], p["y"], p["furo"]))
            if not FURO_MIN <= p["furo"] <= FURO_MAX:
                problemas.append((f"furo de {nome} com {mm(p['furo'])} mm", [peca["ref"]], "furo"))
            menor = p["pad"]["d"] if p["pad"]["forma"] == "C" else min(p["pad"]["w"], p["pad"]["h"])
            anel = (menor - p["furo"]) / 2
            if anel < ANEL_MIN:
                problemas.append((f"anel de {nome} com {mm(anel)} mm (mínimo {mm(ANEL_MIN)})", [peca["ref"]], "anel fino"))
    for i, (n1, x1, y1, d1) in enumerate(furos_pad):
        for n2, x2, y2, d2 in furos_pad[i + 1:]:
            vao = math.hypot(x1 - x2, y1 - y2) - d1 / 2 - d2 / 2
            if vao < FURO_FURO_MIN:
                problemas.append((f"furos {n1} e {n2} a {mm(vao)} mm (mínimo {mm(FURO_FURO_MIN)})", refs(n1, n2), "furos colados"))
    for f in modelo["furos"]:
        if f["d"] < FURO_NPTH_MIN:
            problemas.append((f"furo de fixação com {mm(f['d'])} mm (mínimo {mm(FURO_NPTH_MIN)})", [], ""))
        r = f["d"] / 2
        if f["x"] - r < 0 or f["y"] - r < 0 or f["x"] + r > w or f["y"] + r > h:
            problemas.append(("furo de fixação fora da placa", [], ""))
    for nome, _, miolo, raio in cobres(modelo):
        x0, y0, x1, y1 = caixa(miolo, raio)
        folga = min(x0, y0, w - x1, h - y1)
        if folga < BORDA_MIN:
            problemas.append((f"{nome} a {mm(folga)} mm da borda (mínimo {mm(BORDA_MIN)})", refs(nome), "perto da borda"))
        for f in modelo["furos"]:
            d = distancia((miolo, raio), (("seg", (f["x"], f["y"]), (f["x"], f["y"])), f["d"] / 2))
            if d < BORDA_MIN:
                problemas.append((f"{nome} a {mm(d)} mm do furo de fixação (mínimo {mm(BORDA_MIN)})", refs(nome), "perto do furo"))
    pads = [(n, m, r) for n, _, m, r in cobres(modelo) if not n.startswith("trilha")]
    for i, (n1, m1, r1) in enumerate(pads):
        for n2, m2, r2 in pads[i + 1:]:
            d = distancia((m1, r1), (m2, r2))
            if 0 < d < PONTE_MIN:
                problemas.append((f"máscara entre {n1} e {n2} com {mm(d)} mm (mínimo {mm(PONTE_MIN)})", refs(n1, n2), "máscara"))
    if min(gerar.SILK, gerar.LETRA_LINHA) < SILK_MIN or gerar.LETRA < LETRA_MIN:
        problemas.append((f"serigrafia fina demais (linha {mm(SILK_MIN)} e letra {mm(LETRA_MIN)} mm no mínimo)", [], ""))
    if problemas:
        mais = f" (e mais {len(problemas) - 1})" if len(problemas) > 1 else ""
        rotulos = {}
        for _, onde, rotulo in problemas:
            for ref in onde:
                rotulos.setdefault(ref, rotulo)
        raise Falhou(problemas[0][0] + mais, rotulos=rotulos)
    return "trilha, espaço, furo, anel, borda, máscara e serigrafia (JLCPCB)"


MAPA_GERBER = {r".*-F_Cu\.gbr": "top copper", r".*-B_Cu\.gbr": "bottom copper",
               r".*-F_Mask\.gbr": "top mask", r".*-B_Mask\.gbr": "bottom mask",
               r".*-F_Silkscreen\.gbr": "top silk", r".*-Edge_Cuts\.gbr": "mechanical outline",
               r".*-PTH\.drl": "drill plated", r".*-NPTH\.drl": "drill nonplated"}


def rele_gerber(ctx):
    try:
        from gerbonara import LayerStack
    except ImportError:
        raise Falhou("gerbonara não instalado: uv pip install -r requirements.txt")
    saida = ctx["pasta"] / "saida"
    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        pilha = LayerStack.open_dir(saida, autoguess=False, overrides=MAPA_GERBER)
    if avisos:
        raise Falhou(f"{len(avisos)} aviso(s): {avisos[0].message}")
    ctx["pilha"] = pilha
    lidos = [f for f in saida.iterdir() if any(re.fullmatch(e, f.name) for e in MAPA_GERBER)]
    return f"{len(lidos)} arquivos lidos pelo gerbonara, nenhum aviso"


def tira_foto(ctx):
    saida = ctx["pasta"] / "saida"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")   # avisa das camadas que ainda nao existem (mascara, serigrafia)
        svg = str(ctx["pilha"].to_pretty_svg(side="top"))
    vb = [float(v) for v in re.search(r'viewBox="([^"]+)"', svg)[1].split()]
    largura = 1400
    altura = round(largura * vb[3] / vb[2])
    svg = re.sub(r'width="[^"]*" height="[^"]*"', f'width="{largura}" height="{altura}"', svg, count=1)
    (saida / "foto.svg").write_text(svg)
    chrome = next(filter(None, map(shutil.which, ["google-chrome", "chromium", "chromium-browser"])), None)
    if not chrome:
        return "sem Chrome pra virar png; salvei saida/foto.svg"
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    f"--screenshot={(saida / 'foto.png').resolve()}", f"--window-size={largura},{altura}",
                    (saida / "foto.svg").resolve().as_uri()], capture_output=True, timeout=60, check=True)
    return "saida/foto.png, desenhada a partir do Gerber"


# requisitos: o requisitos.md declara o objetivo e, pra cada requisito, as pecas e como verificar
CHECAGENS = {"existe": 1, "ligado": 2, "separado": 2, "sem_pino_solto": 1, "acende": 1, "nao_queima": 1,
             "brilho": 1}   # checagem -> quantos valores
MOTIVOS = {"existe": "falta a peça", "ligado": "falta ligar", "separado": "em curto", "sem_pino_solto": "pino solto",
           "acende": "não acende", "nao_queima": "queima", "brilho": "brilho diferente do pedido"}


def ler_requisitos(texto):
    obj = {"titulo": "", "texto": "", "itens": []}
    atual = None
    for n, linha in enumerate(texto.splitlines(), 1):
        l = linha.strip()
        if not l:
            continue
        if l.startswith("# "):
            obj["titulo"] = l[2:].removeprefix("Objetivo:").strip()
        elif l.startswith("## "):
            ident, _, titulo = l[3:].partition(" ")
            atual = {"id": ident, "titulo": titulo.strip(), "pecas": [], "detalhes": [], "verifica": []}
            obj["itens"].append(atual)
        elif atual is None:
            obj["texto"] = f"{obj['texto']} {l}".strip()
        elif l.startswith("pecas:"):
            atual["pecas"] += l[6:].split()
        elif l.startswith("verifica:"):
            p = l[9:].split()
            if not p or p[0] not in CHECAGENS:
                raise gerar.ErroTxt(n, f"checagem desconhecida '{l[9:].strip()}' (tem: {', '.join(CHECAGENS)})")
            if len(p) - 1 != CHECAGENS[p[0]]:
                raise gerar.ErroTxt(n, f"'{p[0]}' espera {CHECAGENS[p[0]]} valores")
            atual["verifica"].append({"texto": " ".join(p)})
        elif l.startswith("- "):
            atual["detalhes"].append(l[2:])
    return obj


def checar(texto, modelo, sim, projeto=None):
    """True/False, ou None quando nao da pra saber (acende/nao_queima/brilho sem simulacao)"""
    cmd, *a = texto.split()
    pecas = {p["ref"]: p for p in modelo["pecas"]}
    pecas_da_net = {}   # net -> pecas que tem pino nela
    for p in modelo["pecas"]:
        for pino in p["pinos"]:
            pecas_da_net.setdefault(pino["net"], set()).add(p["ref"])

    def nets(x):   # REF.PINO -> net do pino; REF -> nets de qualquer pino dela; senao e nome de net
        if "." in x:
            ref, n = x.split(".", 1)
            pino = next((q for q in pecas.get(ref, {}).get("pinos", []) if q["n"] == n), None)
            return {pino["net"]} if pino and pino["net"] else set()
        if x in pecas:
            return {q["net"] for q in pecas[x]["pinos"] if q["net"]}
        return {x}

    if cmd == "existe":
        return a[0] in pecas
    if cmd == "ligado":
        return bool(nets(a[0]) & nets(a[1]))
    if cmd == "separado":   # nao pode ser a mesma net (ex: os dois lados de um botao)
        return not nets(a[0]) & nets(a[1])
    if cmd in ("acende", "nao_queima"):   # com as chaves apertadas: acende na pilha nominal, nao queima na nova
        r = (sim or {}).get("nominal", {}).get("pecas", {}).get(a[0])
        if not r or "acende" not in r:   # sem simulacao, ou a peca nao e LED
            return None
        return r["acende"] if cmd == "acende" else not sim["nova"]["pecas"][a[0]]["queima"]
    if cmd == "brilho":   # o brilho na pilha nominal e o nivel que o Luiz pediu (fraca/media/forte, o mais perto)
        r = (sim or {}).get("nominal", {}).get("pecas", {}).get(a[0])
        pedido = ((projeto or {}).get("perguntas", {}).get("brilho") or {}).get("resposta")
        e = (pecas.get(a[0]) or {}).get("eletrica") or {}
        b = blocos.brilho_da_corrente(e, r["i"]) if r and "acende" in r else None
        if b is None or not pedido:
            return None
        return blocos.nivel_do_brilho(b) == pedido
    if cmd == "sem_pino_solto":   # cada pino chega em alguma OUTRA peca (o par interno do botao nao conta)
        return a[0] in pecas and all(q["net"] and pecas_da_net[q["net"]] - {a[0]} for q in pecas[a[0]]["pinos"])


def avaliar_requisitos(pasta, modelo, sim=None):
    """sim = o resultado da etapa 4 (so existe se ela passou); sem ele, acende/nao_queima ficam em '?'"""
    arq = pasta / "requisitos.md"
    if not arq.exists():
        return None
    try:
        obj = ler_requisitos(arq.read_text())
    except gerar.ErroTxt as e:
        return {"titulo": "", "texto": "", "itens": [], "erro": f"requisitos.md, linha {e.linha}: {e.msg}"}
    projeto = blocos.ler_projeto(pasta)
    for item in obj["itens"]:
        if modelo is None:
            item.update(status="?", motivo="a placa não montou")
            continue
        for v in item["verifica"]:
            v["ok"] = checar(v["texto"], modelo, sim, projeto)
        falha = next((v for v in item["verifica"] if v["ok"] is False), None)
        if not item["verifica"]:
            item.update(status="?", motivo="sem verificação")
        elif any(v["ok"] is None for v in item["verifica"]) and not falha:
            item.update(status="?", motivo="não dá pra ligar no papel")
        elif falha:
            item.update(status="falha", motivo=MOTIVOS[falha["texto"].split()[0]])
        else:
            item.update(status="ok", motivo="ok")
    return obj


# a rodada
def salvar(arq, estado):
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(estado, ensure_ascii=False, indent=1))
    tmp.replace(arq)   # troca de uma vez: a bancada nunca le arquivo pela metade


def rodar(pasta, frase=None):
    arq = pasta / "testes.json"
    try:
        anterior = json.loads(arq.read_text())
    except (OSError, ValueError):
        anterior = {}
    estado = {"versao": None, "rodando": True, "inicio": datetime.now().isoformat(timespec="seconds"),
              "etapas": [{"nome": n, "estado": "aguardando", "detalhe": ""} for n in ETAPAS],
              "requisitos": {}, "resumo": ""}
    ctx = {"pasta": pasta, "frase": frase, "estado": estado, "anterior": anterior}
    (pasta / "saida" / "fabrica.zip").unlink(missing_ok=True)
    salvar(arq, estado)
    funcoes = [le_txt, confere_pecas, confere_ligacoes, liga_circuito, regras_fabrica, rele_gerber, tira_foto]
    try:
        rodar_etapas(ctx, funcoes, arq)
    finally:   # aconteca o que acontecer, o testes.json nunca fica "rodando" pra sempre
        estado["rodando"] = False
        estado["fim"] = datetime.now().isoformat(timespec="seconds")
        salvar(arq, estado)
    return estado


def rodar_etapas(ctx, funcoes, arq):
    estado, pasta = ctx["estado"], ctx["pasta"]
    for etapa, funcao in zip(estado["etapas"], funcoes):
        etapa["estado"] = "rodando"
        salvar(arq, estado)
        try:
            etapa["detalhe"] = funcao(ctx)
            etapa["estado"] = "ok"
        except Pulou as e:
            etapa.update(estado="pulou", detalhe=str(e))
        except Falhou as e:
            etapa.update(estado="falhou", detalhe=e.detalhe, onde=e.onde, rotulos=e.rotulos)
        except gerar.ErroTxt as e:
            linhas = ctx.get("texto", "").splitlines()
            etapa.update(estado="falhou", detalhe=f"linha {e.linha}: {e.msg}", onde=e.onde, linha=e.linha,
                         codigo=linhas[e.linha - 1] if 0 < e.linha <= len(linhas) else "",
                         rotulos={ref: "erro no txt" for ref in e.onde})
        except Exception as e:   # erro inesperado tambem para a rodada, sem esconder
            etapa.update(estado="falhou", detalhe=f"erro inesperado: {e!r}", onde=[], rotulos={})
        if etapa["estado"] == "falhou":
            for resto in estado["etapas"][estado["etapas"].index(etapa) + 1:]:
                resto["estado"] = "nao_rodou"
            break
    tudo_ok = all(e["estado"] in ("ok", "pulou") for e in estado["etapas"])
    if tudo_ok and ctx["modelo"]["fabrica"]["pronta"]:
        gerar.zipar(pasta / "saida", ctx["arquivos"])   # fabrica.zip so existe se passou em tudo
    try:
        objetivo = avaliar_requisitos(pasta, ctx.get("modelo"), ctx.get("sim"))
    except Exception as e:   # requisito nao pode derrubar a rodada inteira
        objetivo = {"titulo": "", "texto": "", "itens": [], "erro": f"requisitos: erro inesperado: {e!r}"}
    if objetivo:
        estado["objetivo"] = objetivo
        estado["requisitos"] = {i["id"]: i["status"] for i in objetivo["itens"]}
        for etapa in estado["etapas"]:
            if etapa.get("onde"):
                etapa["requisitos"] = [i["id"] for i in objetivo["itens"] if set(i["pecas"]) & set(etapa["onde"])]
    if ctx["anterior"].get("resumo") and ctx["anterior"].get("versao") == estado["versao"]:
        estado["resumo"] = ctx["anterior"]["resumo"]   # a placa nao mudou, o resumo do Claude continua valendo


def escrever_resumo(pasta, texto):
    arq = pasta / "testes.json"
    estado = json.loads(arq.read_text())
    estado["resumo"] = texto
    salvar(arq, estado)


if __name__ == "__main__":
    args = sys.argv[1:]
    opcoes = {}
    for chave in ("-m", "--resumo"):
        if chave in args:
            i = args.index(chave)
            opcoes[chave] = args[i + 1]
            del args[i:i + 2]
    pasta = Path(args[0] if args else "placas/estudo")
    if "--resumo" in opcoes:
        escrever_resumo(pasta, opcoes["--resumo"])
        sys.exit()
    estado = rodar(pasta, opcoes.get("-m"))
    for i, e in enumerate(estado["etapas"], 1):
        marca = {"ok": "✓", "falhou": "✗"}.get(e["estado"], "·")
        print(f"{marca} {i}. {e['nome']}: {e['detalhe'] or e['estado']}")
    for ident, status in estado["requisitos"].items():
        print(f"  {ident}: {status}")
    if estado.get("objetivo", {}).get("erro"):
        print(f"  {estado['objetivo']['erro']}")
    sys.exit(0 if all(e["estado"] == "ok" for e in estado["etapas"]) else 1)
