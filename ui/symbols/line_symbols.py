from PySide6.QtCore import QPointF, QRectF

from ui.symbols.style import draw_text, line_pen, no_brush, thin_pen


def _block(painter, rect):
    painter.setPen(line_pen())
    painter.setBrush(no_brush())
    painter.drawRect(rect)


def draw_bergeron(painter, component):
    _block(painter, QRectF(-45, -18, 90, 36))
    painter.drawLine(-45, -6, 45, -6)
    painter.drawLine(-45, 6, 45, 6)
    draw_text(painter, "Berg", -18, -25, 9)


def draw_ulm(painter, component):
    n = int(component.params.get("n_phases", 3) or 1)
    _block(painter, QRectF(-45, -28, 90, 56))
    spacing = 14
    start = -(min(n, 5) - 1) * spacing / 2
    for i in range(min(n, 5)):
        y = start + i * spacing
        painter.drawLine(-45, int(y), 45, int(y))
    draw_text(painter, f"ULM {n}ph", -24, -36, 9)


def draw_lcp_ohl(painter, component):
    n = len([p for p in component.pins if p.name.startswith("nk")]) or 1
    _block(painter, QRectF(-48, -30, 96, 60))
    spacing = 12
    start = -(min(n, 5) - 1) * spacing / 2
    for i in range(min(n, 5)):
        y = start + i * spacing
        painter.drawLine(-48, int(y), 48, int(y))
        painter.setPen(thin_pen())
        painter.drawLine(-40, int(y) - 4, 40, int(y) - 4)
        painter.setPen(line_pen())
    draw_text(painter, "LCP-OHL", -25, -38, 9)


def draw_lcp_cable(painter, component, label):
    n = len([p for p in component.pins if p.name.startswith("nk")])
    n = max(1, min(n, 7))
    _block(painter, QRectF(-50, -32, 100, 64))
    spacing = 10
    start = -(n - 1) * spacing / 2
    for i in range(n):
        y = start + i * spacing
        painter.drawEllipse(-34, int(y) - 4, 8, 8)
        painter.drawLine(-22, int(y), 36, int(y))
    draw_text(painter, f"LCP-{label}", -24, -40, 9)
