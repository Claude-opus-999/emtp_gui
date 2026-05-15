import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from models.circuit_model import CircuitModel, ComponentInstance, ComponentType
from models.component_lib import create_component_pins, get_default_params
from ui.circuit_canvas import ComponentGraphicsItem
from ui.symbols.line_symbols import (
    lcp_ohl_port_label,
    lcp_single_cable_port_label,
    lcp_three_cable_port_label,
)


def get_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def render_component(comp):
    get_app()
    image = QImage(240, 190, QImage.Format.Format_ARGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.translate(120, 85)
    item = ComponentGraphicsItem(comp, CircuitModel())
    item.paint(painter, None, None)
    painter.end()
    return image


def image_signature(image):
    return tuple(
        image.pixelColor(x, y).rgba()
        for y in range(image.height())
        for x in range(image.width())
    )


def non_white_pixels(image):
    white = QColor("white")
    count = 0
    for x in range(image.width()):
        for y in range(image.height()):
            if image.pixelColor(x, y) != white:
                count += 1
    return count


def has_ink_in_rect(image, left, top, right, bottom):
    white = QColor("white")
    for x in range(left, right + 1):
        for y in range(top, bottom + 1):
            if image.pixelColor(x, y) != white:
                return True
    return False


class SymbolRenderingTests(unittest.TestCase):
    def test_core_primitive_symbols_render_distinct_shapes(self):
        signatures = {}
        for comp_type in (
            ComponentType.RESISTOR,
            ComponentType.INDUCTOR,
            ComponentType.CAPACITOR,
            ComponentType.VOLTAGE_SOURCE,
            ComponentType.CURRENT_SOURCE,
            ComponentType.SWITCH,
            ComponentType.MOA,
            ComponentType.LPM,
            ComponentType.SERIES_RL,
        ):
            comp = ComponentInstance(
                comp_id=f"{comp_type.value}_001",
                comp_type=comp_type,
                name=comp_type.value,
                x=0,
                y=0,
                params=get_default_params(comp_type),
                pins=create_component_pins(comp_type),
            )
            image = render_component(comp)
            self.assertGreater(non_white_pixels(image), 90, comp_type)
            signatures[comp_type] = image_signature(image)

        self.assertEqual(len(set(signatures.values())), len(signatures))

    def test_probe_symbols_render_distinct_pscad_measurement_shapes(self):
        signatures = {}
        for probe_type in ("voltage_ground", "voltage_between", "branch_current"):
            comp = ComponentInstance(
                comp_id=f"PRB_{probe_type}",
                comp_type=ComponentType.PROBE,
                name={
                    "voltage_ground": "Ea_2",
                    "voltage_between": "Ea_1",
                    "branch_current": "Ia_1",
                }[probe_type],
                x=0,
                y=0,
                params={"probe_type": probe_type, "unit": "kV"},
                pins=create_component_pins(ComponentType.PROBE, probe_type=probe_type),
            )
            image = render_component(comp)
            self.assertGreater(non_white_pixels(image), 80, probe_type)
            signatures[probe_type] = image_signature(image)

        self.assertEqual(len(set(signatures.values())), 3)

    def test_umec_symbol_changes_with_winding_types(self):
        def make_umec(wtype1, wtype2):
            params = get_default_params(ComponentType.UMEC_TRANSFORMER) | {
                "S_mva": 16.85,
                "V1_kV": 1.14,
                "V2_kV": 69.0,
                "wtype1": wtype1,
                "wtype2": wtype2,
            }
            return ComponentInstance(
                comp_id=f"UMEC_{wtype1}_{wtype2}",
                comp_type=ComponentType.UMEC_TRANSFORMER,
                name="umec",
                x=0,
                y=0,
                params=params,
                pins=create_component_pins(ComponentType.UMEC_TRANSFORMER, params=params),
            )

        signatures = []
        for comp in (
            make_umec("Y_gnd", "Delta"),
            make_umec("Y", "Y"),
            make_umec("Delta", "Delta"),
        ):
            image = render_component(comp)
            self.assertGreater(non_white_pixels(image), 180)
            signatures.append(image_signature(image))

        self.assertEqual(len(set(signatures)), 3)

    def test_line_and_block_symbols_render_nonblank(self):
        cases = [
            (ComponentType.BERGERON, {}),
            (ComponentType.ULM, {"n_phases": 3}),
            (ComponentType.LCP_OHL, {"n_phases": 3, "n_gw": 1}),
            (ComponentType.LCP_SINGLE_CABLE, {"n_cables": 2}),
            (ComponentType.LCP_THREE_CABLE, {}),
            (ComponentType.SUBCIRCUIT, {"subcircuit_name": "SUB1"}),
        ]
        for comp_type, overrides in cases:
            params = get_default_params(comp_type) | overrides
            pin_count = params.get("n_phases", params.get("n_cables", 3))
            if comp_type == ComponentType.LCP_OHL:
                pin_count = params.get("n_phases", 3) + params.get("n_gw", 0)
            comp = ComponentInstance(
                comp_id=f"{comp_type.value}_001",
                comp_type=comp_type,
                name=comp_type.value,
                x=0,
                y=0,
                params=params,
                pins=create_component_pins(comp_type, pin_count, params=params),
            )
            image = render_component(comp)
            self.assertGreater(non_white_pixels(image), 120, comp_type)

    def test_ground_symbol_uses_pscad_tall_stem(self):
        comp = ComponentInstance(
            comp_id="GND_001",
            comp_type=ComponentType.GROUND,
            name="GND",
            x=0,
            y=0,
            params=get_default_params(ComponentType.GROUND),
            pins=create_component_pins(ComponentType.GROUND),
        )
        image = render_component(comp)

        self.assertGreater(non_white_pixels(image), 60)
        self.assertTrue(has_ink_in_rect(image, 118, 62, 122, 82))
        self.assertTrue(has_ink_in_rect(image, 102, 83, 138, 88))

    def test_lcp_line_symbols_render_as_labeled_model_blocks(self):
        cases = {
            ComponentType.LCP_OHL: {"n_phases": 3, "n_gw": 1},
            ComponentType.LCP_SINGLE_CABLE: {"n_cables": 1},
            ComponentType.LCP_THREE_CABLE: {},
        }
        signatures = {}
        for comp_type, overrides in cases.items():
            params = get_default_params(comp_type) | overrides
            pin_count = params.get("n_phases", params.get("n_cables", 3))
            if comp_type == ComponentType.LCP_OHL:
                pin_count = params.get("n_phases", 3) + params.get("n_gw", 0)
            comp = ComponentInstance(
                comp_id=f"{comp_type.value}_001",
                comp_type=comp_type,
                name=comp_type.value,
                x=0,
                y=0,
                params=params,
                pins=create_component_pins(comp_type, pin_count, params=params),
            )
            image = render_component(comp)
            signatures[comp_type] = image_signature(image)

        self.assertEqual(len(set(signatures.values())), 3)
        self.assertTrue(has_ink_in_rect(render_component(ComponentInstance(
            comp_id="OHL_001",
            comp_type=ComponentType.LCP_OHL,
            name="TLine_1",
            x=0,
            y=0,
            params=get_default_params(ComponentType.LCP_OHL) | {"n_phases": 3, "n_gw": 1},
            pins=create_component_pins(ComponentType.LCP_OHL, 4),
        )), 70, 45, 170, 125))

    def test_lcp_port_labels_use_chinese_terminal_names(self):
        ohl = ComponentInstance(
            comp_id="OHL_001",
            comp_type=ComponentType.LCP_OHL,
            name="TLine_1",
            x=0,
            y=0,
            params=get_default_params(ComponentType.LCP_OHL) | {"n_phases": 3, "n_gw": 1},
            pins=create_component_pins(ComponentType.LCP_OHL, 4),
        )

        self.assertEqual(lcp_ohl_port_label(ohl, "nk_0"), "导线1")
        self.assertEqual(lcp_ohl_port_label(ohl, "nm_2"), "导线3")
        self.assertEqual(lcp_ohl_port_label(ohl, "nk_3"), "地线1")
        self.assertEqual(lcp_single_cable_port_label("nk_0_core"), "芯线1")
        self.assertEqual(lcp_single_cable_port_label("nm_0_sheath"), "护套1")
        self.assertEqual(lcp_single_cable_port_label("nk_0_armor"), "铠装1")
        self.assertEqual(lcp_three_cable_port_label("nk_core_a"), "芯线A")
        self.assertEqual(lcp_three_cable_port_label("nm_sheath_c"), "护套C")
        self.assertEqual(lcp_three_cable_port_label("nk_pipe"), "管道")


if __name__ == "__main__":
    unittest.main()
