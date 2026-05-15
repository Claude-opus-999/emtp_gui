from PySide6.QtCore import QRectF

from ui.symbols.style import draw_ground, draw_text, line_pen, no_brush


def _draw_wye(painter, cx, cy):
    painter.drawLine(cx, cy, cx - 22, cy - 14)
    painter.drawLine(cx, cy, cx + 22, cy - 14)
    painter.drawLine(cx, cy, cx, cy + 22)


def _draw_delta(painter, cx, cy):
    painter.drawLine(cx, cy - 26, cx - 26, cy + 22)
    painter.drawLine(cx - 26, cy + 22, cx + 26, cy + 22)
    painter.drawLine(cx + 26, cy + 22, cx, cy - 26)


def _draw_bottom_terminal(painter, x, grounded=False):
    painter.drawLine(x, 28, x, 58)
    if grounded:
        draw_ground(painter, x, 63)


def draw_umec(painter, component):
    params = component.params
    wtype1 = params.get("wtype1", "Y_gnd")
    wtype2 = params.get("wtype2", "Delta")
    s_mva = params.get("S_mva", 100.0)
    v1 = params.get("V1_kV", 220.0)
    v2 = params.get("V2_kV", 110.0)

    painter.setPen(line_pen())
    painter.setBrush(no_brush())
    painter.drawRect(QRectF(-52, -55, 104, 110))
    draw_text(painter, "umec", -47, -39, 11)
    draw_text(painter, f"{s_mva:g} [MVA]", -27, -21, 9)

    for y, label in [(-30, "A"), (0, "B"), (30, "C")]:
        painter.drawLine(-60, y, -52, y)
        painter.drawLine(52, y, 60, y)
        draw_text(painter, label, -74, y + 4, 9)
        draw_text(painter, label, 66, y + 4, 9)

    draw_text(painter, "#1", -47, 9, 10)
    draw_text(painter, "#2", 34, 9, 10)

    if wtype1 == "Delta":
        _draw_delta(painter, -26, 6)
    else:
        _draw_wye(painter, -26, 3)
        _draw_bottom_terminal(painter, -30, grounded=(wtype1 == "Y_gnd"))

    if wtype2 == "Delta":
        _draw_delta(painter, 26, 6)
    else:
        _draw_wye(painter, 26, 3)
        _draw_bottom_terminal(painter, 30, grounded=(wtype2 == "Y_gnd"))

    draw_text(painter, f"{v1:g} [kV]", -48, 44, 8)
    draw_text(painter, f"{v2:g} [kV]", 10, 44, 8)
