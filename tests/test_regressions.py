import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QKeyEvent, QPainter, QPainterPath, QValidator
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGraphicsItem, QPushButton, QToolBar

import ui.main_window as main_window_module
from core.code_generator import generate_code
from core.file_io import load_project
from core.solver_builder import SolverBuilder
from core.sim_runner import SimulationRunner
from core.validator import CircuitValidator, ValidationSeverity
from models.circuit_model import (
    CircuitModel,
    ComponentInstance,
    ComponentType,
    Pin,
    ProbeConfig,
    SimSettings,
    SubcircuitDefinition,
    SubcircuitPort,
    Wire,
)
from models.component_lib import create_component_pins, get_default_params
from ui.circuit_canvas import CircuitCanvas, CanvasMode, WireGraphicsItem
from ui.main_window import MainWindow
from ui.probe_panel import ProbePanel
from ui.symbols import draw_component_symbol


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

    def test_property_float_editor_accepts_scientific_notation_text(self):
        app = get_app()
        model = CircuitModel()
        canvas = CircuitCanvas(model)
        panel = main_window_module.PropertyPanel(model, canvas)
        try:
            resistor = ComponentInstance(
                comp_id="R_001",
                comp_type=ComponentType.RESISTOR,
                name="R1",
                x=0,
                y=0,
                params={"R": 100.0},
                pins=create_component_pins(ComponentType.RESISTOR),
            )
            model.add_component(resistor)
            panel._show_component(resistor)
            spin = dict(panel._param_spin_widgets)["R"]

            text = "4.256e-3"
            state, _, _ = spin.validate(text, len(text))
            exp_state, _, _ = spin.validate("4.256e", len("4.256e"))
            sign_state, _, _ = spin.validate("4.256e-", len("4.256e-"))

            self.assertEqual(state, QValidator.State.Acceptable)
            self.assertEqual(exp_state, QValidator.State.Intermediate)
            self.assertEqual(sign_state, QValidator.State.Intermediate)
            spin.lineEdit().selectAll()
            QTest.keyClicks(spin.lineEdit(), text)
            spin.interpretText()
            app.processEvents()

            self.assertAlmostEqual(model.components["R_001"].params["R"], 4.256e-3)
        finally:
            panel.close()
            canvas.close()
            app.processEvents()

    def test_main_toolbar_stops_at_wire_mode_button(self):
        app = get_app()
        window = MainWindow()
        try:
            main_toolbar = next(
                toolbar for toolbar in window.findChildren(QToolBar)
                if toolbar.windowTitle() == "主工具栏"
            )
            tooltips = [
                button.toolTip()
                for button in main_toolbar.findChildren(QPushButton)
            ]

            self.assertEqual(tooltips[-1], "连线模式 (Ctrl+W)")
            for removed in ("添加接地 (Ctrl+G)", "旋转元件 (Ctrl+R)", "删除 (Del)", "清空电路"):
                self.assertNotIn(removed, tooltips)
        finally:
            window.close()
            app.processEvents()

    def test_main_window_connects_simulation_log_and_results(self):
        app = get_app()

        class FakeSignal:
            def __init__(self):
                self.connected = []

            def connect(self, callback):
                self.connected.append(callback)

        class FakeRunner:
            instances = []

            def __init__(self, model, parent=None):
                self.model = model
                self.parent = parent
                self.progress = FakeSignal()
                self.progress_pct = FakeSignal()
                self.log_received = FakeSignal()
                self.results_ready = FakeSignal()
                self.finished_ok = FakeSignal()
                self.finished = FakeSignal()
                self.error = FakeSignal()
                self.started = False
                FakeRunner.instances.append(self)

            def start(self):
                self.started = True

            def isRunning(self):
                return False

            def request_cancel(self):
                pass

        original_runner = main_window_module.SimulationRunner
        main_window_module.SimulationRunner = FakeRunner
        window = MainWindow()
        try:
            self.assertIsNone(window._last_sim_results)

            window._on_run_simulation()

            runner = FakeRunner.instances[-1]
            self.assertIn(window._on_sim_log, runner.log_received.connected)
            self.assertIn(window._on_sim_results, runner.results_ready.connected)
            self.assertTrue(runner.started)

            results = {"probes": {"P1": {}}, "timing": {"steps": 10}}
            window._on_sim_results(results)
            self.assertIs(window._last_sim_results, results)
        finally:
            main_window_module.SimulationRunner = original_runner
            if getattr(window, "_progress_dialog", None):
                window._progress_dialog.close()
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

    def test_reversed_parallel_voltage_sources_are_warning_not_error(self):
        model = CircuitModel()
        for comp_id, comp_type, name in [
            ("J_A", ComponentType.JUNCTION, "JA"),
            ("J_B", ComponentType.JUNCTION, "JB"),
            ("VS_001", ComponentType.VOLTAGE_SOURCE, "VS1"),
            ("VS_002", ComponentType.VOLTAGE_SOURCE, "VS2"),
        ]:
            model.add_component(ComponentInstance(
                comp_id=comp_id,
                comp_type=comp_type,
                name=name,
                x=0,
                y=0,
                pins=create_component_pins(comp_type),
            ))
        model.add_wire(Wire("W1", "VS_001", "node_pos", "J_A", "node"))
        model.add_wire(Wire("W2", "VS_001", "node_neg", "J_B", "node"))
        model.add_wire(Wire("W3", "VS_002", "node_pos", "J_B", "node"))
        model.add_wire(Wire("W4", "VS_002", "node_neg", "J_A", "node"))

        errors = CircuitValidator()._check_voltage_source_conflict(model)

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].severity, ValidationSeverity.WARNING)

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

    def test_canvas_group_drag_moves_wire_waypoints_with_selected_endpoints(self):
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
        model.add_wire(Wire("W_ROUTE", "R_001", "nt", "C_001", "nf", [(0.0, -50.0)]))
        app.processEvents()
        canvas.centerOn(0, 0)
        app.processEvents()

        r_item = canvas.component_items["R_001"]
        c_item = canvas.component_items["C_001"]
        r_item.setSelected(True)
        c_item.setSelected(True)

        start = canvas.mapFromScene(r_item.sceneBoundingRect().center())
        end = start + QPoint(40, 30)
        QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
        QTest.mouseMove(canvas.viewport(), end)
        QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
        app.processEvents()

        dx = model.components["R_001"].x - (-60)
        dy = model.components["R_001"].y - 0
        self.assertEqual(model.wires["W_ROUTE"].waypoints, [(0.0 + dx, -50.0 + dy)])

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
            end = canvas.component_items["R_002"].get_all_scene_pin_positions()["nf"]

            canvas._handle_wire_left_click(start)
            canvas._handle_wire_left_click(QPointF(-50, -40))
            canvas._handle_wire_left_click(QPointF(70, -45))
            canvas._handle_wire_right_click(end)

            wires = list(model.wires.values())
            self.assertEqual(len(wires), 1)
            self.assertEqual(wires[0].from_comp, "R_001")
            self.assertEqual(wires[0].from_pin, "nt")
            self.assertEqual(wires[0].to_comp, "R_002")
            self.assertEqual(wires[0].to_pin, "nf")
            self.assertEqual(
                wires[0].waypoints,
                [(-50.0, 0.0), (-50.0, -40.0), (70.0, -40.0)],
            )
            points = [start, *[QPointF(x, y) for x, y in wires[0].waypoints], end]
            for first, second in zip(points, points[1:]):
                self.assertTrue(
                    abs(first.x() - second.x()) < 0.1
                    or abs(first.y() - second.y()) < 0.1
                )
        finally:
            canvas.close()

    def test_wire_graphics_item_uses_thin_orthogonal_style(self):
        wire = Wire("W_ROUTE", "R_001", "nt", "C_001", "nf", [(-70.0, -40.0), (70.0, -40.0)])
        item = WireGraphicsItem(wire, QPointF(-70, 0), QPointF(70, 0))

        points = item._manhattan_points()

        self.assertEqual(item.pen.color(), QColor("#111111"))
        self.assertLessEqual(item.pen.widthF(), 1.5)
        self.assertLess(WireGraphicsItem.ENDPOINT_DOT_DIAMETER, 4.0)
        self.assertGreater(WireGraphicsItem.ENDPOINT_DOT_DIAMETER, item.pen.widthF())
        self.assertLessEqual(item.selected_pen.widthF(), 2.5)
        for first, second in zip(points, points[1:]):
            self.assertTrue(
                abs(first.x() - second.x()) < 0.1
                or abs(first.y() - second.y()) < 0.1
            )

    def test_wire_graphics_item_repairs_diagonal_wire_without_waypoints(self):
        wire = Wire("W_DIAG", "R_001", "nt", "C_001", "nf")
        item = WireGraphicsItem(wire, QPointF(0, 0), QPointF(100, 50))

        points = item._manhattan_points()

        self.assertGreater(len(points), 2)
        self.assertEqual(points[0], QPointF(0, 0))
        self.assertEqual(points[-1], QPointF(100, 50))
        for first, second in zip(points, points[1:]):
            self.assertTrue(
                abs(first.x() - second.x()) < 0.1
                or abs(first.y() - second.y()) < 0.1
            )

    def test_wire_preview_node_follows_mouse_on_grid_until_wire_finishes(self):
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
            canvas._handle_wire_left_click(start)
            canvas._update_temp_wire(QPointF(17, -24))

            self.assertIsNotNone(canvas._temp_wire_node)
            self.assertEqual(canvas._temp_wire_node.pos(), QPointF(15, -25))
            self.assertEqual(canvas._temp_line.wire.waypoints, [(15.0, 0.0)])
            self.assertEqual(canvas._temp_line.end_pos, QPointF(15, -25))

            end = canvas.component_items["R_002"].get_all_scene_pin_positions()["nf"]
            canvas._handle_wire_right_click(end)

            self.assertIsNone(canvas._temp_wire_node)
        finally:
            canvas.close()

    def test_wire_start_and_finish_snap_to_nearby_component_pins(self):
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

            start_pin = canvas.component_items["R_001"].get_all_scene_pin_positions()["nt"]
            end_pin = canvas.component_items["R_002"].get_all_scene_pin_positions()["nf"]
            start_click = start_pin + QPointF(15, 0)
            end_click = end_pin - QPointF(15, 0)

            self.assertFalse(canvas.component_items["R_001"].sceneBoundingRect().contains(start_click))
            self.assertFalse(canvas.component_items["R_002"].sceneBoundingRect().contains(end_click))

            canvas._handle_wire_left_click(start_click)
            self.assertEqual(canvas._wiring_start, ("R_001", "nt"))
            self.assertEqual(canvas._temp_line.start_pos, start_pin)

            canvas._handle_wire_right_click(end_click)

            wires = list(model.wires.values())
            self.assertEqual(len(wires), 1)
            self.assertEqual(wires[0].from_comp, "R_001")
            self.assertEqual(wires[0].from_pin, "nt")
            self.assertEqual(wires[0].to_comp, "R_002")
            self.assertEqual(wires[0].to_pin, "nf")
        finally:
            canvas.close()

    def test_undo_shortcut_is_ignored_while_component_drag_is_active(self):
        get_app()
        model = CircuitModel()
        canvas = CircuitCanvas(model)
        try:
            comp = ComponentInstance(
                comp_id="R_001",
                comp_type=ComponentType.RESISTOR,
                name="R1",
                x=0,
                y=0,
                pins=create_component_pins(ComponentType.RESISTOR),
            )
            model.add_component(comp)
            item = canvas.component_items["R_001"]
            item.setSelected(True)
            item._drag_snapshot = model._snapshot()

            undo_calls = []
            model.undo = lambda: undo_calls.append(True)
            event = QKeyEvent(
                QEvent.Type.KeyPress,
                Qt.Key.Key_Z,
                Qt.KeyboardModifier.ControlModifier,
            )

            canvas.keyPressEvent(event)

            self.assertEqual(undo_calls, [])
        finally:
            canvas.close()

    def test_wire_preview_uses_last_confirmed_point_for_axis_choice(self):
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
            model.add_component(r1)
            canvas.set_mode(CanvasMode.WIRE)

            start = canvas.component_items["R_001"].get_all_scene_pin_positions()["nt"]
            canvas._handle_wire_left_click(start)
            canvas._handle_wire_left_click(QPointF(20, -10))
            canvas._update_temp_wire(QPointF(25, -75))

            self.assertEqual(canvas._wire_waypoints, [QPointF(20, 0), QPointF(20, -10)])
            self.assertEqual(
                canvas._temp_line.wire.waypoints,
                [(20.0, 0.0), (20.0, -10.0), (25.0, -10.0)],
            )
            self.assertEqual(canvas._temp_line.end_pos, QPointF(25, -75))
        finally:
            canvas.close()

    def test_wire_refresh_clears_temporary_line_before_qt_deletes_it(self):
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
            model.add_component(r1)
            canvas.set_mode(CanvasMode.WIRE)

            start = canvas.component_items["R_001"].get_all_scene_pin_positions()["nt"]
            canvas._handle_wire_left_click(start)
            self.assertIsNotNone(canvas._temp_line)

            canvas._refresh_view()

            self.assertIsNone(canvas._temp_line)
            self.assertIsNone(canvas._temp_wire_node)
            self.assertIsNone(canvas._wiring_start)
            self.assertEqual(canvas.mode, CanvasMode.WIRE)
            canvas._update_temp_wire(QPointF(20, 0))
        finally:
            canvas.close()

    def test_canvas_snap_and_visual_grid_use_five_pixels(self):
        self.assertEqual(CircuitCanvas.GRID_SIZE, 5)
        self.assertEqual(CircuitCanvas.GRID_VISUAL_SIZE, 5)

    def test_wire_right_click_on_empty_space_finishes_at_preview_junction(self):
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
            model.add_component(r1)
            canvas.set_mode(CanvasMode.WIRE)

            start = canvas.component_items["R_001"].get_all_scene_pin_positions()["nt"]
            canvas._handle_wire_left_click(start)
            canvas._handle_wire_right_click(QPointF(17, -24))

            junctions = [
                comp for comp in model.components.values()
                if comp.comp_type == ComponentType.JUNCTION
            ]
            self.assertEqual(len(junctions), 1)
            self.assertEqual((junctions[0].x, junctions[0].y), (15, -25))
            self.assertEqual(len(model.wires), 1)
            self.assertEqual(list(model.wires.values())[0].waypoints, [(15.0, 0.0)])
            self.assertIsNone(canvas._wiring_start)
            self.assertIsNone(canvas._temp_wire_node)
            self.assertEqual(canvas.mode, CanvasMode.WIRE)
        finally:
            canvas.close()

    def test_wire_left_click_on_terminal_auto_commits_with_bend(self):
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
                y=60,
                pins=create_component_pins(ComponentType.RESISTOR),
            )
            model.add_component(r1)
            model.add_component(r2)
            canvas.set_mode(CanvasMode.WIRE)

            start = canvas.component_items["R_001"].get_all_scene_pin_positions()["nt"]
            end = canvas.component_items["R_002"].get_all_scene_pin_positions()["nf"]
            canvas._handle_wire_left_click(start)
            canvas._handle_wire_left_click(end)

            wires = list(model.wires.values())
            self.assertEqual(len(wires), 1)
            self.assertEqual(wires[0].to_comp, "R_002")
            self.assertEqual(wires[0].to_pin, "nf")
            self.assertEqual(wires[0].waypoints, [(70.0, 0.0)])
            self.assertIsNone(canvas._wiring_start)
            self.assertIsNone(canvas._temp_line)
            self.assertEqual(canvas.mode, CanvasMode.WIRE)
        finally:
            canvas.close()

    def test_exiting_wire_mode_discards_temporary_wire(self):
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
            model.add_component(r1)
            canvas.set_mode(CanvasMode.WIRE)
            start = canvas.component_items["R_001"].get_all_scene_pin_positions()["nt"]

            canvas._handle_wire_left_click(start)
            canvas._update_temp_wire(QPointF(15, -25))
            canvas.set_mode(CanvasMode.SELECT)

            self.assertIsNone(canvas._wiring_start)
            self.assertIsNone(canvas._temp_line)
            self.assertIsNone(canvas._temp_wire_node)
            self.assertEqual(len(model.wires), 0)
        finally:
            canvas.close()

    def test_wire_waypoints_are_selectable_and_box_selectable(self):
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
            model.add_wire(Wire("W_ROUTE", "R_001", "nt", "R_002", "nf", [(-70.0, -40.0), (70.0, -40.0)]))

            waypoint_items = getattr(canvas, "wire_waypoint_items", {})
            self.assertEqual(len(waypoint_items), 2)
            handle = waypoint_items[("W_ROUTE", 0)]
            self.assertTrue(handle.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
            self.assertTrue(handle.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
            self.assertLessEqual(handle.boundingRect().width(), 6)
            self.assertLessEqual(handle.boundingRect().height(), 6)

            image = QImage(20, 20, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.translate(10, 10)
            handle.paint(painter, None)
            painter.end()
            self.assertEqual(image.pixelColor(10, 10).alpha(), 0)

            canvas.scene.clearSelection()
            path = QPainterPath()
            path.addRect(handle.sceneBoundingRect().adjusted(-1, -1, 1, 1))
            canvas.scene.setSelectionArea(path)

            self.assertTrue(handle.isSelected())
        finally:
            canvas.close()

    def test_wire_intersections_have_small_black_dots(self):
        get_app()
        model = CircuitModel()
        canvas = CircuitCanvas(model)
        try:
            for comp_id, x, y in [
                ("J_L", -50, 0),
                ("J_R", 50, 0),
                ("J_T", 0, -50),
                ("J_B", 0, 50),
            ]:
                model.add_component(
                    ComponentInstance(
                        comp_id=comp_id,
                        comp_type=ComponentType.JUNCTION,
                        name=comp_id,
                        x=x,
                        y=y,
                        pins=create_component_pins(ComponentType.JUNCTION),
                    )
                )
            model.add_wire(Wire("W_H", "J_L", "node", "J_R", "node"))
            model.add_wire(Wire("W_V", "J_T", "node", "J_B", "node"))

            intersection_items = getattr(canvas, "wire_intersection_items", [])
            self.assertEqual(len(intersection_items), 1)
            dot = intersection_items[0]
            self.assertEqual(dot.sceneBoundingRect().center(), QPointF(0, 0))
            self.assertLessEqual(dot.sceneBoundingRect().width(), WireGraphicsItem.ENDPOINT_DOT_DIAMETER + 0.1)
            self.assertLessEqual(dot.sceneBoundingRect().height(), WireGraphicsItem.ENDPOINT_DOT_DIAMETER + 0.1)
            self.assertEqual(dot.brush().color(), QColor("#111111"))
        finally:
            canvas.close()

    def test_wire_waypoint_drag_updates_adjacent_segments_orthogonally(self):
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
            model.add_wire(Wire("W_ROUTE", "R_001", "nt", "R_002", "nf", [(-70.0, -40.0), (70.0, -40.0)]))

            handle = getattr(canvas, "wire_waypoint_items", {})[("W_ROUTE", 0)]
            handle.setPos(QPointF(-70, -65))

            self.assertEqual(model.wires["W_ROUTE"].waypoints, [(-70.0, -65.0), (70.0, -65.0)])
            self.assertEqual(getattr(canvas, "wire_waypoint_items", {})[("W_ROUTE", 1)].pos(), QPointF(70, -65))
            points = canvas.wire_items["W_ROUTE"]._manhattan_points()
            for first, second in zip(points, points[1:]):
                self.assertTrue(
                    abs(first.x() - second.x()) < 0.1
                    or abs(first.y() - second.y()) < 0.1
                )
        finally:
            canvas.close()

    def test_wire_waypoint_drag_can_be_undone(self):
        app = get_app()
        model = CircuitModel()
        canvas = CircuitCanvas(model)
        canvas.resize(600, 400)
        canvas.show()
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
            model.add_wire(Wire("W_ROUTE", "R_001", "nt", "R_002", "nf", [(-70.0, -40.0), (70.0, -40.0)]))
            canvas.centerOn(0, 0)
            app.processEvents()

            handle = getattr(canvas, "wire_waypoint_items", {})[("W_ROUTE", 0)]
            start = canvas.mapFromScene(handle.scenePos())
            end = canvas.mapFromScene(QPointF(-70, -65))
            QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
            QTest.mouseMove(canvas.viewport(), end)
            QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
            app.processEvents()

            self.assertEqual(model.wires["W_ROUTE"].waypoints, [(-70.0, -65.0), (70.0, -65.0)])
            self.assertTrue(model.undo())
            self.assertEqual(model.wires["W_ROUTE"].waypoints, [(-70.0, -40.0), (70.0, -40.0)])
        finally:
            canvas.close()
            app.processEvents()

    def test_component_drag_reroutes_wire_without_waypoints_orthogonally(self):
        app = get_app()
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
            model.add_wire(Wire("W_ROUTE", "R_001", "nt", "R_002", "nf"))

            moving_item = canvas.component_items["R_001"]
            moving_item.setSelected(True)
            moving_item._drag_snapshot = model._snapshot()
            canvas._begin_component_drag()
            moving_item.setPos(QPointF(-100, 40))
            app.processEvents()

            wire = model.wires["W_ROUTE"]
            start_pos, end_pos = canvas._wire_endpoint_positions(wire)
            self.assertEqual(wire.waypoints, [(end_pos.x(), start_pos.y())])
            points = [start_pos, *[QPointF(x, y) for x, y in wire.waypoints], end_pos]
            for first, second in zip(points, points[1:]):
                self.assertTrue(
                    abs(first.x() - second.x()) < 0.1
                    or abs(first.y() - second.y()) < 0.1
                )
        finally:
            canvas.close()

    def test_component_drag_preserves_existing_route_by_adjusting_moved_endpoint_waypoint(self):
        app = get_app()
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
            model.add_wire(
                Wire(
                    "W_ROUTE",
                    "R_001",
                    "nt",
                    "R_002",
                    "nf",
                    [(-20.0, 0.0), (-20.0, -40.0), (70.0, -40.0)],
                )
            )

            moving_item = canvas.component_items["R_001"]
            moving_item.setSelected(True)
            moving_item._drag_snapshot = model._snapshot()
            canvas._begin_component_drag()
            moving_item.setPos(QPointF(-100, 40))
            app.processEvents()

            self.assertEqual(
                model.wires["W_ROUTE"].waypoints,
                [(-20.0, 40.0), (-20.0, -40.0), (70.0, -40.0)],
            )
        finally:
            canvas.close()

    def test_component_group_drag_moves_wire_waypoints_realtime_with_endpoints(self):
        app = get_app()
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
            model.add_wire(Wire("W_ROUTE", "R_001", "nt", "R_002", "nf", [(-70.0, -40.0), (70.0, -40.0)]))

            first_item = canvas.component_items["R_001"]
            second_item = canvas.component_items["R_002"]
            first_item.setSelected(True)
            second_item.setSelected(True)
            first_item._drag_snapshot = model._snapshot()
            canvas._begin_component_drag()
            first_item.setPos(QPointF(-80, 10))
            second_item.setPos(QPointF(120, 10))
            app.processEvents()

            self.assertEqual(model.wires["W_ROUTE"].waypoints, [(-50.0, -30.0), (90.0, -30.0)])
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
            canvas._handle_wire_left_click(QPointF(-30, 0))
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

    def test_wire_mode_can_start_on_empty_grid_and_commit_between_junctions(self):
        get_app()
        model = CircuitModel()
        canvas = CircuitCanvas(model)
        try:
            canvas.set_mode(CanvasMode.WIRE)

            canvas._handle_wire_left_click(QPointF(11, 11))

            self.assertIsNotNone(canvas._temp_line)
            self.assertEqual(canvas._temp_line.start_pos, QPointF(10, 10))
            self.assertEqual(len(model.components), 0)
            self.assertEqual(len(model.wires), 0)

            canvas._handle_wire_right_click(QPointF(43, 11))

            junctions = [
                comp for comp in model.components.values()
                if comp.comp_type == ComponentType.JUNCTION
            ]
            self.assertEqual(len(junctions), 2)
            self.assertEqual({(comp.x, comp.y) for comp in junctions}, {(10, 10), (45, 10)})
            self.assertEqual(len(model.wires), 1)
            wire = next(iter(model.wires.values()))
            self.assertEqual({wire.from_comp, wire.to_comp}, {junctions[0].comp_id, junctions[1].comp_id})
            self.assertEqual(wire.from_pin, "node")
            self.assertEqual(wire.to_pin, "node")
            self.assertEqual(wire.waypoints, [])
            self.assertIsNone(canvas._temp_line)
            self.assertEqual(canvas.mode, CanvasMode.WIRE)
        finally:
            canvas.close()

    def test_exiting_wire_mode_after_grid_start_discards_temporary_wire(self):
        get_app()
        model = CircuitModel()
        canvas = CircuitCanvas(model)
        try:
            canvas.set_mode(CanvasMode.WIRE)

            canvas._handle_wire_left_click(QPointF(11, 11))
            canvas._update_temp_wire(QPointF(43, 24))
            canvas.set_mode(CanvasMode.SELECT)

            self.assertIsNone(canvas._wiring_start)
            self.assertIsNone(canvas._temp_line)
            self.assertIsNone(canvas._temp_wire_node)
            self.assertEqual(len(model.components), 0)
            self.assertEqual(len(model.wires), 0)
        finally:
            canvas.close()

    def test_wire_mode_can_start_on_existing_wire_midpoint_without_splitting_until_commit(self):
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

            midpoint = QPointF(0, 0)
            end = canvas.component_items["R_003"].get_all_scene_pin_positions()["nf"]
            canvas._handle_wire_left_click(midpoint)

            self.assertIsNotNone(canvas._temp_line)
            self.assertIn("W_MAIN", model.wires)
            self.assertEqual(
                len([comp for comp in model.components.values() if comp.comp_type == ComponentType.JUNCTION]),
                0,
            )

            canvas._handle_wire_right_click(end)

            junctions = [
                comp for comp in model.components.values()
                if comp.comp_type == ComponentType.JUNCTION
            ]
            self.assertEqual(len(junctions), 1)
            self.assertEqual((junctions[0].x, junctions[0].y), (0, 0))
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

    def _build_subcircuit_packaging_fixture(self):
        model = CircuitModel()
        components = [
            ComponentInstance(
                comp_id="VS_001",
                comp_type=ComponentType.VOLTAGE_SOURCE,
                name="VS1",
                x=-220,
                y=0,
                pins=create_component_pins(ComponentType.VOLTAGE_SOURCE),
            ),
            ComponentInstance(
                comp_id="R_TAP",
                comp_type=ComponentType.RESISTOR,
                name="RTAP",
                x=-220,
                y=80,
                pins=create_component_pins(ComponentType.RESISTOR),
            ),
            ComponentInstance(
                comp_id="R_001",
                comp_type=ComponentType.RESISTOR,
                name="R1",
                x=-40,
                y=0,
                pins=create_component_pins(ComponentType.RESISTOR),
            ),
            ComponentInstance(
                comp_id="C_001",
                comp_type=ComponentType.CAPACITOR,
                name="C1",
                x=40,
                y=0,
                pins=create_component_pins(ComponentType.CAPACITOR),
            ),
            ComponentInstance(
                comp_id="GND_001",
                comp_type=ComponentType.GROUND,
                name="GND",
                x=220,
                y=0,
                pins=create_component_pins(ComponentType.GROUND),
            ),
        ]
        for comp in components:
            model.add_component(comp)
        for wire in [
            Wire("W_IN", "R_001", "nt", "C_001", "nf"),
            Wire("W_LEFT", "VS_001", "node_pos", "R_001", "nf"),
            Wire("W_LEFT_TAP", "R_TAP", "nt", "R_001", "nf"),
            Wire("W_RIGHT", "C_001", "nt", "GND_001", "gnd"),
            Wire("W_REF", "VS_001", "node_neg", "GND_001", "gnd"),
        ]:
            model.add_wire(wire)
        model._undo_stack.clear()
        model._redo_stack.clear()
        return model

    def _build_pass_through_subdefinition(self, name="CELL"):
        port_1 = ComponentInstance(
            comp_id="PORT_001",
            comp_type=ComponentType.SUBCIRCUIT_PORT,
            name="P1",
            x=-80,
            y=0,
            pins=create_component_pins(ComponentType.SUBCIRCUIT_PORT),
            params={"port_name": "P1"},
        )
        port_2 = ComponentInstance(
            comp_id="PORT_002",
            comp_type=ComponentType.SUBCIRCUIT_PORT,
            name="P2",
            x=80,
            y=0,
            pins=create_component_pins(ComponentType.SUBCIRCUIT_PORT),
            params={"port_name": "P2"},
        )
        resistor = ComponentInstance(
            comp_id="R_001",
            comp_type=ComponentType.RESISTOR,
            name="R1",
            x=0,
            y=0,
            pins=create_component_pins(ComponentType.RESISTOR),
            params={"R": 100.0},
        )
        return SubcircuitDefinition(
            name=name,
            components={
                port_1.comp_id: port_1,
                port_2.comp_id: port_2,
                resistor.comp_id: resistor,
            },
            wires={
                "W_P1": Wire("W_P1", "PORT_001", "node", "R_001", "nf"),
                "W_P2": Wire("W_P2", "R_001", "nt", "PORT_002", "node"),
            },
            ports=[
                SubcircuitPort("P1", "PORT_001", "node", "left"),
                SubcircuitPort("P2", "PORT_002", "node", "right"),
            ],
        )

    def _build_subcircuit_instance(self, comp_id, name, subdef):
        return ComponentInstance(
            comp_id=comp_id,
            comp_type=ComponentType.SUBCIRCUIT,
            name=name,
            x=0,
            y=0,
            params={"subcircuit_name": subdef.name},
            pins=[
                Pin(pin["name"], pin["local_x"], pin["local_y"])
                for pin in subdef.get_port_pins()
            ],
        )

    def test_subcircuit_packaging_creates_internal_port_nodes(self):
        port_type = getattr(ComponentType, "SUBCIRCUIT_PORT", None)
        self.assertIsNotNone(port_type)

        model = self._build_subcircuit_packaging_fixture()
        result = model.create_subcircuit_from_selection(["R_001", "C_001"], "FILTER")

        self.assertIsNotNone(result)
        sub_comp, subdef = result
        port_components = [
            comp for comp in subdef.components.values()
            if comp.comp_type == port_type
        ]
        self.assertEqual(len(port_components), 2)
        self.assertEqual(len(subdef.ports), 2)
        self.assertEqual(
            {pin.name for pin in sub_comp.pins},
            {port.port_name for port in subdef.ports},
        )

        for port in subdef.ports:
            port_comp = subdef.components[port.internal_comp_id]
            self.assertEqual(port_comp.comp_type, port_type)
            self.assertEqual(port.internal_pin_name, "node")
            self.assertTrue(
                any(
                    (
                        wire.from_comp == port_comp.comp_id
                        and wire.from_pin == "node"
                        and wire.to_comp in {"R_001", "C_001"}
                    )
                    or (
                        wire.to_comp == port_comp.comp_id
                        and wire.to_pin == "node"
                        and wire.from_comp in {"R_001", "C_001"}
                    )
                    for wire in subdef.wires.values()
                )
            )

        left_port_name = next(
            port.port_name
            for port in subdef.ports
            if any(
                wire.from_comp == port.internal_comp_id and wire.to_comp == "R_001"
                or wire.to_comp == port.internal_comp_id and wire.from_comp == "R_001"
                for wire in subdef.wires.values()
            )
        )
        external_left_wires = [
            wire for wire in model.wires.values()
            if (
                wire.from_comp == sub_comp.comp_id
                and wire.from_pin == left_port_name
            )
            or (
                wire.to_comp == sub_comp.comp_id
                and wire.to_pin == left_port_name
            )
        ]
        self.assertEqual(len(external_left_wires), 2)

    def test_subcircuit_flattening_maps_external_ports_to_internal_port_nodes(self):
        port_type = getattr(ComponentType, "SUBCIRCUIT_PORT", None)
        self.assertIsNotNone(port_type)

        model = self._build_subcircuit_packaging_fixture()
        sub_comp, subdef = model.create_subcircuit_from_selection(
            ["R_001", "C_001"],
            "FILTER",
        )

        flat = SolverBuilder()._flatten_subcircuits(model)
        node_map = flat.assign_node_ids()
        prefix = f"{sub_comp.comp_id}__"

        self.assertNotIn(ComponentType.SUBCIRCUIT, {c.comp_type for c in flat.components.values()})
        self.assertIn(port_type, {c.comp_type for c in flat.components.values()})
        self.assertEqual(
            node_map[("VS_001", "node_pos")],
            node_map[(f"{prefix}R_001", "nf")],
        )
        self.assertEqual(
            node_map[("R_TAP", "nt")],
            node_map[(f"{prefix}R_001", "nf")],
        )
        self.assertEqual(
            node_map[("GND_001", "gnd")],
            node_map[(f"{prefix}C_001", "nt")],
        )

    def test_subcircuit_packaging_connects_all_internal_pins_on_boundary_node(self):
        model = CircuitModel()
        for comp in [
            ComponentInstance(
                comp_id="J_EXT",
                comp_type=ComponentType.JUNCTION,
                name="J",
                x=-120,
                y=0,
                pins=create_component_pins(ComponentType.JUNCTION),
            ),
            ComponentInstance(
                comp_id="R_001",
                comp_type=ComponentType.RESISTOR,
                name="R1",
                x=-20,
                y=-40,
                pins=create_component_pins(ComponentType.RESISTOR),
            ),
            ComponentInstance(
                comp_id="R_002",
                comp_type=ComponentType.RESISTOR,
                name="R2",
                x=-20,
                y=40,
                pins=create_component_pins(ComponentType.RESISTOR),
            ),
            ComponentInstance(
                comp_id="GND_001",
                comp_type=ComponentType.GROUND,
                name="GND",
                x=120,
                y=0,
                pins=create_component_pins(ComponentType.GROUND),
            ),
        ]:
            model.add_component(comp)

        for wire in [
            Wire("W_J_R1", "J_EXT", "node", "R_001", "nf"),
            Wire("W_J_R2", "J_EXT", "node", "R_002", "nf"),
            Wire("W_R1_GND", "R_001", "nt", "GND_001", "gnd"),
            Wire("W_R2_GND", "R_002", "nt", "GND_001", "gnd"),
        ]:
            model.add_wire(wire)
        model._undo_stack.clear()
        model._redo_stack.clear()

        sub_comp, subdef = model.create_subcircuit_from_selection(
            ["R_001", "R_002"],
            "PARALLEL",
        )

        port_internal_pins = []
        for port in subdef.ports:
            pins = set()
            for wire in subdef.wires.values():
                if wire.from_comp == port.internal_comp_id:
                    pins.add((wire.to_comp, wire.to_pin))
                if wire.to_comp == port.internal_comp_id:
                    pins.add((wire.from_comp, wire.from_pin))
            port_internal_pins.append(pins)

        self.assertIn({("R_001", "nf"), ("R_002", "nf")}, port_internal_pins)
        self.assertIn({("R_001", "nt"), ("R_002", "nt")}, port_internal_pins)

        top_level_sub_wires = [
            wire for wire in model.wires.values()
            if wire.from_comp == sub_comp.comp_id or wire.to_comp == sub_comp.comp_id
        ]
        self.assertEqual(len(top_level_sub_wires), 2)

    def test_subcircuit_flattening_preserves_direct_subcircuit_to_subcircuit_connection(self):
        model = CircuitModel()
        subdef = self._build_pass_through_subdefinition("CELL")
        model.subcircuit_defs[subdef.name] = subdef
        model.components["S1"] = self._build_subcircuit_instance("S1", "S1", subdef)
        model.components["S2"] = self._build_subcircuit_instance("S2", "S2", subdef)
        model.wires["W_SUBS"] = Wire("W_SUBS", "S1", "P2", "S2", "P1")

        flat = SolverBuilder()._flatten_subcircuits(model)
        node_map = flat.assign_node_ids()

        self.assertNotIn(
            ComponentType.SUBCIRCUIT,
            {comp.comp_type for comp in flat.components.values()},
        )
        self.assertEqual(
            node_map[("S1__PORT_002", "node")],
            node_map[("S2__PORT_001", "node")],
        )

    def test_subcircuit_flattening_recursively_expands_nested_subcircuits(self):
        model = CircuitModel()
        inner = self._build_pass_through_subdefinition("INNER")
        inner_inst = self._build_subcircuit_instance("INNER_INST", "Inner", inner)
        port_1 = ComponentInstance(
            comp_id="PORT_001",
            comp_type=ComponentType.SUBCIRCUIT_PORT,
            name="P1",
            x=-120,
            y=0,
            pins=create_component_pins(ComponentType.SUBCIRCUIT_PORT),
            params={"port_name": "P1"},
        )
        port_2 = ComponentInstance(
            comp_id="PORT_002",
            comp_type=ComponentType.SUBCIRCUIT_PORT,
            name="P2",
            x=120,
            y=0,
            pins=create_component_pins(ComponentType.SUBCIRCUIT_PORT),
            params={"port_name": "P2"},
        )
        outer = SubcircuitDefinition(
            name="OUTER",
            components={
                port_1.comp_id: port_1,
                port_2.comp_id: port_2,
                inner_inst.comp_id: inner_inst,
            },
            wires={
                "W_OUT_IN": Wire("W_OUT_IN", "PORT_001", "node", "INNER_INST", "P1"),
                "W_IN_OUT": Wire("W_IN_OUT", "INNER_INST", "P2", "PORT_002", "node"),
            },
            ports=[
                SubcircuitPort("P1", "PORT_001", "node", "left"),
                SubcircuitPort("P2", "PORT_002", "node", "right"),
            ],
        )
        model.subcircuit_defs = {"INNER": inner, "OUTER": outer}
        model.components["OUTER_INST"] = self._build_subcircuit_instance(
            "OUTER_INST",
            "Outer",
            outer,
        )

        flat = SolverBuilder()._flatten_subcircuits(model)
        node_map = flat.assign_node_ids()

        self.assertNotIn(
            ComponentType.SUBCIRCUIT,
            {comp.comp_type for comp in flat.components.values()},
        )
        self.assertIn("OUTER_INST__INNER_INST__R_001", flat.components)
        self.assertEqual(
            node_map[("OUTER_INST__PORT_001", "node")],
            node_map[("OUTER_INST__INNER_INST__PORT_001", "node")],
        )
        self.assertEqual(
            node_map[("OUTER_INST__INNER_INST__PORT_002", "node")],
            node_map[("OUTER_INST__PORT_002", "node")],
        )

    def test_subcircuit_exposed_params_survive_serialization(self):
        subdef = SubcircuitDefinition(
            name="FILTER",
            exposed_params={"R_001.R": "R_filter"},
        )

        restored = SubcircuitDefinition.from_dict(subdef.to_dict())

        self.assertEqual(restored.exposed_params, {"R_001.R": "R_filter"})

    def test_subcircuit_instances_can_override_exposed_electrical_params(self):
        model = CircuitModel()
        subdef = self._build_pass_through_subdefinition("FILTER")
        subdef.exposed_params = {"R_001.R": "R_filter"}
        model.subcircuit_defs[subdef.name] = subdef

        s1 = self._build_subcircuit_instance("S1", "S1", subdef)
        s1.params["param_overrides"] = {"R_filter": 10.0}
        s2 = self._build_subcircuit_instance("S2", "S2", subdef)
        s2.params["param_overrides"] = {"R_filter": 20.0}
        model.components[s1.comp_id] = s1
        model.components[s2.comp_id] = s2

        flat = SolverBuilder()._flatten_subcircuits(model)

        self.assertEqual(flat.components["S1__R_001"].params["R"], 10.0)
        self.assertEqual(flat.components["S2__R_001"].params["R"], 20.0)

    def test_clear_removes_subcircuit_defs(self):
        model = CircuitModel()
        model.subcircuit_defs["FILTER"] = self._build_pass_through_subdefinition("FILTER")
        model.add_component(ComponentInstance(
            comp_id="R_001",
            comp_type=ComponentType.RESISTOR,
            name="R1",
            x=0,
            y=0,
            pins=create_component_pins(ComponentType.RESISTOR),
        ))

        model.clear()

        self.assertEqual(model.components, {})
        self.assertEqual(model.wires, {})
        self.assertEqual(model.subcircuit_defs, {})
        self.assertEqual(model.to_dict()["subcircuit_defs"], {})

    def test_rebuild_id_counters_includes_subcircuit_components_and_wires(self):
        model = CircuitModel()
        subdef = self._build_pass_through_subdefinition("FILTER")
        subdef.components["R_009"] = ComponentInstance(
            comp_id="R_009",
            comp_type=ComponentType.RESISTOR,
            name="R9",
            x=0,
            y=0,
            pins=create_component_pins(ComponentType.RESISTOR),
        )
        subdef.wires["W_012"] = Wire("W_012", "PORT_001", "node", "R_009", "nf")
        model.subcircuit_defs[subdef.name] = subdef

        model._rebuild_id_counters()

        self.assertEqual(model.generate_component_id(ComponentType.RESISTOR), "R_010")
        self.assertEqual(model._id_counters["W"], 12)

    def test_detect_direct_circular_subcircuit_reference(self):
        model = CircuitModel()
        subdef = self._build_pass_through_subdefinition("A")
        subdef.components["A_INST"] = self._build_subcircuit_instance("A_INST", "A", subdef)
        model.subcircuit_defs["A"] = subdef
        model.components["TOP_A"] = self._build_subcircuit_instance("TOP_A", "TopA", subdef)

        with self.assertRaisesRegex(ValueError, "A -> A"):
            SolverBuilder()._flatten_subcircuits(model)

    def test_detect_indirect_circular_subcircuit_reference(self):
        model = CircuitModel()
        sub_a = self._build_pass_through_subdefinition("A")
        sub_b = self._build_pass_through_subdefinition("B")
        sub_a.components["B_INST"] = self._build_subcircuit_instance("B_INST", "B", sub_b)
        sub_b.components["A_INST"] = self._build_subcircuit_instance("A_INST", "A", sub_a)
        model.subcircuit_defs = {"A": sub_a, "B": sub_b}
        model.components["TOP_A"] = self._build_subcircuit_instance("TOP_A", "TopA", sub_a)

        with self.assertRaisesRegex(ValueError, "A -> B -> A"):
            SolverBuilder()._flatten_subcircuits(model)

    def test_missing_subcircuit_definition_raises(self):
        model = CircuitModel()
        model.components["SUB_001"] = ComponentInstance(
            comp_id="SUB_001",
            comp_type=ComponentType.SUBCIRCUIT,
            name="BrokenSub",
            x=0,
            y=0,
            params={"subcircuit_name": "MISSING"},
            pins=[Pin("P1", -40, 0)],
        )

        with self.assertRaisesRegex(ValueError, "SUB_001.*MISSING"):
            SolverBuilder()._flatten_subcircuits(model)

    def test_validate_duplicate_port_names(self):
        model = CircuitModel()
        subdef = self._build_pass_through_subdefinition("FILTER")
        subdef.ports[1].port_name = "P1"
        model.subcircuit_defs[subdef.name] = subdef

        result = model.validate_subcircuit_definition("FILTER")

        self.assertTrue(result.has_errors)
        self.assertIn("duplicate_port_name", {issue.code for issue in result.issues})

    def test_validate_port_references_missing_component_and_pin(self):
        model = CircuitModel()
        subdef = self._build_pass_through_subdefinition("FILTER")
        subdef.ports[0].internal_comp_id = "MISSING"
        subdef.ports[1].internal_pin_name = "missing_pin"
        model.subcircuit_defs[subdef.name] = subdef

        result = model.validate_subcircuit_definition("FILTER")

        self.assertTrue(result.has_errors)
        self.assertIn("port_missing_component", {issue.code for issue in result.issues})
        self.assertIn("port_missing_pin", {issue.code for issue in result.issues})

    def test_validate_internal_wire_references_missing_component_and_pin(self):
        model = CircuitModel()
        subdef = self._build_pass_through_subdefinition("FILTER")
        subdef.wires["W_BAD_COMP"] = Wire("W_BAD_COMP", "MISSING", "node", "R_001", "nf")
        subdef.wires["W_BAD_PIN"] = Wire("W_BAD_PIN", "R_001", "missing", "PORT_001", "node")
        model.subcircuit_defs[subdef.name] = subdef

        result = model.validate_subcircuit_definition("FILTER")

        self.assertTrue(result.has_errors)
        self.assertIn("wire_missing_component", {issue.code for issue in result.issues})
        self.assertIn("wire_missing_pin", {issue.code for issue in result.issues})

    def test_validate_floating_internal_port_warning(self):
        model = CircuitModel()
        subdef = self._build_pass_through_subdefinition("FILTER")
        subdef.wires = {
            wid: wire for wid, wire in subdef.wires.items()
            if wire.from_comp != "PORT_001" and wire.to_comp != "PORT_001"
        }
        model.subcircuit_defs[subdef.name] = subdef

        result = model.validate_subcircuit_definition("FILTER")

        self.assertTrue(result.has_warnings)
        self.assertIn("floating_internal_port", {issue.code for issue in result.issues})

    def test_validate_subcircuit_instance_port_mismatch(self):
        model = CircuitModel()
        subdef = self._build_pass_through_subdefinition("FILTER")
        model.subcircuit_defs[subdef.name] = subdef
        instance = self._build_subcircuit_instance("SUB_001", "Filter", subdef)
        instance.pins = [Pin("P1", -40, 0)]
        model.components[instance.comp_id] = instance

        result = model.validate_subcircuit_instances()

        self.assertTrue(result.has_errors)
        self.assertIn("instance_ports_mismatch", {issue.code for issue in result.issues})

    def test_rename_subcircuit_port_updates_instance_pins_and_wires(self):
        model = CircuitModel()
        subdef = self._build_pass_through_subdefinition("FILTER")
        model.subcircuit_defs[subdef.name] = subdef
        s1 = self._build_subcircuit_instance("S1", "S1", subdef)
        s2 = self._build_subcircuit_instance("S2", "S2", subdef)
        model.components[s1.comp_id] = s1
        model.components[s2.comp_id] = s2
        model.wires["W_EXT"] = Wire("W_EXT", "S1", "P1", "S2", "P1")

        model.rename_subcircuit_port("FILTER", "P1", "IN")

        self.assertEqual({pin.name for pin in model.components["S1"].pins}, {"IN", "P2"})
        self.assertEqual({pin.name for pin in model.components["S2"].pins}, {"IN", "P2"})
        self.assertEqual(model.wires["W_EXT"].from_pin, "IN")
        self.assertEqual(model.wires["W_EXT"].to_pin, "IN")
        self.assertEqual(subdef.ports[0].port_name, "IN")

    def test_rename_subcircuit_port_updates_nested_instance_wires(self):
        model = CircuitModel()
        child = self._build_pass_through_subdefinition("CHILD")
        parent = self._build_pass_through_subdefinition("PARENT")
        child_inst = self._build_subcircuit_instance("CHILD_INST", "Child", child)
        parent.components[child_inst.comp_id] = child_inst
        parent.wires["W_CHILD"] = Wire("W_CHILD", "PORT_001", "node", "CHILD_INST", "P1")
        model.subcircuit_defs = {"CHILD": child, "PARENT": parent}

        model.rename_subcircuit_port("CHILD", "P1", "IN")

        nested = model.subcircuit_defs["PARENT"].components["CHILD_INST"]
        self.assertIn("IN", {pin.name for pin in nested.pins})
        self.assertEqual(model.subcircuit_defs["PARENT"].wires["W_CHILD"].to_pin, "IN")

    def test_update_port_side_repositions_pin(self):
        model = CircuitModel()
        subdef = self._build_pass_through_subdefinition("FILTER")
        model.subcircuit_defs[subdef.name] = subdef
        inst = self._build_subcircuit_instance("SUB_001", "Filter", subdef)
        model.components[inst.comp_id] = inst

        model.update_subcircuit_port_side("FILTER", "P1", "right")

        p1 = next(pin for pin in model.components["SUB_001"].pins if pin.name == "P1")
        self.assertEqual(p1.local_x, 40)

    def test_update_port_order_changes_display_order_and_persists(self):
        model = CircuitModel()
        subdef = self._build_pass_through_subdefinition("FILTER")
        subdef.ports[0].side = "left"
        subdef.ports[1].side = "left"
        model.subcircuit_defs[subdef.name] = subdef

        model.update_subcircuit_port_order("FILTER", "P1", 20)
        model.update_subcircuit_port_order("FILTER", "P2", 10)
        pins = subdef.get_port_pins()

        p2 = next(pin for pin in pins if pin["name"] == "P2")
        p1 = next(pin for pin in pins if pin["name"] == "P1")
        self.assertLess(p2["local_y"], p1["local_y"])

        restored = SubcircuitDefinition.from_dict(subdef.to_dict())
        self.assertEqual(
            {port.port_name: port.order for port in restored.ports},
            {"P1": 20, "P2": 10},
        )

    def test_subcircuit_edit_mode_places_and_wires_inside_definition(self):
        get_app()
        port_type = getattr(ComponentType, "SUBCIRCUIT_PORT", None)
        self.assertIsNotNone(port_type)

        model = self._build_subcircuit_packaging_fixture()
        model.create_subcircuit_from_selection(["R_001", "C_001"], "FILTER")
        subdef = model.subcircuit_defs["FILTER"]
        canvas = CircuitCanvas(model)
        try:
            canvas._enter_subcircuit("FILTER")
            before_top_level_ids = set(model.components)

            canvas._placing_type = ComponentType.RESISTOR
            canvas._placing_params = {}
            canvas._place_component(QPointF(140, 0))

            new_ids = set(subdef.components) - {"R_001", "C_001", "PORT_001", "PORT_002"}
            self.assertEqual(len(new_ids), 1)
            new_id = next(iter(new_ids))
            self.assertEqual(set(model.components), before_top_level_ids)

            port_id = next(
                comp.comp_id for comp in subdef.components.values()
                if comp.comp_type == port_type
            )
            canvas._add_wire_between(new_id, "nf", port_id, "node")

            self.assertTrue(
                any(
                    wire.from_comp == new_id and wire.to_comp == port_id
                    or wire.from_comp == port_id and wire.to_comp == new_id
                    for wire in subdef.wires.values()
                )
            )
            self.assertFalse(
                any(
                    wire.from_comp == new_id or wire.to_comp == new_id
                    for wire in model.wires.values()
                )
            )
        finally:
            canvas.close()

    def test_subcircuit_edit_mode_refreshes_internal_wires(self):
        get_app()
        model = self._build_subcircuit_packaging_fixture()
        model.create_subcircuit_from_selection(["R_001", "C_001"], "FILTER")
        canvas = CircuitCanvas(model)
        try:
            canvas._enter_subcircuit("FILTER")
            expected_wire_count = len(model.subcircuit_defs["FILTER"].wires)

            canvas._refresh_wires()

            self.assertEqual(len(canvas.wire_items), expected_wire_count)
        finally:
            canvas.close()

    def test_subcircuit_edit_mode_wire_midpoint_junction_stays_inside_definition(self):
        get_app()
        model = self._build_subcircuit_packaging_fixture()
        model.create_subcircuit_from_selection(["R_001", "C_001"], "FILTER")
        subdef = model.subcircuit_defs["FILTER"]
        subdef.components["R_001"].x = -100
        subdef.components["C_001"].x = 100
        tap = ComponentInstance(
            comp_id="R_IN_TAP",
            comp_type=ComponentType.RESISTOR,
            name="Rtap",
            x=0,
            y=90,
            pins=create_component_pins(ComponentType.RESISTOR),
        )
        subdef.components[tap.comp_id] = tap

        canvas = CircuitCanvas(model)
        try:
            canvas._enter_subcircuit("FILTER")
            canvas.set_mode(CanvasMode.WIRE)

            start = canvas.component_items["R_IN_TAP"].get_all_scene_pin_positions()["nf"]
            canvas._handle_wire_left_click(start)
            canvas._handle_wire_left_click(QPointF(-30, 0))
            canvas._handle_wire_right_click(QPointF(0, 0))

            junction_type = getattr(ComponentType, "JUNCTION")
            self.assertFalse(
                any(comp.comp_type == junction_type for comp in model.components.values())
            )
            junctions = [
                comp for comp in subdef.components.values()
                if comp.comp_type == junction_type
            ]
            self.assertEqual(len(junctions), 1)
            self.assertNotIn("W_IN", subdef.wires)
            self.assertGreaterEqual(
                len([
                    wire for wire in subdef.wires.values()
                    if wire.from_comp == junctions[0].comp_id or wire.to_comp == junctions[0].comp_id
                ]),
                3,
            )
        finally:
            canvas.close()

    def test_code_generator_flattens_subcircuits_through_port_nodes(self):
        model = self._build_subcircuit_packaging_fixture()
        sub_comp, _ = model.create_subcircuit_from_selection(["R_001", "C_001"], "FILTER")

        code = generate_code(model)

        self.assertIn(f'solver.add_R("{sub_comp.comp_id}__R1"', code)
        self.assertIn(f'solver.add_C("{sub_comp.comp_id}__C1"', code)
        self.assertNotIn("add_subcircuit", code)
        self.assertNotIn("PORT_001", code)

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

    def test_custom_source_expression_uses_restricted_eval(self):
        builder = SolverBuilder()

        func = builder._build_source_func({
            "mode": "custom",
            "expression": "lambda t: sin(t) + np.cos(t)",
        })

        self.assertAlmostEqual(func(0.0), 1.0)
        with self.assertRaises(ValueError):
            builder._build_source_func({
                "mode": "custom",
                "expression": "lambda t: ().__class__.__mro__",
            })

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

    def test_user_voltage_probe_prevents_duplicate_auto_probe(self):
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
        model.add_component(r1)
        model.add_component(gnd)
        model.add_wire(Wire("W_GND", "R_001", "nt", "GND_001", "gnd"))

        node_id = model.assign_node_ids()[("R_001", "nf")]
        model.probes.append(ProbeConfig(
            probe_id="USER_V",
            probe_type="voltage",
            node_pos=node_id,
            node_neg=0,
        ))
        model.settings.auto_voltage_probes = True

        auto_ids = {p.probe_id for p in model.get_auto_voltage_probes()}

        self.assertNotIn(f"auto_V_n{node_id}", auto_ids)

    def test_auto_voltage_probe_setting_defaults_and_round_trips(self):
        settings = CircuitModel().settings

        self.assertTrue(hasattr(settings, "auto_voltage_probes"))
        self.assertFalse(settings.auto_voltage_probes)

        serialized = settings.to_dict()
        self.assertIn("auto_voltage_probes", serialized)
        self.assertFalse(serialized["auto_voltage_probes"])
        self.assertFalse(SimSettings.from_dict({}).auto_voltage_probes)
        self.assertTrue(
            SimSettings.from_dict({"auto_voltage_probes": True}).auto_voltage_probes
        )

    def test_auto_voltage_probe_generation_uses_dedicated_setting(self):
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
            params={"probe_type": "voltage_ground", "unit": "kV"},
            pins=create_component_pins(ComponentType.PROBE),
        )

        for comp in (r1, c1, gnd, probe):
            model.add_component(comp)
        model.add_wire(Wire("W_PROBE", "PRB_001", "sense", "R_001", "nf"))
        model.add_wire(Wire("W_GND", "R_001", "nt", "GND_001", "gnd"))

        node_map = model.assign_node_ids()
        explicit_node = node_map[("R_001", "nf")]
        uncovered_node = node_map[("C_001", "nf")]

        probe_ids = {p.probe_id for p in model.get_auto_voltage_probes()}

        self.assertIn(f"PRB1_V_n{explicit_node}", probe_ids)
        self.assertNotIn(f"auto_V_n{uncovered_node}", probe_ids)

        model.update_settings(auto_voltage_probes=True)
        probe_ids = {p.probe_id for p in model.get_auto_voltage_probes()}
        self.assertIn(f"auto_V_n{uncovered_node}", probe_ids)

        model.update_settings(result_mode="full")
        probe_ids = {p.probe_id for p in model.get_auto_voltage_probes()}
        self.assertIn(f"auto_V_n{uncovered_node}", probe_ids)

    def test_simulation_config_auto_probe_checkbox_updates_setting_only(self):
        app = get_app()
        model = CircuitModel()
        panel = main_window_module.SimulationConfigPanel(model)
        try:
            self.assertTrue(hasattr(panel, "auto_vprobe_check"))
            self.assertFalse(panel.auto_vprobe_check.isChecked())

            original_result_mode = model.settings.result_mode
            panel.auto_vprobe_check.setChecked(True)

            self.assertTrue(model.settings.auto_voltage_probes)
            self.assertEqual(model.settings.result_mode, original_result_mode)

            model.settings.auto_voltage_probes = False
            panel.sync_from_model()
            self.assertFalse(panel.auto_vprobe_check.isChecked())
        finally:
            panel.close()
            app.processEvents()

    def test_probe_panel_auto_probe_checkbox_updates_setting_only(self):
        app = get_app()
        model = CircuitModel()
        model.update_settings(result_mode="full")
        panel = ProbePanel(model)
        try:
            self.assertFalse(panel.auto_probe_check.isChecked())

            panel.auto_probe_check.setChecked(True)

            self.assertTrue(getattr(model.settings, "auto_voltage_probes", False))
            self.assertEqual(model.settings.result_mode, "full")

            panel.auto_probe_check.setChecked(False)

            self.assertFalse(model.settings.auto_voltage_probes)
            self.assertEqual(model.settings.result_mode, "full")
        finally:
            panel.close()
            app.processEvents()

    def test_model_tracks_selected_components(self):
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
            x=80,
            y=0,
            pins=create_component_pins(ComponentType.CAPACITOR),
        )
        model.add_component(r1)
        model.add_component(c1)

        model.select_component("R_001")
        self.assertEqual([c.comp_id for c in model.get_selected_components()], ["R_001"])

        model.select_components(["R_001", "C_001", "MISSING"])
        self.assertEqual(
            [c.comp_id for c in model.get_selected_components()],
            ["R_001", "C_001"],
        )

        model.clear_selection()
        self.assertEqual(model.get_selected_components(), [])

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

    def test_sim_runner_uses_model_snapshot_copy(self):
        model = CircuitModel()
        model.add_component(ComponentInstance(
            comp_id="R_001",
            comp_type=ComponentType.RESISTOR,
            name="R1",
            x=0,
            y=0,
            pins=create_component_pins(ComponentType.RESISTOR),
        ))

        runner = SimulationRunner(model)
        runner.model.components["R_001"].x = 123

        self.assertIsNot(runner.model, model)
        self.assertEqual(model.components["R_001"].x, 0)

    def test_solver_builder_has_no_dead_wire_type_assignment(self):
        with open("core/solver_builder.py", "r", encoding="utf-8") as f:
            source = f.read()

        self.assertNotIn("type(flat.wires.get", source)

    def test_subcircuit_port_symbol_draws_label(self):
        get_app()
        image = QImage(96, 64, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        try:
            port = ComponentInstance(
                comp_id="PORT_001",
                comp_type=ComponentType.SUBCIRCUIT_PORT,
                name="IN",
                x=0,
                y=0,
                pins=[],
            )

            self.assertTrue(draw_component_symbol(painter, port))
        finally:
            painter.end()


if __name__ == "__main__":
    unittest.main()
