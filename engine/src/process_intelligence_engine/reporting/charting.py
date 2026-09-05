"""Lightweight SVG chart helpers for inline report visuals.

Returns raw SVG markup (HTML-escaped by the caller). Charts are authored in a
fixed logical viewBox so they scale responsively via width:100%.
"""
from __future__ import annotations
import html as _html
from typing import Any, Iterable, Sequence

_PLOT_LEFT = 44
_PLOT_RIGHT = 14
_PLOT_TOP = 12
_PLOT_BOTTOM = 34
_WIDTH = 640
_HEIGHT = 300


def _e(value: Any) -> str:
    return _html.escape(str(value)) if value is not None else ""


def _nice_ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    if not (lo < hi):
        return [lo]
    span = hi - lo
    step = span / n
    mag = 10 ** (int(_log10(step)))
    for m in (1, 2, 2.5, 5, 10):
        if step <= m * mag:
            step = m * mag
            break
    ticks = []
    start = (int(lo / step) - 1) * step
    t = start
    while t <= hi + step:
        ticks.append(round(t, 6))
        t += step
    return ticks


def _log10(x: float) -> float:
    import math
    return math.log10(x) if x > 0 else 0.0


def histogram_svg(
    edges: Sequence[float],
    counts: Sequence[float],
    title: str = "",
    fit_curve: dict | None = None,
    lsl: float | None = None,
    usl: float | None = None,
    xlabel: str = "Value",
) -> str:
    """Render a bar histogram with optional fitted curve + spec limit lines.

    ``fit_curve`` is ``{"x": [...], "y": [...]}`` (density values).
    """
    edges = [float(v) for v in edges]
    counts = [float(v) for v in counts] if counts else []
    if len(edges) < 2 or not counts:
        return f'<p class="chart-empty">{_e("No histogram data")}</p>'

    xmin, xmax = edges[0], edges[-1]
    ymax = max(counts) if counts else 1.0

    lo = xmin - (xmax - xmin) * 0.05
    hi = xmax + (xmax - xmin) * 0.05
    plot_w = _WIDTH - _PLOT_LEFT - _PLOT_RIGHT
    plot_h = _HEIGHT - _PLOT_TOP - _PLOT_BOTTOM

    def sx(x: float) -> float:
        return _PLOT_LEFT + (x - lo) / (hi - lo) * plot_w

    def sy(y: float) -> float:
        return _PLOT_TOP + (1 - y / (ymax * 1.08)) * plot_h

    # Bars
    bar_w = max(1.0, (xmax - xmin) / len(counts) * plot_w * 0.9)
    bars = []
    for i, c in enumerate(counts):
        x0 = sx(edges[i]) + (bar_w * 0.15 if i < len(counts) else 0)
        y0 = sy(c)
        bars.append(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{bar_w:.1f}" '
                    f'height="{_PLOT_TOP + plot_h - y0:.1f}" '
                    f'fill="#2563EB" fill-opacity="0.55" stroke="none"/>')

    # Violation (ng) regions
    overlays = []
    if lsl is not None and lsl > lo:
        x = sx(lsl)
        overlays.append(f'<rect x="{_PLOT_LEFT:.1f}" y="{_PLOT_TOP:.1f}" '
                        f'width="{max(0.0, x - _PLOT_LEFT):.1f}" height="{plot_h:.1f}" fill="#ef4444" fill-opacity="0.12"/>')
        overlays.append(f'<line x1="{x:.1f}" y1="{_PLOT_TOP:.1f}" x2="{x:.1f}" y2="{_PLOT_TOP + plot_h:.1f}" stroke="#dc2626" stroke-width="2"/>')
    if usl is not None and usl < hi:
        x = sx(usl)
        overlays.append(f'<rect x="{x:.1f}" y="{_PLOT_TOP:.1f}" '
                        f'width="{max(0.0, _PLOT_LEFT + plot_w - x):.1f}" height="{plot_h:.1f}" fill="#ef4444" fill-opacity="0.12"/>')
        overlays.append(f'<line x1="{x:.1f}" y1="{_PLOT_TOP:.1f}" x2="{x:.1f}" y2="{_PLOT_TOP + plot_h:.1f}" stroke="#dc2626" stroke-width="2"/>')

    # Fitted density curve (mapped onto the same plot)
    poly = []
    if fit_curve and fit_curve.get("x") and fit_curve.get("y"):
        xs = [float(v) for v in fit_curve["x"]]
        ys = [float(v) for v in fit_curve["y"]]
        if xs and max(ys) > 0:
            y_scale = ymax / max(ys)
            for fx, fy in zip(xs, ys):
                poly.append(f"{sx(fx):.1f},{sy(fy * y_scale):.1f}")
    curve = ""
    if poly:
        curve = (f'<polyline points="{" ".join(poly)}" fill="none" '
                 f'stroke="#dc2626" stroke-width="2.5" stroke-linejoin="round"/>')

    # Axes + ticks
    ticks_svg = []
    for tx in _nice_ticks(lo, hi):
        x = sx(tx)
        ticks_svg.append(
            f'<line x1="{x:.1f}" y1="{_PLOT_TOP + plot_h:.1f}" x2="{x:.1f}" y2="{_PLOT_TOP + plot_h + 4:.1f}" stroke="#999" stroke-width="1"/>'
            f'<text x="{x:.1f}" y="{_PLOT_TOP + plot_h + 16:.1f}" font-size="10" fill="#666" text-anchor="middle">{_e(tx)}</text>'
        )
    for ty in _nice_ticks(0, ymax, 4):
        y = sy(ty)
        if _PLOT_TOP - 6 <= y <= _PLOT_TOP + plot_h:
            ticks_svg.append(
                f'<line x1="{_PLOT_LEFT - 4:.1f}" y1="{y:.1f}" x2="{_PLOT_LEFT:.1f}" y2="{y:.1f}" stroke="#999" stroke-width="1"/>'
                f'<text x="{_PLOT_LEFT - 6:.1f}" y="{y + 3:.1f}" font-size="10" fill="#666" text-anchor="end">{_e(ty)}</text>'
            )

    # spec limit labels
    if lsl is not None:
        ticks_svg.append(f'<text x="{sx(lsl):.1f}" y="{_PLOT_TOP - 4:.1f}" font-size="10" fill="#dc2626" text-anchor="middle">LSL {_e(round(lsl, 3))}</text>')
    if usl is not None:
        ticks_svg.append(f'<text x="{sx(usl):.1f}" y="{_PLOT_TOP - 4:.1f}" font-size="10" fill="#dc2626" text-anchor="middle">USL {_e(round(usl, 3))}</text>')

    title_svg = ""
    if title:
        title_svg = f'<text x="{_PLOT_LEFT:.1f}" y="16" font-size="12" font-weight="600" fill="#333">{_e(title)}</text>'

    svg = (
        f'<svg viewBox="0 0 {_WIDTH} {_HEIGHT}" style="width:100%;max-width:640px;height:auto;">'
        f'{title_svg}'
        f'<g>{"".join(overlays)}</g>'
        f'<g>{curve}</g>'
        f'<g>{"".join(bars)}</g>'
        f'<g>{"".join(ticks_svg)}</g>'
        f'<line x1="{_PLOT_LEFT:.1f}" y1="{_PLOT_TOP + plot_h:.1f}" x2="{_PLOT_LEFT + plot_w:.1f}" y2="{_PLOT_TOP + plot_h:.1f}" stroke="#999" stroke-width="1"/>'
        f'<line x1="{_PLOT_LEFT:.1f}" y1="{_PLOT_TOP:.1f}" x2="{_PLOT_LEFT:.1f}" y2="{_PLOT_TOP + plot_h:.1f}" stroke="#999" stroke-width="1"/>'
        f'<text x="{_PLOT_LEFT + plot_w:.1f}" y="{_HEIGHT - 6:.1f}" font-size="10" fill="#666" text-anchor="end">{_e(xlabel)}</text>'
        f'</svg>'
    )
    return svg


def heatmap_svg(
    matrix: Sequence[Sequence[float]],
    labels: Sequence[str],
    title: str = "",
) -> str:
    """Render an interaction-strength heatmap."""
    n = len(matrix)
    if n == 0:
        return ""
    max_v = 0.0
    for row in matrix:
        for v in row:
            try:
                max_v = max(max_v, abs(float(v)))
            except (TypeError, ValueError):
                pass
    max_v = max_v or 1.0

    cell = 44
    hm_size = n * cell
    off = 90
    svg_w = off + hm_size + 16
    svg_h = 46 + hm_size + 60

    def color(v: float) -> str:
        intensity = abs(v) / max_v
        if v >= 0:
            r = int(37 + (220 - 37) * intensity)
            return f"rgb({r},{int(99 - 50 * intensity)},{int(235 - 180 * intensity)})"
        else:
            g = int(180 - 160 * intensity)
            return f"rgb({int(220)},{g},{int(37 + 180 * intensity)})"

    cells = []
    for i in range(n):
        for j in range(n):
            v = float(matrix[i][j]) if i < len(matrix) and j < len(matrix[i]) else 0.0
            x = off + j * cell
            y = 40 + i * cell
            cells.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" fill="{color(v)}" stroke="#fff" stroke-width="1"/>'
                f'<text x="{x + cell / 2:.1f}" y="{y + cell / 2 + 3:.1f}" font-size="11" fill="#fff" text-anchor="middle">{v:.2f}</text>'
            )
            if i == 0:
                cells.append(f'<text x="{x + cell / 2:.1f}" y="{y - 8:.1f}" font-size="11" fill="#555" text-anchor="middle" font-weight="600">{_e(labels[j])}</text>')
            if j == 0:
                cells.append(f'<text x="{x - 8:.1f}" y="{y + cell / 2 + 3:.1f}" font-size="11" fill="#555" text-anchor="end" font-weight="600">{_e(labels[i])}</text>')

    title_svg = ""
    if title:
        title_svg = f'<text x="{off:.1f}" y="20" font-size="12" font-weight="600" fill="#333">{_e(title)}</text>'

    return (
        f'<svg viewBox="0 0 {svg_w} {svg_h}" style="width:100%;max-width:480px;height:auto;">'
        f'{title_svg}{"".join(cells)}'
        f'</svg>'
    )


def control_chart_svg(
    x_values: Sequence[float],
    mr_values: Sequence[float | None],
    x_ucl: float,
    x_lcl: float,
    x_cl: float,
    mr_ucl: float,
    mr_cl: float,
    title: str = "I-MR Control Chart",
) -> str:
    """Render I-MR control chart as inline SVG for reports."""
    n = len(x_values)
    if n == 0:
        return ""

    # Compute y ranges
    all_y = [v for v in x_values if v is not None] + [x_ucl, x_lcl, x_cl, mr_ucl, mr_cl]
    y_min = min(all_y)
    y_max = max(all_y)
    y_pad = (y_max - y_min) * 0.1 or 1
    y_min -= y_pad
    y_max += y_pad

    def sx(i: float) -> float:
        return _PLOT_LEFT + (i / max(n - 1, 1)) * (_WIDTH - _PLOT_LEFT - _PLOT_RIGHT)

    def sy_top(y: float) -> float:
        return _PLOT_TOP + (1 - (y - y_min) / (y_max - y_min)) * 160

    def sy_bottom(y: float) -> float:
        return 220 + (1 - (y - y_min) / (y_max - y_min)) * 140

    elems: list[str] = []

    # Title
    elems.append(f'<text x="320" y="10" text-anchor="middle" font-size="12" font-weight="bold">{_e(title)}</text>')

    # Top chart border
    elems.append(f'<line x1="{_PLOT_LEFT}" y1="180" x2="{_WIDTH - _PLOT_RIGHT}" y2="180" stroke="#ccc" stroke-width="0.5"/>')
    elems.append(f'<line x1="{_PLOT_LEFT}" y1="20" x2="{_PLOT_LEFT}" y2="180" stroke="#ccc" stroke-width="0.5"/>')

    # CL, UCL, LCL lines (top chart)
    elems.append(f'<line x1="{_PLOT_LEFT}" y1="{sy_top(x_cl):.1f}" x2="{_WIDTH - _PLOT_RIGHT}" y2="{sy_top(x_cl):.1f}" stroke="#52c41a" stroke-width="1" stroke-dasharray="4,2"/>')
    elems.append(f'<text x="{_WIDTH - _PLOT_RIGHT + 2}" y="{sy_top(x_cl):.1f}-3" font-size="8" fill="#52c41a">CL</text>')
    elems.append(f'<line x1="{_PLOT_LEFT}" y1="{sy_top(x_ucl):.1f}" x2="{_WIDTH - _PLOT_RIGHT}" y2="{sy_top(x_ucl):.1f}" stroke="#fa8c16" stroke-width="1" stroke-dasharray="4,2"/>')
    elems.append(f'<text x="{_WIDTH - _PLOT_RIGHT + 2}" y="{sy_top(x_ucl):.1f}-3" font-size="8" fill="#fa8c16">UCL</text>')
    elems.append(f'<line x1="{_PLOT_LEFT}" y1="{sy_top(x_lcl):.1f}" x2="{_WIDTH - _PLOT_RIGHT}" y2="{sy_top(x_lcl):.1f}" stroke="#fa8c16" stroke-width="1" stroke-dasharray="4,2"/>')
    elems.append(f'<text x="{_WIDTH - _PLOT_RIGHT + 2}" y="{sy_top(x_lcl):.1f}+8" font-size="8" fill="#fa8c16">LCL</text>')

    # Data line + markers (top chart)
    points = []
    for i, v in enumerate(x_values):
        if v is None:
            continue
        x = sx(float(i))
        y = sy_top(v)
        points.append(f"{x:.1f},{y:.1f}")
    if len(points) > 1:
        elems.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="#1677ff" stroke-width="1.5"/>')
    for i, v in enumerate(x_values):
        if v is None:
            continue
        x = sx(float(i))
        y = sy_top(v)
        color = "#ff4d4f" if v > x_ucl or v < x_lcl else "#1677ff"
        elems.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2" fill="{color}"/>')

    # Bottom chart border
    elems.append(f'<line x1="{_PLOT_LEFT}" y1="360" x2="{_WIDTH - _PLOT_RIGHT}" y2="360" stroke="#ccc" stroke-width="0.5"/>')
    elems.append(f'<line x1="{_PLOT_LEFT}" y1="220" x2="{_PLOT_LEFT}" y2="360" stroke="#ccc" stroke-width="0.5"/>')

    # MR chart lines
    elems.append(f'<line x1="{_PLOT_LEFT}" y1="{sy_bottom(mr_cl):.1f}" x2="{_WIDTH - _PLOT_RIGHT}" y2="{sy_bottom(mr_cl):.1f}" stroke="#52c41a" stroke-width="1" stroke-dasharray="4,2"/>')
    elems.append(f'<line x1="{_PLOT_LEFT}" y1="{sy_bottom(mr_ucl):.1f}" x2="{_WIDTH - _PLOT_RIGHT}" y2="{sy_bottom(mr_ucl):.1f}" stroke="#fa8c16" stroke-width="1" stroke-dasharray="4,2"/>')

    mr_points = []
    for i, v in enumerate(mr_values):
        if v is None:
            continue
        x = sx(float(i))
        y = sy_bottom(v)
        mr_points.append(f"{x:.1f},{y:.1f}")
    if len(mr_points) > 1:
        elems.append(f'<polyline points="{" ".join(mr_points)}" fill="none" stroke="#722ed1" stroke-width="1.5"/>')
    for i, v in enumerate(mr_values):
        if v is None:
            continue
        x = sx(float(i))
        y = sy_bottom(v)
        color = "#ff4d4f" if v > mr_ucl else "#722ed1"
        elems.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2" fill="{color}"/>')

    svg = f'<svg viewBox="0 0 {_WIDTH} 400" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:640px;">{"".join(elems)}</svg>'
    return svg
