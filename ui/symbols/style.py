from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QBrush, QFont, QPen


INK = QColor("#111827")
MUTED = QColor("#475569")
MEASURE_BLUE = QColor("#0000d4")


def line_pen(width: float = 2.0) -> QPen:
    pen = QPen(INK, width)
    pen.setCosmetic(True)
    return pen


def thin_pen() -> QPen:
    return line_pen(1.2)


def measure_pen(width: float = 2.0) -> QPen:
    pen = QPen(MEASURE_BLUE, width)
    pen.setCosmetic(True)
    return pen


def no_brush() -> QBrush:
    return QBrush(Qt.BrushStyle.NoBrush)


def draw_text(
    painter,
    text: str,
    x,
    y=None,
    size: int = 9,
    color=MUTED,
    bold: bool = False,
    alignment=Qt.AlignmentFlag.AlignCenter,
):
    old_pen = painter.pen()
    old_font = painter.font()
    font = QFont("Arial", size)
    font.setBold(bold)
    painter.setPen(QPen(color, 1))
    painter.setFont(font)
    if isinstance(x, QRectF):
        painter.drawText(x, alignment, str(text))
    else:
        if y is None:
            raise TypeError("draw_text() missing y coordinate")
        painter.drawText(QPointF(float(x), float(y)), str(text))
    painter.setPen(old_pen)
    painter.setFont(old_font)


def draw_ground(painter, x: float = 0, y: float = 0):
    painter.drawLine(x - 12, y, x + 12, y)
    painter.drawLine(x - 8, y + 5, x + 8, y + 5)
    painter.drawLine(x - 4, y + 10, x + 4, y + 10)
