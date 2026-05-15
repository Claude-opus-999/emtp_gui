import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from core.code_generator import generate_code
from core.file_io import load_project
from core.solver_builder import SolverBuilder
from models.circuit_model import CircuitModel, ComponentInstance, ComponentType, Pin, Wire
from models.component_lib import create_component_pins, get_default_params
from ui.circuit_canvas import CircuitCanvas, CanvasMode
from ui.main_window import MainWindow


def get_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class RegressionTests(unittest.TestCase):
    def test_umec_pins_follow_winding_types(self):
        yg_delta = create_component_pins(
            ComponentType.UMEC_TRANSFORMER,
            params={"wtype1": "Y_gnd", "wtype2": "Delta"},
        )
        self.assertEqual(
            [pin.name for pin in yg_delta],
            ["H_A", "H_B", "H_C", "H_N", "X_A", "X_B", "X_C"],
        )

        y_y = create_component_pins(
            ComponentType.UMEC_TRANSFORMER,
            params={"wtype1": "Y", "wtype2": "Y"},
        )
        self.assertIn("H_N", [pin.name for pin in y_y])
        self.assertIn("X_N", [pin.name for pin in y_y])

        delta_delta = create_component_pins(
            ComponentType.UMEC_TRANSFORMER,
            params={"wtype1": "Delta", "wtype2": "Delta"},
        )
        self.assertEqual(
            [pin.name for pin in delta_delta],
            ["H_A", "H_B", "H_C", "X_A", "X_B", "X_C"],
        )

    def test_property_param_change_rebuilds_probe_and_umec_pins(self):
        app = get_app()
        window = MainWindow()
        model = window.model

        try:
            probe = ComponentInstance(
                comp_id="PRB_001",
                comp_type=ComponentType.PROBE,
                name="PRB1",
                x=0,
                y=0,
                params={"probe_type": "voltage_ground"},
                pins=create_component_pins(
                    ComponentType.PROBE,
                    probe_type="voltage_ground",
                ),
            )
            model.add_component(probe)

            window.property_panel._current_comp_id = "PRB_001"
            window.property_panel._on_param_changed("probe_type", "voltage_between")

            self.assertEqual(
                [pin.name for pin in model.components["PRB_001"].pins],
                ["sense", "ref"],
            )

            umec_params = get_default_params(ComponentType.UMEC_TRANSFORMER) | {
                "wtype1": "Y",
                "wtype2": "Y",
            }
            umec = ComponentInstance(
                comp_id="UMEC_001",
                comp_type=ComponentType.UMEC_TRANSFORMER,
                name="UMEC1",
                x=0,
                y=0,
                params=umec_params,
                pins=create_component_pins(
                    ComponentType.UMEC_TRANSFORMER,
                    params=umec_params,
                ),
            )
            ground = ComponentInstance(
                comp_id="GND_001",
                comp_type=ComponentType.GROUND,
                name="GND1",
                x=0,
                y=0,
                pins=create_component_pins(ComponentType.GROUND),
            )
            model.add_component(umec)
            model.add_component(ground)
            model.add_wire(Wire("W_UMEC_N", "UMEC_001", "X_N", "GND_001", "gnd"))

            window.property_panel._current_comp_id = "UMEC_001"
            window.property_panel._on_param_changed("wtype2", "Delta")

            self.assertNotIn(
                "X_N",
                [pin.name for pin in model.components["UMEC_001"].pins],
            )
            self.assertNotIn("W_UMEC_N", model.wires)
        finally:
            model.components.clear()
            model.wires.clear()
            window.close()
            app.processEvents()

    def test_load_legacy_project_keeps_component_types(self):
        model = load_project("example_circuit.emtp")

        component_types = {comp.name: comp.comp_type for comp in model.components.values()}

        self.assertEqual(component_types["Vdc"], ComponentType.VOLTAGE_SOURCE)
        self.assertEqual(component_types["R1"], ComponentType.RESISTOR)
        self.assertEqual(component_types["C1"], ComponentType.CAPACITOR)
        self.assertIn(ComponentType.GROUND, component_types.values())

        code = generate_code(model)
        self.assertIn('solver.add_VS("Vdc", 1, 0, 100)', code)
        self.assertIn('solver.add_R("R1", 1, 2, 100)', code)
        self.assertIn('solver.add_C("C1", 2, 0, 0.000001, Rp=0)', code)

    def test_single_phase_ulm_uses_legacy_pin_names(self):
        model = CircuitModel()
        ulm = ComponentInstance(
            comp_id="ULM_001",
            comp_type=ComponentType.ULM,
            name="ULM1",
            x=0,
            y=0,
            params=get_default_params(ComponentType.ULM) | {
                "n_phases": 1,
                "fitulm_file": "line.fitULM",
                "length": 1000,
            },
            pins=create_component_pins(ComponentType.ULM, 1),
        )
        model.add_component(ulm)

        code = generate_code(model)

        self.assertIn('solver.add_ulm_line("ULM1", [1], [2], "line.fitULM", 1000)', code)

    def test_assign_node_ids_is_stable(self):
        def make_comp(cid, comp_type, name, pin_names):
            return ComponentInstance(
                comp_id=cid,
                comp_type=comp_type,
                name=name,
                x=0,
                y=0,
                pins=[Pin(pin_name, 0, 0) for pin_name in pin_names],
            )

        def build(order):
            model = CircuitModel()
            components = {
                "vs": make_comp("VS_001", ComponentType.VOLTAGE_SOURCE, "VS1", ["node_pos", "node_neg"]),
                "r": make_comp("R_001", ComponentType.RESISTOR, "R1", ["nf", "nt"]),
                "c": make_comp("C_001", ComponentType.CAPACITOR, "C1", ["nf", "nt"]),
                "g": make_comp("GND_001", ComponentType.GROUND, "GND", ["gnd"]),
            }
            for key in order:
                model.add_component(components[key])
            model._undo_stack.clear()
            model._redo_stack.clear()

            for wire in [
                Wire("W1", "VS_001", "node_pos", "R_001", "nf"),
                Wire("W2", "R_001", "nt", "C_001", "nf"),
                Wire("W3", "VS_001", "node_neg", "GND_001", "gnd"),
                Wire("W4", "C_001", "nt", "GND_001", "gnd"),
            ]:
                model.add_wire(wire)
            model._undo_stack.clear()
            model._redo_stack.clear()
            return {key: value for key, value in sorted(model.assign_node_ids().items())}

        self.assertEqual(
            build(("vs", "r", "c", "g")),
            build(("c", "r", "vs", "g")),
        )

    def test_canvas_copy_paste_does_not_raise(self):
        app = get_app()
        model = CircuitModel()
        canvas = CircuitCanvas(model)

        comp_id = model.generate_component_id(ComponentType.RESISTOR)
        model.add_component(
            ComponentInstance(
                comp_id=comp_id,
                comp_type=ComponentType.RESISTOR,
                name="R1",
                x=0,
                y=0,
                pins=create_component_pins(ComponentType.RESISTOR),
            )
        )
        app.processEvents()

        canvas.component_items[comp_id].setSelected(True)
        canvas._copy_selected()
        canvas._paste_clipboard(canvas.mapToScene(0, 0))

        self.assertEqual(len(model.components), 2)

    def test_canvas_click_selection_replaces_unless_ctrl_is_held(self):
        app = get_app()
        model = CircuitModel()
        canvas = CircuitCanvas(model)
        canvas.resize(600, 400)
        canvas.show()

        for comp_id, name, x in [("R_001", "R1", -60), ("C_001", "C1", 60)]:
            model.add_component(
                ComponentInstance(
                    comp_id=comp_id,
                    comp_type=ComponentType.RESISTOR,
                    name=name,
                    x=x,
                    y=0,
                    pins=create_component_pins(ComponentType.RESISTOR),
                )
            )
        app.processEvents()
        canvas.centerOn(0, 0)
        app.processEvents()

        r_item = canvas.component_items["R_001"]
        c_item = canvas.component_items["C_001"]

        QTest.mouseClick(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            canvas.mapFromScene(r_item.sceneBoundingRect().center()),
        )
        self.assertTrue(r_item.isSelected())
        self.assertFalse(c_item.isSelected())

        QTest.mouseClick(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            canvas.mapFromScene(c_item.sceneBoundingRect().center()),
        )
        self.assertFalse(r_item.isSelected())
        self.assertTrue(c_item.isSelected())

        QTest.mouseClick(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.ControlModifier,
            canvas.mapFromScene(r_item.sceneBoundingRect().center()),
        )
        self.assertTrue(r_item.isSelected())
        self.assertTrue(c_item.isSelected())

        canvas.close()
        app.processEvents()

    def test_canvas_drag_preserves_multi_selection_and_moves_group(self):
        app = get_app()
        model = CircuitModel()
        canvas = CircuitCanvas(model)
        canvas.resize(600, 400)
        canvas.show()

        for comp_id, name, x in [("R_001", "R1", -60), ("C_001", "C1", 60)]:
            model.add_component(
                ComponentInstance(
                    comp_id=comp_id,
                    comp_type=ComponentType.RESISTOR,
                    name=name,
                    x=x,
                    y=0,
                    pins=create_component_pins(ComponentType.RESISTOR),
                )
            )
        app.processEvents()
        canvas.centerOn(0, 0)
        app.processEvents()

        r_item = canvas.component_items["R_001"]
        c_item = canvas.component_items["C_001"]
        r_item.setSelected(True)
        c_item.setSelected(True)

        start = canvas.mapFromScene(r_item.sceneBoundingRect().center())
        end = start + QPoint(40, 0)
        QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
        QTest.mouseMove(canvas.viewport(), end)
        QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
        app.processEvents()

        self.assertTrue(r_item.isSelected())
        self.assertTrue(c_item.isSelected())
        self.assertGreater(model.components["R_001"].x, -60)
        self.assertGreater(model.components["C_001"].x, 60)

        canvas.close()
        app.processEvents()

    def test_ground_pin_is_at_top_of_symbol(self):
        pins = create_component_pins(ComponentType.GROUND)

        self.assertEqual(len(pins), 1)
        self.assertEqual(pins[0].name, "gnd")
        self.assertLessEqual(pins[0].local_y, -20)

    def test_canvas_scene_is_large_and_middle_drag_pans(self):
        app = get_app()
        model = CircuitModel()
        canvas = CircuitCanvas(model)
        canvas.resize(600, 400)
        canvas.show()
        app.processEvents()

        scene_rect = canvas.sceneRect()
        self.assertGreaterEqual(scene_rect.width(), 6000)
        self.assertGreaterEqual(scene_rect.height(), 6000)

        canvas.centerOn(0, 0)
        app.processEvents()
        start_h = canvas.horizontalScrollBar().value()
        start_v = canvas.verticalScrollBar().value()
        start = canvas.viewport().rect().center()
        end = start + QPoint(80, 60)

        QTest.mousePress(canvas.viewport(), Qt.MouseButton.MiddleButton, Qt.KeyboardModifier.NoModifier, start)
        QTest.mouseMove(canvas.viewport(), end)
        QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.MiddleButton, Qt.KeyboardModifier.NoModifier, end)
        app.processEvents()

        self.assertNotEqual(canvas.horizontalScrollBar().value(), start_h)
        self.assertNotEqual(canvas.verticalScrollBar().value(), start_v)

        canvas.close()
        app.processEvents()

    def test_pscad_wire_mode_left_click_adds_waypoint_and_right_click_finishes(self):
        get_app()
        model = CircuitModel()
        canvas = CircuitCanvas(model)
        try:
            r1 = ComponentInstance(
                comp_id="R_001",
                comp_type=ComponentType.RESISTOR,
                name="R1",
                x=-100,
                y=0,
                pins=create_component_pins(ComponentType.RESISTOR),
            )
            r2 = ComponentInstance(
                comp_id="R_002",
                comp_type=ComponentType.RESISTOR,
                name="R2",
                x=100,
                y=0,
                pins=create_component_pins(ComponentType.RESISTOR),
            )
            model.add_component(r1)
            model.add_component(r2)
            canvas.set_mode(CanvasMode.WIRE)

            start = canvas.component_items["R_001"].get_all_scene_pin_positions()["nt"]
            waypoint = QPointF(0, -50)
            end = canvas.component_items["R_002"].get_all_scene_pin_positions()["nf"]

            canvas._handle_wire_left_click(start)
            canvas._handle_wire_left_click(waypoint)
            canvas._handle_wire_right_click(end)

            wires = list(model.wires.values())
            self.assertEqual(len(wires), 1)
            self.assertEqual(wires[0].from_comp, "R_001")
            self.assertEqual(wires[0].from_pin, "nt")
            self.assertEqual(wires[0].to_comp, "R_002")
            self.assertEqual(wires[0].to_pin, "nf")
            self.assertEqual(wires[0].waypoints, [(0.0, -50.0)])
        finally:
            canvas.close()

    def test_pscad_wire_mode_can_finish_on_existing_wire_midpoint(self):
        get_app()
        model = CircuitModel()
        canvas = CircuitCanvas(model)
        try:
            r1 = ComponentInstance(
                comp_id="R_001",
                comp_type=ComponentType.RESISTOR,
                name="R1",
                x=-100,
                y=0,
                pins=create_component_pins(ComponentType.RESISTOR),
            )
            r2 = ComponentInstance(
                comp_id="R_002",
                comp_type=ComponentType.RESISTOR,
                name="R2",
                x=100,
                y=0,
                pins=create_component_pins(ComponentType.RESISTOR),
            )
            r3 = ComponentInstance(
                comp_id="R_003",
                comp_type=ComponentType.RESISTOR,
                name="R3",
                x=0,
                y=100,
                pins=create_component_pins(ComponentType.RESISTOR),
            )
            for comp in (r1, r2, r3):
                model.add_component(comp)
            model.add_wire(Wire("W_MAIN", "R_001", "nt", "R_002", "nf"))
            canvas.set_mode(CanvasMode.WIRE)

            start = canvas.component_items["R_003"].get_all_scene_pin_positions()["nf"]
            midpoint = QPointF(0, 0)
            canvas._handle_wire_left_click(start)
            canvas._handle_wire_right_click(midpoint)

            junction_type = getattr(ComponentType, "JUNCTION")
            junctions = [
                comp for comp in model.components.values()
                if comp.comp_type == junction_type
            ]
            self.assertEqual(len(junctions), 1)
            self.assertNotIn("W_MAIN", model.wires)
            self.assertEqual(len(model.wires), 3)
            self.assertGreaterEqual(
                len([
                    wire for wire in model.wires.values()
                    if wire.from_comp == junctions[0].comp_id or wire.to_comp == junctions[0].comp_id
                ]),
                3,
            )
        finally:
            canvas.close()

    def test_code_preview_refreshes_after_wire_change(self):
        app = get_app()
        window = MainWindow()
        model = window.model

        model.add_component(
            ComponentInstance(
                comp_id="R_001",
                comp_type=ComponentType.RESISTOR,
                name="R1",
                x=0,
                y=0,
                pins=create_component_pins(ComponentType.RESISTOR),
            )
        )
        model.add_component(
            ComponentInstance(
                comp_id="GND_001",
                comp_type=ComponentType.GROUND,
                name="GND",
                x=0,
                y=0,
                pins=create_component_pins(ComponentType.GROUND),
            )
        )
        model.add_wire(Wire("W1", "R_001", "nf", "GND_001", "gnd"))
        app.processEvents()

        self.assertEqual(window.code_preview.code_edit.toPlainText(), generate_code(model))
        window.model.components.clear()
        window.model.wires.clear()
        window.close()

    def test_lcp_ohl_export_includes_config_fields(self):
        model = CircuitModel()
        comp = ComponentInstance(
            comp_id="LCP_OHL_001",
            comp_type=ComponentType.LCP_OHL,
            name="LCP1",
            x=0,
            y=0,
            params=get_default_params(ComponentType.LCP_OHL) | {
                "length": 1200.0,
                "force_rebuild": False,
                "n_phases": 3,
                "n_gw": 1,
                "ground_resistivity": 500.0,
                "phase_positions": [[0.0, 10.0], [4.0, 10.0], [8.0, 10.0]],
                "gw_positions": [[4.0, 16.0]],
                "phase_radius": 0.015,
                "phase_dc_resistance": 0.08,
                "phase_bundle_n": 2,
                "phase_bundle_spacing": 0.4,
                "gw_radius": 0.008,
                "gw_dc_resistance": 0.2,
            },
            pins=create_component_pins(ComponentType.LCP_OHL, 4),
        )
        model.add_component(comp)

        code = generate_code(model)

        self.assertIn("_config_LCP1", code)
        self.assertIn(
            "'phase_positions': [[0.0, 10.0], [4.0, 10.0], [8.0, 10.0]]",
            code,
        )
        self.assertIn("'gw_positions': [[4.0, 16.0]]", code)
        self.assertIn("'ground_resistivity': 500.0", code)
        self.assertNotIn("'n_phases'", code)
        self.assertNotIn("'n_gw'", code)
        self.assertIn('nodes_k=[1, 2, 3, 4]', code)
        self.assertIn('nodes_m=[5, 6, 7, 8]', code)
        self.assertIn("config=_config_LCP1", code)

    def test_lcp_ohl_solver_config_omits_gui_only_fields(self):
        model = CircuitModel()
        comp = ComponentInstance(
            comp_id="LCP_OHL_001",
            comp_type=ComponentType.LCP_OHL,
            name="LCP1",
            x=0,
            y=0,
            params=get_default_params(ComponentType.LCP_OHL) | {
                "length": 1200.0,
                "force_rebuild": False,
                "n_phases": 4,
                "n_gw": 1,
                "ground_resistivity": 500.0,
                "phase_positions": [[0.0, 10.0], [4.0, 10.0], [8.0, 10.0]],
                "gw_positions": [[4.0, 16.0]],
                "phase_sag": 6.0,
                "gw_sag": 3.0,
                "eliminate_ground_wires": True,
                "n_freq_increments": 37,
            },
            pins=create_component_pins(ComponentType.LCP_OHL, 4),
        )
        model.add_component(comp)

        class FakeSolver:
            def add_lcp_ohl_line(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

        fake_solver = FakeSolver()
        builder = SolverBuilder()
        builder._node_map = model.assign_node_ids()

        builder._add_components(fake_solver, model)

        config = fake_solver.kwargs["config"]
        self.assertNotIn("n_phases", config)
        self.assertNotIn("n_gw", config)
        self.assertNotIn("length", config)
        self.assertNotIn("force_rebuild", config)
        self.assertNotIn("phase_sag", config)
        self.assertNotIn("gw_sag", config)
        self.assertNotIn("eliminate_ground_wires", config)
        self.assertNotIn("n_freq_increments", config)
        self.assertEqual(config["n_freq"], 37)
        self.assertTrue(config["kron_reduction"])
        self.assertEqual(len(fake_solver.kwargs["nodes_k"]), 4)
        self.assertEqual(len(fake_solver.kwargs["nodes_m"]), 4)
        self.assertEqual(fake_solver.kwargs["length"], 1200.0)
        self.assertFalse(fake_solver.kwargs["force_rebuild"])

    def test_canvas_places_lcp_ohl_with_phase_and_ground_wire_pins(self):
        get_app()
        model = CircuitModel()
        canvas = CircuitCanvas(model)
        try:
            canvas.set_placing_type(ComponentType.LCP_OHL)
            canvas._place_component(canvas.snap_to_grid(canvas.mapToScene(0, 0)))

            comp = next(iter(model.components.values()))
            pin_names = {pin.name for pin in comp.pins}

            self.assertEqual(comp.params["n_phases"], 2)
            self.assertEqual(comp.params["n_gw"], 2)
            self.assertIn("nk_3", pin_names)
            self.assertIn("nm_3", pin_names)
            self.assertEqual(len([p for p in comp.pins if p.name.startswith("nk")]), 4)
            self.assertEqual(len([p for p in comp.pins if p.name.startswith("nm")]), 4)
        finally:
            canvas.close()

    def test_lcp_symbol_pins_use_wide_port_columns(self):
        cases = [
            (ComponentType.LCP_OHL, 4, {"n_phases": 3, "n_gw": 1}),
            (ComponentType.LCP_SINGLE_CABLE, 1, {"n_cables": 1}),
            (ComponentType.LCP_THREE_CABLE, 3, {}),
        ]

        for comp_type, pin_count, overrides in cases:
            with self.subTest(comp_type=comp_type):
                params = get_default_params(comp_type) | overrides
                pins = create_component_pins(comp_type, pin_count, params=params)
                xs = [pin.local_x for pin in pins]

                self.assertLessEqual(min(xs), -70)
                self.assertGreaterEqual(max(xs), 70)

    def test_lcp_single_core_cable_uses_kernel_api_and_clean_config(self):
        model = CircuitModel()
        params = get_default_params(ComponentType.LCP_SINGLE_CABLE) | {
            "length": 2500.0,
            "force_rebuild": False,
            "n_cables": 2,
            "soil_resistivity": 250.0,
            "soil_permittivity": 8.0,
            "cables": [
                {
                    "core_radius": 0.02,
                    "core_resistivity": 1.7e-8,
                    "insulation_outer_radius": 0.035,
                    "insulation_eps_r": 3.5,
                    "sheath_outer_radius": 0.04,
                    "sheath_resistivity": 2.2e-7,
                    "armor_outer_radius": 0.045,
                    "outer_jacket_radius": 0.05,
                    "burial_depth": 1.0,
                    "horizontal_pos": -0.5,
                },
                {
                    "core_radius": 0.02,
                    "core_resistivity": 1.7e-8,
                    "insulation_outer_radius": 0.035,
                    "insulation_eps_r": 3.5,
                    "sheath_outer_radius": 0.04,
                    "sheath_resistivity": 2.2e-7,
                    "armor_outer_radius": 0.045,
                    "outer_jacket_radius": 0.05,
                    "burial_depth": 1.0,
                    "horizontal_pos": 0.5,
                },
            ],
        }
        comp = ComponentInstance(
            comp_id="LCP_SC_001",
            comp_type=ComponentType.LCP_SINGLE_CABLE,
            name="SC1",
            x=0,
            y=0,
            params=params,
            pins=create_component_pins(ComponentType.LCP_SINGLE_CABLE, 2),
        )
        model.add_component(comp)

        class FakeSolver:
            def add_lcp_single_core_cable_line(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

            def add_lcp_single_cable_line(self, *args, **kwargs):
                raise AssertionError("used deprecated single-cable API name")

        fake_solver = FakeSolver()
        builder = SolverBuilder()
        builder._node_map = model.assign_node_ids()

        builder._add_components(fake_solver, model)

        config = fake_solver.kwargs["config"]
        self.assertNotIn("n_cables", config)
        self.assertNotIn("length", config)
        self.assertNotIn("force_rebuild", config)
        self.assertNotIn("soil_resistivity", config)
        self.assertNotIn("soil_permittivity", config)
        self.assertEqual(config["soil_rho"], 250.0)
        self.assertEqual(config["soil_epsilon_r"], 8.0)
        self.assertEqual(len(config["cables"]), 2)
        self.assertNotIn("core_resistivity", config["cables"][0])
        self.assertNotIn("insulation_outer_radius", config["cables"][0])
        self.assertNotIn("outer_jacket_radius", config["cables"][0])
        self.assertEqual(config["cables"][0]["core_rho"], 1.7e-8)
        self.assertEqual(config["cables"][0]["insulation_radius"], 0.035)
        self.assertEqual(config["cables"][0]["jacket_radius"], 0.05)
        self.assertEqual(len(fake_solver.kwargs["nodes_k"]), 6)
        self.assertEqual(len(fake_solver.kwargs["nodes_m"]), 6)

        code = generate_code(model)
        self.assertIn("solver.add_lcp_single_core_cable_line", code)
        self.assertNotIn("solver.add_lcp_single_cable_line", code)
        self.assertNotIn("'n_cables'", code)
        self.assertNotIn("'core_resistivity'", code)
        self.assertIn("'soil_rho': 250.0", code)

    def test_lcp_three_core_cable_uses_kernel_api_and_clean_config(self):
        model = CircuitModel()
        params = get_default_params(ComponentType.LCP_THREE_CABLE) | {
            "length": 5000.0,
            "force_rebuild": False,
            "pipe_inner_radius": 0.0665,
            "pipe_outer_radius": 0.0715,
            "pipe_resistivity": 9.78e-8,
            "pipe_mu_r": 200.0,
            "core_radius": 0.001175,
            "core_resistivity": 1.72e-8,
            "insulation_radius": 0.02505,
            "insulation_eps_r": 2.3,
            "sheath_radius": 0.02715,
            "sheath_resistivity": 2.2e-7,
            "dist_from_center": 0.03415,
            "conductor_angles": [270.0, 30.0, 150.0],
            "soil_resistivity": 100.0,
            "soil_permittivity": 1.0,
            "burial_depth": 1.0,
        }
        comp = ComponentInstance(
            comp_id="LCP_3C_001",
            comp_type=ComponentType.LCP_THREE_CABLE,
            name="TC1",
            x=0,
            y=0,
            params=params,
            pins=create_component_pins(ComponentType.LCP_THREE_CABLE),
        )
        model.add_component(comp)

        class FakeSolver:
            def add_lcp_three_core_cable_line(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

            def add_lcp_three_cable_line(self, *args, **kwargs):
                raise AssertionError("used deprecated three-cable API name")

        fake_solver = FakeSolver()
        builder = SolverBuilder()
        builder._node_map = model.assign_node_ids()

        builder._add_components(fake_solver, model)

        config = fake_solver.kwargs["config"]
        self.assertNotIn("length", config)
        self.assertNotIn("force_rebuild", config)
        self.assertNotIn("pipe_resistivity", config)
        self.assertNotIn("core_resistivity", config)
        self.assertNotIn("sheath_radius", config)
        self.assertNotIn("conductor_angles", config)
        self.assertNotIn("soil_resistivity", config)
        self.assertEqual(config["pipe_rho"], 9.78e-8)
        self.assertEqual(config["core_rho"], 1.72e-8)
        self.assertEqual(config["sheath_outer_radius"], 0.02715)
        self.assertEqual(config["cable_angles_deg"], [270.0, 30.0, 150.0])
        self.assertEqual(config["ground_resistivity"], 100.0)
        self.assertEqual(len(fake_solver.kwargs["nodes_k"]), 7)
        self.assertEqual(len(fake_solver.kwargs["nodes_m"]), 7)

        code = generate_code(model)
        self.assertIn("solver.add_lcp_three_core_cable_line", code)
        self.assertNotIn("'pipe_resistivity'", code)
        self.assertNotIn("'conductor_angles'", code)
        self.assertIn("'pipe_rho': 9.78e-08", code)

    def test_branch_current_probe_uses_explicit_branch_name_once(self):
        model = CircuitModel()

        r1 = ComponentInstance(
            comp_id="R_001",
            comp_type=ComponentType.RESISTOR,
            name="R1",
            x=0,
            y=0,
            pins=create_component_pins(ComponentType.RESISTOR),
        )
        c1 = ComponentInstance(
            comp_id="C_001",
            comp_type=ComponentType.CAPACITOR,
            name="C1",
            x=0,
            y=0,
            pins=create_component_pins(ComponentType.CAPACITOR),
        )
        gnd = ComponentInstance(
            comp_id="GND_001",
            comp_type=ComponentType.GROUND,
            name="GND1",
            x=0,
            y=0,
            pins=create_component_pins(ComponentType.GROUND),
        )
        probe = ComponentInstance(
            comp_id="PRB_001",
            comp_type=ComponentType.PROBE,
            name="PRB1",
            x=0,
            y=0,
            params={"probe_type": "branch_current", "unit": "A", "branch_name": "R1"},
            pins=create_component_pins(ComponentType.PROBE),
        )

        for comp in (r1, c1, gnd, probe):
            model.add_component(comp)

        model.add_wire(Wire("W1", "R_001", "nf", "C_001", "nf"))
        model.add_wire(Wire("W2", "PRB_001", "sense", "R_001", "nf"))
        model.add_wire(Wire("W3", "R_001", "nt", "GND_001", "gnd"))

        probes = [
            p for p in model.get_auto_voltage_probes()
            if p.probe_type == "branch_current"
        ]

        self.assertEqual(len(probes), 1)
        self.assertEqual(probes[0].branch_name, "R1")

    def test_two_node_voltage_probe_uses_positive_and_negative_nodes(self):
        model = CircuitModel()

        r1 = ComponentInstance(
            comp_id="R_001",
            comp_type=ComponentType.RESISTOR,
            name="R1",
            x=0,
            y=0,
            pins=create_component_pins(ComponentType.RESISTOR),
        )
        gnd = ComponentInstance(
            comp_id="GND_001",
            comp_type=ComponentType.GROUND,
            name="GND",
            x=0,
            y=0,
            pins=create_component_pins(ComponentType.GROUND),
        )
        probe = ComponentInstance(
            comp_id="PRB_001",
            comp_type=ComponentType.PROBE,
            name="PRB1",
            x=0,
            y=0,
            params={"probe_type": "voltage_between", "unit": "kV"},
            pins=create_component_pins(ComponentType.PROBE, probe_type="voltage_between"),
        )

        for comp in (r1, probe):
            model.add_component(comp)

        model.add_wire(Wire("W1", "PRB_001", "sense", "R_001", "nf"))
        model.add_wire(Wire("W2", "PRB_001", "ref", "R_001", "nt"))

        probes = [
            p for p in model.get_auto_voltage_probes()
            if p.probe_id.startswith("PRB1_V_")
        ]

        self.assertEqual(len(probes), 1)
        self.assertEqual(probes[0].probe_type, "voltage")
        self.assertGreater(probes[0].node_pos, 0)
        self.assertGreater(probes[0].node_neg, 0)
        self.assertNotEqual(probes[0].node_pos, probes[0].node_neg)

    def test_sim_runner_detects_step_callback_support(self):
        from core.sim_runner import solver_supports_step_callback

        class WithCallback:
            def run(self, step_callback=None):
                return None

        class WithoutCallback:
            def run(self):
                return None

        self.assertTrue(solver_supports_step_callback(WithCallback()))
        self.assertFalse(solver_supports_step_callback(WithoutCallback()))

    def test_solver_builder_has_no_dead_wire_type_assignment(self):
        with open("core/solver_builder.py", "r", encoding="utf-8") as f:
            source = f.read()

        self.assertNotIn("type(flat.wires.get", source)


if __name__ == "__main__":
    unittest.main()
