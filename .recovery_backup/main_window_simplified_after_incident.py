"""Main window for the EMTP GUI.

This module keeps the GUI shell intentionally compact: component palette,
canvas, property editor, bottom output tabs, and the run/validation controls
that the rest of the application expects.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QSpinBox,
    QStatusBar,
    QTabWidget,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QPlainTextEdit,
    QDialog,
)

from core.code_generator import generate_code
from core.file_io import export_python_code, load_project, save_project
from core.lcp_config import get_lcp_ohl_conductor_count
from core.sim_runner import SimulationRunner
from models.circuit_model import CircuitModel, ComponentInstance, ComponentType
from models.component_lib import COMPONENT_REGISTRY, create_component_pins, get_default_params
from ui.circuit_canvas import CanvasMode, CircuitCanvas
from ui.scientific_spin_box import ScientificSpinBox
from ui.statistics_panel import StatisticsPanel
from ui.validation_panel import ValidationPanel


class ComponentPalette(QWidget):
    """Left-side component library."""

    def __init__(self, canvas: CircuitCanvas, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self._setup_ui()

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self._section(layout, "基础元件")
        self._button(layout, "电阻 (R)", ComponentType.RESISTOR, "#ef4444")
        self._button(layout, "电感 (L)", ComponentType.INDUCTOR, "#3b82f6")
        self._button(layout, "电容 (C)", ComponentType.CAPACITOR, "#22c55e")
        self._button(layout, "串联RL (SRL)", ComponentType.SERIES_RL, "#8b5cf6")
        self._button(layout, "开关 (SW)", ComponentType.SWITCH, "#f59e0b")

        self._section(layout, "电源")
        self._button(layout, "电压源 (VS)", ComponentType.VOLTAGE_SOURCE, "#dc2626")
        self._button(layout, "电流源 (IS)", ComponentType.CURRENT_SOURCE, "#2563eb")

        self._section(layout, "非线性元件")
        self._button(layout, "MOA避雷器", ComponentType.MOA, "#7c3aed")
        self._button(layout, "LPM绝缘子", ComponentType.LPM, "#f97316")

        self._section(layout, "传输线")
        self._button(layout, "Bergeron", ComponentType.BERGERON, "#0891b2")
        self._button(layout, "ULM", ComponentType.ULM, "#0891b2")
        self._button(layout, "LCP架空线", ComponentType.LCP_OHL, "#0d9488")
        self._button(layout, "LCP单芯电缆", ComponentType.LCP_SINGLE_CABLE, "#0d9488")
        self._button(layout, "LCP三芯电缆", ComponentType.LCP_THREE_CABLE, "#0d9488")

        self._section(layout, "变压器")
        self._button(layout, "UMEC变压器", ComponentType.UMEC_TRANSFORMER, "#6366f1")

        self._section(layout, "接地")
        self._button(layout, "接地 (GND)", ComponentType.GROUND, "#1e2a3a")

        self._section(layout, "测量")
        self._button(
            layout,
            "对地电压探针",
            ComponentType.PROBE,
            "#2563eb",
            {"probe_type": "voltage_ground", "unit": "kV"},
        )
        self._button(
            layout,
            "两节点电压探针",
            ComponentType.PROBE,
            "#2563eb",
            {"probe_type": "voltage_between", "unit": "kV"},
        )
        self._button(
            layout,
            "电流探针",
            ComponentType.PROBE,
            "#2563eb",
            {"probe_type": "branch_current", "unit": "A"},
        )

        layout.addStretch()
        scroll.setWidget(content)

    def _section(self, layout: QVBoxLayout, text: str):
        label = QLabel(text)
        label.setStyleSheet("color:#64748b;font-size:11px;margin-top:8px;")
        layout.addWidget(label)

    def _button(
        self,
        layout: QVBoxLayout,
        text: str,
        comp_type: ComponentType,
        color: str,
        default_params: Optional[Dict[str, Any]] = None,
    ):
        button = QPushButton(text)
        button.setStyleSheet(
            f"QPushButton{{background:{color}15;color:{color};border:1px solid {color}40;"
            "border-radius:4px;padding:6px 8px;text-align:left;font-size:12px;}}"
            f"QPushButton:hover{{background:{color}30;border-color:{color};}}"
        )
        button.clicked.connect(
            lambda _=False, ct=comp_type, params=default_params: self.canvas.set_placing_type(ct, params)
        )
        layout.addWidget(button)


class PropertyPanel(QWidget):
    """Right-side component property editor."""

    def __init__(self, model: CircuitModel, parent=None):
        super().__init__(parent)
        self.model = model
        self._current_comp_id: Optional[str] = None
        self._params_layout = QVBoxLayout()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self.info_label = QLabel("选择元件查看属性")
        self.info_label.setStyleSheet("color:#64748b;font-style:italic;")
        layout.addWidget(self.info_label)
        layout.addLayout(self._params_layout)
        layout.addStretch()

    def show_component(self, comp_id: str):
        self._clear_params()
        self._current_comp_id = comp_id
        comp = self.model.components.get(comp_id)
        if comp is None:
            self.info_label.setText("选择元件查看属性")
            return

        self.info_label.setText(f"{comp.name} ({comp.comp_type.value})")
        self._add_name_editor(comp)
        for param_name, value in comp.params.items():
            self._add_param_editor(param_name, value)

    def _clear_params(self):
        while self._params_layout.count():
            item = self._params_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def _add_name_editor(self, comp: ComponentInstance):
        form = QFormLayout()
        edit = QLineEdit(comp.name)
        edit.textChanged.connect(lambda text: self._on_param_changed("name", text))
        form.addRow("名称:", edit)
        self._params_layout.addLayout(form)

    def _add_param_editor(self, param_name: str, value: Any):
        form = QFormLayout()
        editor: QWidget
        if isinstance(value, bool):
            checkbox = QCheckBox()
            checkbox.setChecked(value)
            checkbox.toggled.connect(lambda checked, p=param_name: self._on_param_changed(p, checked))
            editor = checkbox
        elif param_name in {"probe_type", "wtype1", "wtype2"}:
            combo = QComboBox()
            if param_name == "probe_type":
                combo.addItems(["voltage_ground", "voltage_between", "branch_current"])
            else:
                combo.addItems(["Y_gnd", "Y", "Delta"])
            combo.setCurrentText(str(value))
            combo.currentTextChanged.connect(lambda text, p=param_name: self._on_param_changed(p, text))
            editor = combo
        elif isinstance(value, int):
            spin = QSpinBox()
            spin.setRange(-1_000_000, 1_000_000)
            spin.setValue(value)
            spin.valueChanged.connect(lambda val, p=param_name: self._on_param_changed(p, val))
            editor = spin
        elif isinstance(value, float):
            spin = ScientificSpinBox()
            spin.setValue(value)
            spin.valueChanged.connect(lambda val, p=param_name: self._on_param_changed(p, val))
            editor = spin
        else:
            edit = QLineEdit(str(value))
            edit.textChanged.connect(lambda text, p=param_name: self._on_param_changed(p, text))
            editor = edit
        form.addRow(f"{param_name}:", editor)
        self._params_layout.addLayout(form)

    def _on_param_changed(self, param_name: str, value):
        if not self._current_comp_id or self._current_comp_id not in self.model.components:
            return
        comp = self.model.components[self._current_comp_id]
        if param_name == "name":
            self.model._save_undo_state()
            comp.name = value
            self.model._notify("params_updated")
            return
        if param_name in {"n_phases", "n_cables", "probe_type", "wtype1", "wtype2"}:
            self.model._save_undo_state()
            comp.params[param_name] = value
            self._rebuild_component_pins(comp)
            self.model._notify("params_updated")
            return
        self.model.update_params(self._current_comp_id, {param_name: value})

    def _remove_wires_with_invalid_pins(self, comp: ComponentInstance) -> int:
        valid_pins = {pin.name for pin in comp.pins}
        wires_to_remove = [
            wire_id
            for wire_id, wire in self.model.wires.items()
            if (
                wire.from_comp == comp.comp_id and wire.from_pin not in valid_pins
            ) or (
                wire.to_comp == comp.comp_id and wire.to_pin not in valid_pins
            )
        ]
        for wire_id in wires_to_remove:
            del self.model.wires[wire_id]
        return len(wires_to_remove)

    def _rebuild_component_pins(self, comp: ComponentInstance) -> int:
        probe_type = comp.params.get("probe_type") if comp.comp_type == ComponentType.PROBE else None
        pin_count = int(comp.params.get("n_phases", 3) or 3)
        if comp.comp_type == ComponentType.LCP_SINGLE_CABLE:
            pin_count = int(comp.params.get("n_cables", 1) or 1)
        elif comp.comp_type == ComponentType.LCP_OHL:
            pin_count = get_lcp_ohl_conductor_count(comp.params)
        comp.pins = create_component_pins(
            comp.comp_type,
            pin_count,
            probe_type=probe_type,
            params=comp.params,
        )
        return self._remove_wires_with_invalid_pins(comp)

    def _open_umec_config(self, comp: ComponentInstance):
        from ui.umec_param_dialog import UMECTransformerDialog

        dialog = UMECTransformerDialog(comp.params, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.model._save_undo_state()
            comp.params.update(dialog.get_config())
            self._rebuild_component_pins(comp)
            self.model._notify("params_updated")


class SimulationConfigPanel(QWidget):
    def __init__(self, model: CircuitModel, parent=None):
        super().__init__(parent)
        self.model = model
        layout = QFormLayout(self)
        self.dt_spin = ScientificSpinBox()
        self.dt_spin.setValue(model.settings.dt)
        self.finish_spin = ScientificSpinBox()
        self.finish_spin.setValue(model.settings.finish_time)
        layout.addRow("dt:", self.dt_spin)
        layout.addRow("finish_time:", self.finish_spin)


class CodePreviewPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.code_edit = QPlainTextEdit()
        self.code_edit.setReadOnly(True)
        self.code_edit.setFont(QFont("Consolas", 10))
        layout.addWidget(self.code_edit)

    def set_code(self, code: str):
        self.code_edit.setPlainText(code)


class ConsolePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        layout.addWidget(self.text_edit)

    def append_text(self, text: str):
        self.text_edit.append(text)


class PlotPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        label = QLabel("波形图")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)


class MainWindow(QMainWindow):
    """Application main window."""

    def __init__(self):
        super().__init__()
        self.model = CircuitModel()
        self.runner: Optional[SimulationRunner] = None
        self._setup_actions()
        self._setup_ui()
        self._setup_toolbar()
        self.model.add_observer(self._on_model_changed)
        self._refresh_code_preview()
        self.setWindowTitle("EMTP Circuit Designer")

    def _setup_actions(self):
        self.run_action = QAction("运行", self)
        self.run_action.triggered.connect(self._on_run)

    def _setup_ui(self):
        self.canvas = CircuitCanvas(self.model)
        self.component_palette = ComponentPalette(self.canvas)
        self.property_panel = PropertyPanel(self.model)
        self.simulation_config = SimulationConfigPanel(self.model)
        self.validation_panel = ValidationPanel()
        self.statistics_panel = StatisticsPanel()
        self.code_preview = CodePreviewPanel()
        self.console_panel = ConsolePanel()
        self.plot_panel = PlotPanel()
        self.right_dock = None

        self.right_tabs = QTabWidget()
        self.right_tabs.addTab(self.property_panel, "属性")
        self.right_tabs.addTab(self.simulation_config, "仿真")

        self.output_tabs = QTabWidget()
        self.output_tabs.addTab(self.plot_panel, "波形图")
        self.output_tabs.addTab(self.console_panel, "输出")
        self.output_tabs.addTab(self.code_preview, "代码")
        self.output_tabs.addTab(self.validation_panel, "校验")
        self.output_tabs.addTab(self.statistics_panel, "统计")

        self.work_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.work_splitter.addWidget(self.component_palette)
        self.work_splitter.addWidget(self.canvas)
        self.work_splitter.addWidget(self.right_tabs)
        self.work_splitter.setSizes([220, 860, 320])

        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.addWidget(self.work_splitter)
        self.main_splitter.addWidget(self.output_tabs)
        self.main_splitter.setSizes([620, 240])
        self.setCentralWidget(self.main_splitter)

        self.status_label = QLabel("就绪")
        status = QStatusBar()
        status.addWidget(self.status_label)
        self.setStatusBar(status)

        self.canvas.component_selected.connect(self.property_panel.show_component)

    def _setup_toolbar(self):
        toolbar = QToolBar("工具")
        self.addToolBar(toolbar)
        self.run_btn = QPushButton("运行")
        self.run_btn.clicked.connect(self._on_run)
        toolbar.addAction(self.run_action)
        toolbar.addWidget(self.run_btn)

        validate_btn = QPushButton("校验")
        validate_btn.clicked.connect(self._on_validate)
        toolbar.addWidget(validate_btn)

        select_btn = QPushButton("选择")
        select_btn.clicked.connect(lambda: self.canvas.set_mode(CanvasMode.SELECT))
        toolbar.addWidget(select_btn)

        wire_btn = QPushButton("连线")
        wire_btn.clicked.connect(lambda: self.canvas.set_mode(CanvasMode.WIRE))
        toolbar.addWidget(wire_btn)

    def _set_running_ui(self, running: bool):
        self.run_action.setEnabled(not running)
        self.run_btn.setEnabled(not running)
        self.status_label.setText("运行中..." if running else "就绪")

    def _on_model_changed(self, event: str = "changed"):
        self._refresh_code_preview()

    def _refresh_code_preview(self):
        try:
            self.code_preview.set_code(generate_code(self.model))
        except Exception as exc:
            self.code_preview.set_code(f"# 代码生成失败: {exc}")

    def _on_sim_settings(self):
        self.right_tabs.setCurrentWidget(self.simulation_config)

    def _on_validate(self):
        from core.validator import validate_circuit

        errors, warnings = validate_circuit(self.model)
        self.console_panel.append_text(f">>> 校验完成: {len(errors)} 错误, {len(warnings)} 警告")

    def _on_run(self):
        self._set_running_ui(True)
        try:
            self.console_panel.append_text(">>> 开始仿真")
            self.runner = SimulationRunner(self.model)
            result = self.runner.run()
            self.console_panel.append_text(f">>> 仿真完成: {result}")
        except Exception as exc:
            QMessageBox.critical(self, "运行失败", str(exc))
            self.console_panel.append_text(f">>> 运行失败: {exc}")
        finally:
            self._set_running_ui(False)

    def _on_new(self):
        self.model = CircuitModel()
        self.canvas.model = self.model
        self.property_panel.model = self.model
        self.model.add_observer(self._on_model_changed)
        self.canvas._refresh_view()
        self._refresh_code_preview()

    def _on_open(self):
        path, _ = QFileDialog.getOpenFileName(self, "打开工程", "", "EMTP Project (*.emtp);;All Files (*)")
        if path:
            self.model = load_project(path)
            self.canvas.model = self.model
            self.property_panel.model = self.model
            self.model.add_observer(self._on_model_changed)
            self.canvas._refresh_view()
            self._refresh_code_preview()

    def _on_save(self):
        path, _ = QFileDialog.getSaveFileName(self, "保存工程", "", "EMTP Project (*.emtp);;All Files (*)")
        if path:
            save_project(self.model, path)

    def _on_export_python(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出 Python", "", "Python Files (*.py)")
        if path:
            export_python_code(self.model, path)

    def closeEvent(self, event: QCloseEvent):
        event.accept()
