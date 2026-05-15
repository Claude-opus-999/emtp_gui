from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPen

from ui.symbols.style import draw_text, line_pen, no_brush, thin_pen


def _set_line(painter, width=1.4, color="#111827", style=Qt.PenStyle.SolidLine):
    pen = QPen(QColor(color), width, style)
    pen.setCosmetic(True)
    painter.setPen(pen)
    painter.setBrush(no_brush())


def _block(painter, rect):
    painter.setPen(line_pen())
    painter.setBrush(no_brush())
    painter.drawRect(rect)


def _draw_arrow_up(painter, x, y_tip, height=18, half_width=7):
    painter.drawLine(x, y_tip + height, x, y_tip)
    painter.drawLine(x, y_tip, x - half_width, y_tip + height)
    painter.drawLine(x, y_tip, x + half_width, y_tip + height)


def _draw_arrow_down(painter, x, y_tip, height=18, half_width=7):
    painter.drawLine(x, y_tip - height, x, y_tip)
    painter.drawLine(x, y_tip, x - half_width, y_tip - height)
    painter.drawLine(x, y_tip, x + half_width, y_tip - height)


def _draw_terminal_tube(painter, x, y, width=58, height=13, label="C1", right=False):
    rect = QRectF(x, y - height / 2, width, height)
    painter.drawRoundedRect(rect, 5, 5)
    if right:
        painter.drawEllipse(x - 5, y - 5, 10, 10)
        draw_text(painter, label, x + width + 16, y + 5, 8, QColor("#111827"))
    else:
        painter.drawEllipse(x + width - 5, y - 5, 10, 10)
        draw_text(painter, label, x - 34, y + 5, 8, QColor("#111827"))


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
    _set_line(painter)
    label = component.name if component.name else "TLine"

    _draw_arrow_up(painter, 0, -54, 18, 7)
    painter.drawLine(0, -36, 0, -23)
    _draw_arrow_up(painter, 36, -48, 18, 7)
    _draw_arrow_down(painter, -36, 48, 18, 7)
    painter.drawLine(36, -30, 36, -2)
    painter.drawLine(-36, 2, -36, 30)
    painter.drawLine(36, -2, 4, -14)
    painter.drawLine(4, -14, 18, 1)
    painter.drawLine(18, 1, -10, -4)
    painter.drawLine(-10, -4, 6, 11)
    painter.drawLine(6, 11, -36, 2)

    painter.drawLine(-56, -28, -56, 26)
    painter.drawLine(56, -28, 56, 26)
    for y in (-18, 0, 18):
        painter.drawLine(-56, y, -42, y)
        painter.drawLine(42, y, 56, y)
    painter.setPen(thin_pen())
    painter.drawLine(-48, -28, -48, 26)
    painter.drawLine(-52, -20, -44, -8)
    painter.drawLine(-52, -2, -44, 10)
    painter.drawLine(48, -28, 48, 26)
    painter.drawLine(44, -20, 52, -8)
    painter.drawLine(44, -2, 52, 10)

    draw_text(painter, label, -24, 45, 9, QColor("#0000d4"))


def draw_lcp_single_cable(painter, component):
    _set_line(painter)
    label = component.name if component.name else "Cable_1"

    _draw_arrow_up(painter, 0, -47, 18, 7)
    painter.drawLine(0, -29, 0, -18)
    painter.drawLine(0, -18, 20, -7)
    painter.drawLine(20, -7, -6, 2)
    painter.drawLine(-6, 2, 11, 14)
    _draw_arrow_down(painter, 0, 47, 18, 7)
    painter.drawLine(0, 29, 0, 14)

    _draw_terminal_tube(painter, -56, -15, 55, 12, "C1")
    _draw_terminal_tube(painter, 5, -15, 55, 12, "C1", right=True)
    painter.setPen(thin_pen())
    painter.drawLine(-47, -5, -10, -5)
    painter.drawLine(-44, 5, -12, 5)
    painter.drawLine(15, -5, 48, -5)
    painter.drawLine(18, 5, 50, 5)

    draw_text(painter, "S1", -22, 10, 8, QColor("#111827"))
    draw_text(painter, "A1", 10, 10, 8, QColor("#111827"))
    draw_text(painter, label, -20, 35, 8, QColor("#111827"))


def draw_lcp_three_cable(painter, component):
    _set_line(painter)
    label = component.name if component.name else "Cable_3"
    y_positions = (-33, -12, 9)
    names = ("C3", "C2", "C1")
    shields = ("S3", "S2", "S1")

    for y, core, shield in zip(y_positions, names, shields):
        _draw_terminal_tube(painter, -58, y, 58, 13, core)
        _draw_terminal_tube(painter, 7, y, 58, 13, core, right=True)
        draw_text(painter, shield, -24, y - 8, 8, QColor("#111827"))
        draw_text(painter, shield, 26, y - 8, 8, QColor("#111827"))

    _draw_arrow_up(painter, 0, -54, 17, 7)
    _draw_arrow_down(painter, 0, 38, 17, 7)
    painter.drawLine(0, -37, 0, -24)
    painter.drawLine(0, 21, 0, 9)
    painter.drawLine(0, -24, 22, -13)
    painter.drawLine(22, -13, -6, -4)
    painter.drawLine(-6, -4, 11, 8)

    painter.setPen(thin_pen())
    painter.drawLine(-58, 31, -24, 31)
    painter.drawLine(24, 31, 58, 31)
    _set_line(painter, 1.1, "#111827", Qt.PenStyle.DotLine)
    painter.drawRect(QRectF(-31, 18, 22, 28))
    painter.drawRect(QRectF(9, 18, 22, 28))
    _set_line(painter)
    painter.drawLine(-34, 42, -34, 18)
    painter.drawLine(34, 42, 34, 18)
    painter.drawLine(-34, 42, 34, 42)

    draw_text(painter, label, -21, 15, 8, QColor("#111827"))
    draw_text(painter, "Pipe", -52, 65, 8, QColor("#111827"))
    draw_text(painter, "Pipe", 34, 65, 8, QColor("#111827"))


def draw_lcp_cable(painter, component, label):
    if label == "3C":
        draw_lcp_three_cable(painter, component)
    else:
        draw_lcp_single_cable(painter, component)
