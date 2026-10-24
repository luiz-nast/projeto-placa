"""geometria.py: distância entre pedaços de cobre. Cada um é um "miolo" (segmento ou retângulo) mais um raio em volta.

Usado pelo roteador (gerar.py) pra escolher o caminho da trilha e pelas checagens (testar.py) pra achar curto e folga.
"""
import math


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


ENCOSTA = 1e-3   # o que a distancia devolve (alem dos raios) quando os cobres se tocam ou um entra no outro


def distancia(c1, c2):
    """distancia entre as bordas de dois cobres; c = (miolo, raio). Negativa = encostam: um entra no outro, as bordas
    se cruzam ou se tocam (inclusive retangulo dentro de retangulo, que da distancia de borda zero)"""
    (m1, r1), (m2, r2) = c1, c2
    s1, s2 = segmentos(m1), segmentos(m2)
    if any(dentro(s[0], m2) for s in s1) or any(dentro(s[0], m1) for s in s2):
        return -ENCOSTA - r1 - r2
    d = min(dist_seg_seg(a, b, c, e) for a, b in s1 for c, e in s2)
    return (-ENCOSTA if d == 0 else d) - r1 - r2


def sobrepoe(a, b, folga=0.05):
    """dois corpos de peça (("ret", x0, y0, x1, y1) ou ("circ", x, y, raio)) se sobrepoem mais que a folga?"""
    if a[0] == "circ" and b[0] == "ret":
        a, b = b, a
    if a[0] == "ret" and b[0] == "ret":
        return min(a[3], b[3]) - max(a[1], b[1]) > folga and min(a[4], b[4]) - max(a[2], b[2]) > folga
    if a[0] == "ret":   # retangulo e circulo: o ponto do retangulo mais perto do centro
        _, x, y, raio = b
        px, py = min(max(x, a[1]), a[3]), min(max(y, a[2]), a[4])
        return raio - math.hypot(x - px, y - py) > folga
    return a[3] + b[3] - math.hypot(a[1] - b[1], a[2] - b[2]) > folga


def caixa(miolo, raio):
    pts = [p for s in segmentos(miolo) for p in s]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs) - raio, min(ys) - raio, max(xs) + raio, max(ys) + raio


def do_pad(x, y, pad):
    """(miolo, raio) de um pad: redondo, retângulo ou oblongo (segmento no meio, raio = metade do lado curto)"""
    if pad["forma"] == "C":
        return ("seg", (x, y), (x, y)), pad["d"] / 2
    w, h = pad["w"], pad["h"]
    if pad["forma"] == "O":
        meio = abs(w - h) / 2
        a, b = ((x - meio, y), (x + meio, y)) if w >= h else ((x, y - meio), (x, y + meio))
        return ("seg", a, b), min(w, h) / 2
    return ("ret", x - w / 2, y - h / 2, x + w / 2, y + h / 2), 0
