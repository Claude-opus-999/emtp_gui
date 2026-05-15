from models.circuit_model import ComponentType
from ui.symbols.line_symbols import (
    draw_bergeron,
    draw_lcp_cable,
    draw_lcp_ohl,
    draw_ulm,
)
from ui.symbols.primitive_symbols import (
    draw_capacitor,
    draw_current_source,
    draw_ground_component,
    draw_inductor,
    draw_junction,
    draw_lpm,
    draw_moa,
    draw_resistor,
    draw_series_rl,
    draw_subcircuit,
    draw_switch,
    draw_voltage_source,
)
from ui.symbols.probe_symbols import draw_probe
from ui.symbols.umec_symbols import draw_umec


def draw_component_symbol(painter, component) -> bool:
    drawers = {
        ComponentType.RESISTOR: draw_resistor,
        ComponentType.INDUCTOR: draw_inductor,
        ComponentType.CAPACITOR: draw_capacitor,
        ComponentType.SERIES_RL: draw_series_rl,
        ComponentType.VOLTAGE_SOURCE: draw_voltage_source,
        ComponentType.CURRENT_SOURCE: draw_current_source,
        ComponentType.SWITCH: draw_switch,
        ComponentType.MOA: draw_moa,
        ComponentType.LPM: draw_lpm,
        ComponentType.GROUND: draw_ground_component,
        ComponentType.JUNCTION: draw_junction,
        ComponentType.BERGERON: draw_bergeron,
        ComponentType.ULM: draw_ulm,
        ComponentType.LCP_OHL: draw_lcp_ohl,
        ComponentType.SUBCIRCUIT: draw_subcircuit,
        ComponentType.PROBE: draw_probe,
        ComponentType.UMEC_TRANSFORMER: draw_umec,
    }
    if component.comp_type == ComponentType.LCP_SINGLE_CABLE:
        draw_lcp_cable(painter, component, "SC")
        return True
    if component.comp_type == ComponentType.LCP_THREE_CABLE:
        draw_lcp_cable(painter, component, "3C")
        return True
    drawer = drawers.get(component.comp_type)
    if drawer is None:
        return False
    drawer(painter, component)
    return True
