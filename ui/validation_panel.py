"""
EMTP GUI - 验证结果面板

持久化错误列表面板，显示 CircuitValidator 的校验结果。
支持级别图标、定位跳转（点击错误项高亮画布对应元件）。
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget,
    QTreeWidgetItem, QLabel, QPushButton, QHeaderView,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush

from core.validator import ValidationError, ValidationSeverity


class ValidationPanel(QWidget):
    """验证结果面板 - 显示电路校验的错误和警告"""

    # 点击某项时发出信号，携带 component_id（可能为 None）
    item_clicked = Signal(str)   # component_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._errors: list = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 顶部摘要栏
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        self.summary_label = QLabel("验证结果: --")
        self.summary_label.setStyleSheet("""
            QLabel {
                font-weight: bold; font-size: 12px; padding: 2px 6px;
            }
        """)
        header_layout.addWidget(self.summary_label)

        header_layout.addStretch()

        self.refresh_btn = QPushButton("🔄 刷新")
        self.refresh_btn.setFixedWidth(70)
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6; color: white; border: none;
                border-radius: 3px; padding: 4px 8px; font-size: 11px;
            }
            QPushButton:hover { background-color: #2563eb; }
        """)
        header_layout.addWidget(self.refresh_btn)

        self.clear_btn = QPushButton("✖ 清空")
        self.clear_btn.setFixedWidth(70)
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #94a3b8; color: white; border: none;
                border-radius: 3px; padding: 4px 8px; font-size: 11px;
            }
            QPushButton:hover { background-color: #64748b; }
        """)
        self.clear_btn.clicked.connect(self.clear_results)
        header_layout.addWidget(self.clear_btn)

        layout.addLayout(header_layout)

        # 错误/警告树形列表
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["级别", "消息", "修复建议"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setStyleSheet("""
            QTreeWidget {
                font-size: 11px;
                border: 1px solid #e2e8f0;
                border-radius: 4px;
                background-color: #fafbfc;
            }
            QTreeWidget::item {
                padding: 3px 2px;
                border-bottom: 1px solid #f1f5f9;
            }
            QTreeWidget::item:selected {
                background-color: #dbeafe;
                color: #1e3a5f;
            }
            QTreeWidget::item:alternate {
                background-color: #f8fafc;
            }
        """)

        # 列宽
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.tree.setColumnWidth(0, 50)
        self.tree.setColumnWidth(2, 180)

        # 点击跳转
        self.tree.itemClicked.connect(self._on_item_clicked)

        layout.addWidget(self.tree)

        # 底部统计
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("""
            QLabel {
                font-size: 10px; color: #64748b; padding: 2px 4px;
            }
        """)
        layout.addWidget(self.stats_label)

    def set_results(self, errors: list):
        """设置验证结果并更新显示

        Args:
            errors: List[ValidationError] 验证结果列表
        """
        self._errors = errors
        self.tree.clear()

        error_count = sum(1 for e in errors if e.severity == ValidationSeverity.ERROR)
        warning_count = sum(1 for e in errors if e.severity == ValidationSeverity.WARNING)
        info_count = sum(1 for e in errors if e.severity == ValidationSeverity.INFO)

        # 更新摘要
        if not errors:
            self.summary_label.setText("✅ 验证通过")
            self.summary_label.setStyleSheet("""
                QLabel {
                    font-weight: bold; font-size: 12px; padding: 2px 6px;
                    color: #059669;
                }
            """)
            self.stats_label.setText("无错误或警告")
        else:
            parts = []
            if error_count:
                parts.append(f"❌ {error_count} 错误")
            if warning_count:
                parts.append(f"⚠️ {warning_count} 警告")
            if info_count:
                parts.append(f"ℹ️ {info_count} 信息")
            self.summary_label.setText("  ".join(parts))

            color = "#ef4444" if error_count > 0 else "#f59e0b"
            self.summary_label.setStyleSheet(f"""
                QLabel {{
                    font-weight: bold; font-size: 12px; padding: 2px 6px;
                    color: {color};
                }}
            """)
            self.stats_label.setText(
                f"共 {len(errors)} 项: {error_count} 错误, {warning_count} 警告, {info_count} 信息"
            )

        # 填充树
        for err in errors:
            item = QTreeWidgetItem()

            # 级别图标 + 颜色
            if err.severity == ValidationSeverity.ERROR:
                item.setText(0, "❌")
                item.setForeground(1, QBrush(QColor("#dc2626")))
            elif err.severity == ValidationSeverity.WARNING:
                item.setText(0, "⚠️")
                item.setForeground(1, QBrush(QColor("#d97706")))
            else:
                item.setText(0, "ℹ️")
                item.setForeground(1, QBrush(QColor("#2563eb")))

            item.setText(1, err.message)
            item.setText(2, err.fix or "")

            # 存储 component_id 在 data 中
            comp_id = err.component_id or ""
            item.setData(0, Qt.ItemDataRole.UserRole, comp_id)

            # tooltip
            tip = err.message
            if err.fix:
                tip += f"\n修复: {err.fix}"
            if err.component_id:
                tip += f"\n元件: {err.component_id}"
            item.setToolTip(1, tip)

            self.tree.addTopLevelItem(item)

    def clear_results(self):
        """清空验证结果"""
        self._errors = []
        self.tree.clear()
        self.summary_label.setText("验证结果: --")
        self.summary_label.setStyleSheet("""
            QLabel { font-weight: bold; font-size: 12px; padding: 2px 6px; }
        """)
        self.stats_label.setText("")

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        """点击错误项 → 发出定位信号"""
        comp_id = item.data(0, Qt.ItemDataRole.UserRole)
        if comp_id:
            self.item_clicked.emit(comp_id)
