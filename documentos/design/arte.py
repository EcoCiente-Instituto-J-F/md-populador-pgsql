"""Ilustração low-poly em SVG, port fiel de arte.mjs (mesma saída byte a byte)."""
import math
from decimal import Decimal, ROUND_HALF_UP

_M32 = 0xFFFFFFFF


def _imul(a, b):
    """Math.imul devolvendo o valor como inteiro com sinal de 32 bits."""
    r = (a * b) & _M32
    return r - (1 << 32) if r & 0x80000000 else r


def _i32(x):
    x &= _M32
    return x - (1 << 32) if x & 0x80000000 else x


def rng(semente):
    estado = [semente & _M32]

    def proximo():
        estado[0] = (estado[0] + 0x6D2B79F5) & _M32
        t = estado[0]
        t = _imul(t ^ (t >> 15), t | 1)
        t = _i32(t ^ _i32(t + _imul(t ^ ((t & _M32) >> 7), t | 61)))
        return ((t ^ ((t & _M32) >> 14)) & _M32) / 4294967296

    return proximo


def rgb(hex_):
    return [int(hex_[i:i + 2], 16) for i in (1, 3, 5)]


def misturar(a, b, t):
    return [v + (b[i] - v) * t for i, v in enumerate(a)]


def _round(x):
    return math.floor(x + 0.5)


def css(c):
    return "rgb(" + ",".join(str(_round(max(0, min(255, v)))) for v in c) + ")"


def rampa(paradas, t):
    for i in range(1, len(paradas)):
        if t <= paradas[i][0]:
            p0, c0 = paradas[i - 1]
            p1, c1 = paradas[i]
            return misturar(rgb(c0), rgb(c1), (t - p0) / ((p1 - p0) or 1))
    return rgb(paradas[-1][1])


def _fixo1(x):
    """Number.prototype.toFixed(1): meio para cima sobre o valor binário exato."""
    d = Decimal(abs(x)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    s = str(d)
    return "-" + s if x < 0 else s


def num(v):
    """Número como o JS imprime em template string (inteiro sem .0)."""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v)


def pt(p):
    return f"{_fixo1(p[0])},{_fixo1(p[1])}"


def poligono(pontos, cor):
    return (f'<polygon points="{" ".join(pt(p) for p in pontos)}" fill="{cor}" '
            f'stroke="{cor}" stroke-width="0.7" stroke-linejoin="round"/>')


def arvore(r, a):
    x, y, s, paleta = a["x"], a["y"], a["s"], a["paleta"]
    partes = [poligono([[x - s * 0.07, y], [x + s * 0.07, y], [x + s * 0.04, y - s * 0.62],
                        [x - s * 0.04, y - s * 0.62]], css(rgb("#14382d")))]
    cx = x
    cy = y - s * 1.15
    n = 10
    anel = []
    for i in range(n):
        ang = (i / n) * math.pi * 2 + r() * 0.25
        raio = s * (0.78 + r() * 0.34)
        anel.append([cx + math.cos(ang) * raio, cy + math.sin(ang) * raio * 0.86])
    for i in range(n):
        base = rgb(paleta[math.floor(r() * len(paleta))])
        luz = (r() - 0.5) * 26
        partes.append(poligono([[cx, cy], anel[i], anel[(i + 1) % n]], css([v + luz for v in base])))
    return "".join(partes)


def arte(w, h, seed=1, cols=22, rows=12, stops=None, tiras=(), arvores=()):
    r = rng(seed)
    dx = w / cols
    dy = h / rows
    grade = []
    for j in range(rows + 1):
        linha = []
        for i in range(cols + 1):
            borda_x = i == 0 or i == cols
            borda_y = j == 0 or j == rows
            px = i * dx + (0 if borda_x else (r() - 0.5) * dx * 0.8)
            py = j * dy + (0 if borda_y else (r() - 0.5) * dy * 0.8)
            linha.append([px, py])
        grade.append(linha)
    saida = []

    def triangulo(a, b, c):
        cy = (a[1] + b[1] + c[1]) / 3 / h
        cx = (a[0] + b[0] + c[0]) / 3 / w
        t = min(1, max(0, cy + (r() - 0.5) * 0.12))
        luz = (r() - 0.5) * 30 + (0.5 - cx) * 10
        saida.append(poligono([a, b, c], css([v + luz for v in rampa(stops, t)])))

    for j in range(rows):
        for i in range(cols):
            a = grade[j][i]
            b = grade[j][i + 1]
            c = grade[j + 1][i]
            d = grade[j + 1][i + 1]
            if r() < 0.5:
                triangulo(a, b, c)
                triangulo(b, d, c)
            else:
                triangulo(a, b, d)
                triangulo(a, d, c)
    for x, y, tw, th in tiras:
        saida.append(f'<rect x="{num(x)}" y="{num(y)}" width="{num(tw)}" height="{num(th)}" '
                     f'fill="#ffffff" fill-opacity="0.2"/>')
    for a in arvores:
        saida.append(arvore(r, a))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {num(w)} {num(h)}" '
            f'width="{num(w)}" height="{num(h)}" aria-hidden="true">{"".join(saida)}</svg>')


PALETA_ROSA = ["#D64573", "#B93C63", "#E8789A", "#F29BB4"]
PALETA_VERDE = ["#2E5C41", "#3F7A57", "#6BA37F", "#A7B7AA"]
