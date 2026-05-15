from PySide6.QtCore import QPointF, QRectF, Qt

from ui.symbols.style import draw_text, line_pen, no_brush, thin_pen


def _setup_line_symbol(painter):
    painter.setPen(line_pen())
    painter.setBrush(no_brush())


def draw_resistor(painter, component=None):
    _setup_line_symbol(painter)
    painter.drawLine(-30, 0, -15, 0)
    points = [
        QPointF(-15, 0), QPointF(-12, -8), QPointF(-6, 8),
        QPointF(0, -8), QPointF(6, 8), QPointF(12, -8), QPointF(15, 0),
    ]
    for start, end in zip(points, points[1:]):
        painter.drawLine(start, end)
    painter.drawLine(15, 0, 30, 0)


def draw_inductor(painter, component=None):
    _setup_line_symbol(painter)
    painter.drawLine(-30, 0, -18, 0)
    for i in range(4):
        painter.drawArc(-18 + i * 9, -8, 12, 16, 0, 180 * 16)
    painter.drawLine(18, 0, 30, 0)


def draw_capacitor(painter, component=None):
    _setup_line_symbol(painter)
    painter.drawLine(-30, 0, -6, 0)
    painter.drawLine(-6, -14, -6, 14)
    painter.drawLine(6, -14, 6, 14)
    painter.drawLine(6, 0, 30, 0)


def draw_series_rl(painter, component=None):
    _setup_line_symbol(painter)
    painter.drawLine(-30, 0, -20, 0)
    points = [
        QPointF(-20, 0), QPointF(-17, -7), QPointF(-11, 7),
        QPointF(-5, -7), QPointF(0, 0),
    ]
    for start, end in zip(points, points[1:]):
        painter.drawLine(start, end)
    for i in range(3):
        painter.drawArc(2 + i * 7, -7, 10, 14, 0, 180 * 16)
    painter.drawLine(25, 0, 30, 0)


def draw_voltage_source(painter, component=None):
    _setup_line_symbol(painter)
    painter.drawLine(-30, 0, -13, 0)
    painter.drawEllipse(-13, -13, 26, 26)
    painter.drawLine(13, 0, 30, 0)
    painter.drawLine(0, -7, 0, 7)
    painter.drawLine(-7, 0, 7, 0)


def draw_current_source(painter, component=None):
    _setup_line_symbol(painter)
    painter.drawLine(-30, 0, -13, 0)
    painter.drawEllipse(-13, -13, 26, 26)
    painter.drawLine(13, 0, 30, 0)
    painter.drawLine(0, 8, 0, -8)
    painter.drawLine(0, -8, -5, -2)
    painter.drawLine(0, -8, 5, -2)


def draw_switch(painter, component=None):
    _setup_line_symbol(painter)
    painter.drawLine(-30, 0, -10, 0)
    painter.drawEllipse(-12, -2, 4, 4)
    painter.drawLine(-8, -1, 13, -12)
    painter.drawEllipse(13, -2, 4, 4)
    painter.drawLine(17, 0, 30, 0)


def draw_moa(painter, component=None):
    _setup_line_symbol(painter)
    painter.drawLine(-30, 0, -16, 0)
    painter.drawLine(16, 0, 30, 0)
    painter.drawLine(-16, -12, -16, 12)
    painter.drawLine(16, -12, 16, 12)
    painter.setPen(thin_pen())
    painter.drawLine(-10, 10, -4, -10)
    painter.drawLine(-4, -10, 4, 10)
    painter.drawLine(4, 10, 10, -10)


def draw_lpm(painter, component=None):
    _setup_line_symbol(painter)
    painter.drawLine(-30, 0, -12, 0)
    painter.drawLine(12, 0, 30, 0)
    painter.drawLine(-12, -10, -12, 10)
    painter.drawLine(12, -10, 12, 10)
    painter.drawLine(-5, -8, 2, -1)
    painter.drawLine(2, -1, -2, 2)
    painter.drawLine(-2, 2, 6, 10)


def draw_ground_component(painter, component=None):
    _setup_line_symbol(painter)
    painter.drawLine(0, -24, 0, 0)
    painter.drawLine(-18, 0, 18, 0)
    painter.drawLine(-11, 8, 11, 8)
    painter.drawLine(-5, 15, 5, 15)


def draw_subcircuit(painter, component):
    painter.setPen(line_pen())
    painter.setBrush(no_brush())
    rect = QRectF(-45, -28, 90, 56)
    painter.drawRect(rect)
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, component.name)


PRIMITIVE_DRAWERS = {}
