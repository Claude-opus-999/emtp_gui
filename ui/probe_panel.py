"""
EMTP 电路仿真 GUI - 探针管理面板
显示画布上 PROBE 元件 + 手动添加的自定义探针
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QCheckBox, QLabel, QComboBox, QFormLayout,
    QSpinBox, QGroupBox, QMessageBox, QLineEdit,
)
from PySide6.QtCore import Signal

from models.circuit_model import CircuitModel, ComponentType, ProbeConfig


class ProbePanel(QWidget):
    """探针管理面板 — 显示画布探针 + 手动添加自定义探针"""

    probes_changed = Signal()  # 探针列表变化

    def __init__(self, model: CircuitModel, parent=None):
        super().__init__(parent)
        self.model = model
        self.model.add_observer(self._on_model_changed)
        self._setup_ui()
        self._refresh_list()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 自动探针开关
        self.auto_probe_check = QCheckBox("自动为所有非地节点添加电压探针")
        self.auto_probe_check.setChecked(self.model.settings.auto_voltage_probes)
        self.auto_probe_check.setStyleSheet("color: #334155; font-weight: bold;")
        self.auto_probe_check.toggled.connect(self._on_auto_probe_toggled)
        layout.addWidget(self.auto_probe_check)

        # 画布探针列表
        layout.addWidget(QLabel("画布探针:"))
        self.canvas_probe_list = QListWidget()
        self.canvas_probe_list.setMaximumHeight(120)
        self.canvas_probe_list.setStyleSheet("""
            QListWidget { background-color: #fef9c3; border: 1px solid #fde047; border-radius: 4px; }
        """)
        layout.addWidget(self.canvas_probe_list)

        # 自定义探针列表
        layout.addWidget(QLabel("自定义探针:"))
        self.probe_list = QListWidget()
        self.probe_list.setMaximumHeight(120)
        layout.addWidget(self.probe_list)

        # 添加按钮
        btn_row = QHBoxLayout()
        self.add_voltage_btn = QPushButton("+ 电压探针")
        self.add_current_btn = QPushButton("+ 电流探针")
        self.add_line_current_btn = QPushButton("+ 线路电流")
        self.remove_btn = QPushButton("- 删除")

        self.add_voltage_btn.setStyleSheet("""
            QPushButton { background-color: #3b82f615; color: #3b82f6; border: 1px solid #3b82f640;
                border-radius: 4px; padding: 4px 8px; font-size: 11px; }
            QPushButton:hover { background-color: #3b82f630; border-color: #3b82f6; }
        """)
        self.add_current_btn.setStyleSheet("""
            QPushButton { background-color: #22c55e15; color: #22c55e; border: 1px solid #22c55e40;
                border-radius: 4px; padding: 4px 8px; font-size: 11px; }
            QPushButton:hover { background-color: #22c55e30; border-color: #22c55e; }
        """)
        self.add_line_current_btn.setStyleSheet("""
            QPushButton { background-color: #f59e0b15; color: #f59e0b; border: 1px solid #f59e0b40;
                border-radius: 4px; padding: 4px 8px; font-size: 11px; }
            QPushButton:hover { background-color: #f59e0b30; border-color: #f59e0b; }
        """)
        self.remove_btn.setStyleSheet("""
            QPushButton { background-color: #ef444415; color: #ef4444; border: 1px solid #ef444440;
                border-radius: 4px; padding: 4px 8px; font-size: 11px; }
            QPushButton:hover { background-color: #ef444430; border-color: #ef4444; }
        """)

        self.add_voltage_btn.clicked.connect(self._add_voltage_probe)
        self.add_current_btn.clicked.connect(self._add_branch_current_probe)
        self.add_line_current_btn.clicked.connect(self._add_line_current_probe)
        self.remove_btn.clicked.connect(self._remove_selected)

        btn_row.addWidget(self.add_voltage_btn)
        btn_row.addWidget(self.add_current_btn)
        btn_row.addWidget(self.add_line_current_btn)
        btn_row.addWidget(self.remove_btn)
        layout.addLayout(btn_row)

        # 电压探针添加表单
        v_group = QGroupBox("电压探针参数")
        v_form = QFormLayout(v_group)
        v_form.setSpacing(4)

        self.v_probe_id = QLineEdit("V_custom")
        self.v_node_pos = QSpinBox()
        self.v_node_pos.setRange(0, 9999)
        self.v_node_pos.setValue(1)
        self.v_node_neg = QSpinBox()
        self.v_node_neg.setRange(0, 9999)
        self.v_node_neg.setValue(0)
        self.v_unit = QComboBox()
        self.v_unit.addItems(["kV", "V", "mV"])

        v_form.addRow("探针ID:", self.v_probe_id)
        v_form.addRow("正节点:", self.v_node_pos)
        v_form.addRow("负节点:", self.v_node_neg)
        v_form.addRow("单位:", self.v_unit)
        layout.addWidget(v_group)

        # 电流探针添加表单
        i_group = QGroupBox("支路电流探针参数")
        i_form = QFormLayout(i_group)
        i_form.setSpacing(4)

        self.i_probe_id = QLineEdit("I_custom")
        self.i_branch_name = QLineEdit("R1")
        self.i_unit = QComboBox()
        self.i_unit.addItems(["A", "kA", "mA"])

        i_form.addRow("探针ID:", self.i_probe_id)
        i_form.addRow("支路名:", self.i_branch_name)
        i_form.addRow("单位:", self.i_unit)
        layout.addWidget(i_group)

        # 线路电流探针添加表单
        lc_group = QGroupBox("线路电流探针参数")
        lc_form = QFormLayout(lc_group)
        lc_form.setSpacing(4)

        self.lc_probe_id = QLineEdit("I_line")
        self.lc_line_name = QLineEdit("TL1")
        self.lc_line_end = QComboBox()
        self.lc_line_end.addItems(["k", "m"])
        self.lc_line_phase = QSpinBox()
        self.lc_line_phase.setRange(0, 99)
        self.lc_line_phase.setValue(0)
        self.lc_unit = QComboBox()
        self.lc_unit.addItems(["kA", "A", "mA"])

        lc_form.addRow("探针ID:", self.lc_probe_id)
        lc_form.addRow("线路名:", self.lc_line_name)
        lc_form.addRow("测量端:", self.lc_line_end)
        lc_form.addRow("相号:", self.lc_line_phase)
        lc_form.addRow("单位:", self.lc_unit)
        layout.addWidget(lc_group)

        # 提示
        hint = QLabel("💡 提示：也可在画布上右键元件→添加探针")
        hint.setStyleSheet("color: #64748b; font-size: 10px; font-style: italic;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addStretch()

    def _refresh_list(self):
        """刷新探针列表"""
        self._sync_auto_probe_check()

        # 画布探针
        self.canvas_probe_list.clear()
        for comp in self.model.components.values():
            if comp.comp_type == ComponentType.PROBE:
                probe_type = comp.params.get('probe_type', 'voltage')
                unit = comp.params.get('unit', 'kV')
                type_label = '⚡V' if probe_type == 'voltage' else '⚡I'
                item_text = f"{type_label} {comp.name} ({unit})"
                item = QListWidgetItem(item_text)
                item.setData(0x100, comp.comp_id)  # 存储 comp_id
                self.canvas_probe_list.addItem(item)

        # 自定义探针
        self.probe_list.clear()
        for probe in self.model.probes:
            type_label = {
                'voltage': '⚡V',
                'branch_current': '⚡I',
                'line_current': '⚡L',
            }.get(probe.probe_type, '⚡')
            item_text = f"{type_label} {probe.probe_id}"
            if probe.probe_type == 'voltage':
                item_text += f" (n{probe.node_pos}-n{probe.node_neg})"
            elif probe.probe_type == 'branch_current':
                item_text += f" ({probe.branch_name})"
            elif probe.probe_type == 'line_current':
                end = getattr(probe, 'end', 'k') or 'k'
                phase = getattr(probe, 'phase', 0) or 0
                lname = getattr(probe, 'line_name', '') or ''
                item_text += f" ({lname}@{end}, ph{phase})"
            item = QListWidgetItem(item_text)
            self.probe_list.addItem(item)

    def _add_voltage_probe(self):
        """添加电压探针"""
        probe = ProbeConfig(
            probe_id=self.v_probe_id.text(),
            probe_type="voltage",
            node_pos=self.v_node_pos.value(),
            node_neg=self.v_node_neg.value(),
            unit=self.v_unit.currentText(),
        )
        self.model.add_probe(probe)
        self._refresh_list()
        self.probes_changed.emit()

    def _add_branch_current_probe(self):
        """添加支路电流探针"""
        probe = ProbeConfig(
            probe_id=self.i_probe_id.text(),
            probe_type="branch_current",
            branch_name=self.i_branch_name.text(),
            unit=self.i_unit.currentText(),
        )
        self.model.add_probe(probe)
        self._refresh_list()
        self.probes_changed.emit()

    def _add_line_current_probe(self):
        """添加线路电流探针"""
        probe = ProbeConfig(
            probe_id=self.lc_probe_id.text(),
            probe_type="line_current",
            line_name=self.lc_line_name.text(),
            end=self.lc_line_end.currentText(),
            phase=self.lc_line_phase.value(),
            unit=self.lc_unit.currentText(),
        )
        self.model.add_probe(probe)
        self._refresh_list()
        self.probes_changed.emit()

    def _remove_selected(self):
        """删除选中的探针"""
        current = self.probe_list.currentItem()
        if current is None:
            return
        idx = self.probe_list.row(current)
        if 0 <= idx < len(self.model.probes):
            probe_id = self.model.probes[idx].probe_id
            self.model.remove_probe(probe_id)
            self._refresh_list()
            self.probes_changed.emit()

    def _on_auto_probe_toggled(self, checked: bool):
        self.model.update_settings(auto_voltage_probes=checked)

    def _sync_auto_probe_check(self):
        checked = self.model.settings.auto_voltage_probes
        self.auto_probe_check.blockSignals(True)
        self.auto_probe_check.setChecked(checked)
        self.auto_probe_check.blockSignals(False)

    def _on_model_changed(self, event: str = "changed"):
        if event in (
            "component_added",
            "component_removed",
            "params_updated",
            "settings_updated",
            "probes_updated",
            "cleared",
            "undone",
            "redone",
        ):
            self._refresh_list()

    def set_model(self, model: CircuitModel):
        """更新 model 引用"""
        try:
            self.model.remove_observer(self._on_model_changed)
        except (ValueError, AttributeError):
            pass
        self.model = model
        self.model.add_observer(self._on_model_changed)
        self._refresh_list()
