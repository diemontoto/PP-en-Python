"""Gráficos estadísticos en SVG puro (sin librerías externas, funcionan sin conexión)."""
import math

from markupsafe import Markup, escape

PALETTE = ["#2f6fb3", "#1b7f4b", "#d98a1d", "#b42318", "#5b3a9a", "#0f6b6b", "#6b7280", "#a14a0a"]


def _short(s, n=28):
    s = str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def bar_chart(items, unit="", width=560, max_value=None):
    """Barras horizontales. items: [(etiqueta, valor[, color])]"""
    items = list(items)
    if not items:
        return Markup('<p class="muted">Sin datos para mostrar.</p>')
    row_h, left, right = 30, 190, 60
    height = row_h * len(items) + 10
    mx = max_value or max((i[1] for i in items), default=0) or 1
    bar_w = width - left - right
    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Gráfico de barras">']
    for n, it in enumerate(items):
        label, val = it[0], it[1]
        color = it[2] if len(it) > 2 else PALETTE[0]
        y = n * row_h + 5
        w = max(0 if not val else 3, bar_w * val / mx)
        txt = f"{val:g}{unit}" if isinstance(val, (int, float)) else f"{val}{unit}"
        out.append(f'<text x="{left - 8}" y="{y + 16}" text-anchor="end" font-size="12" fill="#374151">{escape(_short(label))}</text>')
        out.append(f'<rect x="{left}" y="{y + 3}" width="{bar_w}" height="18" rx="4" fill="#eef1f6"/>')
        out.append(f'<rect x="{left}" y="{y + 3}" width="{w:.1f}" height="18" rx="4" fill="{color}"><title>{escape(label)}: {escape(txt)}</title></rect>')
        out.append(f'<text x="{left + bar_w + 8}" y="{y + 17}" font-size="12" font-weight="600" fill="#1f2937">{escape(txt)}</text>')
    out.append("</svg>")
    return Markup("".join(out))


def donut(items, center_label="Total", size=200):
    """Gráfico de dona con leyenda. items: [(etiqueta, valor, color)]"""
    items = [i for i in items if i[1]]
    total = sum(i[1] for i in items)
    if not total:
        return Markup('<p class="muted">Sin datos para mostrar.</p>')
    cx = cy = size / 2
    r_out, r_in = size / 2 - 4, size / 2 - 34
    angle = -math.pi / 2
    paths = []
    for label, val, color in items:
        frac = val / total
        if frac >= 0.9999:
            paths.append(f'<circle cx="{cx}" cy="{cy}" r="{(r_out + r_in) / 2}" fill="none" stroke="{color}" stroke-width="{r_out - r_in}"><title>{escape(label)}: {val}</title></circle>')
            break
        a2 = angle + frac * 2 * math.pi
        large = 1 if frac > 0.5 else 0
        x1, y1 = cx + r_out * math.cos(angle), cy + r_out * math.sin(angle)
        x2, y2 = cx + r_out * math.cos(a2), cy + r_out * math.sin(a2)
        x3, y3 = cx + r_in * math.cos(a2), cy + r_in * math.sin(a2)
        x4, y4 = cx + r_in * math.cos(angle), cy + r_in * math.sin(angle)
        d = (f"M{x1:.2f},{y1:.2f} A{r_out},{r_out} 0 {large} 1 {x2:.2f},{y2:.2f} "
             f"L{x3:.2f},{y3:.2f} A{r_in},{r_in} 0 {large} 0 {x4:.2f},{y4:.2f} Z")
        paths.append(f'<path d="{d}" fill="{color}"><title>{escape(label)}: {val}</title></path>')
        angle = a2
    svg = (f'<svg viewBox="0 0 {size} {size}" role="img" aria-label="Gráfico de dona" style="max-width:{size}px;margin:auto">'
           + "".join(paths)
           + f'<text x="{cx}" y="{cy - 2}" text-anchor="middle" font-size="26" font-weight="700" fill="#1e3a5f">{total}</text>'
           + f'<text x="{cx}" y="{cy + 16}" text-anchor="middle" font-size="11" fill="#6b7280">{escape(center_label)}</text></svg>')
    legend = '<div class="legend">' + "".join(
        f'<span><i style="background:{c}"></i>{escape(l)}: <strong>{v}</strong></span>' for l, v, c in items) + "</div>"
    return Markup(svg + legend)
