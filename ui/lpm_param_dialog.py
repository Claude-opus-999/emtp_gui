"""
EMTP GUI - LPM 绝缘子闪络参数对话框

对齐内核 API:
  solver.add_insulator_LPM(name, node_from, node_to,
      gap_length, k, E0, R_arc, altitude_m,
      allow_extinction, extinction_current)

参数说明:
  - gap_length:  间隙长度 (m)
  - k:           CIGRE 速度系数 (s/m)
  - E0:          临界场强 (kV/m)
  - R_arc:       闪络后电弧电阻 (Ω)
  - altitude_m:  海拔高度 (m)
  - allow_extinction: 是否允许电弧熄灭
  - extinction_current: 熄弧电流阈值 (A)
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QTabWidget,
    QGroupBox, QPushButton, QLabel, QComboBox, QCheckBox,
    QDoubleSpinBox, QLineEdit, QDialogButtonBox,
    QWidget, QTextEdit,
)
from PySide6.QtCore import Qt
from typing import Dict

from ui.scientific_spin_box import ScientificSpinBox


class LPMParamDialog(QDialog):
    """LPM 绝缘子闪络参数配置对话框"""

    def __init__(self, current_params: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LPM 绝缘子闪络参数配置")
        self.setMinimumSize(580, 520)
        self._params = current_params
        self._setup_ui()
        self._load_from_params(current_params)

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # ====== 选项卡 ======
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.tabs.addTab(self._build_geometry_tab(), "几何与场强")
        self.tabs.addTab(self._build_arc_tab(), "电弧参数")
        self.tabs.addTab(self._build_preview_tab(), "配置预览")

        # ====== 按钮 ======
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    # ================================================================
    #  几何与场强选项卡
    # ================================================================

    def _build_geometry_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 间隙参数组
        gap_group = QGroupBox("间隙参数")
        gap_form = QFormLayout(gap_group)
        gap_form.setSpacing(8)

        self.gap_length_spin = QDoubleSpinBox()
        self.gap_length_spin.setRange(0.01, 100.0)
        self.gap_length_spin.setDecimals(3)
        self.gap_length_spin.setSingleStep(0.1)
        self.gap_length_spin.setSuffix(" m")
        self.gap_length_spin.setValue(2.5)
        gap_form.addRow("间隙长度:", self.gap_length_spin)

        layout.addWidget(gap_group)

        # 场强参数组
        field_group = QGroupBox("临界场强")
        field_form = QFormLayout(field_group)
        field_form.setSpacing(8)

        self.E0_spin = QDoubleSpinBox()
        self.E0_spin.setRange(1.0, 1e5)
        self.E0_spin.setDecimals(1)
        self.E0_spin.setSingleStep(10.0)
        self.E0_spin.setSuffix(" kV/m")
        self.E0_spin.setValue(600.0)
        field_form.addRow("临界场强 E0:", self.E0_spin)

        self.k_spin = ScientificSpinBox()
        self.k_spin.setRange(1e-15, 1.0)
        self.k_spin.setDecimals(6)
        self.k_spin.setValue(1e-6)
        field_form.addRow("CIGRE 速度系数 k:", self.k_spin)

        layout.addWidget(field_group)

        # 海拔参数组
        alt_group = QGroupBox("海拔修正")
        alt_form = QFormLayout(alt_group)
        alt_form.setSpacing(8)

        self.altitude_m_spin = QDoubleSpinBox()
        self.altitude_m_spin.setRange(0.0, 5000.0)
        self.altitude_m_spin.setDecimals(1)
        self.altitude_m_spin.setSingleStep(100.0)
        self.altitude_m_spin.setSuffix(" m")
        self.altitude_m_spin.setValue(0.0)
        alt_form.addRow("海拔高度:", self.altitude_m_spin)

        alt_tip = QLabel(
            "海拔修正：海拔越高，空气密度越低，闪络电压越低。\n"
            "修正系数约为 exp(-altitude/8150)"
        )
        alt_tip.setStyleSheet("color: #64748b; font-size: 11px;")
        alt_tip.setWordWrap(True)
        alt_form.addRow(alt_tip)

        layout.addWidget(alt_group)
        layout.addStretch()
        return widget

    # ================================================================
    #  电弧参数选项卡
    # ================================================================

    def _build_arc_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 电弧电阻组
        arc_group = QGroupBox("电弧参数")
        arc_form = QFormLayout(arc_group)
        arc_form.setSpacing(8)

        self.R_arc_spin = QDoubleSpinBox()
        self.R_arc_spin.setRange(1e-6, 1e6)
        self.R_arc_spin.setDecimals(4)
        self.R_arc_spin.setSingleStep(0.1)
        self.R_arc_spin.setSuffix(" Ω")
        self.R_arc_spin.setValue(1.0)
        arc_form.addRow("电弧电阻 R_arc:", self.R_arc_spin)

        arc_tip_r = QLabel("闪络后电弧的恒定电阻值，影响短路电流幅值")
        arc_tip_r.setStyleSheet("color: #64748b; font-size: 11px;")
        arc_tip_r.setWordWrap(True)
        arc_form.addRow(arc_tip_r)

        layout.addWidget(arc_group)

        # 熄弧参数组
        ext_group = QGroupBox("熄弧控制")
        ext_form = QFormLayout(ext_group)
        ext_form.setSpacing(8)

        self.allow_extinction_check = QCheckBox("允许电弧熄灭")
        self.allow_extinction_check.setChecked(True)
        self.allow_extinction_check.toggled.connect(self._on_extinction_toggled)
        ext_form.addRow(self.allow_extinction_check)

        self.extinction_current_spin = QDoubleSpinBox()
        self.extinction_current_spin.setRange(0.0, 1e6)
        self.extinction_current_spin.setDecimals(3)
        self.extinction_current_spin.setSingleStep(0.01)
        self.extinction_current_spin.setSuffix(" A")
        self.extinction_current_spin.setValue(0.1)
        ext_form.addRow("熄弧电流阈值:", self.extinction_current_spin)

        ext_tip = QLabel(
            "当流过绝缘子的电流低于熄弧电流阈值时，\n"
            "电弧熄灭，绝缘子恢复绝缘状态。\n"
            "若关闭此选项，闪络后电弧将持续到仿真结束。"
        )
        ext_tip.setStyleSheet("color: #64748b; font-size: 11px;")
        ext_tip.setWordWrap(True)
        ext_form.addRow(ext_tip)

        layout.addWidget(ext_group)

        # 物理说明
        info_group = QGroupBox("LPM 模型说明")
        info_layout = QVBoxLayout(info_group)
        info_label = QLabel(
            "LPM (Leader Progression Model) 基于先导发展模型：\n"
            "1. 当间隙电压超过临界场强 E0×gap_length 时开始发展先导\n"
            "2. 先导速度 v = k × (E/E0 - 1)，E 为当前场强\n"
            "3. 先导贯穿整个间隙时发生闪络\n"
            "4. 闪络后绝缘子等效为电阻 R_arc\n"
            "5. 若允许熄弧，电流低于阈值时恢复绝缘"
        )
        info_label.setStyleSheet("color: #334155; font-size: 11px;")
        info_label.setWordWrap(True)
        info_layout.addWidget(info_label)
        layout.addWidget(info_group)

        layout.addStretch()
        return widget

    # ================================================================
    #  配置预览选项卡
    # ================================================================

    def _build_preview_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 12px; "
            "background: #f8fafc; border: 1px solid #e2e8f0;"
        )
        layout.addWidget(self.preview_text)

        refresh_btn = QPushButton("刷新预览")
        refresh_btn.clicked.connect(self._update_preview)
        layout.addWidget(refresh_btn)

        return widget

    # ================================================================
    #  事件处理
    # ================================================================

    def _on_extinction_toggled(self, checked: bool):
        """熄弧开关切换"""
        self.extinction_current_spin.setEnabled(checked)

    def _update_preview(self):
        """更新配置预览文本"""
        p = self._params
        name = p.get('name', 'LPM1')

        lines = ["LPM 绝缘子闪络配置预览", "=" * 50, ""]

        lines.append("几何参数:")
        lines.append(f"  间隙长度 gap_length  = {self.gap_length_spin.value()} m")
        lines.append(f"  临界场强 E0          = {self.E0_spin.value()} kV/m")
        lines.append(f"  速度系数 k           = {self.k_spin.value()}")
        lines.append(f"  海拔 altitude_m      = {self.altitude_m_spin.value()} m")
        lines.append("")

        lines.append("电弧参数:")
        lines.append(f"  电弧电阻 R_arc       = {self.R_arc_spin.value()} Ω")
        lines.append(f"  允许熄弧             = {self.allow_extinction_check.isChecked()}")
        if self.allow_extinction_check.isChecked():
            lines.append(f"  熄弧电流阈值         = {self.extinction_current_spin.value()} A")
        lines.append("")

        # 闪络电压估算
        V_flash = self.E0_spin.value() * self.gap_length_spin.value()
        lines.append("估算:")
        lines.append(f"  临界闪络电压 ≈ E0 × gap_length = {V_flash:.1f} kV")
        lines.append("")

        lines.append("生成的内核代码:")
        ext_str = f", extinction_current={self.extinction_current_spin.value()}" if self.allow_extinction_check.isChecked() else ""
        lines.append(
            f'  solver.add_insulator_LPM("{name}",'
        )
        lines.append(
            f'    node_from=nf, node_to=nt,'
        )
        lines.append(
            f'    gap_length={self.gap_length_spin.value()},'
        )
        lines.append(
            f'    k={self.k_spin.value()},'
        )
        lines.append(
            f'    E0={self.E0_spin.value()},'
        )
        lines.append(
            f'    R_arc={self.R_arc_spin.value()},'
        )
        lines.append(
            f'    altitude_m={self.altitude_m_spin.value()},'
        )
        lines.append(
            f'    allow_extinction={self.allow_extinction_check.isChecked()}'
            f'{ext_str})'
        )

        self.preview_text.setText("\n".join(lines))

    # ================================================================
    #  加载 / 导出
    # ================================================================

    def _load_from_params(self, params: dict):
        """从参数字典加载到 UI"""
        self.gap_length_spin.setValue(params.get('gap_length', 2.5))
        self.k_spin.setValue(params.get('k', 1e-6))
        self.E0_spin.setValue(params.get('E0', 600.0))
        self.R_arc_spin.setValue(params.get('R_arc', 1.0))
        self.altitude_m_spin.setValue(params.get('altitude_m', 0.0))
        self.allow_extinction_check.setChecked(params.get('allow_extinction', True))
        self.extinction_current_spin.setValue(params.get('extinction_current', 0.1))
        self._on_extinction_toggled(self.allow_extinction_check.isChecked())
        self._update_preview()

    def get_config(self) -> dict:
        """导出为参数字典"""
        return {
            'gap_length': self.gap_length_spin.value(),
            'k': self.k_spin.value(),
            'E0': self.E0_spin.value(),
            'R_arc': self.R_arc_spin.value(),
            'altitude_m': self.altitude_m_spin.value(),
            'allow_extinction': self.allow_extinction_check.isChecked(),
            'extinction_current': self.extinction_current_spin.value(),
        }
