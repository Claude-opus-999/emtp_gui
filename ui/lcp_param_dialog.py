"""
EMTP GUI - LCP 参数对话框

支持三种 LCP 线路类型的可视化参数配置：
- 架空线 (Overhead Line)
- 单芯电缆 (Single-Core Cable)
- 三芯电缆 (Three-Core Cable)

每个对话框包含截面预览选项卡和自动更新的端口映射预览。
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QTabWidget,
    QGroupBox, QPushButton, QLabel, QComboBox, QCheckBox,
    QDoubleSpinBox, QSpinBox, QLineEdit, QTableWidget, QTableWidgetItem,
    QDialogButtonBox, QHeaderView, QMessageBox, QWidget,
)
from PySide6.QtCore import Qt, QTimer
from typing import Dict, Optional, List

from ui.lcp_preview_widgets import LCPCrossSectionCanvas, build_port_preview_text


# ================================================================
#  混入: 预览去抖定时器
# ================================================================

class _PreviewDebounceMixin:
    """为对话框提供 150ms 去抖预览刷新能力。"""

    def _init_preview_timer(self):
        """在 __init__ 末尾调用，初始化去抖定时器。"""
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(150)
        self._preview_timer.timeout.connect(self._refresh_previews)

    def _on_param_changed_for_preview(self):
        """任意参数变化时调用，启动去抖定时器。"""
        self._preview_timer.start()


class _LCPFittingMixin:
    """Shared VF fitting page for LCP overhead lines and cables."""

    def _build_fitting_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        yc_group = QGroupBox("Yc (特性导纳) 拟合")
        yc_form = QFormLayout(yc_group)
        self.yc_poles_min_spin = QSpinBox()
        self.yc_poles_min_spin.setRange(2, 50)
        self.yc_poles_min_spin.setValue(6)
        yc_form.addRow("最小极点数:", self.yc_poles_min_spin)

        self.yc_poles_max_spin = QSpinBox()
        self.yc_poles_max_spin.setRange(2, 50)
        self.yc_poles_max_spin.setValue(20)
        yc_form.addRow("最大极点数:", self.yc_poles_max_spin)

        self.yc_error_spin = QDoubleSpinBox()
        self.yc_error_spin.setRange(0.0001, 1.0)
        self.yc_error_spin.setDecimals(4)
        self.yc_error_spin.setValue(0.002)
        yc_form.addRow("目标误差:", self.yc_error_spin)
        layout.addWidget(yc_group)

        h_group = QGroupBox("H (传播函数) 拟合")
        h_form = QFormLayout(h_group)
        self.h_poles_min_spin = QSpinBox()
        self.h_poles_min_spin.setRange(2, 50)
        self.h_poles_min_spin.setValue(8)
        h_form.addRow("最小极点数:", self.h_poles_min_spin)

        self.h_poles_max_spin = QSpinBox()
        self.h_poles_max_spin.setRange(2, 50)
        self.h_poles_max_spin.setValue(20)
        h_form.addRow("最大极点数:", self.h_poles_max_spin)

        self.h_error_spin = QDoubleSpinBox()
        self.h_error_spin.setRange(0.0001, 1.0)
        self.h_error_spin.setDecimals(4)
        self.h_error_spin.setValue(0.002)
        h_form.addRow("目标误差:", self.h_error_spin)
        layout.addWidget(h_group)

        freq_group = QGroupBox("频率扫描范围")
        freq_form = QFormLayout(freq_group)
        self.freq_min_spin = QDoubleSpinBox()
        self.freq_min_spin.setRange(1e-6, 1e6)
        self.freq_min_spin.setDecimals(4)
        self.freq_min_spin.setValue(0.01)
        self.freq_min_spin.setSuffix(" Hz")
        freq_form.addRow("起始频率:", self.freq_min_spin)

        self.freq_max_spin = QDoubleSpinBox()
        self.freq_max_spin.setRange(1, 1e9)
        self.freq_max_spin.setDecimals(0)
        self.freq_max_spin.setValue(100000)
        self.freq_max_spin.setSuffix(" Hz")
        freq_form.addRow("终止频率:", self.freq_max_spin)

        self.freq_n_spin = QSpinBox()
        self.freq_n_spin.setRange(10, 10000)
        self.freq_n_spin.setValue(200)
        freq_form.addRow("频率增量数:", self.freq_n_spin)
        layout.addWidget(freq_group)

        layout.addStretch()
        return widget

    def _load_fitting_from_params(self, params: dict):
        self.yc_poles_min_spin.setValue(params.get('Yc_poles_min', 6))
        self.yc_poles_max_spin.setValue(params.get('Yc_poles_max', 20))
        self.yc_error_spin.setValue(params.get('Yc_target_error', 0.002))
        self.h_poles_min_spin.setValue(params.get('H_poles_min', 8))
        self.h_poles_max_spin.setValue(params.get('H_poles_max', 20))
        self.h_error_spin.setValue(params.get('H_target_error', 0.002))
        self.freq_min_spin.setValue(params.get('freq_min', 0.01))
        self.freq_max_spin.setValue(params.get('freq_max', 100000))
        self.freq_n_spin.setValue(params.get('n_freq_increments', 200))

    def _fitting_config(self) -> Dict:
        return {
            'Yc_poles_min': self.yc_poles_min_spin.value(),
            'Yc_poles_max': self.yc_poles_max_spin.value(),
            'Yc_target_error': self.yc_error_spin.value(),
            'H_poles_min': self.h_poles_min_spin.value(),
            'H_poles_max': self.h_poles_max_spin.value(),
            'H_target_error': self.h_error_spin.value(),
            'freq_min': self.freq_min_spin.value(),
            'freq_max': self.freq_max_spin.value(),
            'n_freq_increments': self.freq_n_spin.value(),
        }


# ================================================================
#  LCPOHLDialog — 架空线
# ================================================================

class LCPOHLDialog(QDialog, _PreviewDebounceMixin):
    """LCP 架空线参数对话框

    对应 emtp_0508 的 PSCADLineConfig / CalculationConfig。
    导线/地线坐标编辑 → 自动生成 config dict → 传递给 solver.add_lcp_ohl_line()

    包含5个选项卡：通用参数、导线配置、地线配置、拟合配置、截面预览
    """

    def __init__(self, current_params: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LCP 架空线参数配置")
        self.setMinimumSize(800, 650)
        self._params = current_params
        self._setup_ui()
        self._connect_preview_signals()
        self._init_preview_timer()
        self._load_from_params(current_params)

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # ====== 选项卡 ======
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # 通用参数选项卡
        self.tabs.addTab(self._build_common_tab(), "通用参数")
        # 导线选项卡
        self.tabs.addTab(self._build_phase_tab(), "导线配置")
        # 地线选项卡
        self.tabs.addTab(self._build_gw_tab(), "地线配置")
        # 拟合配置选项卡
        self.tabs.addTab(self._build_fitting_tab(), "拟合配置")
        # 截面预览选项卡
        self.tabs.addTab(self._build_preview_tab(), "截面预览")

        # ====== 按钮 ======
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    # ================================================================
    #  通用参数
    # ================================================================

    def _build_common_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        form = QFormLayout()
        form.setSpacing(8)

        # 长度
        self.length_spin = QDoubleSpinBox()
        self.length_spin.setRange(0.1, 1e9)
        self.length_spin.setDecimals(1)
        self.length_spin.setSuffix(" m")
        self.length_spin.setValue(900.0)
        form.addRow("线路长度:", self.length_spin)

        # 土壤电阻率
        self.ground_resistivity_spin = QDoubleSpinBox()
        self.ground_resistivity_spin.setRange(0.01, 1e8)
        self.ground_resistivity_spin.setDecimals(2)
        self.ground_resistivity_spin.setSuffix(" Ω·m")
        self.ground_resistivity_spin.setValue(1000.0)
        form.addRow("土壤电阻率:", self.ground_resistivity_spin)

        # 土壤相对磁导率
        self.ground_permeability_spin = QDoubleSpinBox()
        self.ground_permeability_spin.setRange(0.1, 1000)
        self.ground_permeability_spin.setDecimals(2)
        self.ground_permeability_spin.setValue(1.0)
        form.addRow("土壤相对磁导率:", self.ground_permeability_spin)

        # 土壤相对介电常数
        self.ground_permittivity_spin = QDoubleSpinBox()
        self.ground_permittivity_spin.setRange(0.1, 1000)
        self.ground_permittivity_spin.setDecimals(2)
        self.ground_permittivity_spin.setValue(1.0)
        form.addRow("土壤相对介电常数:", self.ground_permittivity_spin)

        # force_rebuild
        self.force_rebuild_check = QCheckBox("强制重建（忽略缓存）")
        self.force_rebuild_check.setChecked(True)
        form.addRow(self.force_rebuild_check)

        layout.addLayout(form)

        # 端口映射预览（自动更新，无手动按钮）
        port_group = QGroupBox("端口映射预览")
        port_layout = QVBoxLayout(port_group)
        self.port_preview_label = QLabel("添加导线/地线后自动生成")
        self.port_preview_label.setWordWrap(True)
        self.port_preview_label.setStyleSheet("color: #64748b; font-family: Consolas;")
        port_layout.addWidget(self.port_preview_label)
        layout.addWidget(port_group)

        layout.addStretch()
        return widget

    # ================================================================
    #  导线配置
    # ================================================================

    def _build_phase_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 导线参数
        phase_params = QGroupBox("导线物理参数")
        pf = QFormLayout(phase_params)

        self.phase_radius_spin = QDoubleSpinBox()
        self.phase_radius_spin.setRange(0.001, 1.0)
        self.phase_radius_spin.setDecimals(4)
        self.phase_radius_spin.setSuffix(" m")
        self.phase_radius_spin.setValue(0.03)
        pf.addRow("导线半径:", self.phase_radius_spin)

        self.phase_dc_resistance_spin = QDoubleSpinBox()
        self.phase_dc_resistance_spin.setRange(0.0001, 1000)
        self.phase_dc_resistance_spin.setDecimals(5)
        self.phase_dc_resistance_spin.setSuffix(" Ω/km")
        self.phase_dc_resistance_spin.setValue(0.05741)
        pf.addRow("直流电阻:", self.phase_dc_resistance_spin)

        self.phase_mu_r_spin = QDoubleSpinBox()
        self.phase_mu_r_spin.setRange(0.1, 1000)
        self.phase_mu_r_spin.setDecimals(2)
        self.phase_mu_r_spin.setValue(1.0)
        pf.addRow("相对磁导率:", self.phase_mu_r_spin)

        self.phase_sag_spin = QDoubleSpinBox()
        self.phase_sag_spin.setRange(0, 100)
        self.phase_sag_spin.setDecimals(2)
        self.phase_sag_spin.setSuffix(" m")
        self.phase_sag_spin.setValue(9.2)
        pf.addRow("弧垂:", self.phase_sag_spin)

        layout.addWidget(phase_params)

        # 分裂导线
        bundle_group = QGroupBox("分裂导线")
        bf = QFormLayout(bundle_group)

        self.bundle_n_spin = QSpinBox()
        self.bundle_n_spin.setRange(1, 12)
        self.bundle_n_spin.setValue(4)
        bf.addRow("分裂数:", self.bundle_n_spin)

        self.bundle_spacing_spin = QDoubleSpinBox()
        self.bundle_spacing_spin.setRange(0, 10)
        self.bundle_spacing_spin.setDecimals(3)
        self.bundle_spacing_spin.setSuffix(" m")
        self.bundle_spacing_spin.setValue(0.5)
        bf.addRow("分裂间距:", self.bundle_spacing_spin)

        layout.addWidget(bundle_group)

        # 导线坐标表
        pos_group = QGroupBox("导线坐标（X, 塔顶高度）")
        pos_layout = QVBoxLayout(pos_group)

        self.phase_table = QTableWidget(0, 2)
        self.phase_table.setHorizontalHeaderLabels(["X 坐标 (m)", "塔顶高度 (m)"])
        self.phase_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.phase_table.setMinimumHeight(150)
        pos_layout.addWidget(self.phase_table)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ 添加导线")
        add_btn.clicked.connect(lambda: (self._add_table_row(self.phase_table, [-11.777, 41.87]),
                                          self._on_param_changed_for_preview()))
        del_btn = QPushButton("- 删除选中")
        del_btn.clicked.connect(lambda: (self._del_table_row(self.phase_table),
                                          self._on_param_changed_for_preview()))
        btn_row.addWidget(add_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        pos_layout.addLayout(btn_row)

        layout.addWidget(pos_group)
        layout.addStretch()
        return widget

    # ================================================================
    #  地线配置
    # ================================================================

    def _build_gw_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 地线参数
        gw_params = QGroupBox("地线物理参数")
        gf = QFormLayout(gw_params)

        self.gw_radius_spin = QDoubleSpinBox()
        self.gw_radius_spin.setRange(0.001, 1.0)
        self.gw_radius_spin.setDecimals(5)
        self.gw_radius_spin.setSuffix(" m")
        self.gw_radius_spin.setValue(0.00875)
        gf.addRow("地线半径:", self.gw_radius_spin)

        self.gw_dc_resistance_spin = QDoubleSpinBox()
        self.gw_dc_resistance_spin.setRange(0.0001, 1000)
        self.gw_dc_resistance_spin.setDecimals(4)
        self.gw_dc_resistance_spin.setSuffix(" Ω/km")
        self.gw_dc_resistance_spin.setValue(0.7098)
        gf.addRow("直流电阻:", self.gw_dc_resistance_spin)

        self.gw_mu_r_spin = QDoubleSpinBox()
        self.gw_mu_r_spin.setRange(0.1, 1000)
        self.gw_mu_r_spin.setDecimals(2)
        self.gw_mu_r_spin.setValue(1.0)
        gf.addRow("相对磁导率:", self.gw_mu_r_spin)

        self.gw_sag_spin = QDoubleSpinBox()
        self.gw_sag_spin.setRange(0, 100)
        self.gw_sag_spin.setDecimals(2)
        self.gw_sag_spin.setSuffix(" m")
        self.gw_sag_spin.setValue(6.1)
        gf.addRow("弧垂:", self.gw_sag_spin)

        layout.addWidget(gw_params)

        # Kron 消元
        self.eliminate_gw_check = QCheckBox("Kron 消元（消去地线）")
        self.eliminate_gw_check.setChecked(False)
        layout.addWidget(self.eliminate_gw_check)

        # 地线坐标表
        pos_group = QGroupBox("地线坐标（X, 塔顶高度）")
        pos_layout = QVBoxLayout(pos_group)

        self.gw_table = QTableWidget(0, 2)
        self.gw_table.setHorizontalHeaderLabels(["X 坐标 (m)", "塔顶高度 (m)"])
        self.gw_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.gw_table.setMinimumHeight(120)
        pos_layout.addWidget(self.gw_table)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ 添加地线")
        add_btn.clicked.connect(lambda: (self._add_table_row(self.gw_table, [-19.25, 63.0]),
                                          self._on_param_changed_for_preview()))
        del_btn = QPushButton("- 删除选中")
        del_btn.clicked.connect(lambda: (self._del_table_row(self.gw_table),
                                          self._on_param_changed_for_preview()))
        btn_row.addWidget(add_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        pos_layout.addLayout(btn_row)

        layout.addWidget(pos_group)
        layout.addStretch()
        return widget

    # ================================================================
    #  拟合配置
    # ================================================================

    def _build_fitting_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        form = QFormLayout()
        form.setSpacing(8)

        # Yc 拟合
        yc_group = QGroupBox("Yc (特性导纳) 拟合")
        yc_form = QFormLayout(yc_group)
        self.yc_poles_min_spin = QSpinBox()
        self.yc_poles_min_spin.setRange(2, 50)
        self.yc_poles_min_spin.setValue(6)
        yc_form.addRow("最小极点数:", self.yc_poles_min_spin)

        self.yc_poles_max_spin = QSpinBox()
        self.yc_poles_max_spin.setRange(2, 50)
        self.yc_poles_max_spin.setValue(20)
        yc_form.addRow("最大极点数:", self.yc_poles_max_spin)

        self.yc_error_spin = QDoubleSpinBox()
        self.yc_error_spin.setRange(0.0001, 1.0)
        self.yc_error_spin.setDecimals(4)
        self.yc_error_spin.setValue(0.002)
        yc_form.addRow("目标误差:", self.yc_error_spin)
        layout.addWidget(yc_group)

        # H 拟合
        h_group = QGroupBox("H (传播函数) 拟合")
        h_form = QFormLayout(h_group)
        self.h_poles_min_spin = QSpinBox()
        self.h_poles_min_spin.setRange(2, 50)
        self.h_poles_min_spin.setValue(8)
        h_form.addRow("最小极点数:", self.h_poles_min_spin)

        self.h_poles_max_spin = QSpinBox()
        self.h_poles_max_spin.setRange(2, 50)
        self.h_poles_max_spin.setValue(20)
        h_form.addRow("最大极点数:", self.h_poles_max_spin)

        self.h_error_spin = QDoubleSpinBox()
        self.h_error_spin.setRange(0.0001, 1.0)
        self.h_error_spin.setDecimals(4)
        self.h_error_spin.setValue(0.002)
        h_form.addRow("目标误差:", self.h_error_spin)
        layout.addWidget(h_group)

        # 频率扫描
        freq_group = QGroupBox("频率扫描范围")
        freq_form = QFormLayout(freq_group)
        self.freq_min_spin = QDoubleSpinBox()
        self.freq_min_spin.setRange(1e-6, 1e6)
        self.freq_min_spin.setDecimals(4)
        self.freq_min_spin.setValue(0.01)
        self.freq_min_spin.setSuffix(" Hz")
        freq_form.addRow("起始频率:", self.freq_min_spin)

        self.freq_max_spin = QDoubleSpinBox()
        self.freq_max_spin.setRange(1, 1e9)
        self.freq_max_spin.setDecimals(0)
        self.freq_max_spin.setValue(100000)
        self.freq_max_spin.setSuffix(" Hz")
        freq_form.addRow("终止频率:", self.freq_max_spin)

        self.freq_n_spin = QSpinBox()
        self.freq_n_spin.setRange(10, 10000)
        self.freq_n_spin.setValue(200)
        freq_form.addRow("频率增量数:", self.freq_n_spin)
        layout.addWidget(freq_group)

        layout.addStretch()
        return widget

    # ================================================================
    #  截面预览选项卡
    # ================================================================

    def _build_preview_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 截面图
        self._preview_canvas = LCPCrossSectionCanvas(self, width=6, height=4.5)
        layout.addWidget(self._preview_canvas, stretch=1)

        # 参数摘要
        self._preview_summary = QLabel()
        self._preview_summary.setWordWrap(True)
        self._preview_summary.setStyleSheet(
            "font-size: 11px; color: #475569; background: #f8fafc; "
            "padding: 4px; border: 1px solid #e2e8f0; border-radius: 3px;"
        )
        self._preview_summary.setMaximumHeight(60)
        layout.addWidget(self._preview_summary)

        return widget

    # ================================================================
    #  表格操作辅助
    # ================================================================

    @staticmethod
    def _add_table_row(table: QTableWidget, values: list = None):
        row = table.rowCount()
        table.insertRow(row)
        if values:
            for col, v in enumerate(values):
                item = QTableWidgetItem(str(v))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(row, col, item)

    @staticmethod
    def _del_table_row(table: QTableWidget):
        rows = set(item.row() for item in table.selectedItems())
        for row in sorted(rows, reverse=True):
            table.removeRow(row)

    # ================================================================
    #  预览信号连接
    # ================================================================

    def _connect_preview_signals(self):
        """连接所有影响预览的信号到去抖处理器。"""
        # 表格编辑
        self.phase_table.cellChanged.connect(self._on_param_changed_for_preview)
        self.gw_table.cellChanged.connect(self._on_param_changed_for_preview)

        # 复选框
        self.eliminate_gw_check.toggled.connect(self._on_param_changed_for_preview)

        # 导线参数 spinbox
        self.phase_radius_spin.valueChanged.connect(self._on_param_changed_for_preview)
        self.phase_sag_spin.valueChanged.connect(self._on_param_changed_for_preview)
        self.bundle_n_spin.valueChanged.connect(self._on_param_changed_for_preview)
        self.bundle_spacing_spin.valueChanged.connect(self._on_param_changed_for_preview)

        # 地线参数 spinbox
        self.gw_radius_spin.valueChanged.connect(self._on_param_changed_for_preview)
        self.gw_sag_spin.valueChanged.connect(self._on_param_changed_for_preview)

        # 土壤参数
        self.ground_resistivity_spin.valueChanged.connect(self._on_param_changed_for_preview)

        # 切换到预览选项卡时也刷新
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index: int):
        """切换到预览选项卡时立即刷新。"""
        if index == 4:  # 截面预览选项卡
            self._refresh_previews()

    # ================================================================
    #  端口预览 + 截面预览刷新
    # ================================================================

    def _refresh_previews(self):
        """更新端口映射预览和截面预览。"""
        self._update_port_preview()
        self._refresh_cross_section_preview()

    def _update_port_preview(self):
        """更新端口映射文本。"""
        n_phases = self.phase_table.rowCount()
        n_gw = self.gw_table.rowCount()
        eliminate = self.eliminate_gw_check.isChecked()

        lines = [f"导线数: {n_phases}，地线数: {n_gw}"]
        lines.append("")

        # k 端端口
        k_ports = []
        for i in range(n_phases):
            k_ports.append(f"nk_{i} (Phase_{i+1})")
        if not eliminate:
            for i in range(n_gw):
                k_ports.append(f"nk_{n_phases + i} (GW_{i+1})")

        # m 端端口
        m_ports = []
        for i in range(n_phases):
            m_ports.append(f"nm_{i} (Phase_{i+1})")
        if not eliminate:
            for i in range(n_gw):
                m_ports.append(f"nm_{n_phases + i} (GW_{i+1})")

        lines.append("K 端端口:")
        for p in k_ports:
            lines.append(f"  {p}")
        lines.append("")
        lines.append("M 端端口:")
        for p in m_ports:
            lines.append(f"  {p}")

        self.port_preview_label.setText("\n".join(lines))

    def _refresh_cross_section_preview(self):
        """使用当前对话框值重绘截面预览。"""
        config = self._get_current_config()
        self._preview_canvas.draw_ohl(config)
        self._preview_summary.setText(
            f"架空线 | 长度: {config.get('length', 0):.1f}m | "
            f"导线: {len(config.get('phase_positions', []))} | "
            f"地线: {len(config.get('gw_positions', []))}"
        )

    # ================================================================
    #  轻量级配置读取（用于预览，不走完整 get_config 校验）
    # ================================================================

    def _get_current_config(self) -> dict:
        """读取当前 UI 控件值，用于预览渲染。"""
        phase_positions = []
        for row in range(self.phase_table.rowCount()):
            x_item = self.phase_table.item(row, 0)
            h_item = self.phase_table.item(row, 1)
            if x_item and h_item:
                try:
                    phase_positions.append(
                        (float(x_item.text()), float(h_item.text()))
                    )
                except ValueError:
                    pass

        gw_positions = []
        for row in range(self.gw_table.rowCount()):
            x_item = self.gw_table.item(row, 0)
            h_item = self.gw_table.item(row, 1)
            if x_item and h_item:
                try:
                    gw_positions.append(
                        (float(x_item.text()), float(h_item.text()))
                    )
                except ValueError:
                    pass

        return {
            'phase_positions': phase_positions,
            'phase_radius': self.phase_radius_spin.value(),
            'phase_sag': self.phase_sag_spin.value(),
            'phase_bundle_n': self.bundle_n_spin.value(),
            'phase_bundle_spacing': self.bundle_spacing_spin.value(),
            'gw_positions': gw_positions,
            'gw_radius': self.gw_radius_spin.value(),
            'gw_sag': self.gw_sag_spin.value(),
            'eliminate_ground_wires': self.eliminate_gw_check.isChecked(),
            'ground_resistivity': self.ground_resistivity_spin.value(),
            'length': self.length_spin.value(),
        }

    # ================================================================
    #  数据加载
    # ================================================================

    def _load_from_params(self, params: dict):
        """从现有参数字典加载到 UI"""
        # 临时阻塞信号，避免加载时触发过多预览刷新
        self._preview_timer.blockSignals(True)

        self.length_spin.setValue(params.get('length', 900.0))
        self.ground_resistivity_spin.setValue(params.get('ground_resistivity', 1000.0))
        self.ground_permeability_spin.setValue(params.get('ground_permeability', 1.0))
        self.ground_permittivity_spin.setValue(params.get('ground_permittivity', 1.0))
        self.force_rebuild_check.setChecked(params.get('force_rebuild', True))

        # 导线参数
        self.phase_radius_spin.setValue(params.get('phase_radius', 0.03))
        self.phase_dc_resistance_spin.setValue(params.get('phase_dc_resistance', 0.05741))
        self.phase_mu_r_spin.setValue(params.get('phase_mu_r', 1.0))
        self.phase_sag_spin.setValue(params.get('phase_sag', 9.2))
        self.bundle_n_spin.setValue(params.get('phase_bundle_n', 4))
        self.bundle_spacing_spin.setValue(params.get('phase_bundle_spacing', 0.5))

        # 导线坐标
        phase_positions = params.get('phase_positions', [
            (-11.777, 41.87), (11.777, 41.87)
        ])
        for pos in phase_positions:
            self._add_table_row(self.phase_table, [pos[0], pos[1]])

        # 地线参数
        self.gw_radius_spin.setValue(params.get('gw_radius', 0.00875))
        self.gw_dc_resistance_spin.setValue(params.get('gw_dc_resistance', 0.7098))
        self.gw_mu_r_spin.setValue(params.get('gw_mu_r', 1.0))
        self.gw_sag_spin.setValue(params.get('gw_sag', 6.1))
        self.eliminate_gw_check.setChecked(params.get('eliminate_ground_wires', False))

        # 地线坐标
        gw_positions = params.get('gw_positions', [
            (-19.25, 63.0), (19.25, 63.0)
        ])
        for pos in gw_positions:
            self._add_table_row(self.gw_table, [pos[0], pos[1]])

        # 拟合参数
        self.yc_poles_min_spin.setValue(params.get('Yc_poles_min', 6))
        self.yc_poles_max_spin.setValue(params.get('Yc_poles_max', 20))
        self.yc_error_spin.setValue(params.get('Yc_target_error', 0.002))
        self.h_poles_min_spin.setValue(params.get('H_poles_min', 8))
        self.h_poles_max_spin.setValue(params.get('H_poles_max', 20))
        self.h_error_spin.setValue(params.get('H_target_error', 0.002))
        self.freq_min_spin.setValue(params.get('freq_min', 0.01))
        self.freq_max_spin.setValue(params.get('freq_max', 100000))
        self.freq_n_spin.setValue(params.get('n_freq_increments', 200))

        self._preview_timer.blockSignals(False)

        # 初始刷新
        self._update_port_preview()

    # ================================================================
    #  导出配置
    # ================================================================

    def get_config(self) -> dict:
        """导出为 config 字典，可传递给 solver.add_lcp_ohl_line()"""
        phase_positions = []
        for row in range(self.phase_table.rowCount()):
            x_item = self.phase_table.item(row, 0)
            h_item = self.phase_table.item(row, 1)
            if x_item and h_item:
                try:
                    phase_positions.append(
                        (float(x_item.text()), float(h_item.text()))
                    )
                except ValueError:
                    pass

        gw_positions = []
        for row in range(self.gw_table.rowCount()):
            x_item = self.gw_table.item(row, 0)
            h_item = self.gw_table.item(row, 1)
            if x_item and h_item:
                try:
                    gw_positions.append(
                        (float(x_item.text()), float(h_item.text()))
                    )
                except ValueError:
                    pass

        config = {
            # 通用
            'length': self.length_spin.value(),
            'ground_resistivity': self.ground_resistivity_spin.value(),
            'ground_permeability': self.ground_permeability_spin.value(),
            'ground_permittivity': self.ground_permittivity_spin.value(),
            'force_rebuild': self.force_rebuild_check.isChecked(),

            # 导线
            'n_phases': len(phase_positions),
            'phase_positions': phase_positions,
            'phase_radius': self.phase_radius_spin.value(),
            'phase_dc_resistance': self.phase_dc_resistance_spin.value(),
            'phase_mu_r': self.phase_mu_r_spin.value(),
            'phase_sag': self.phase_sag_spin.value(),
            'phase_bundle_n': self.bundle_n_spin.value(),
            'phase_bundle_spacing': self.bundle_spacing_spin.value(),

            # 地线
            'n_gw': len(gw_positions),
            'gw_positions': gw_positions,
            'gw_radius': self.gw_radius_spin.value(),
            'gw_dc_resistance': self.gw_dc_resistance_spin.value(),
            'gw_mu_r': self.gw_mu_r_spin.value(),
            'gw_sag': self.gw_sag_spin.value(),
            'eliminate_ground_wires': self.eliminate_gw_check.isChecked(),

            # 拟合
            'Yc_poles_min': self.yc_poles_min_spin.value(),
            'Yc_poles_max': self.yc_poles_max_spin.value(),
            'Yc_target_error': self.yc_error_spin.value(),
            'H_poles_min': self.h_poles_min_spin.value(),
            'H_poles_max': self.h_poles_max_spin.value(),
            'H_target_error': self.h_error_spin.value(),
            'freq_min': self.freq_min_spin.value(),
            'freq_max': self.freq_max_spin.value(),
            'n_freq_increments': self.freq_n_spin.value(),
        }

        return config


# ================================================================
#  LCPSingleCableDialog — 单芯电缆
# ================================================================

class LCPSingleCableDialog(QDialog, _PreviewDebounceMixin, _LCPFittingMixin):
    """LCP 单芯电缆参数对话框

    支持多根电缆的动态配置，每根电缆包含芯线/护套/铠装参数。
    包含2个选项卡：参数配置、截面预览
    """

    def __init__(self, current_params: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LCP 单芯电缆参数配置")
        self.setMinimumSize(750, 600)
        self._params = current_params
        self._setup_ui()
        self._connect_preview_signals()
        self._init_preview_timer()
        self._load_from_params(current_params)

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # ====== 选项卡 ======
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.tabs.addTab(self._build_params_tab(), "参数配置")
        self.tabs.addTab(self._build_fitting_tab(), "拟合配置")
        self.tabs.addTab(self._build_preview_tab(), "截面预览")

        # ====== 按钮 ======
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _build_params_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        form = QFormLayout()

        # 电缆数量
        self.n_cables_spin = QSpinBox()
        self.n_cables_spin.setRange(1, 20)
        self.n_cables_spin.setValue(self._params.get('n_cables', 1))
        self.n_cables_spin.valueChanged.connect(self._rebuild_cable_table)
        form.addRow("电缆数量:", self.n_cables_spin)

        # 长度
        self.length_spin = QDoubleSpinBox()
        self.length_spin.setRange(0.1, 1e9)
        self.length_spin.setDecimals(1)
        self.length_spin.setSuffix(" m")
        self.length_spin.setValue(self._params.get('length', 1000.0))
        form.addRow("线路长度:", self.length_spin)

        # 土壤参数
        self.soil_rho_spin = QDoubleSpinBox()
        self.soil_rho_spin.setRange(0.01, 1e8)
        self.soil_rho_spin.setDecimals(2)
        self.soil_rho_spin.setSuffix(" Ω·m")
        self.soil_rho_spin.setValue(100.0)
        form.addRow("土壤电阻率:", self.soil_rho_spin)

        self.soil_eps_spin = QDoubleSpinBox()
        self.soil_eps_spin.setRange(0.1, 100)
        self.soil_eps_spin.setDecimals(2)
        self.soil_eps_spin.setValue(10.0)
        form.addRow("土壤相对介电常数:", self.soil_eps_spin)

        self.force_rebuild_check = QCheckBox("强制重建")
        self.force_rebuild_check.setChecked(True)
        form.addRow(self.force_rebuild_check)

        layout.addLayout(form)

        # 电缆参数表
        cable_group = QGroupBox("电缆参数（每行一根电缆）")
        cable_layout = QVBoxLayout(cable_group)

        self.cable_table = QTableWidget(0, 8)
        self.cable_table.setHorizontalHeaderLabels([
            "芯线半径(m)", "芯线电阻率(Ω·m)",
            "绝缘外半径(m)", "绝缘εr",
            "护套外半径(m)", "护套电阻率(Ω·m)",
            "铠装外半径(m)", "外护套半径(m)",
        ])
        self.cable_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.cable_table.setMinimumHeight(200)
        cable_layout.addWidget(self.cable_table)

        # 埋深/水平位置表
        pos_group = QGroupBox("埋设位置")
        pos_layout = QVBoxLayout(pos_group)
        self.pos_table = QTableWidget(0, 2)
        self.pos_table.setHorizontalHeaderLabels(["埋深 (m)", "水平位置 (m)"])
        self.pos_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        pos_layout.addWidget(self.pos_table)

        layout.addWidget(cable_group)
        layout.addWidget(pos_group)

        self._rebuild_cable_table(self.n_cables_spin.value())

        return widget

    def _build_preview_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 端口映射预览
        port_group = QGroupBox("端口映射预览")
        port_layout = QVBoxLayout(port_group)
        self.port_preview_label = QLabel("根据电缆参数自动生成")
        self.port_preview_label.setWordWrap(True)
        self.port_preview_label.setStyleSheet("color: #64748b; font-family: Consolas;")
        port_layout.addWidget(self.port_preview_label)
        layout.addWidget(port_group)

        # 截面图
        self._preview_canvas = LCPCrossSectionCanvas(self, width=6, height=4.5)
        layout.addWidget(self._preview_canvas, stretch=1)

        # 参数摘要
        self._preview_summary = QLabel()
        self._preview_summary.setWordWrap(True)
        self._preview_summary.setStyleSheet(
            "font-size: 11px; color: #475569; background: #f8fafc; "
            "padding: 4px; border: 1px solid #e2e8f0; border-radius: 3px;"
        )
        self._preview_summary.setMaximumHeight(50)
        layout.addWidget(self._preview_summary)

        return widget

    # ================================================================
    #  预览信号连接
    # ================================================================

    def _connect_preview_signals(self):
        self.n_cables_spin.valueChanged.connect(self._on_param_changed_for_preview)
        self.cable_table.cellChanged.connect(self._on_param_changed_for_preview)
        self.pos_table.cellChanged.connect(self._on_param_changed_for_preview)
        self.length_spin.valueChanged.connect(self._on_param_changed_for_preview)
        self.soil_rho_spin.valueChanged.connect(self._on_param_changed_for_preview)
        self.soil_eps_spin.valueChanged.connect(self._on_param_changed_for_preview)
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index: int):
        if index == 2:  # 截面预览选项卡
            self._refresh_previews()

    # ================================================================
    #  预览刷新
    # ================================================================

    def _refresh_previews(self):
        self._update_port_preview()
        self._refresh_cross_section_preview()

    def _update_port_preview(self):
        """更新端口映射文本。"""
        from models.component_lib import ComponentType
        config = self._get_current_config()
        text = build_port_preview_text(ComponentType.LCP_SINGLE_CABLE, config)
        self.port_preview_label.setText(text)

    def _refresh_cross_section_preview(self):
        config = self._get_current_config()
        self._preview_canvas.draw_single_cable(config)
        n = config.get('n_cables', len(config.get('cables', [])))
        self._preview_summary.setText(
            f"单芯电缆 | 长度: {config.get('length', 0):.1f}m | 电缆数: {n}"
        )

    def _get_current_config(self) -> dict:
        """轻量级读取当前 UI 值用于预览。"""
        cables = []
        for row in range(self.cable_table.rowCount()):
            try:
                cable = {
                    'core_radius': float(self.cable_table.item(row, 0).text()),
                    'core_resistivity': float(self.cable_table.item(row, 1).text()),
                    'insulation_outer_radius': float(self.cable_table.item(row, 2).text()),
                    'insulation_eps_r': float(self.cable_table.item(row, 3).text()),
                    'sheath_outer_radius': float(self.cable_table.item(row, 4).text()),
                    'sheath_resistivity': float(self.cable_table.item(row, 5).text()),
                    'armor_outer_radius': float(self.cable_table.item(row, 6).text()),
                    'outer_jacket_radius': float(self.cable_table.item(row, 7).text()),
                }
                d_item = self.pos_table.item(row, 0)
                x_item = self.pos_table.item(row, 1)
                cable['burial_depth'] = float(d_item.text()) if d_item else 1.0
                cable['horizontal_pos'] = float(x_item.text()) if x_item else 0.0
                cables.append(cable)
            except (ValueError, AttributeError):
                pass
        return {
            'n_cables': self.n_cables_spin.value(),
            'length': self.length_spin.value(),
            'soil_resistivity': self.soil_rho_spin.value(),
            'soil_permittivity': self.soil_eps_spin.value(),
            'cables': cables,
        }

    # ================================================================
    #  表格重建
    # ================================================================

    def _rebuild_cable_table(self, n_cables: int):
        """根据电缆数量重建表格"""
        # 保留已有数据
        old_data = []
        for row in range(self.cable_table.rowCount()):
            row_data = []
            for col in range(8):
                item = self.cable_table.item(row, col)
                row_data.append(item.text() if item else "")
            old_data.append(row_data)

        old_pos = []
        for row in range(self.pos_table.rowCount()):
            d_item = self.pos_table.item(row, 0)
            x_item = self.pos_table.item(row, 1)
            old_pos.append([
                d_item.text() if d_item else "1.0",
                x_item.text() if x_item else "0.0",
            ])

        # 默认值
        default_row = ["0.02", "1.7e-8", "0.035", "3.5", "0.04", "2.2e-7", "0.045", "0.05"]

        self.cable_table.setRowCount(n_cables)
        for row in range(n_cables):
            for col in range(8):
                if row < len(old_data) and col < len(old_data[row]):
                    text = old_data[row][col]
                else:
                    text = default_row[col]
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.cable_table.setItem(row, col, item)

        self.pos_table.setRowCount(n_cables)
        for row in range(n_cables):
            for col in range(2):
                if row < len(old_pos):
                    text = old_pos[row][col]
                else:
                    text = "1.0" if col == 0 else str(row * 0.5)
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.pos_table.setItem(row, col, item)

    def _load_from_params(self, params: dict):
        self._preview_timer.blockSignals(True)
        self.soil_rho_spin.setValue(params.get('soil_resistivity', 100.0))
        self.soil_eps_spin.setValue(params.get('soil_permittivity', 10.0))
        self._load_fitting_from_params(params)
        self._preview_timer.blockSignals(False)

    def get_config(self) -> dict:
        cables = []
        for row in range(self.cable_table.rowCount()):
            try:
                cable = {
                    'core_radius': float(self.cable_table.item(row, 0).text()),
                    'core_resistivity': float(self.cable_table.item(row, 1).text()),
                    'insulation_outer_radius': float(self.cable_table.item(row, 2).text()),
                    'insulation_eps_r': float(self.cable_table.item(row, 3).text()),
                    'sheath_outer_radius': float(self.cable_table.item(row, 4).text()),
                    'sheath_resistivity': float(self.cable_table.item(row, 5).text()),
                    'armor_outer_radius': float(self.cable_table.item(row, 6).text()),
                    'outer_jacket_radius': float(self.cable_table.item(row, 7).text()),
                }
                # 添加位置信息
                d_item = self.pos_table.item(row, 0)
                x_item = self.pos_table.item(row, 1)
                cable['burial_depth'] = float(d_item.text()) if d_item else 1.0
                cable['horizontal_pos'] = float(x_item.text()) if x_item else 0.0
                cables.append(cable)
            except (ValueError, AttributeError):
                pass

        config = {
            'n_cables': self.n_cables_spin.value(),
            'length': self.length_spin.value(),
            'soil_resistivity': self.soil_rho_spin.value(),
            'soil_permittivity': self.soil_eps_spin.value(),
            'force_rebuild': self.force_rebuild_check.isChecked(),
            'cables': cables,
        }
        config.update(self._fitting_config())
        return config


# ================================================================
#  LCPThreeCoreCableDialog — 三芯电缆
# ================================================================

class LCPThreeCoreCableDialog(QDialog, _PreviewDebounceMixin, _LCPFittingMixin):
    """LCP 三芯电缆参数对话框

    管道内三芯结构，导体按角度排列。
    包含2个选项卡：参数配置、截面预览
    """

    def __init__(self, current_params: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LCP 三芯电缆参数配置")
        self.setMinimumSize(700, 600)
        self._params = current_params
        self._setup_ui()
        self._connect_preview_signals()
        self._init_preview_timer()
        self._load_from_params(current_params)

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # ====== 选项卡 ======
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.tabs.addTab(self._build_params_tab(), "参数配置")
        self.tabs.addTab(self._build_fitting_tab(), "拟合配置")
        self.tabs.addTab(self._build_preview_tab(), "截面预览")

        # ====== 按钮 ======
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _build_params_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        form = QFormLayout()

        # 长度
        self.length_spin = QDoubleSpinBox()
        self.length_spin.setRange(0.1, 1e9)
        self.length_spin.setDecimals(1)
        self.length_spin.setSuffix(" m")
        self.length_spin.setValue(1000.0)
        form.addRow("线路长度:", self.length_spin)

        self.force_rebuild_check = QCheckBox("强制重建")
        self.force_rebuild_check.setChecked(True)
        form.addRow(self.force_rebuild_check)

        layout.addLayout(form)

        # 管道参数
        pipe_group = QGroupBox("管道参数")
        pf = QFormLayout(pipe_group)

        self.pipe_inner_radius_spin = QDoubleSpinBox()
        self.pipe_inner_radius_spin.setRange(0.001, 10)
        self.pipe_inner_radius_spin.setDecimals(5)
        self.pipe_inner_radius_spin.setSuffix(" m")
        self.pipe_inner_radius_spin.setValue(0.065)
        pf.addRow("管道内半径:", self.pipe_inner_radius_spin)

        self.pipe_outer_radius_spin = QDoubleSpinBox()
        self.pipe_outer_radius_spin.setRange(0.001, 10)
        self.pipe_outer_radius_spin.setDecimals(5)
        self.pipe_outer_radius_spin.setSuffix(" m")
        self.pipe_outer_radius_spin.setValue(0.07)
        pf.addRow("管道外半径:", self.pipe_outer_radius_spin)

        self.pipe_resistivity_spin = QDoubleSpinBox()
        self.pipe_resistivity_spin.setRange(1e-10, 1)
        self.pipe_resistivity_spin.setDecimals(10)
        self.pipe_resistivity_spin.setSuffix(" Ω·m")
        self.pipe_resistivity_spin.setValue(1.7e-7)
        pf.addRow("管道电阻率:", self.pipe_resistivity_spin)

        self.pipe_mu_r_spin = QDoubleSpinBox()
        self.pipe_mu_r_spin.setRange(0.1, 10000)
        self.pipe_mu_r_spin.setDecimals(2)
        self.pipe_mu_r_spin.setValue(1.0)
        pf.addRow("管道相对磁导率:", self.pipe_mu_r_spin)

        layout.addWidget(pipe_group)

        # 导体参数
        cond_group = QGroupBox("导体参数（三相对称）")
        cf = QFormLayout(cond_group)

        self.core_radius_spin = QDoubleSpinBox()
        self.core_radius_spin.setRange(0.001, 1)
        self.core_radius_spin.setDecimals(5)
        self.core_radius_spin.setSuffix(" m")
        self.core_radius_spin.setValue(0.0165)
        cf.addRow("芯线半径:", self.core_radius_spin)

        self.core_resistivity_spin = QDoubleSpinBox()
        self.core_resistivity_spin.setRange(1e-10, 1)
        self.core_resistivity_spin.setDecimals(10)
        self.core_resistivity_spin.setSuffix(" Ω·m")
        self.core_resistivity_spin.setValue(1.7e-8)
        cf.addRow("芯线电阻率:", self.core_resistivity_spin)

        self.insulation_radius_spin = QDoubleSpinBox()
        self.insulation_radius_spin.setRange(0.001, 1)
        self.insulation_radius_spin.setDecimals(5)
        self.insulation_radius_spin.setSuffix(" m")
        self.insulation_radius_spin.setValue(0.027)
        cf.addRow("绝缘外半径:", self.insulation_radius_spin)

        self.insulation_eps_r_spin = QDoubleSpinBox()
        self.insulation_eps_r_spin.setRange(0.1, 100)
        self.insulation_eps_r_spin.setDecimals(2)
        self.insulation_eps_r_spin.setValue(3.5)
        cf.addRow("绝缘εr:", self.insulation_eps_r_spin)

        self.sheath_radius_spin = QDoubleSpinBox()
        self.sheath_radius_spin.setRange(0.001, 1)
        self.sheath_radius_spin.setDecimals(5)
        self.sheath_radius_spin.setSuffix(" m")
        self.sheath_radius_spin.setValue(0.03)
        cf.addRow("护套外半径:", self.sheath_radius_spin)

        self.sheath_resistivity_spin = QDoubleSpinBox()
        self.sheath_resistivity_spin.setRange(1e-10, 1)
        self.sheath_resistivity_spin.setDecimals(10)
        self.sheath_resistivity_spin.setSuffix(" Ω·m")
        self.sheath_resistivity_spin.setValue(2.2e-7)
        cf.addRow("护套电阻率:", self.sheath_resistivity_spin)

        layout.addWidget(cond_group)

        # 导体位置
        pos_group = QGroupBox("导体排列")
        posf = QFormLayout(pos_group)

        self.dist_from_center_spin = QDoubleSpinBox()
        self.dist_from_center_spin.setRange(0.001, 1)
        self.dist_from_center_spin.setDecimals(5)
        self.dist_from_center_spin.setSuffix(" m")
        self.dist_from_center_spin.setValue(0.03415)
        posf.addRow("距管中心距离:", self.dist_from_center_spin)

        self.angles_edit = QLineEdit("270, 30, 150")
        self.angles_edit.setToolTip("三相角度，逗号分隔（度）")
        posf.addRow("角度位置(°):", self.angles_edit)

        layout.addWidget(pos_group)

        # 土壤参数
        soil_group = QGroupBox("土壤参数")
        sf = QFormLayout(soil_group)

        self.soil_rho_spin = QDoubleSpinBox()
        self.soil_rho_spin.setRange(0.01, 1e8)
        self.soil_rho_spin.setDecimals(2)
        self.soil_rho_spin.setSuffix(" Ω·m")
        self.soil_rho_spin.setValue(100.0)
        sf.addRow("电阻率:", self.soil_rho_spin)

        self.soil_eps_spin = QDoubleSpinBox()
        self.soil_eps_spin.setRange(0.1, 100)
        self.soil_eps_spin.setDecimals(2)
        self.soil_eps_spin.setValue(10.0)
        sf.addRow("相对介电常数:", self.soil_eps_spin)

        self.burial_depth_spin = QDoubleSpinBox()
        self.burial_depth_spin.setRange(0.01, 100)
        self.burial_depth_spin.setDecimals(2)
        self.burial_depth_spin.setSuffix(" m")
        self.burial_depth_spin.setValue(1.0)
        sf.addRow("埋深:", self.burial_depth_spin)

        layout.addWidget(soil_group)
        return widget

    def _build_preview_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 端口映射预览
        port_group = QGroupBox("端口映射预览")
        port_layout = QVBoxLayout(port_group)
        self.port_preview_label = QLabel("根据参数自动生成")
        self.port_preview_label.setWordWrap(True)
        self.port_preview_label.setStyleSheet("color: #64748b; font-family: Consolas;")
        port_layout.addWidget(self.port_preview_label)
        layout.addWidget(port_group)

        # 截面图
        self._preview_canvas = LCPCrossSectionCanvas(self, width=6, height=4.5)
        layout.addWidget(self._preview_canvas, stretch=1)

        # 参数摘要
        self._preview_summary = QLabel()
        self._preview_summary.setWordWrap(True)
        self._preview_summary.setStyleSheet(
            "font-size: 11px; color: #475569; background: #f8fafc; "
            "padding: 4px; border: 1px solid #e2e8f0; border-radius: 3px;"
        )
        self._preview_summary.setMaximumHeight(50)
        layout.addWidget(self._preview_summary)

        return widget

    # ================================================================
    #  预览信号连接
    # ================================================================

    def _connect_preview_signals(self):
        self.pipe_inner_radius_spin.valueChanged.connect(self._on_param_changed_for_preview)
        self.pipe_outer_radius_spin.valueChanged.connect(self._on_param_changed_for_preview)
        self.core_radius_spin.valueChanged.connect(self._on_param_changed_for_preview)
        self.insulation_radius_spin.valueChanged.connect(self._on_param_changed_for_preview)
        self.sheath_radius_spin.valueChanged.connect(self._on_param_changed_for_preview)
        self.dist_from_center_spin.valueChanged.connect(self._on_param_changed_for_preview)
        self.angles_edit.textChanged.connect(self._on_param_changed_for_preview)
        self.burial_depth_spin.valueChanged.connect(self._on_param_changed_for_preview)
        self.soil_rho_spin.valueChanged.connect(self._on_param_changed_for_preview)
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index: int):
        if index == 2:  # 截面预览选项卡
            self._refresh_previews()

    # ================================================================
    #  预览刷新
    # ================================================================

    def _refresh_previews(self):
        self._update_port_preview()
        self._refresh_cross_section_preview()

    def _update_port_preview(self):
        """更新端口映射文本。"""
        from models.component_lib import ComponentType
        config = self._get_current_config()
        text = build_port_preview_text(ComponentType.LCP_THREE_CABLE, config)
        self.port_preview_label.setText(text)

    def _refresh_cross_section_preview(self):
        config = self._get_current_config()
        self._preview_canvas.draw_three_core_cable(config)
        angles = config.get('conductor_angles', [270, 30, 150])
        angles_str = '/'.join(f'{a:.0f}°' for a in angles[:3])
        self._preview_summary.setText(
            f"三芯电缆 | 管道外径: {config.get('pipe_outer_radius', 0)*1000:.1f}mm | "
            f"角度: {angles_str}"
        )

    def _get_current_config(self) -> dict:
        """轻量级读取当前 UI 值用于预览。"""
        angles_text = self.angles_edit.text().strip()
        try:
            angles = [float(a.strip()) for a in angles_text.split(",")]
        except ValueError:
            angles = [270.0, 30.0, 150.0]
        return {
            'pipe_inner_radius': self.pipe_inner_radius_spin.value(),
            'pipe_outer_radius': self.pipe_outer_radius_spin.value(),
            'pipe_resistivity': self.pipe_resistivity_spin.value(),
            'core_radius': self.core_radius_spin.value(),
            'insulation_radius': self.insulation_radius_spin.value(),
            'insulation_eps_r': self.insulation_eps_r_spin.value(),
            'sheath_radius': self.sheath_radius_spin.value(),
            'dist_from_center': self.dist_from_center_spin.value(),
            'conductor_angles': angles,
            'soil_resistivity': self.soil_rho_spin.value(),
            'soil_permittivity': self.soil_eps_spin.value(),
            'burial_depth': self.burial_depth_spin.value(),
            'length': self.length_spin.value(),
        }

    # ================================================================
    #  数据加载
    # ================================================================

    def _load_from_params(self, params: dict):
        self._preview_timer.blockSignals(True)
        self.length_spin.setValue(params.get('length', 1000.0))
        self.pipe_inner_radius_spin.setValue(params.get('pipe_inner_radius', 0.065))
        self.pipe_outer_radius_spin.setValue(params.get('pipe_outer_radius', 0.07))
        self.pipe_resistivity_spin.setValue(params.get('pipe_resistivity', 1.7e-7))
        self.pipe_mu_r_spin.setValue(params.get('pipe_mu_r', 1.0))
        self.core_radius_spin.setValue(params.get('core_radius', 0.0165))
        self.core_resistivity_spin.setValue(params.get('core_resistivity', 1.7e-8))
        self.insulation_radius_spin.setValue(params.get('insulation_radius', 0.027))
        self.insulation_eps_r_spin.setValue(params.get('insulation_eps_r', 3.5))
        self.sheath_radius_spin.setValue(params.get('sheath_radius', 0.03))
        self.sheath_resistivity_spin.setValue(params.get('sheath_resistivity', 2.2e-7))
        self.dist_from_center_spin.setValue(params.get('dist_from_center', 0.03415))
        self.soil_rho_spin.setValue(params.get('soil_resistivity', 100.0))
        self.soil_eps_spin.setValue(params.get('soil_permittivity', 10.0))
        self.burial_depth_spin.setValue(params.get('burial_depth', 1.0))
        self._load_fitting_from_params(params)
        self._preview_timer.blockSignals(False)

    # ================================================================
    #  导出配置
    # ================================================================

    def get_config(self) -> dict:
        angles_text = self.angles_edit.text().strip()
        try:
            angles = [float(a.strip()) for a in angles_text.split(",")]
        except ValueError:
            angles = [270.0, 30.0, 150.0]

        config = {
            'length': self.length_spin.value(),
            'force_rebuild': self.force_rebuild_check.isChecked(),
            'pipe_inner_radius': self.pipe_inner_radius_spin.value(),
            'pipe_outer_radius': self.pipe_outer_radius_spin.value(),
            'pipe_resistivity': self.pipe_resistivity_spin.value(),
            'pipe_mu_r': self.pipe_mu_r_spin.value(),
            'core_radius': self.core_radius_spin.value(),
            'core_resistivity': self.core_resistivity_spin.value(),
            'insulation_radius': self.insulation_radius_spin.value(),
            'insulation_eps_r': self.insulation_eps_r_spin.value(),
            'sheath_radius': self.sheath_radius_spin.value(),
            'sheath_resistivity': self.sheath_resistivity_spin.value(),
            'dist_from_center': self.dist_from_center_spin.value(),
            'conductor_angles': angles,
            'soil_resistivity': self.soil_rho_spin.value(),
            'soil_permittivity': self.soil_eps_spin.value(),
            'burial_depth': self.burial_depth_spin.value(),
        }
        config.update(self._fitting_config())
        return config
