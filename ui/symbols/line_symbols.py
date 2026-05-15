from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPen

from ui.symbols.style import draw_text, line_pen, no_brush


def _set_line(painter, width=1.4, color="#111827", style=Qt.PenStyle.SolidLine):
    pen = QPen(QColor(color), width, style)
    pen.setCosmetic(True)
    painter.setPen(pen)
    painter.setBrush(no_brush())


def _block(painter, rect):
    painter.setPen(line_pen())
    painter.setBrush(no_brush())
    painter.drawRect(rect)


def _draw_center_text(painter, rect, title, subtitle=""):
    old_pen = painter.pen()
    old_font = painter.font()
    painter.setPen(QPen(QColor("#111827"), 1))
    painter.setFont(QFont("Microsoft YaHei", 9))
    painter.drawText(rect.adjusted(0, -10, 0, 0), Qt.AlignmentFlag.AlignCenter, title)
    if subtitle:
        painter.setFont(QFont("Microsoft YaHei", 7))
        painter.drawText(rect.adjusted(0, 18, 0, 0), Qt.AlignmentFlag.AlignCenter, subtitle)
    painter.setPen(old_pen)
    painter.setFont(old_font)


def _pin_index(pin_name):
    parts = pin_name.split("_")
    if len(parts) >= 2 and parts[1].isdigit():
        return int(parts[1])
    return 0


def lcp_ohl_port_label(component, pin_name):
    idx = _pin_index(pin_name)
    n_phases = int(component.params.get("n_phases", 0) or 0)
    if idx < n_phases:
        return f"导线{idx + 1}"
    return f"地线{idx - n_phases + 1}"


def lcp_single_cable_port_label(pin_name):
    parts = pin_name.split("_")
    cable_index = int(parts[1]) + 1 if len(parts) >= 3 and parts[1].isdigit() else 1
    conductor = parts[2] if len(parts) >= 3 else ""
    names = {
        "core": "芯线",
        "sheath": "护套",
        "armor": "铠装",
    }
    return f"{names.get(conductor, '端口')}{cable_index}"


def lcp_three_cable_port_label(pin_name):
    label_map = {
        "core_a": "芯线A",
        "core_b": "芯线B",
        "core_c": "芯线C",
        "sheath_a": "护套A",
        "sheath_b": "护套B",
        "sheath_c": "护套C",
        "pipe": "管道",
    }
    key = pin_name[3:] if pin_name.startswith(("nk_", "nm_")) else pin_name
    return label_map.get(key, "端口")


def _draw_labeled_box(painter, component, title, label_func, subtitle=""):
    _set_line(painter)
    pins = list(component.pins)
    ys = [pin.local_y for pin in pins] or [0]
    top = min(-32, min(ys) - 9)
    bottom = max(32, max(ys) + 9)
    rect = QRectF(-42, top, 84, bottom - top)

    painter.drawRect(rect)
    _draw_center_text(painter, rect, title, subtitle)

    for pin in pins:
        is_left = pin.local_x < 0
        side_x = rect.left() if is_left else rect.right()
        painter.drawLine(pin.local_x, pin.local_y, side_x, pin.local_y)
        label = label_func(component, pin.name)
        if is_left:
            draw_text(painter, label, pin.local_x - 32, pin.local_y + 3, 6, QColor("#111827"))
        else:
            draw_text(painter, label, pin.local_x + 6, pin.local_y + 3, 6, QColor("#111827"))


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
    _draw_labeled_box(
        painter,
        component,
        "LCP架空线",
        lcp_ohl_port_label,
        "OHL",
    )


def draw_lcp_single_cable(painter, component):
    _draw_labeled_box(
        painter,
        component,
        "LCP单芯电缆",
        lambda _component, pin_name: lcp_single_cable_port_label(pin_name),
        "SC",
    )


def draw_lcp_three_cable(painter, component):
    _draw_labeled_box(
        painter,
        component,
        "LCP三芯电缆",
        lambda _component, pin_name: lcp_three_cable_port_label(pin_name),
        "3C",
    )


def draw_lcp_cable(painter, component, label):
    if label == "3C":
        draw_lcp_three_cable(painter, component)
    else:
        draw_lcp_single_cable(painter, component)
