"""
EMTP GUI - MOA 避雷器参数对话框

支持两种输入模式:
  1. 从文件加载 V-I 曲线 (vi_file)
  2. 断点表格输入 (breakpoints)

对齐内核 API:
  - solver.add_MOA_from_file(name, nf, nt, file_path, rated_voltage, voltage_is_pu)
  - SegmentedMOAResistor.from_breakpoints(name, breakpoints, rated_voltage, voltage_is_pu)
    + solver.add_MOA_device(name, nf, nt, moa)
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QTabWidget,
    QGroupBox, QPushButton, QLabel, QComboBox, QCheckBox,
    QDoubleSpinBox, QLineEdit, QDialogButtonBox,
    QWidget, QTextEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QFileDialog, QSizePolicy,
)
from PySide6.QtCore import Qt
from typing import Dict, List, Tuple


class MOAParamDialog(QDialog):
    """MOA 避雷器参数配置对话框"""

    def __init__(self, current_params: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MOA 避雷器参数配置")
        self.setMinimumSize(600, 550)
        self._params = current_params
        self._setup_ui()
        self._load_from_params(current_params)

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # ====== 选项卡 ======
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.tabs.addTab(self._build_basic_tab(), "基本参数")
        self.tabs.addTab(self._build_vi_tab(), "V-I 特性")
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
    #  基本参数选项卡
    # ================================================================

    def _build_basic_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 额定参数组
        rated_group = QGroupBox("额定参数")
        rated_form = QFormLayout(rated_group)
        rated_form.setSpacing(8)

        self.rated_voltage_spin = QDoubleSpinBox()
        self.rated_voltage_spin.setRange(0.001, 1e8)
        self.rated_voltage_spin.setDecimals(3)
        self.rated_voltage_spin.setSuffix(" V")
        self.rated_voltage_spin.setValue(1.0)
        rated_form.addRow("额定电压:", self.rated_voltage_spin)

        self.voltage_is_pu_check = QCheckBox("电压为标幺值 (pu)")
        self.voltage_is_pu_check.setChecked(True)
        rated_form.addRow("", self.voltage_is_pu_check)

        layout.addWidget(rated_group)

        # 输入模式组
        mode_group = QGroupBox("V-I 数据输入模式")
        mode_layout = QVBoxLayout(mode_group)

        self.input_mode_combo = QComboBox()
        self.input_mode_combo.addItems(["断点表格输入", "从文件加载"])
        self.input_mode_combo.currentIndexChanged.connect(self._on_input_mode_changed)
        mode_layout.addWidget(self.input_mode_combo)

        # 文件路径 (当选择"从文件加载"时显示)
        file_layout = QHBoxLayout()
        self.vi_file_edit = QLineEdit()
        self.vi_file_edit.setPlaceholderText("选择 V-I 数据文件...")
        self.vi_file_edit.setEnabled(False)
        file_layout.addWidget(self.vi_file_edit)

        self.browse_btn = QPushButton("浏览...")
        self.browse_btn.setEnabled(False)
        self.browse_btn.clicked.connect(self._browse_vi_file)
        file_layout.addWidget(self.browse_btn)
        mode_layout.addLayout(file_layout)

        layout.addWidget(mode_group)

        # 提示
        tip = QLabel(
            "提示：\n"
            "• 断点表格模式下，每一行定义一个 V-I 断点 (V, I)\n"
            "• 电压单位取决于「电压为标幺值」选项：pu 或 V\n"
            "• 电流单位为 A\n"
            "• 至少需要 2 个断点，建议 5-20 个以获得良好拟合\n"
            "• 文件格式：每行两个数值，空格或逗号分隔"
        )
        tip.setStyleSheet("color: #64748b; font-size: 11px;")
        tip.setWordWrap(True)
        layout.addWidget(tip)
        layout.addStretch()
        return widget

    # ================================================================
    #  V-I 特性选项卡
    # ================================================================

    def _build_vi_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 断点表格
        bp_group = QGroupBox("V-I 断点表格")
        bp_layout = QVBoxLayout(bp_group)

        self.bp_table = QTableWidget(0, 2)
        self.bp_table.setHorizontalHeaderLabels(["V (电压)", "I (电流/A)"])
        self.bp_table.horizontalHeader().setStretchLastSection(True)
        self.bp_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.bp_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.bp_table.setMinimumHeight(250)
        self.bp_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        bp_layout.addWidget(self.bp_table)

        # 表格操作按钮
        btn_row = QHBoxLayout()
        self.add_row_btn = QPushButton("+ 添加行")
        self.add_row_btn.clicked.connect(self._add_bp_row)
        btn_row.addWidget(self.add_row_btn)

        self.del_row_btn = QPushButton("- 删除选中行")
        self.del_row_btn.clicked.connect(self._del_bp_row)
        btn_row.addWidget(self.del_row_btn)

        self.clear_table_btn = QPushButton("清空表格")
        self.clear_table_btn.clicked.connect(self._clear_bp_table)
        btn_row.addWidget(self.clear_table_btn)

        btn_row.addStretch()
        bp_layout.addLayout(btn_row)

        layout.addWidget(bp_group)
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

    def _on_input_mode_changed(self, index: int):
        """切换输入模式"""
        is_file_mode = (index == 1)  # "从文件加载"
        self.vi_file_edit.setEnabled(is_file_mode)
        self.browse_btn.setEnabled(is_file_mode)
        self.bp_table.setEnabled(not is_file_mode)
        self.add_row_btn.setEnabled(not is_file_mode)
        self.del_row_btn.setEnabled(not is_file_mode)
        self.clear_table_btn.setEnabled(not is_file_mode)

    def _browse_vi_file(self):
        """浏览选择 V-I 数据文件"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 V-I 数据文件", "",
            "数据文件 (*.dat *.txt *.csv);;所有文件 (*)"
        )
        if path:
            self.vi_file_edit.setText(path)

    def _add_bp_row(self):
        """添加断点行"""
        row = self.bp_table.rowCount()
        self.bp_table.insertRow(row)
        # 默认值
        self.bp_table.setItem(row, 0, QTableWidgetItem("0.0"))
        self.bp_table.setItem(row, 1, QTableWidgetItem("0.0"))

    def _del_bp_row(self):
        """删除选中行"""
        rows = set(item.row() for item in self.bp_table.selectedItems())
        for row in sorted(rows, reverse=True):
            self.bp_table.removeRow(row)

    def _clear_bp_table(self):
        """清空表格"""
        self.bp_table.setRowCount(0)

    def _get_breakpoints_from_table(self) -> List[Tuple[float, float]]:
        """从表格读取断点列表"""
        breakpoints = []
        for row in range(self.bp_table.rowCount()):
            v_item = self.bp_table.item(row, 0)
            i_item = self.bp_table.item(row, 1)
            if v_item and i_item:
                try:
                    v = float(v_item.text().strip())
                    i = float(i_item.text().strip())
                    breakpoints.append((v, i))
                except ValueError:
                    continue
        return breakpoints

    def _update_preview(self):
        """更新配置预览文本"""
        lines = ["MOA 避雷器配置预览", "=" * 50, ""]

        lines.append(f"额定电压: {self.rated_voltage_spin.value()} V")
        lines.append(f"电压单位: {'标幺值 (pu)' if self.voltage_is_pu_check.isChecked() else '绝对值 (V)'}")
        lines.append("")

        mode = self.input_mode_combo.currentText()
        if mode == "从文件加载":
            lines.append(f"输入模式: 文件加载")
            vi_file = self.vi_file_edit.text().strip()
            if vi_file:
                lines.append(f"V-I 文件: {vi_file}")
                lines.append("")
                lines.append("生成的内核代码:")
                lines.append(
                    f'  solver.add_MOA_from_file("{self._params.get("name", "MOA1")}", '
                    f'nf, nt,'
                )
                lines.append(
                    f'    file_path="{vi_file}",'
                )
                lines.append(
                    f'    rated_voltage={self.rated_voltage_spin.value()},'
                )
                lines.append(
                    f'    voltage_is_pu={self.voltage_is_pu_check.isChecked()})'
                )
            else:
                lines.append("⚠ 尚未选择 V-I 数据文件")
        else:
            bp = self._get_breakpoints_from_table()
            lines.append(f"输入模式: 断点表格")
            lines.append(f"断点数量: {len(bp)}")
            if bp:
                lines.append("")
                lines.append("V-I 断点数据:")
                lines.append(f"  {'序号':>4}  {'V':>12}  {'I (A)':>12}")
                lines.append("  " + "-" * 34)
                for idx, (v, i) in enumerate(bp, 1):
                    lines.append(f"  {idx:>4}  {v:>12.4f}  {i:>12.6f}")
                lines.append("")
                lines.append("生成的内核代码:")
                bp_str = repr(bp)
                lines.append(
                    f'  _moa = SegmentedMOAResistor.from_breakpoints('
                )
                lines.append(
                    f'    "{self._params.get("name", "MOA1")}", {bp_str},'
                )
                lines.append(
                    f'    rated_voltage={self.rated_voltage_spin.value()}, '
                    f'voltage_is_pu={self.voltage_is_pu_check.isChecked()})'
                )
                lines.append(
                    f'  solver.add_MOA_device("MOA1", nf, nt, _moa)'
                )
            else:
                lines.append("⚠ 尚未输入断点数据")

        self.preview_text.setText("\n".join(lines))

    # ================================================================
    #  加载 / 导出
    # ================================================================

    def _load_from_params(self, params: dict):
        """从参数字典加载到 UI"""
        self.rated_voltage_spin.setValue(params.get('rated_voltage', 1.0))
        self.voltage_is_pu_check.setChecked(params.get('voltage_is_pu', True))

        # 判断输入模式
        vi_file = params.get('vi_file', '')
        breakpoints = params.get('breakpoints', [])

        if vi_file:
            self.input_mode_combo.setCurrentIndex(1)  # "从文件加载"
            self.vi_file_edit.setText(vi_file)
        else:
            self.input_mode_combo.setCurrentIndex(0)  # "断点表格输入"

        # 加载断点到表格
        if breakpoints:
            self.bp_table.setRowCount(len(breakpoints))
            for row, (v, i) in enumerate(breakpoints):
                self.bp_table.setItem(row, 0, QTableWidgetItem(f"{v}"))
                self.bp_table.setItem(row, 1, QTableWidgetItem(f"{i}"))
        else:
            # 默认 5 行空行
            for _ in range(5):
                self._add_bp_row()

        self._on_input_mode_changed(self.input_mode_combo.currentIndex())
        self._update_preview()

    def get_config(self) -> dict:
        """导出为参数字典"""
        config = {
            'rated_voltage': self.rated_voltage_spin.value(),
            'voltage_is_pu': self.voltage_is_pu_check.isChecked(),
        }

        if self.input_mode_combo.currentIndex() == 1:
            # 文件模式
            config['vi_file'] = self.vi_file_edit.text().strip()
            config['breakpoints'] = []
        else:
            # 断点模式
            config['vi_file'] = ''
            config['breakpoints'] = self._get_breakpoints_from_table()

        return config
