"""catalogo.py: a lista de compras de sempre (ferramenta/catalogo.json).

Cada peça que a gente já viu na loja, com tudo que a loja diz (preço, estoque e o dia em que viu) e, quando o
Claude leu o datasheet, o que ele conferiu (polaridade, pinos ligados por dentro, limites, curvas). O app procura
aqui primeiro, na hora e sem internet; a loja online é o double check (checar) e o jeito de achar peça nova (buscar).
Peça que sumiu da loja ou ficou sem estoque não sai da lista: fica marcada, pra ninguém escolher sem ver.

uso: python3 ferramenta/catalogo.py encher [bloco]        (busca as peças de cada bloco na loja e põe na lista)
     python3 ferramenta/catalogo.py checar [codigo ...]   (preço e estoque na loja agora; sem código, a lista toda)
     python3 ferramenta/catalogo.py ver [bloco]
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ARQ = Path(__file__).parent / "catalogo.json"
E24 = [10, 11, 12, 13, 15, 16, 18, 20, 22, 24, 27, 30, 33, 36, 39, 43, 47, 51, 56, 62, 68, 75, 82, 91]


def ohms_busca(o):
    """como a loja escreve o valor: 240Ω, 1.1kΩ"""
    return f"{o:g}Ω" if o < 1000 else f"{o / 1000:g}kΩ"

CORES = {"Red": "vermelho", "Orange Red": "laranja-avermelhado", "Orange": "laranja", "Yellow": "amarelo",
         "Yellow Green": "verde-amarelado", "Green": "verde", "Emerald Green": "verde", "Blue": "azul", "White": "branco"}

# buscas que enchem cada bloco (a busca da JLCPCB e por palavra exata) e quantas pecas de cada uma entram
SEMENTES = {
    "pilha": ["CR2032 Plugin"],
    "botao": ["6x6mm tactile", "Tactile Switches 6x6"],
    "led": ["LED 5mm", "LED 3mm"],   # "LED 5mm green" nao acha nada; a geral traz todas as cores
    "resistor": [f"{ohms_busca(v * 10 ** d)} 250mW metal film through hole resistor" for d in range(0, 3) for v in E24]
                + ["10kΩ 250mW metal film through hole resistor"],
}
POR_BUSCA = {"pilha": 10, "botao": 12, "led": 4, "resistor": 3}   # LED: 4 de cada cor


def hoje():
    return datetime.now().strftime("%Y-%m-%d")


def ler():
    return json.loads(ARQ.read_text()) if ARQ.exists() else {"pecas": {}}


def salvar(cat):
    import blocos
    ordem = {b: i for i, b in enumerate(blocos.BLOCOS)}
    pecas = dict(sorted(cat["pecas"].items(), key=lambda kv: (ordem.get(kv[1]["bloco"], 99), chave(kv[1]), kv[0])))
    cat = {"_leia": cat.get("_leia", LEIA), "pecas": pecas}
    tmp = ARQ.with_suffix(".tmp")
    tmp.write_text(json.dumps(cat, ensure_ascii=False, indent=1) + "\n")
    tmp.replace(ARQ)


LEIA = ("A lista de compras do Sianvolt: cada peça da loja (código da LCSC) com o que a loja diz, o dia em que viu "
        "(visto) e a situação (ok, sem estoque, sumiu). 'conferido' é o que o Claude leu no datasheet; sem ele, a peça "
        "só entra na placa depois de conferida. O desenho (pads, furos) vem do EasyEDA e fica só na máquina.")


def chave(e):
    """ordem dentro do bloco: resistor por valor, LED por cor e tamanho"""
    import blocos
    if e["bloco"] == "resistor":
        return (blocos.numero_com_unidade(e["atributos"].get("Resistance"), "Ω") or 0, -e["estoque"])
    if e["bloco"] == "led":
        return (e["atributos"].get("Illumination Color", ""), e["pacote"], -e["estoque"])
    return (-e["estoque"],)


# ---------- o que serve pra cada bloco ----------
def serve(bloco, i):
    """peca de furo, com estoque, do tipo certo (a busca da loja traz de tudo)"""
    import blocos
    if not blocos.de_furo(i) or i["estoque"] <= 0:
        return False
    at = i["atributos"]
    if bloco == "resistor":
        return i["categoria"] == "Through Hole Resistors" and bool(at.get("Resistance")) and bool(at.get("Power(Watts)"))
    if bloco == "led":
        return at.get("Illumination Color") in CORES
    if bloco == "botao":
        return "Tactile" in i["categoria"] and "4P" in i["pacote"]
    if bloco == "pilha":
        return bool(at.get("Battery Type"))
    return True


def entrada(bloco, i):
    import blocos
    return {"bloco": bloco, "nome": blocos.nome_da_loja(bloco, i), "marca": i["marca"], "modelo": i["modelo"],
            "pacote": i["pacote"], "tamanho": blocos.tamanho(i["pacote"]), "categoria": i["categoria"],
            "descricao": i["descricao"], "atributos": i["atributos"], "datasheet": i["datasheet"], "link": i["link"],
            "preco": i["preco"], "minimo": i["minimo"], "estoque": i["estoque"], "visto": hoje(), "situacao": "ok"}


def adicionar(cat, bloco, itens):
    """poe (ou atualiza) as pecas na lista; o que o Claude conferiu nunca se perde. Devolve quantas eram novas"""
    novas = 0
    for i in itens:
        velha = cat["pecas"].get(i["codigo"])
        nova = entrada(bloco, i)
        if velha:   # o que a loja diz agora por cima; o conferido e a medida tirada do desenho ficam
            medida = velha.get("tamanho")
            nova = {**velha, **nova}
            if nova["tamanho"] == nova["pacote"] and medida:
                nova["tamanho"] = medida
        else:
            novas += 1
        cat["pecas"][i["codigo"]] = nova
    return novas


def encher(cat, bloco=None, avisar=print):
    import loja
    total = 0
    for b, buscas in SEMENTES.items():
        if bloco and b != bloco:
            continue
        for busca in buscas:
            itens = [i for i in loja.buscar(busca, 100 if b == "led" else 30) if serve(b, i)]
            itens.sort(key=lambda i: -i["estoque"])
            grupos = {}   # LED: as de mais estoque de cada cor; o resto: as de mais estoque
            for i in itens:
                grupos.setdefault(i["atributos"].get("Illumination Color") if b == "led" else "", []).append(i)
            escolhidas = [i for g in grupos.values() for i in g[:POR_BUSCA[b]]]
            n = adicionar(cat, b, escolhidas)
            total += n
            avisar(f"{b}: '{busca}' -> {len(escolhidas)} peças ({n} novas)")
            time.sleep(0.3)   # devagar com a loja
    return total


def checar(cat, codigos=None, avisar=print):
    """preco e estoque agora, direto da loja (sem cache); marca 'sem estoque' e 'sumiu'"""
    import loja
    mudou = []
    for codigo in codigos or list(cat["pecas"]):
        e = cat["pecas"].get(codigo)
        if not e:
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


def do_bloco(cat, bloco):
    return [{"codigo": c, **e} for c, e in cat["pecas"].items() if e["bloco"] == bloco]


def conferido(codigo):
    return (ler()["pecas"].get(codigo) or {}).get("conferido")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    args = sys.argv[1:]
    cat = ler()
    if args[:1] == ["encher"]:
        print(f"{encher(cat, args[1] if len(args) > 1 else None)} peças novas")
        salvar(cat)
    elif args[:1] == ["checar"]:
        print(f"{len(checar(cat, args[1:] or None))} mudaram")
        salvar(cat)
    elif args[:1] == ["ver"]:
        for c, e in cat["pecas"].items():
            if len(args) < 2 or e["bloco"] == args[1]:
                print(f"{c:>10}  {e['bloco']:8}  {e['nome'][:34]:34}  {e['modelo'][:24]:24}  {e['situacao']:11}  "
                      f"{e['estoque']:>7}  {'conferido' if e.get('conferido') else ''}")
    else:
        sys.exit(__doc__)
