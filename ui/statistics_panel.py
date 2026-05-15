"""
EMTP GUI - 仿真统计面板

显示仿真完成后的 timing 统计和性能信息：
- 总步数 / 总耗时
- 矩阵构建 / LU 分解 / RHS 构建 / 线性求解
- MOA 段切换 / LPM 重解次数
- 探针数据摘要
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QFormLayout, QTableWidget,
    QTableWidgetItem, QHeaderView, QSizePolicy,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor


class StatisticsPanel(QWidget):
    """仿真统计面板 - 显示 timing 和探针数据摘要"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._results = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 标题
        title_layout = QHBoxLayout()
        self.title_label = QLabel("📊 仿真统计")
        self.title_label.setStyleSheet("""
            QLabel {
                font-size: 14px; font-weight: bold; color: #1e293b;
                padding: 4px 0;
            }
        """)
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()

        self.clear_btn = QPushButton("清空")
        self.clear_btn.setFixedWidth(60)
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #94a3b8; color: white; border: none;
                border-radius: 3px; padding: 4px 8px; font-size: 11px;
            }
            QPushButton:hover { background-color: #64748b; }
        """)
        self.clear_btn.clicked.connect(self.clear_results)
        title_layout.addWidget(self.clear_btn)
        layout.addLayout(title_layout)

        # Timing 统计组
        timing_group = QGroupBox("⏱ Timing 统计")
        timing_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold; font-size: 12px; color: #334155;
                border: 1px solid #e2e8f0; border-radius: 6px;
                margin-top: 10px; padding-top: 16px;
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 10px; padding: 0 4px;
            }
        """)
        timing_layout = QFormLayout()
        timing_layout.setSpacing(6)
        timing_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._timing_labels = {}
        timing_items = [
            ("total_steps", "总步数"),
            ("total_time", "总耗时 (s)"),
            ("matrix_build", "矩阵构建 (s)"),
            ("lu_factorization", "LU 分解 (s)"),
            ("rhs_build", "RHS 构建 (s)"),
            ("linear_solve", "线性求解 (s)"),
            ("moa_switches", "MOA 段切换"),
            ("lpm_resolves", "LPM 重解"),
        ]
        for key, label_text in timing_items:
            lbl = QLabel("--")
            lbl.setStyleSheet("font-family: Consolas, monospace; font-size: 12px; color: #475569;")
            self._timing_labels[key] = lbl
            timing_layout.addRow(f"{label_text}:", lbl)

        timing_group.setLayout(timing_layout)
        layout.addWidget(timing_group)

        # 探针数据摘要组
        probe_group = QGroupBox("📈 探针数据摘要")
        probe_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold; font-size: 12px; color: #334155;
                border: 1px solid #e2e8f0; border-radius: 6px;
                margin-top: 10px; padding-top: 16px;
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 10px; padding: 0 4px;
            }
        """)
        probe_layout = QVBoxLayout()

        self.probe_table = QTableWidget()
        self.probe_table.setColumnCount(5)
        self.probe_table.setHorizontalHeaderLabels(["探针名", "类型", "最小值", "最大值", "数据点"])
        self.probe_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.probe_table.setAlternatingRowColors(True)
        self.probe_table.setStyleSheet("""
            QTableWidget {
                font-size: 11px; border: 1px solid #e2e8f0;
                border-radius: 4px; background-color: #fafbfc;
            }
            QTableWidget::item { padding: 2px 4px; }
            QTableWidget::item:alternate { background-color: #f8fafc; }
        """)
        self.probe_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.probe_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        probe_layout.addWidget(self.probe_table)

        probe_group.setLayout(probe_layout)
        layout.addWidget(probe_group)

        layout.addStretch()

        # 初始状态
        self._set_empty_state()

    def set_results(self, results: dict):
        """设置仿真结果并更新显示

        Args:
            results: dict, 来自 SimRunner.results_ready 信号
                     包含 'time', 'probes', 'timing' 键
        """
        self._results = results

        # 更新 timing 统计
        timing = results.get('timing', {})
        if timing:
            for key, lbl in self._timing_labels.items():
                value = timing.get(key, None)
                if value is not None:
                    if isinstance(value, float):
                        lbl.setText(f"{value:.4f}")
                    else:
                        lbl.setText(str(value))
                    lbl.setStyleSheet(
                        "font-family: Consolas, monospace; font-size: 12px; color: #059669;"
                    )
                else:
                    lbl.setText("--")
        else:
            self._set_empty_timing()

        # 更新探针摘要
        probes = results.get('probes', {})
        self.probe_table.setRowCount(len(probes))

        for row, (name, info) in enumerate(probes.items()):
            self.probe_table.setItem(row, 0, QTableWidgetItem(name))

            ptype = info.get('type', '--')
            type_map = {
                'voltage': '⚡ 电压',
                'branch_current': '🔀 支路电流',
                'line_current': '📡 线路电流',
            }
            self.probe_table.setItem(row, 1, QTableWidgetItem(type_map.get(ptype, ptype)))

            data = info.get('data')
            if data is not None:
                try:
                    self.probe_table.setItem(row, 2, QTableWidgetItem(f"{data.min():.4g}"))
                    self.probe_table.setItem(row, 3, QTableWidgetItem(f"{data.max():.4g}"))
                    self.probe_table.setItem(row, 4, QTableWidgetItem(str(len(data))))
                except Exception:
                    self.probe_table.setItem(row, 2, QTableWidgetItem("--"))
                    self.probe_table.setItem(row, 3, QTableWidgetItem("--"))
                    self.probe_table.setItem(row, 4, QTableWidgetItem("--"))

        if probes:
            self.title_label.setText(f"📊 仿真统计 — {len(probes)} 个探针")

    def clear_results(self):
        """清空统计结果"""
        self._results = None
        self._set_empty_state()

    def _set_empty_state(self):
        """设置空状态"""
        self._set_empty_timing()
        self.probe_table.setRowCount(0)
        self.title_label.setText("📊 仿真统计（等待仿真完成）")

    def _set_empty_timing(self):
        """设置 timing 空状态"""
        for lbl in self._timing_labels.values():
            lbl.setText("--")
            lbl.setStyleSheet(
                "font-family: Consolas, monospace; font-size: 12px; color: #475569;"
            )
