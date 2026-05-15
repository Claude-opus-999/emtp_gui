"""
EMTP GUI - UMEC 变压器参数对话框

对齐内核 API: create_umec_transformer_3ph_bank() + solver.add_UMEC_transformer()
支持两绕组三相组，Y/Y_gnd/Delta 接法选择。
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QTabWidget,
    QGroupBox, QPushButton, QLabel, QComboBox, QCheckBox,
    QDoubleSpinBox, QSpinBox, QLineEdit, QDialogButtonBox,
    QWidget, QTextEdit,
)
from PySide6.QtCore import Qt
from typing import Dict


class UMECTransformerDialog(QDialog):
    """UMEC 变压器参数配置对话框"""

    def __init__(self, current_params: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("UMEC 变压器参数配置")
        self.setMinimumSize(600, 500)
        self._params = current_params
        self._setup_ui()
        self._load_from_params(current_params)

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # ====== 选项卡 ======
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.tabs.addTab(self._build_basic_tab(), "基本参数")
        self.tabs.addTab(self._build_impedance_tab(), "阻抗参数")
        self.tabs.addTab(self._build_port_tab(), "端口映射")

        # ====== 按钮 ======
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    # ================================================================
    #  基本参数选项卡
    # ================================================================

    def _build_basic_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 额定参数组
        rated_group = QGroupBox("额定参数")
        rated_form = QFormLayout(rated_group)
        rated_form.setSpacing(8)

        self.S_mva_spin = QDoubleSpinBox()
        self.S_mva_spin.setRange(0.1, 10000.0)
        self.S_mva_spin.setDecimals(2)
        self.S_mva_spin.setSuffix(" MVA")
        self.S_mva_spin.setValue(100.0)
        rated_form.addRow("额定容量:", self.S_mva_spin)

        self.freq_spin = QDoubleSpinBox()
        self.freq_spin.setRange(1.0, 1000.0)
        self.freq_spin.setDecimals(1)
        self.freq_spin.setSuffix(" Hz")
        self.freq_spin.setValue(50.0)
        rated_form.addRow("额定频率:", self.freq_spin)

        layout.addWidget(rated_group)

        # 绕组参数组
        winding_group = QGroupBox("绕组参数")
        winding_layout = QVBoxLayout(winding_group)

        # 绕组 #1
        w1_form = QFormLayout()
        self.V1_kV_spin = QDoubleSpinBox()
        self.V1_kV_spin.setRange(0.1, 1000.0)
        self.V1_kV_spin.setDecimals(2)
        self.V1_kV_spin.setSuffix(" kV")
        self.V1_kV_spin.setValue(220.0)
        w1_form.addRow("#1侧线电压:", self.V1_kV_spin)

        self.wtype1_combo = QComboBox()
        self.wtype1_combo.addItems(["Y", "Y_gnd", "Delta"])
        self.wtype1_combo.setCurrentText("Y_gnd")
        w1_form.addRow("#1侧接法:", self.wtype1_combo)
        winding_layout.addLayout(w1_form)

        winding_layout.addSpacing(10)

        # 绕组 #2
        w2_form = QFormLayout()
        self.V2_kV_spin = QDoubleSpinBox()
        self.V2_kV_spin.setRange(0.1, 1000.0)
        self.V2_kV_spin.setDecimals(2)
        self.V2_kV_spin.setSuffix(" kV")
        self.V2_kV_spin.setValue(110.0)
        w2_form.addRow("#2侧线电压:", self.V2_kV_spin)

        self.wtype2_combo = QComboBox()
        self.wtype2_combo.addItems(["Y", "Y_gnd", "Delta"])
        self.wtype2_combo.setCurrentText("Delta")
        w2_form.addRow("#2侧接法:", self.wtype2_combo)
        winding_layout.addLayout(w2_form)

        layout.addWidget(winding_group)
        layout.addStretch()
        return widget

    # ================================================================
    #  阻抗参数选项卡
    # ================================================================

    def _build_impedance_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        form = QFormLayout()
        form.setSpacing(10)

        self.X_leak_pu_spin = QDoubleSpinBox()
        self.X_leak_pu_spin.setRange(0.001, 0.5)
        self.X_leak_pu_spin.setDecimals(4)
        self.X_leak_pu_spin.setSingleStep(0.01)
        self.X_leak_pu_spin.setValue(0.08)
        form.addRow("漏抗 (pu):", self.X_leak_pu_spin)

        self.Im_percent_spin = QDoubleSpinBox()
        self.Im_percent_spin.setRange(0.01, 50.0)
        self.Im_percent_spin.setDecimals(2)
        self.Im_percent_spin.setSingleStep(0.1)
        self.Im_percent_spin.setValue(1.0)
        form.addRow("励磁电流 (%):", self.Im_percent_spin)

        self.NLL_pu_spin = QDoubleSpinBox()
        self.NLL_pu_spin.setRange(0.0, 0.1)
        self.NLL_pu_spin.setDecimals(4)
        self.NLL_pu_spin.setSingleStep(0.001)
        self.NLL_pu_spin.setValue(0.0)
        form.addRow("空载损耗 (pu):", self.NLL_pu_spin)

        self.CL_pu_spin = QDoubleSpinBox()
        self.CL_pu_spin.setRange(0.0, 0.1)
        self.CL_pu_spin.setDecimals(4)
        self.CL_pu_spin.setSingleStep(0.001)
        self.CL_pu_spin.setValue(0.0)
        form.addRow("铜损 (pu):", self.CL_pu_spin)

        layout.addLayout(form)

        # 提示
        tip = QLabel(
            "提示：\n"
            "• 漏抗 X_leak_pu 为一次侧测得的漏抗标幺值\n"
            "• 励磁电流 Im_percent 为额定电压下的励磁电流百分比\n"
            "• 空载损耗 NLL_pu = 空载损耗 / 额定容量\n"
            "• 铜损 CL_pu = 负载损耗 / 额定容量\n"
            "• NLL_pu=0 时铁损并联电导退化为很小默认值\n"
            "• CL_pu=0 时绕组电阻退化为很小默认值"
        )
        tip.setStyleSheet("color: #64748b; font-size: 11px;")
        tip.setWordWrap(True)
        layout.addWidget(tip)
        layout.addStretch()
        return widget

    # ================================================================
    #  端口映射选项卡
    # ================================================================

    def _build_port_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.port_preview = QTextEdit()
        self.port_preview.setReadOnly(True)
        self.port_preview.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 12px; "
            "background: #f8fafc; border: 1px solid #e2e8f0;"
        )
        layout.addWidget(self.port_preview)

        # 刷新按钮
        refresh_btn = QPushButton("刷新预览")
        refresh_btn.clicked.connect(self._update_port_preview)
        layout.addWidget(refresh_btn)

        return widget

    def _update_port_preview(self):
        """更新端口映射预览文本"""
        wtype1 = self.wtype1_combo.currentText()
        wtype2 = self.wtype2_combo.currentText()

        lines = ["UMEC 变压器端口映射 (两绕组三相组)", "=" * 50, ""]

        lines.append("左侧引脚 (高压侧 #1):")
        lines.append("  H_A  → A相线端")
        lines.append("  H_B  → B相线端")
        lines.append("  H_C  → C相线端")
        if wtype1 == 'Y':
            lines.append("  H_N  → 中性点 (Y接法)")
        elif wtype1 == 'Y_gnd':
            lines.append("  H_N  → 悬空 (Y_gnd 内部自动接地)")
        else:
            lines.append("  H_N  → 悬空 (Delta 无中性点)")

        lines.append("")
        lines.append("右侧引脚 (低压侧 #2):")
        lines.append("  X_A  → A相线端")
        lines.append("  X_B  → B相线端")
        lines.append("  X_C  → C相线端")
        if wtype2 == 'Y':
            lines.append("  X_N  → 中性点 (Y接法)")
        elif wtype2 == 'Y_gnd':
            lines.append("  X_N  → 悬空 (Y_gnd 内部自动接地)")
        else:
            lines.append("  X_N  → 悬空 (Delta 无中性点)")

        lines.append("")
        lines.append("内核节点映射规则:")
        lines.append(f"  #1侧 ({wtype1}):")
        for ph in ['A', 'B', 'C']:
            if wtype1 in ('Y', 'Y_gnd'):
                to_str = "0 (接地)" if wtype1 == 'Y_gnd' else "H_N"
            else:
                next_p = {'A': 'B', 'B': 'C', 'C': 'A'}[ph]
                to_str = f"H_{next_p}"
            lines.append(f"    H_{ph} → ({ph}相, {to_str})")

        lines.append(f"  #2侧 ({wtype2}):")
        for ph in ['A', 'B', 'C']:
            if wtype2 in ('Y', 'Y_gnd'):
                to_str = "0 (接地)" if wtype2 == 'Y_gnd' else "X_N"
            else:
                next_p = {'A': 'B', 'B': 'C', 'C': 'A'}[ph]
                to_str = f"X_{next_p}"
            lines.append(f"    X_{ph} → ({ph}相, {to_str})")

        self.port_preview.setText("\n".join(lines))

    # ================================================================
    #  加载 / 导出
    # ================================================================

    def _load_from_params(self, params: dict):
        """从参数字典加载到 UI"""
        self.S_mva_spin.setValue(params.get('S_mva', 100.0))
        self.freq_spin.setValue(params.get('freq', 50.0))
        self.V1_kV_spin.setValue(params.get('V1_kV', 220.0))
        self.V2_kV_spin.setValue(params.get('V2_kV', 110.0))
        self.wtype1_combo.setCurrentText(params.get('wtype1', 'Y_gnd'))
        self.wtype2_combo.setCurrentText(params.get('wtype2', 'Delta'))
        self.X_leak_pu_spin.setValue(params.get('X_leak_pu', 0.08))
        self.Im_percent_spin.setValue(params.get('Im_percent', 1.0))
        self.NLL_pu_spin.setValue(params.get('NLL_pu', 0.0))
        self.CL_pu_spin.setValue(params.get('CL_pu', 0.0))
        self._update_port_preview()

    def get_config(self) -> dict:
        """导出为参数字典"""
        return {
            'S_mva': self.S_mva_spin.value(),
            'freq': self.freq_spin.value(),
            'V1_kV': self.V1_kV_spin.value(),
            'V2_kV': self.V2_kV_spin.value(),
            'wtype1': self.wtype1_combo.currentText(),
            'wtype2': self.wtype2_combo.currentText(),
            'X_leak_pu': self.X_leak_pu_spin.value(),
            'Im_percent': self.Im_percent_spin.value(),
            'NLL_pu': self.NLL_pu_spin.value(),
            'CL_pu': self.CL_pu_spin.value(),
        }
