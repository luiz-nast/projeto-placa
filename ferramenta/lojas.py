"""lojas.py: preço e estoque das lojas brasileiras que dá pra ler sem login (pro checar do catálogo).

Só a página do produto, que o robots.txt de cada uma libera, com a pausa que ele pede (Crawl-delay). Sem busca,
sem carrinho, sem login. A LCSC fica no loja.py; aqui é o resto.
"""
import html
import json
import re
import time
import urllib.request
from urllib.parse import urlparse

# host -> (nome da loja, pausa entre páginas em segundos, como ler)
LOJAS = {"www.eletrogate.com": ("Eletrogate", 10, "loja_integrada"),
         "www.baudaeletronica.com.br": ("Baú da Eletrônica", 10, "loja_integrada"),
         "www.usinainfo.com.br": ("Usinainfo", 5, "usinainfo"),
         "www.robocore.net": ("RoboCore", 5, "robocore")}
AGENTE = "sianvolt-catalogo/0.1 (uso pessoal; confere preço e estoque de poucas páginas)"
ultima = {}   # host -> quando leu a última página


class SemPagina(Exception):
    pass


def meta(t, prop):
    m = re.search(r'<meta\s+(?:property|name|itemprop)="' + re.escape(prop) + r'"\s+content="([^"]*)"', t) or \
        re.search(r'<meta\s+content="([^"]*)"\s+(?:property|name|itemprop)="' + re.escape(prop) + r'"', t)
    return html.unescape(m[1]).strip() if m else None


def disponivel(t):
    m = re.search(r'itemprop="availability" content="[^"]*/(\w+)"', t)
    return (m[1] == "InStock") if m else None


def loja_integrada(t):
    """Eletrogate e Baú (plataforma Loja Integrada): o preço do produto fica no bloco 'acoes-produto'"""
    i = t.find('class="acoes-produto')
    fim = t.find('itemprop="offers"', i)
    bloco = t[i:fim if fim > i else i + 3000] if i >= 0 else ""
    m = re.search(r'data-sell-price="([\d.]+)"', bloco) or re.search(r"var produto_preco = ([\d.]+);", t)
    tem = disponivel(t)
    if i >= 0 and 'class="acoes-produto indisponivel' in t[:i + 100]:
        tem = False
    return {"preco": float(m[1]) if m else None, "disponivel": tem, "estoque": None, "foto": meta(t, "og:image")}


def usinainfo(t):
    p = meta(t, "product:price:amount")
    m = re.search(r"var quantityAvailable = (-?\d+);", t)
    estoque = max(int(m[1]), 0) if m else None
    tem = disponivel(t) if estoque is None else estoque > 0
    return {"preco": float(p) if p else None, "disponivel": tem, "estoque": estoque, "foto": meta(t, "og:image")}


def robocore(t):
    m = re.search(r"getElementById\('valor_\d+'\)\.innerHTML = \"(.*?)\";", t, re.S)
    precos = re.findall(r"R\$\s*([\d.]+)\s*,\s*(\d{2})", re.sub(r"<[^>]+>", " ", m[1])) if m else []
    preco = float(precos[0][0].replace(".", "") + "." + precos[0][1]) if precos else (
        float(meta(t, "product:price:amount")) if meta(t, "product:price:amount") else None)
    m = re.search(r"\((\d+) un\. em estoque\)", t)
    estoque = int(m[1]) if m else None
    av = meta(t, "product:availability")
    return {"preco": preco, "disponivel": (av == "in stock") if av else (estoque or 0) > 0, "estoque": estoque,
            "foto": meta(t, "og:image")}


def ler(url):
    """{"preco", "disponivel", "estoque", "foto"} da página do produto; levanta SemPagina"""
    host = urlparse(url).netloc
    if host not in LOJAS or not url.startswith("https://"):
        raise SemPagina(f"não sei ler {host}")
    _, pausa, como = LOJAS[host]
    espera = ultima.get(host, 0) + pausa - time.monotonic()
    if espera > 0:
        time.sleep(espera)
    req = urllib.request.Request(url, headers={"User-Agent": AGENTE, "Accept-Encoding": "identity"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            corpo = r.read()
    except OSError as e:
        raise SemPagina(f"{host} não respondeu ({e})")
    finally:
        ultima[host] = time.monotonic()
    t = corpo.decode("latin-1" if host == "www.robocore.net" else "utf-8", errors="replace")
    return {"loja_integrada": loja_integrada, "usinainfo": usinainfo, "robocore": robocore}[como](t)


def nome_da_loja(url):
    return LOJAS.get(urlparse(url).netloc, (None,))[0]


if __name__ == "__main__":
    import sys
    print(json.dumps(ler(sys.argv[1]), ensure_ascii=False))
