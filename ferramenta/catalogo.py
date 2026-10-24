"""catalogo.py: a lista de compras de sempre (ferramenta/catalogo/, um arquivo por categoria).

Cada arquivo diz o que é a categoria (nome, grupo, uma frase pro Luiz), como achar as peças dela na loja (sementes),
o que serve (filtro), o que diferencia uma peça da outra (destaques) e como dar nome a cada uma; e guarda as peças.
Cada peça tem tudo que a loja diz, o dia em que viu (visto), a situação (ok, sem estoque, sumiu), outras lojas que
vendem a mesma coisa e, quando o Claude leu o datasheet, o que ele conferiu. O app procura aqui primeiro, na hora e
sem internet; a loja online é o double check (checar) e o jeito de achar peça nova (encher, buscar).

uso: python3 ferramenta/catalogo.py encher [categoria]      (busca as sementes na loja e põe as peças na lista)
     python3 ferramenta/catalogo.py checar [codigo ...]     (preço e estoque na loja agora; sem código, a lista toda)
     python3 ferramenta/catalogo.py ver [categoria]
     python3 ferramenta/catalogo.py limpar <categoria>     (tira da LCSC o que não passa mais no filtro; conferida fica)
     python3 ferramenta/catalogo.py categorias

Formato de uma categoria (ferramenta/catalogo/<id>.json):
  {"categoria": "capacitor", "nome": "Capacitor", "grupo": "Passivos",
   "explica": "uma frase de gente: pra que serve",
   "nome_peca": "Capacitor {Capacitance}, {Voltage Rated}",     # {Atributo da loja}; faltou um, vira "<nome> <modelo>"
   "destaques": ["Capacitance", "Voltage Rated", "Tolerance"],   # o que aparece no cartão
   "chips": "Capacitance",                                       # atributo dos botões de filtro (opcional)
   "filtro": {"montagem": ["furo"],                              # furo | superfície | módulo (sem: qualquer)
              "categorias_loja": ["Capacitors"],                 # pedaço do nome da categoria na loja (sem: qualquer)
              "pacotes": ["4P"],                                 # pedaço do pacote (sem: qualquer)
              "atributos": ["Capacitance"],                      # atributos que a peça tem que ter
              "valores": {"Illumination Color": ["Red", "Blue"]}},  # atributo -> valores aceitos
   "sementes": [{"busca": "100nF 50V ceramic", "quantos": 4, "agrupar": "Capacitance"}],
   "pecas": {"C123": {...}}}
"""
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

PASTA = Path(__file__).parent / "catalogo"
E24 = [10, 11, 12, 13, 15, 16, 18, 20, 22, 24, 27, 30, 33, 36, 39, 43, 47, 51, 56, 62, 68, 75, 82, 91]
CORES = {"Red": "vermelho", "Orange Red": "laranja-avermelhado", "Orange": "laranja", "Yellow": "amarelo",
         "Yellow Green": "verde-amarelado", "Green": "verde", "Emerald Green": "verde", "Blue": "azul", "White": "branco"}
CAMPOS_SPEC = ("categoria", "nome", "grupo", "explica", "nome_peca", "destaques", "chips", "filtro", "sementes")


def ohms_busca(o):
    """como a loja escreve o valor: 240Ω, 1.1kΩ"""
    return f"{o:g}Ω" if o < 1000 else f"{o / 1000:g}kΩ"


def hoje():
    return datetime.now().strftime("%Y-%m-%d")


# ---------- ler e salvar ----------
def ler():
    """{"categorias": {id: spec}, "pecas": {codigo: peca (com "categoria")}}"""
    cat = {"categorias": {}, "pecas": {}}
    for arq in sorted(PASTA.glob("*.json")):
        d = json.loads(arq.read_text())
        cat["categorias"][d["categoria"]] = {k: d[k] for k in CAMPOS_SPEC if k in d}
        for codigo, e in d.get("pecas", {}).items():
            cat["pecas"][codigo] = {**e, "categoria": d["categoria"]}
    return cat


def numero(txt):
    """'4.7kΩ' -> 4700, '100nF' -> 1e-07, '3.3V' -> 3.3; pra ordenar"""
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*([pnuµmkM]?)", str(txt or ""))
    if not m:
        return None
    return float(m[1]) * {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "k": 1e3, "M": 1e6, "": 1}[m[2]]


def chave(spec, e):
    """ordem dentro da categoria: pelo atributo dos chips (valor), depois mais estoque"""
    v = e["atributos"].get(spec.get("chips") or "", "")
    return (numero(v) is None, numero(v) or 0, str(v), -(e.get("estoque") or 0))


def salvar(cat, so=None):
    """grava cada categoria no seu arquivo (so=lista de categorias pra gravar so essas)"""
    PASTA.mkdir(exist_ok=True)
    for cid, spec in cat["categorias"].items():
        if so and cid not in so:
            continue
        pecas = sorted(((c, e) for c, e in cat["pecas"].items() if e["categoria"] == cid),
                       key=lambda ce: (chave(spec, ce[1]), ce[0]))
        dado = {**{k: spec[k] for k in CAMPOS_SPEC if k in spec},
                "pecas": {c: {k: v for k, v in e.items() if k != "categoria"} for c, e in pecas}}
        arq = PASTA / f"{cid}.json"
        tmp = arq.with_suffix(".tmp")
        tmp.write_text(json.dumps(dado, ensure_ascii=False, indent=1) + "\n")
        tmp.replace(arq)


# ---------- o que serve pra cada categoria ----------
def montagem(i):
    if i["pacote"].startswith(("Plugin", "Through Hole")) or "Through Hole" in i["categoria"]:
        return "furo"
    if any(p in i["categoria"] for p in ("Module", "Development", "Dev Board", "Evaluation")):
        return "módulo"
    return "superfície"


def serve(cat, categoria, i):
    """a peca da loja e do tipo certo, com estoque? (a busca da loja traz de tudo)"""
    f = cat["categorias"][categoria].get("filtro", {})
    if (i.get("estoque") or 0) <= 0:
        return False
    if f.get("montagem") and montagem(i) not in f["montagem"]:
        return False
    if f.get("categorias_loja") and not any(c.lower() in i["categoria"].lower() for c in f["categorias_loja"]):
        return False
    if f.get("pacotes") and not any(p in i["pacote"] for p in f["pacotes"]):
        return False
    if any(not i["atributos"].get(a) or i["atributos"][a] == "-" for a in f.get("atributos", [])):
        return False
    return all(i["atributos"].get(a) in vs for a, vs in f.get("valores", {}).items())


def nome_da_peca(cat, categoria, i):
    import blocos
    if categoria in blocos.BLOCOS:   # as categorias que ja montam placa tem nome feito a mao
        return blocos.nome_da_loja(categoria, i)
    spec = cat["categorias"][categoria]
    modelo = spec.get("nome_peca") or ""
    campos = re.findall(r"\{([^}]+)\}", modelo)
    if campos and all(i["atributos"].get(c) and i["atributos"][c] != "-" for c in campos):
        return re.sub(r"\{([^}]+)\}", lambda m: i["atributos"][m[1]], modelo)
    return f"{spec['nome']} {i['modelo']}".strip()


def entrada(cat, categoria, i):
    import blocos
    return {"nome": nome_da_peca(cat, categoria, i), "marca": i["marca"], "modelo": i["modelo"],
            "pacote": i["pacote"], "tamanho": blocos.tamanho(i["pacote"]), "montagem": montagem(i),
            "categoria_loja": i["categoria"], "descricao": i["descricao"], "atributos": i["atributos"],
            "datasheet": i["datasheet"], "loja": "LCSC", "link": i["link"], "preco": i["preco"], "moeda": "USD",
            "minimo": i["minimo"], "estoque": i["estoque"], "visto": hoje(), "situacao": "ok"}


def adicionar(cat, categoria, itens):
    """poe (ou atualiza) pecas da LCSC na lista; o conferido, outras lojas e a medida do desenho ficam. Devolve as novas"""
    novas = 0
    for i in itens:
        velha = cat["pecas"].get(i["codigo"])
        nova = {**entrada(cat, categoria, i), "categoria": categoria}
        if velha:
            medida = velha.get("tamanho")
            nova = {**velha, **nova, "categoria": velha["categoria"]}   # quem ja estava numa categoria fica nela
            if nova["tamanho"] == nova["pacote"] and medida:
                nova["tamanho"] = medida
        else:
            novas += 1
        cat["pecas"][i["codigo"]] = nova
    return novas


def encher(cat, categoria=None, avisar=print):
    import loja
    total = 0
    for cid, spec in cat["categorias"].items():
        if categoria and cid != categoria:
            continue
        for s in spec.get("sementes", []):
            itens = [i for i in loja.buscar(s["busca"], 100 if s.get("agrupar") else 30) if serve(cat, cid, i)]
            itens.sort(key=lambda i: -i["estoque"])
            grupos = {}   # agrupar: as de mais estoque de cada valor do atributo (ex: de cada cor)
            for i in itens:
                grupos.setdefault(i["atributos"].get(s["agrupar"]) if s.get("agrupar") else "", []).append(i)
            escolhidas = [i for g in grupos.values() for i in g[:s.get("quantos", 4)]]
            n = adicionar(cat, cid, escolhidas)
            total += n
            avisar(f"{cid}: '{s['busca']}' -> {len(escolhidas)} peças ({n} novas)")
            time.sleep(0.3)   # devagar com a loja
    return total


def checar(cat, codigos=None, avisar=print):
    """preco e estoque agora, direto da LCSC (sem cache); marca 'sem estoque' e 'sumiu'. Peca de outra loja: pula"""
    import loja
    mudou = []
    for codigo in codigos or list(cat["pecas"]):
        e = cat["pecas"].get(codigo)
        if not e or e.get("loja", "LCSC") != "LCSC":
            continue
        try:
            i = loja.ficha(codigo, validade=0)
        except loja.SemLoja as erro:
            if "não está na loja" in str(erro):
                e.update(situacao="sumiu", visto=hoje())
                mudou.append(codigo)
                avisar(f"{codigo}: sumiu da loja")
            else:
                avisar(f"{codigo}: {erro}")
            continue
        antes = (e["estoque"], e["preco"], e["situacao"])
        e.update(estoque=i["estoque"], preco=i["preco"], minimo=i["minimo"], visto=hoje(),
                 situacao="ok" if i["estoque"] > 0 else "sem estoque")
        if (e["estoque"], e["preco"], e["situacao"]) != antes:
            mudou.append(codigo)
        avisar(f"{codigo}: {e['situacao']}, {e['estoque']} em estoque, US$ {e['preco']}")
        time.sleep(0.2)
    return mudou


def limpar(cat, categoria):
    """tira da categoria as pecas da LCSC que nao passam mais no filtro dela (depois de apertar o filtro); conferida fica"""
    fora = []
    for codigo, e in list(cat["pecas"].items()):
        if e["categoria"] != categoria or e.get("loja", "LCSC") != "LCSC" or e.get("conferido"):
            continue
        como_loja = {**e, "categoria": e.get("categoria_loja", ""), "estoque": e.get("estoque") or 1}   # estoque: sem estoque fica, marcada
        if not serve(cat, categoria, como_loja):
            fora.append(codigo)
            del cat["pecas"][codigo]
    return fora


def do_bloco(cat, categoria):
    return [{"codigo": c, **e} for c, e in cat["pecas"].items() if e["categoria"] == categoria]


def conferido(codigo):
    return (ler()["pecas"].get(codigo) or {}).get("conferido")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    args = sys.argv[1:]
    cat = ler()
    if args[:1] == ["encher"]:
        alvo = args[1] if len(args) > 1 else None
        if alvo and alvo not in cat["categorias"]:
            sys.exit(f"categoria '{alvo}' não existe (tem: {', '.join(cat['categorias'])})")
        print(f"{encher(cat, alvo)} peças novas")
        salvar(cat, [alvo] if alvo else None)
    elif args[:1] == ["checar"]:
        print(f"{len(checar(cat, args[1:] or None))} mudaram")
        salvar(cat)
    elif args[:1] == ["ver"]:
        for c, e in cat["pecas"].items():
            if len(args) < 2 or e["categoria"] == args[1]:
                print(f"{c:>12}  {e['categoria']:12}  {e['nome'][:38]:38}  {e['modelo'][:24]:24}  {e.get('montagem', ''):10}  "
                      f"{e['situacao']:11}  {e.get('estoque') or '':>7}  {'conferido' if e.get('conferido') else ''}")
    elif args[:1] == ["limpar"] and len(args) == 2 and args[1] in cat["categorias"]:
        fora = limpar(cat, args[1])
        print(f"{len(fora)} peças saíram: {' '.join(fora)}")
        salvar(cat, [args[1]])
    elif args[:1] == ["categorias"]:
        for cid, spec in cat["categorias"].items():
            n = sum(1 for e in cat["pecas"].values() if e["categoria"] == cid)
            print(f"{cid:16} {spec['grupo']:22} {spec['nome']:28} {n:>4} peças")
    else:
        sys.exit(__doc__)
