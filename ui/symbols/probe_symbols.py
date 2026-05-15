from ui.symbols.style import draw_ground, draw_text, measure_pen, no_brush


def _draw_arrow_up(painter, x=0, y_top=-24, y_bottom=18):
    painter.drawLine(x, y_bottom, x, y_top)
    painter.drawLine(x, y_top, x - 7, y_top + 8)
    painter.drawLine(x, y_top, x + 7, y_top + 8)


def draw_probe(painter, component):
    probe_type = component.params.get("probe_type", "voltage_ground")
    label = component.name or {
        "voltage_ground": "Ea",
        "voltage_between": "Ea",
        "branch_current": "Ia",
    }.get(probe_type, "Ea")

    painter.setPen(measure_pen())
    painter.setBrush(no_brush())
    if probe_type == "branch_current":
        painter.drawLine(-30, -4, 30, -4)
        painter.drawLine(-18, 12, 20, 12)
        painter.drawLine(20, 12, 10, 6)
        painter.drawLine(20, 12, 10, 18)
        draw_text(painter, label, -16, -13, 10)
    elif probe_type == "voltage_between":
        painter.drawLine(-12, -15, -12, -3)
        painter.drawLine(12, -15, 12, -3)
        _draw_arrow_up(painter, 0, -24, 18)
        draw_text(painter, label, -16, 35, 10)
    else:
        painter.drawLine(0, -15, 0, -3)
        _draw_arrow_up(painter, 0, -24, 14)
        draw_text(painter, label, -16, 31, 10)
        draw_ground(painter, 0, 39)
