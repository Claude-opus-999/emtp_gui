"""
EMTP 电路仿真 GUI - 电路画布
基于 QGraphicsView + QGraphicsScene 实现
支持选择/放置/连线/拖拽等交互模式
"""

import copy
import uuid

from shiboken6 import isValid
from PySide6.QtWidgets import (QGraphicsView, QGraphicsScene, QGraphicsItem,
                              QGraphicsLineItem, QGraphicsEllipseItem,
                              QGraphicsTextItem, QGraphicsRectItem,
                              QGraphicsPathItem, QApplication)
from PySide6.QtCore import Qt, QPointF, Signal, QRectF, QLineF, QPoint
from PySide6.QtGui import (QPen, QBrush, QColor, QPainter, QPainterPath,
                           QPainterPathStroker, QFont, QKeyEvent,
                           QMouseEvent, QWheelEvent)
from enum import Enum, auto
from typing import Optional, Dict, List, Tuple
import math

from models.circuit_model import (
    CircuitModel, ComponentType, ComponentInstance, Wire, Pin
)
from models.component_lib import COMPONENT_REGISTRY, get_pins
from ui.symbols import draw_component_symbol


class CanvasMode(Enum):
    """画布交互模式"""
    SELECT = auto()   # 选择/移动模式
    PLACE = auto()    # 放置元件模式
    WIRE = auto()     # 连线模式
    DELETE = auto()   # 删除模式


class ComponentGraphicsItem(QGraphicsItem):
    """元件图形项"""

    def __init__(
        self,
        component: ComponentInstance,
        model: CircuitModel,
        canvas: Optional['CircuitCanvas'] = None,
    ):
        super().__init__()
        self.component = component
        self.model = model
        self.canvas = canvas
        self._drag_started = False
        self._drag_snapshot = None
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setPos(component.x, component.y)
        self.setRotation(component.rotation)

        # 颜色配置
        registry = COMPONENT_REGISTRY.get(component.comp_type, {})
        color_str = registry.get('symbol_color', '#2563eb')
        self.brush = QBrush(QColor(color_str).lighter(180))
        self.pen = QPen(QColor(color_str), 2)
        self.selected_pen = QPen(QColor("#f59e0b"), 3)
        self.selection_frame_pen = QPen(QColor("#2563eb"), 1.5, Qt.PenStyle.DashLine)

        # 元件尺寸
        if component.comp_type == ComponentType.SUBCIRCUIT:
            self._bounding_rect = QRectF(-50, -35, 100, 70)
        elif component.comp_type == ComponentType.UMEC_TRANSFORMER:
            self._bounding_rect = QRectF(-100, -75, 200, 160)
        elif component.comp_type == ComponentType.PROBE:
            self._bounding_rect = QRectF(-45, -45, 90, 100)
        elif component.comp_type == ComponentType.JUNCTION:
            self._bounding_rect = QRectF(-8, -8, 16, 16)
        elif component.comp_type == ComponentType.SUBCIRCUIT_PORT:
            self._bounding_rect = QRectF(-24, -14, 48, 44)
        elif component.comp_type in (
            ComponentType.BERGERON,
            ComponentType.ULM,
            ComponentType.LCP_OHL,
            ComponentType.LCP_SINGLE_CABLE,
            ComponentType.LCP_THREE_CABLE,
        ):
            if component.comp_type in (
                ComponentType.LCP_OHL,
                ComponentType.LCP_SINGLE_CABLE,
                ComponentType.LCP_THREE_CABLE,
            ):
                pin_ys = [pin.local_y for pin in component.pins] or [0]
                top = min(-70, min(pin_ys) - 24)
                bottom = max(75, max(pin_ys) + 24)
                self._bounding_rect = QRectF(-115, top, 230, bottom - top)
            else:
                self._bounding_rect = QRectF(-65, -50, 130, 100)
        else:
            self._bounding_rect = QRectF(-40, -25, 80, 50)

    def boundingRect(self) -> QRectF:
        return self._bounding_rect

    def paint(self, painter: QPainter, option, widget=None):
        """绘制元件"""
        pen = self.selected_pen if self.isSelected() else self.pen
        painter.setPen(pen)
        painter.setBrush(self.brush)

        ct = self.component.comp_type

        if draw_component_symbol(painter, self.component):
            pass
        elif ct == ComponentType.RESISTOR:
            self._draw_resistor(painter)
        elif ct == ComponentType.INDUCTOR:
            self._draw_inductor(painter)
        elif ct == ComponentType.CAPACITOR:
            self._draw_capacitor(painter)
        elif ct == ComponentType.SERIES_RL:
            self._draw_series_rl(painter)
        elif ct == ComponentType.VOLTAGE_SOURCE:
            self._draw_voltage_source(painter)
        elif ct == ComponentType.CURRENT_SOURCE:
            self._draw_current_source(painter)
        elif ct == ComponentType.SWITCH:
            self._draw_switch(painter)
        elif ct == ComponentType.MOA:
            self._draw_moa(painter)
        elif ct == ComponentType.LPM:
            self._draw_lpm(painter)
        elif ct == ComponentType.BERGERON:
            self._draw_bergeron(painter)
        elif ct == ComponentType.ULM:
            self._draw_ulm(painter)
        elif ct == ComponentType.LCP_OHL:
            self._draw_lcp_ohl(painter)
        elif ct == ComponentType.LCP_SINGLE_CABLE:
            self._draw_lcp_cable(painter, "SC")
        elif ct == ComponentType.LCP_THREE_CABLE:
            self._draw_lcp_cable(painter, "3C")
        elif ct == ComponentType.UMEC_TRANSFORMER:
            self._draw_umec(painter)
        elif ct == ComponentType.GROUND:
            self._draw_ground(painter)
        elif ct == ComponentType.PROBE:
            self._draw_probe(painter)
        elif ct == ComponentType.SUBCIRCUIT:
            self._draw_subcircuit(painter)
        else:
            painter.drawRect(-25, -15, 50, 30)

        # 绘制标签
        if ct not in (
            ComponentType.UMEC_TRANSFORMER,
            ComponentType.JUNCTION,
            ComponentType.SUBCIRCUIT_PORT,
        ):
            painter.setPen(QColor("#1e2a3a"))
            font = QFont("Arial", 9)
            painter.setFont(font)
            painter.drawText(QPointF(-15, 35), self.component.name)

        # 绘制引脚
        if ct not in (ComponentType.JUNCTION, ComponentType.SUBCIRCUIT_PORT):
            self._draw_pins(painter)

        if self.isSelected():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(self.selection_frame_pen)
            painter.drawRect(self.boundingRect().adjusted(3, 3, -3, -3))

    def _draw_pins(self, painter: QPainter):
        """绘制引脚端子（paint() 坐标系已被 Qt 自动旋转，直接用本地坐标）"""
        painter.setBrush(QBrush(QColor("#2563eb")))
        for pin in self.component.pins:
            painter.setPen(QPen(QColor("#2563eb"), 2))
            painter.drawEllipse(pin.local_x - 3, pin.local_y - 3, 6, 6)

    def _draw_resistor(self, painter: QPainter):
        """绘制电阻符号"""
        painter.drawLine(-30, 0, -15, 0)
        points = [
            QPointF(-15, 0), QPointF(-12, -8), QPointF(-6, 8),
            QPointF(0, -8), QPointF(6, 8), QPointF(12, -8), QPointF(15, 0)
        ]
        for i in range(len(points) - 1):
            painter.drawLine(points[i], points[i + 1])
        painter.drawLine(15, 0, 30, 0)

    def _draw_inductor(self, painter: QPainter):
        """绘制电感符号"""
        painter.drawLine(-30, 0, -15, 0)
        for i in range(4):
            x = -12 + i * 8
            painter.drawArc(int(x), -8, 10, 16, 0, 180 * 16)
        painter.drawLine(18, 0, 30, 0)

    def _draw_capacitor(self, painter: QPainter):
        """绘制电容符号"""
        painter.drawLine(-30, 0, -5, 0)
        painter.drawLine(-5, -12, -5, 12)
        painter.drawLine(5, -12, 5, 12)
        painter.drawLine(5, 0, 30, 0)

    def _draw_voltage_source(self, painter: QPainter):
        """绘制电压源符号"""
        painter.drawLine(-30, 0, -10, 0)
        painter.drawEllipse(-10, -10, 20, 20)
        painter.drawLine(0, -5, 0, 5)
        painter.drawLine(-4, 0, 4, 0)
        painter.drawLine(10, 0, 30, 0)
        # 极性标记
        painter.drawText(QPointF(-3, -15), "+")

    def _draw_current_source(self, painter: QPainter):
        """绘制电流源符号"""
        painter.drawLine(-30, 0, -10, 0)
        painter.drawEllipse(-10, -10, 20, 20)
        # 箭头
        painter.drawLine(-3, -6, 0, -6)
        painter.drawLine(0, -6, -2, -3)
        painter.drawLine(0, -6, 3, -6)
        painter.drawLine(0, -6, 0, 2)
        painter.drawLine(10, 0, 30, 0)

    def _draw_switch(self, painter: QPainter):
        """绘制开关符号"""
        painter.drawLine(-30, 0, -10, 0)
        painter.drawLine(-10, 0, 10, -10)
        painter.drawEllipse(8, -3, 6, 6)
        painter.drawLine(15, 0, 30, 0)

    def _draw_moa(self, painter: QPainter):
        """绘制MOA避雷器符号"""
        painter.drawLine(-30, 0, -15, 0)
        painter.drawLine(-15, -10, -15, 10)
        painter.drawLine(15, -10, 15, 10)
        for i in range(4):
            x1 = -12 + i * 7
            x2 = x1 + 3
            y = 10 if i % 2 == 0 else -10
            painter.drawLine(x1, -y if i > 0 else 0, x2, y)
        painter.drawLine(15, 0, 30, 0)

    def _draw_bergeron(self, painter: QPainter):
        """绘制Bergeron传输线符号"""
        painter.drawLine(-30, 0, 30, 0)
        painter.drawLine(-30, -10, 30, -10)
        painter.drawLine(-30, 10, 30, 10)
        painter.drawText(QPointF(-5, -18), "~")

    def _draw_ulm(self, painter: QPainter):
        """绘制ULM传输线符号"""
        n_phases = self.component.params.get('n_phases', 3)
        spacing = 15
        start_y = -(n_phases - 1) * spacing / 2

        for i in range(n_phases):
            y = start_y + i * spacing
            painter.drawLine(-30, int(y), 30, int(y))
            painter.drawLine(-30, int(y) - 5, 30, int(y) - 5)

        painter.drawText(QPointF(-10, int(start_y) - 18), "ULM")

    def _draw_ground(self, painter: QPainter):
        """绘制接地符号"""
        painter.drawLine(0, -15, 0, 5)
        painter.drawLine(-10, 5, 10, 5)
        painter.drawLine(-15, 10, 15, 10)
        painter.drawLine(-20, 15, 20, 15)

    def _draw_probe(self, painter: QPainter):
        """绘制探针符号：探测头 + 连接线"""
        # 探测头（小三角形+圆点）
        probe_type = self.component.params.get('probe_type', 'voltage_ground')
        is_voltage = probe_type in ('voltage', 'voltage_ground', 'voltage_between')
        color = QColor("#eab308") if is_voltage else QColor("#22c55e")

        # 竖直连接线（从 sense 引脚向下）
        painter.setPen(QPen(color, 2))
        painter.drawLine(0, -15, 0, 0)

        # 探测头圆
        painter.setBrush(QBrush(color))
        painter.drawEllipse(-6, -6, 12, 12)

        # 内部标记：V 或 A
        painter.setPen(QPen(QColor("white"), 1))
        font = QFont("Arial", 8, QFont.Bold)
        painter.setFont(font)
        label = "Vg" if probe_type in ('voltage', 'voltage_ground') else ("V" if is_voltage else "I")
        painter.drawText(QPointF(-6, 3), label)

        # 恢复画笔
        painter.setPen(self.selected_pen if self.isSelected() else self.pen)

    def _draw_subcircuit(self, painter: QPainter):
        """绘制子电路：矩形盒子 + 端口标签"""
        # 绘制矩形主体
        rect = QRectF(-35, -25, 70, 50)
        painter.setBrush(QBrush(QColor("#f0f9ff")))
        painter.setPen(QPen(QColor("#0369a1"), 2))
        painter.drawRoundedRect(rect, 6, 6)

        # 子电路名称
        painter.setPen(QColor("#0369a1"))
        font = QFont("Arial", 9, QFont.Bold)
        painter.setFont(font)
        name = self.component.name
        painter.drawText(rect, Qt.AlignCenter, name)

        # 绘制端口标签（小方块+名称）
        font_small = QFont("Arial", 7)
        painter.setFont(font_small)
        for pin in self.component.pins:
            # 小方块标记端口
            painter.setBrush(QBrush(QColor("#0369a1")))
            painter.setPen(QPen(QColor("#0369a1"), 1))
            painter.drawRect(int(pin.local_x) - 4, int(pin.local_y) - 4, 8, 8)
            # 端口名称
            painter.setPen(QColor("#0369a1"))
            if pin.local_x < 0:
                painter.drawText(QPointF(pin.local_x - 25, pin.local_y + 4), pin.name)
            elif pin.local_x > 0:
                painter.drawText(QPointF(pin.local_x + 8, pin.local_y + 4), pin.name)
            elif pin.local_y < 0:
                painter.drawText(QPointF(-8, pin.local_y - 8), pin.name)
            else:
                painter.drawText(QPointF(-8, pin.local_y + 16), pin.name)

    def _draw_series_rl(self, painter: QPainter):
        """绘制串联RL符号: R锯齿 + L半圆串联"""
        # 左端线
        painter.drawLine(-30, 0, -20, 0)
        # 电阻部分 (缩小版锯齿)
        points = [
            QPointF(-20, 0), QPointF(-17, -6), QPointF(-11, 6),
            QPointF(-5, -6), QPointF(-1, 0)
        ]
        for i in range(len(points) - 1):
            painter.drawLine(points[i], points[i + 1])
        # 电感部分 (缩小版半圆)
        for i in range(3):
            x = 2 + i * 6
            painter.drawArc(int(x), -6, 8, 12, 0, 180 * 16)
        # 右端线
        painter.drawLine(20, 0, 30, 0)

    def _draw_lpm(self, painter: QPainter):
        """绘制LPM绝缘子符号: 火花间隙 + 闪电箭头"""
        painter.drawLine(-30, 0, -10, 0)
        # 两个电极
        painter.drawLine(-10, -8, -10, 8)
        painter.drawLine(10, -8, 10, 8)
        # 闪电箭头
        lightning = [
            QPointF(-4, -6), QPointF(2, -1), QPointF(-1, 1),
            QPointF(4, 6)
        ]
        for i in range(len(lightning) - 1):
            painter.drawLine(lightning[i], lightning[i + 1])
        painter.drawLine(10, 0, 30, 0)

    def _draw_lcp_ohl(self, painter: QPainter):
        """绘制LCP架空线符号 (类似ULM多相)"""
        n_phases = self.component.params.get('n_phases', 2)
        spacing = 12
        start_y = -(n_phases - 1) * spacing / 2

        for i in range(n_phases):
            y = start_y + i * spacing
            painter.drawLine(-30, int(y), 30, int(y))
            painter.drawLine(-30, int(y) - 4, 30, int(y) - 4)

        painter.drawText(QPointF(-12, int(start_y) - 14), "LCP")

    def _draw_lcp_cable(self, painter: QPainter, label: str):
        """绘制LCP电缆符号"""
        n_conductors = len([p for p in self.component.pins if p.name.startswith('nk_')])
        if n_conductors == 0:
            n_conductors = 3
        spacing = 10
        start_y = -(n_conductors - 1) * spacing / 2

        for i in range(min(n_conductors, 7)):  # 最多显示7条
            y = start_y + i * spacing
            painter.drawLine(-30, int(y), 30, int(y))

        painter.drawText(QPointF(-12, int(start_y) - 14), f"LCP-{label}")

    def _draw_umec(self, painter: QPainter):
        """绘制UMEC变压器符号: 矩形框+Y/Delta内部图形+标注"""
        p = self.component.params
        wtype1 = p.get('wtype1', 'Y_gnd')
        wtype2 = p.get('wtype2', 'Delta')
        S_mva = p.get('S_mva', 100.0)
        V1 = p.get('V1_kV', 220.0)
        V2 = p.get('V2_kV', 110.0)

        # 外框矩形
        painter.drawRect(-25, -22, 50, 50)

        # 引脚连接线
        for y in (-15, 0, 15):
            painter.drawLine(-30, y, -25, y)  # 左侧
            painter.drawLine(25, y, 30, y)    # 右侧
        # 中性点引脚线
        painter.drawLine(-30, 30, -25, 30)
        painter.drawLine(25, 30, 30, 30)

        # 内部绕组图形
        self._draw_winding_symbol(painter, -18, 0, wtype1, is_left=True)
        self._draw_winding_symbol(painter, 2, 0, wtype2, is_left=False)

        # 标注
        painter.setPen(QPen(QColor("#1e2a3a"), 1))
        font = QFont("Arial", 7)
        painter.setFont(font)
        painter.drawText(QPointF(-20, -26), f"umec {S_mva:g}MVA")
        font2 = QFont("Arial", 6)
        painter.setFont(font2)
        painter.drawText(QPointF(-22, 34), f"{V1:g}kV #1")
        painter.drawText(QPointF(2, 34), f"{V2:g}kV #2")

        # 恢复画笔
        painter.setPen(self.selected_pen if self.isSelected() else self.pen)

    def _draw_winding_symbol(self, painter: QPainter, cx: int, cy: int,
                             wtype: str, is_left: bool):
        """绘制单个绕组的 Y/Delta 符号
        cx, cy: 符号中心坐标
        is_left: True=左侧(高压), False=右侧(低压)
        """
        pen = painter.pen()
        painter.setPen(QPen(QColor("#1e2a3a"), 1))

        if wtype in ('Y', 'Y_gnd'):
            # Y 形: 三条线从中心向外
            r = 8
            # 三条臂
            for angle_deg in (90, 210, 330):
                rad = math.radians(angle_deg)
                x1 = cx + r * 0.3 * math.cos(rad)
                y1 = cy + r * 0.3 * math.sin(rad)
                x2 = cx + r * math.cos(rad)
                y2 = cy + r * math.sin(rad)
                painter.drawLine(int(x1), int(y1), int(x2), int(y2))
            # 中性点线向下
            nx = cx
            ny = cy + r * 0.3
            if wtype == 'Y_gnd':
                # 接地符号
                painter.drawLine(int(nx), int(ny), int(nx), int(ny + 12))
                painter.drawLine(int(nx - 4), int(ny + 12), int(nx + 4), int(ny + 12))
                painter.drawLine(int(nx - 2), int(ny + 14), int(nx + 2), int(ny + 14))
                painter.drawLine(int(nx - 1), int(ny + 16), int(nx + 1), int(ny + 16))
            else:
                # Y 接法: 中性点线连到中性点引脚
                painter.drawLine(int(nx), int(ny), int(nx), 30)
        else:
            # Delta: 三角形
            r = 8
            pts = []
            for angle_deg in (90, 210, 330):
                rad = math.radians(angle_deg)
                pts.append(QPointF(
                    cx + r * math.cos(rad),
                    cy + r * math.sin(rad)
                ))
            for i in range(3):
                painter.drawLine(pts[i], pts[(i + 1) % 3])

        painter.setPen(pen)

    def get_terminal_positions(self) -> Tuple[QPointF, QPointF]:
        """获取元件端子位置（本地坐标）"""
        if not self.component.pins:
            return QPointF(-30, 0), QPointF(30, 0)

        pin1 = self.component.pins[0]
        pin2 = self.component.pins[-1] if len(self.component.pins) > 1 else pin1

        return QPointF(pin1.local_x, pin1.local_y), QPointF(pin2.local_x, pin2.local_y)

    def get_scene_terminal_positions(self) -> Tuple[QPointF, QPointF]:
        """获取元件端子位置（场景坐标，使用 Qt 内建坐标映射）"""
        term1, term2 = self.get_terminal_positions()
        return self.mapToScene(term1), self.mapToScene(term2)

    def get_all_scene_pin_positions(self) -> Dict[str, QPointF]:
        """获取所有引脚的场景坐标（使用 Qt 内建坐标映射）"""
        positions = {}
        for pin in self.component.pins:
            positions[pin.name] = self.mapToScene(QPointF(pin.local_x, pin.local_y))
        return positions

    def mousePressEvent(self, event):
        """鼠标按下 - 单击即可选中"""
        was_selected = self.isSelected()
        is_left_click = event.button() == Qt.MouseButton.LeftButton
        ctrl_held = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        self._drag_started = False
        if is_left_click and self.flags() & QGraphicsItem.ItemIsMovable:
            self._drag_snapshot = self.model._snapshot()
        super().mousePressEvent(event)
        if is_left_click and self.flags() & QGraphicsItem.ItemIsSelectable:
            if ctrl_held:
                self.setSelected(not was_selected)
            elif was_selected and len(self.scene().selectedItems()) > 1:
                self.setSelected(True)
            else:
                for item in self.scene().selectedItems():
                    if item is not self:
                        item.setSelected(False)
                self.setSelected(True)
            self.model.select_component(self.component.comp_id)
            if self.canvas:
                self.canvas._begin_component_drag()

    def mouseReleaseEvent(self, event):
        """鼠标释放 - 拖拽结束时保存撤销状态"""
        if self._drag_snapshot is not None:
            if self._drag_started and self.flags() & QGraphicsItem.ItemIsMovable:
                old_comp = self._drag_snapshot.get("components", {}).get(self.component.comp_id, {})
                moved = (
                    old_comp.get("x") != self.component.x
                    or old_comp.get("y") != self.component.y
                )
                if moved and self.canvas:
                    self.canvas._finish_component_drag_waypoints(apply=True)
                elif self.canvas:
                    self.canvas._finish_component_drag_waypoints(apply=False)
                if moved:
                    self.model._push_undo_snapshot(self._drag_snapshot)
                    self.model._notify("component_moved")
            elif self.canvas:
                self.canvas._finish_component_drag_waypoints(apply=False)
            self._drag_snapshot = None
            self._drag_started = False
        super().mouseReleaseEvent(event)

    def itemChange(self, change, value):
        """状态变化"""
        if change == QGraphicsItem.ItemPositionChange:
            # 拖拽时吸附到网格
            snapped = self._snap_pos(value)
            if self._drag_snapshot is not None:
                self._drag_started = True
            self.component.x = int(snapped.x())
            self.component.y = int(snapped.y())
            return snapped
        if change == QGraphicsItem.ItemPositionHasChanged:
            if self._drag_snapshot is not None:
                self._drag_started = True
            if (
                self.canvas is not None
                and self.component.comp_id in self.canvas._component_drag_selected_ids
            ):
                self.canvas._update_connected_wires_during_component_drag()
        return super().itemChange(change, value)

    def _snap_pos(self, pos: QPointF) -> QPointF:
        """将位置吸附到网格"""
        grid = CircuitCanvas.GRID_SIZE
        x = round(pos.x() / grid) * grid
        y = round(pos.y() / grid) * grid
        return QPointF(x, y)


class WireGraphicsItem(QGraphicsItem):
    """连线图形项 — Manhattan 折线路由（只允许水平/垂直线段）"""

    WIRE_COLOR = QColor("#111111")
    WIRE_WIDTH = 1.0
    ENDPOINT_DOT_DIAMETER = 2.0

    def __init__(self, wire: Wire, start_pos: QPointF, end_pos: QPointF):
        super().__init__()
        self.wire = wire
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.pen = QPen(self.WIRE_COLOR, self.WIRE_WIDTH)
        self.selected_pen = QPen(QColor("#f59e0b"), 2.25)
        self._update_bounds()

    @staticmethod
    def _same_point(first: QPointF, second: QPointF, tolerance: float = 0.1) -> bool:
        return (
            abs(first.x() - second.x()) <= tolerance
            and abs(first.y() - second.y()) <= tolerance
        )

    @classmethod
    def _append_unique(cls, points: List[QPointF], point: QPointF):
        if not points or not cls._same_point(points[-1], point):
            points.append(QPointF(point))

    @classmethod
    def _orthogonal_points(
        cls,
        start_pos: QPointF,
        waypoints: List[QPointF],
        end_pos: QPointF,
    ) -> List[QPointF]:
        """Return the route through explicit user-created waypoint anchors."""
        return cls._repair_points_for_drawing(
            [QPointF(start_pos), *[QPointF(point) for point in waypoints], QPointF(end_pos)]
        )

    @classmethod
    def _repair_points_for_drawing(cls, points: List[QPointF]) -> List[QPointF]:
        if not points:
            return []

        result = [QPointF(points[0])]
        for target in points[1:]:
            last = result[-1]
            if cls._same_point(last, target):
                continue
            if abs(last.x() - target.x()) <= 0.1 or abs(last.y() - target.y()) <= 0.1:
                result.append(QPointF(target))
                continue

            bend = QPointF(target.x(), last.y())
            cls._append_unique(result, bend)
            cls._append_unique(result, target)

        return cls._collapse_collinear_for_drawing(result)

    @classmethod
    def _collapse_collinear_for_drawing(cls, points: List[QPointF]) -> List[QPointF]:
        if len(points) <= 2:
            return points

        result = [QPointF(points[0])]
        for index in range(1, len(points) - 1):
            prev = result[-1]
            curr = points[index]
            next_point = points[index + 1]
            horizontal = (
                abs(prev.y() - curr.y()) <= 0.1
                and abs(curr.y() - next_point.y()) <= 0.1
            )
            vertical = (
                abs(prev.x() - curr.x()) <= 0.1
                and abs(curr.x() - next_point.x()) <= 0.1
            )
            if horizontal or vertical:
                continue
            result.append(QPointF(curr))
        result.append(QPointF(points[-1]))
        return result

    @classmethod
    def orthogonal_waypoints(
        cls,
        start_pos: QPointF,
        waypoints: List[QPointF],
        end_pos: QPointF,
    ) -> List[tuple]:
        points = cls._orthogonal_points(start_pos, waypoints, end_pos)
        return [(float(point.x()), float(point.y())) for point in points[1:-1]]

    def _manhattan_points(self) -> list:
        """??? Manhattan ???????????????????????????????"""
        return self._orthogonal_points(
            self.start_pos,
            [QPointF(float(x), float(y)) for x, y in self.wire.waypoints],
            self.end_pos,
        )

    def _path(self) -> QPainterPath:
        pts = self._manhattan_points()
        path = QPainterPath()
        if not pts:
            return path
        path.moveTo(pts[0])
        for point in pts[1:]:
            path.lineTo(point)
        return path

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(12)
        return stroker.createStroke(self._path())

    @staticmethod
    def _distance_to_segment(pos: QPointF, start: QPointF, end: QPointF) -> Tuple[float, QPointF]:
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length_sq = dx * dx + dy * dy
        if length_sq == 0:
            return math.hypot(pos.x() - start.x(), pos.y() - start.y()), QPointF(start)
        t = (
            (pos.x() - start.x()) * dx + (pos.y() - start.y()) * dy
        ) / length_sq
        t = max(0.0, min(1.0, t))
        nearest = QPointF(start.x() + t * dx, start.y() + t * dy)
        distance = math.hypot(pos.x() - nearest.x(), pos.y() - nearest.y())
        return distance, nearest

    def distance_to_point(self, pos: QPointF) -> float:
        pts = self._manhattan_points()
        if len(pts) < 2:
            return math.inf
        return min(
            self._distance_to_segment(pos, pts[i], pts[i + 1])[0]
            for i in range(len(pts) - 1)
        )

    def nearest_point(self, pos: QPointF) -> QPointF:
        pts = self._manhattan_points()
        if len(pts) < 2:
            return QPointF(pos)
        nearest = min(
            (
                self._distance_to_segment(pos, pts[i], pts[i + 1])
                for i in range(len(pts) - 1)
            ),
            key=lambda item: item[0],
        )
        return nearest[1]

    def _update_bounds(self):
        self.prepareGeometryChange()
        pts = self._manhattan_points()
        xs = [p.x() for p in pts]
        ys = [p.y() for p in pts]
        left = min(xs) - 5
        top = min(ys) - 5
        width = max(xs) - min(xs) + 10
        height = max(ys) - min(ys) + 10
        self._bounding_rect = QRectF(left, top, width, height)

    def boundingRect(self) -> QRectF:
        return self._bounding_rect

    def paint(self, painter: QPainter, option, widget=None):
        pen = self.selected_pen if self.isSelected() else self.pen
        painter.setPen(pen)

        pts = self._manhattan_points()
        for i in range(len(pts) - 1):
            painter.drawLine(pts[i], pts[i + 1])

        # 绘制端点
        dot_radius = self.ENDPOINT_DOT_DIAMETER / 2
        painter.setPen(QPen(Qt.PenStyle.NoPen))
        painter.setBrush(QBrush(self.WIRE_COLOR))
        painter.drawEllipse(
            self.start_pos.x() - dot_radius,
            self.start_pos.y() - dot_radius,
            self.ENDPOINT_DOT_DIAMETER,
            self.ENDPOINT_DOT_DIAMETER,
        )
        painter.drawEllipse(
            self.end_pos.x() - dot_radius,
            self.end_pos.y() - dot_radius,
            self.ENDPOINT_DOT_DIAMETER,
            self.ENDPOINT_DOT_DIAMETER,
        )

    def update_positions(self, start_pos: QPointF = None, end_pos: QPointF = None):
        if start_pos:
            self.start_pos = start_pos
        if end_pos:
            self.end_pos = end_pos
        self._update_bounds()
        self.update()


class WireWaypointGraphicsItem(QGraphicsItem):
    """Interactive handle for a wire waypoint."""

    def __init__(self, canvas: 'CircuitCanvas', wire: Wire, waypoint_index: int):
        super().__init__()
        self.canvas = canvas
        self.wire = wire
        self.waypoint_index = waypoint_index
        self._drag_snapshot = None
        self._drag_started = False
        self._syncing_from_model = False
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setZValue(12)
        self.sync_from_model()

    def boundingRect(self) -> QRectF:
        return QRectF(-3, -3, 6, 6)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addEllipse(self.boundingRect())
        return path

    def paint(self, painter: QPainter, option, widget=None):
        return

    def sync_from_model(self):
        if self.waypoint_index >= len(self.wire.waypoints):
            return
        x, y = self.wire.waypoints[self.waypoint_index]
        self._syncing_from_model = True
        self.setPos(QPointF(float(x), float(y)))
        self._syncing_from_model = False

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.flags() & QGraphicsItem.ItemIsMovable:
            self._drag_snapshot = self.canvas.model._snapshot()
            self._drag_started = False
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_snapshot is not None:
            if self._drag_started:
                self.canvas.model._push_undo_snapshot(self._drag_snapshot)
                self.canvas.canvas_changed.emit()
            self._drag_snapshot = None
            self._drag_started = False
        super().mouseReleaseEvent(event)

    def itemChange(self, change, value):
        if self._syncing_from_model:
            return super().itemChange(change, value)
        if change == QGraphicsItem.ItemPositionChange:
            if self._drag_snapshot is not None:
                self._drag_started = True
            return self.canvas._move_wire_waypoint(
                self.wire,
                self.waypoint_index,
                value,
                moving_item=self,
            )
        if change == QGraphicsItem.ItemPositionHasChanged and self._drag_snapshot is not None:
            self._drag_started = True
        return super().itemChange(change, value)


class NodeGraphicsItem(QGraphicsItem):
    """节点图形项"""

    def __init__(self, node_id: int, position: QPointF = None):
        super().__init__()
        self.node_id = node_id
        self.setPos(position or QPointF(0, 0))
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

    def boundingRect(self) -> QRectF:
        return QRectF(-8, -8, 16, 16)

    def paint(self, painter: QPainter, option, widget=None):
        pen = QPen(QColor("#1e2a3a"), 2)
        painter.setPen(pen)

        if self.node_id == 0:
            # 接地符号
            painter.drawLine(-8, 0, 8, 0)
            painter.drawLine(-6, 4, 6, 4)
            painter.drawLine(-4, 8, 4, 8)
        else:
            painter.setBrush(QBrush(QColor("#fef3c7")))
            painter.drawEllipse(-6, -6, 12, 12)
            painter.drawText(QPointF(-3, 20), str(self.node_id))

    def itemChange(self, change, value):
        return super().itemChange(change, value)


class CircuitCanvas(QGraphicsView):
    """电路画布"""

    # 信号
    component_selected = Signal(str)
    canvas_changed = Signal()
    wire_created = Signal(str, str, str, str)
    add_ground_requested = Signal(object)  # QPointF
    placement_completed = Signal()  # 放置完成，自动切回选择模式
    subcircuit_entered = Signal(str)  # 进入子电路编辑，传子电路名
    subcircuit_exited = Signal()     # 退出子电路编辑

    GRID_SIZE = 5  # 网格吸附间距
    GRID_VISUAL_SIZE = 5
    GRID_MAJOR_SIZE = 50

    def __init__(self, model: CircuitModel):
        super().__init__()
        self.model = model
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)

        self.show_grid = True

        # 交互模式
        self.mode = CanvasMode.SELECT
        self._placing_type: Optional[ComponentType] = None
        self._placing_params: Dict[str, object] = {}
        self._wiring_start: Optional[Tuple[str, str]] = None  # (comp_id, pin_name)
        self._wire_start_pos: Optional[QPointF] = None
        self._wire_start_wire_id: Optional[str] = None
        self._wire_waypoints: List[QPointF] = []
        self._temp_line: Optional[WireGraphicsItem] = None
        self._temp_wire_node: Optional[QGraphicsEllipseItem] = None
        self._middle_panning = False
        self._middle_pan_last_pos: Optional[QPoint] = None
        self._component_drag_selected_ids: set = set()
        self._component_drag_start_positions: Dict[str, Tuple[int, int]] = {}
        self._component_drag_wire_snapshot: Dict[str, Dict[str, object]] = {}

        # 子电路编辑模式
        self._editing_subcircuit: Optional[str] = None  # 当前正在编辑的子电路名
        self._subcircuit_breadcrumb: List[str] = []     # 面包屑路径

        # 图形项映射
        self.component_items: Dict[str, ComponentGraphicsItem] = {}
        self.wire_items: Dict[str, WireGraphicsItem] = {}
        self.wire_waypoint_items: Dict[Tuple[str, int], WireWaypointGraphicsItem] = {}
        self.wire_intersection_items: List[QGraphicsEllipseItem] = []

        # 复制粘贴剪贴板 — 同时保存元件和它们之间的连线
        self._clipboard: Optional[Dict] = None  # {'components': {...}, 'wires': {...}}

        # 监听模型变化
        self.model.add_observer(self._on_model_changed)

        self._init_background()
        self._draw_grid()

    def _init_background(self):
        self.setBackgroundBrush(QColor("#f8fafc"))
        self.setSceneRect(-3000, -3000, 6000, 6000)

    def drawBackground(self, painter: QPainter, rect: QRectF):
        """绘制网格背景（在场景背景层，不会遮挡任何图形项）"""
        painter.fillRect(rect, QColor("#f8fafc"))
        if not self.show_grid:
            return
        minor_pen = QPen(QColor("#edf2f7"), 0.25)
        major_pen = QPen(QColor("#dbe3ec"), 0.45)

        visual = self.GRID_VISUAL_SIZE
        left = int(rect.left()) - (int(rect.left()) % visual)
        top = int(rect.top()) - (int(rect.top()) % visual)
        for x in range(left, int(rect.right()) + 1, visual):
            painter.setPen(major_pen if x % self.GRID_MAJOR_SIZE == 0 else minor_pen)
            painter.drawLine(x, int(rect.top()), x, int(rect.bottom()))
        for y in range(top, int(rect.bottom()) + 1, visual):
            painter.setPen(major_pen if y % self.GRID_MAJOR_SIZE == 0 else minor_pen)
            painter.drawLine(int(rect.left()), y, int(rect.right()), y)

    def _draw_grid(self):
        """不再使用 — 网格已改由 drawBackground 绘制"""
        pass

    def set_mode(self, mode: CanvasMode):
        """设置交互模式"""
        previous_mode = self.mode
        if previous_mode == CanvasMode.WIRE and mode != CanvasMode.WIRE:
            self._clear_wire_input_state()
        self.mode = mode
        if mode == CanvasMode.SELECT:
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            self.setCursor(Qt.ArrowCursor)
            self._set_items_interactive(True)
        elif mode == CanvasMode.PLACE:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.setCursor(Qt.CrossCursor)
            self._set_items_interactive(False)
        elif mode == CanvasMode.WIRE:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.setCursor(Qt.CrossCursor)
            self._set_items_interactive(False)
        elif mode == CanvasMode.DELETE:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.setCursor(Qt.ForbiddenCursor)
            self._set_items_interactive(False)

    def _set_items_interactive(self, enabled: bool):
        """统一设置场景中所有元件的交互能力"""
        for item in self.scene.items():
            if isinstance(item, ComponentGraphicsItem):
                item.setFlag(QGraphicsItem.ItemIsSelectable, enabled)
                item.setFlag(QGraphicsItem.ItemIsMovable, enabled)
            elif isinstance(item, WireGraphicsItem):
                item.setFlag(QGraphicsItem.ItemIsSelectable, enabled)
            elif isinstance(item, WireWaypointGraphicsItem):
                item.setFlag(QGraphicsItem.ItemIsSelectable, enabled)
                item.setFlag(QGraphicsItem.ItemIsMovable, enabled)

    def set_placing_type(self, comp_type: ComponentType, default_params=None):
        """设置要放置的元件类型"""
        self._placing_type = comp_type
        self._placing_params = dict(default_params or {})
        self.set_mode(CanvasMode.PLACE)

    def snap_to_grid(self, pos: QPointF) -> QPointF:
        """对齐到网格"""
        x = round(pos.x() / self.GRID_SIZE) * self.GRID_SIZE
        y = round(pos.y() / self.GRID_SIZE) * self.GRID_SIZE
        return QPointF(x, y)

    def get_item_at(self, pos: QPointF) -> Optional[QGraphicsItem]:
        """获取指定位置的图形项（pos 为场景坐标）"""
        items = self.scene.items(pos)
        for item in items:
            if isinstance(item, (ComponentGraphicsItem, WireGraphicsItem, WireWaypointGraphicsItem, NodeGraphicsItem)):
                return item
        return None

    def get_component_at(self, pos: QPointF) -> Optional[ComponentGraphicsItem]:
        """获取指定位置的元件（pos 为场景坐标）"""
        item = self.get_item_at(pos)
        if isinstance(item, ComponentGraphicsItem):
            return item
        return None

    def get_pin_at(self, pos: QPointF) -> Optional[Tuple[ComponentGraphicsItem, str]]:
        """获取指定位置的引脚 (返回元件和引脚名，pos 为场景坐标)"""
        best = None
        best_dist = 20  # 最大引脚吸附距离（像素）
        for item in self.component_items.values():
            pin_positions = item.get_all_scene_pin_positions()
            for pin_name, pin_pos in pin_positions.items():
                dist = (pos - pin_pos).manhattanLength()
                if dist < best_dist:
                    best_dist = dist
                    best = (item, pin_name)
        return best

    def _apply_component_selection(self, item: ComponentGraphicsItem, additive: bool = False):
        """按 GUI 选择规则更新元件选择状态。"""
        if additive:
            item.setSelected(not item.isSelected())
        else:
            for selected in self.scene.selectedItems():
                if selected is not item:
                    selected.setSelected(False)
            item.setSelected(True)
        self.model.select_component(item.component.comp_id)

    def mouseDoubleClickEvent(self, event):
        """双击 — 进入子电路编辑模式"""
        if event.button() == Qt.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            item = self.get_component_at(scene_pos)
            if item and item.component.comp_type == ComponentType.SUBCIRCUIT:
                sub_name = item.component.params.get('subcircuit_name', '')
                if sub_name in self.model.subcircuit_defs:
                    self._enter_subcircuit(sub_name)
                    return
        super().mouseDoubleClickEvent(event)

    def _enter_subcircuit(self, sub_name: str):
        """进入子电路编辑模式"""
        self._subcircuit_breadcrumb.append(sub_name)
        self._editing_subcircuit = sub_name
        self.subcircuit_entered.emit(sub_name)
        self._refresh_view()

    def _exit_subcircuit(self):
        """退出子电路编辑模式（返回上一层）"""
        if self._subcircuit_breadcrumb:
            self._subcircuit_breadcrumb.pop()
        if self._subcircuit_breadcrumb:
            self._editing_subcircuit = self._subcircuit_breadcrumb[-1]
        else:
            self._editing_subcircuit = None
        self.subcircuit_exited.emit()
        self._refresh_view()

    def _active_subcircuit_def(self):
        if not self._editing_subcircuit:
            return None
        return self.model.subcircuit_defs.get(self._editing_subcircuit)

    def _active_components(self):
        subdef = self._active_subcircuit_def()
        if subdef is not None:
            return subdef.components
        return self.model.components

    def _active_wires(self):
        subdef = self._active_subcircuit_def()
        if subdef is not None:
            return subdef.wires
        return self.model.wires

    def _active_design(self):
        subdef = self._active_subcircuit_def()
        if subdef is not None:
            return subdef.components, subdef.wires
        return self.model.components, self.model.wires

    def _wire_endpoint_positions(self, wire: Wire) -> Tuple[Optional[QPointF], Optional[QPointF]]:
        start_item = self.component_items.get(wire.from_comp)
        end_item = self.component_items.get(wire.to_comp)
        if not start_item or not end_item:
            return None, None

        start_pos = start_item.get_all_scene_pin_positions().get(wire.from_pin)
        end_pos = end_item.get_all_scene_pin_positions().get(wire.to_pin)
        return start_pos, end_pos

    @staticmethod
    def _segment_orientation(first: QPointF, second: QPointF) -> Optional[str]:
        dx = abs(first.x() - second.x())
        dy = abs(first.y() - second.y())
        if dx <= 0.1 and dy <= 0.1:
            return None
        if dx <= 0.1:
            return "vertical"
        if dy <= 0.1:
            return "horizontal"
        return "horizontal" if dx >= dy else "vertical"

    @staticmethod
    def _set_point_axis(point: QPointF, orientation: Optional[str], value: float):
        if orientation == "vertical":
            point.setX(value)
        elif orientation == "horizontal":
            point.setY(value)

    @staticmethod
    def _strict_segment_orientation(first: QPointF, second: QPointF) -> Optional[str]:
        dx = abs(first.x() - second.x())
        dy = abs(first.y() - second.y())
        if dx <= 0.1 and dy <= 0.1:
            return None
        if dx <= 0.1:
            return "vertical"
        if dy <= 0.1:
            return "horizontal"
        return None

    @staticmethod
    def _point_delta(old_point: QPointF, new_point: QPointF) -> Tuple[float, float]:
        return (
            float(new_point.x() - old_point.x()),
            float(new_point.y() - old_point.y()),
        )

    @staticmethod
    def _same_delta(first: Tuple[float, float], second: Tuple[float, float]) -> bool:
        return abs(first[0] - second[0]) <= 0.1 and abs(first[1] - second[1]) <= 0.1

    def _orthogonal_route_between(self, start: QPointF, end: QPointF) -> List[QPointF]:
        if self._same_wire_point(start, end):
            return [QPointF(start)]
        if abs(start.x() - end.x()) <= 0.1 or abs(start.y() - end.y()) <= 0.1:
            return [QPointF(start), QPointF(end)]
        return [QPointF(start), QPointF(end.x(), start.y()), QPointF(end)]

    def _repair_orthogonal_points(self, points: List[QPointF]) -> List[QPointF]:
        if not points:
            return []

        result = [QPointF(points[0])]
        for target in points[1:]:
            last = result[-1]
            if self._same_wire_point(last, target):
                continue
            if abs(last.x() - target.x()) <= 0.1 or abs(last.y() - target.y()) <= 0.1:
                result.append(QPointF(target))
                continue

            bend = QPointF(target.x(), last.y())
            if not self._same_wire_point(last, bend):
                result.append(bend)
            if not self._same_wire_point(bend, target):
                result.append(QPointF(target))

        return self._normalize_wire_points(result)

    def _points_to_waypoints(self, points: List[QPointF]) -> List[tuple]:
        normalized = self._normalize_wire_points(points)
        if len(normalized) <= 2:
            return []
        return self._wire_point_tuples(normalized[1:-1])

    def _reroute_wire_after_endpoint_move(
        self,
        old_start: QPointF,
        old_end: QPointF,
        old_waypoints: List[QPointF],
        new_start: QPointF,
        new_end: QPointF,
    ) -> List[QPointF]:
        start_moved = not self._same_wire_point(old_start, new_start)
        end_moved = not self._same_wire_point(old_end, new_end)

        if not old_waypoints:
            return self._orthogonal_route_between(new_start, new_end)

        start_delta = self._point_delta(old_start, new_start)
        end_delta = self._point_delta(old_end, new_end)
        if start_moved and end_moved and self._same_delta(start_delta, end_delta):
            dx, dy = start_delta
            return self._normalize_wire_points([
                QPointF(new_start),
                *[QPointF(point.x() + dx, point.y() + dy) for point in old_waypoints],
                QPointF(new_end),
            ])

        old_points = [QPointF(old_start), *[QPointF(point) for point in old_waypoints], QPointF(old_end)]
        points = [QPointF(new_start), *[QPointF(point) for point in old_waypoints], QPointF(new_end)]

        if start_moved and len(points) >= 3:
            old_first_orientation = self._strict_segment_orientation(old_points[0], old_points[1])
            if old_first_orientation == "horizontal":
                points[1].setY(new_start.y())
            elif old_first_orientation == "vertical":
                points[1].setX(new_start.x())

        if end_moved and len(points) >= 3:
            old_last_orientation = self._strict_segment_orientation(old_points[-2], old_points[-1])
            if old_last_orientation == "horizontal":
                points[-2].setY(new_end.y())
            elif old_last_orientation == "vertical":
                points[-2].setX(new_end.x())

        return self._repair_orthogonal_points(points)

    def _sync_wire_waypoint_items(self, wire: Wire, moving_item: Optional[WireWaypointGraphicsItem] = None):
        for index in range(len(wire.waypoints)):
            item = self.wire_waypoint_items.get((wire.wire_id, index))
            if item is not None and item is not moving_item:
                item.sync_from_model()

    def _update_wire_item_after_waypoint_change(
        self,
        wire: Wire,
        moving_item: Optional[WireWaypointGraphicsItem] = None,
    ):
        wire_item = self.wire_items.get(wire.wire_id)
        if wire_item is not None and isValid(wire_item):
            wire_item._update_bounds()
            wire_item.update()
        self._sync_wire_waypoint_items(wire, moving_item)
        self._refresh_wire_intersections()
        self.canvas_changed.emit()

    def _move_wire_waypoint(
        self,
        wire: Wire,
        waypoint_index: int,
        desired_pos: QPointF,
        moving_item: Optional[WireWaypointGraphicsItem] = None,
    ) -> QPointF:
        if waypoint_index < 0 or waypoint_index >= len(wire.waypoints):
            return self.snap_to_grid(desired_pos)

        start_pos, end_pos = self._wire_endpoint_positions(wire)
        if start_pos is None or end_pos is None:
            return self.snap_to_grid(desired_pos)

        waypoints = [QPointF(float(x), float(y)) for x, y in wire.waypoints]
        anchors = [QPointF(start_pos), *[QPointF(point) for point in waypoints], QPointF(end_pos)]
        anchor_index = waypoint_index + 1
        target = self.snap_to_grid(desired_pos)

        neighbor_specs = [
            (anchor_index - 1, self._segment_orientation(anchors[anchor_index - 1], anchors[anchor_index])),
            (anchor_index + 1, self._segment_orientation(anchors[anchor_index], anchors[anchor_index + 1])),
        ]

        for neighbor_index, orientation in neighbor_specs:
            if orientation is None:
                continue
            neighbor = anchors[neighbor_index]
            if neighbor_index == 0 or neighbor_index == len(anchors) - 1:
                if orientation == "vertical":
                    target.setX(neighbor.x())
                else:
                    target.setY(neighbor.y())

        waypoints[waypoint_index] = QPointF(target)
        for neighbor_index, orientation in neighbor_specs:
            if orientation is None or neighbor_index == 0 or neighbor_index == len(anchors) - 1:
                continue
            self._set_point_axis(
                waypoints[neighbor_index - 1],
                orientation,
                target.x() if orientation == "vertical" else target.y(),
            )

        wire.waypoints = self._wire_point_tuples(waypoints)
        self._update_wire_item_after_waypoint_change(wire, moving_item)
        return QPointF(target)

    def _begin_component_drag(self):
        """Capture the selected component group before a drag starts."""
        active_components = self._active_components()
        selected_ids = {
            item.component.comp_id
            for item in self.scene.selectedItems()
            if isinstance(item, ComponentGraphicsItem)
        }
        self._component_drag_selected_ids = selected_ids
        self._component_drag_start_positions = {
            comp_id: (active_components[comp_id].x, active_components[comp_id].y)
            for comp_id in selected_ids
            if comp_id in active_components
        }
        self._component_drag_wire_snapshot = {}
        for wire in self._active_wires().values():
            if wire.from_comp not in selected_ids and wire.to_comp not in selected_ids:
                continue
            old_start, old_end = self._wire_endpoint_positions(wire)
            if old_start is None or old_end is None:
                continue
            self._component_drag_wire_snapshot[wire.wire_id] = {
                "old_start": QPointF(old_start),
                "old_end": QPointF(old_end),
                "old_waypoints": [
                    QPointF(float(x), float(y))
                    for x, y in wire.waypoints
                ],
            }

    def _update_connected_wires_during_component_drag(self):
        if not self._component_drag_wire_snapshot:
            return

        active_wires = self._active_wires()
        for wire_id, snapshot in self._component_drag_wire_snapshot.items():
            wire = active_wires.get(wire_id)
            if wire is None:
                continue

            new_start, new_end = self._wire_endpoint_positions(wire)
            if new_start is None or new_end is None:
                continue

            new_points = self._reroute_wire_after_endpoint_move(
                old_start=snapshot["old_start"],
                old_end=snapshot["old_end"],
                old_waypoints=snapshot["old_waypoints"],
                new_start=new_start,
                new_end=new_end,
            )
            wire.waypoints = self._points_to_waypoints(new_points)

            wire_item = self.wire_items.get(wire.wire_id)
            if wire_item is not None and isValid(wire_item):
                wire_item.update_positions(start_pos=new_start, end_pos=new_end)

            self._sync_wire_waypoint_items(wire)

        self._refresh_wire_intersections()
        self.canvas_changed.emit()

    def _finish_component_drag_waypoints(self, apply: bool):
        """Finalize or restore wire waypoints after a component drag."""
        try:
            if not self._component_drag_start_positions:
                return

            if not apply:
                active_wires = self._active_wires()
                for wire_id, snapshot in self._component_drag_wire_snapshot.items():
                    wire = active_wires.get(wire_id)
                    if wire is None:
                        continue
                    wire.waypoints = self._wire_point_tuples(snapshot["old_waypoints"])
                self._refresh_wires()
                return

            self._refresh_wires()
        finally:
            self._component_drag_selected_ids = set()
            self._component_drag_start_positions = {}
            self._component_drag_wire_snapshot = {}

    def _add_component_to_active_design(self, comp: ComponentInstance):
        subdef = self._active_subcircuit_def()
        if subdef is None:
            self.model.add_component(comp)
            return
        self.model._save_undo_state()
        subdef.components[comp.comp_id] = comp
        self.model._sync_counter_for_component(comp)
        self.model._notify("component_added")

    def _add_wire_to_active_design(self, wire: Wire):
        subdef = self._active_subcircuit_def()
        if subdef is None:
            self.model.add_wire(wire)
            return
        self.model._save_undo_state()
        subdef.wires[wire.wire_id] = wire
        self.model._notify("wire_added")

    def _remove_component_from_active_design(self, comp_id: str):
        subdef = self._active_subcircuit_def()
        if subdef is None:
            self.model.remove_component(comp_id)
            return
        self.model._save_undo_state()
        if comp_id in subdef.components:
            del subdef.components[comp_id]
        for wire_id in [
            wid for wid, wire in subdef.wires.items()
            if wire.from_comp == comp_id or wire.to_comp == comp_id
        ]:
            del subdef.wires[wire_id]
        self.model._notify("component_removed")

    def _remove_wire_from_active_design(self, wire_id: str):
        subdef = self._active_subcircuit_def()
        if subdef is None:
            self.model.remove_wire(wire_id)
            return
        self.model._save_undo_state()
        if wire_id in subdef.wires:
            del subdef.wires[wire_id]
            self.model._notify("wire_removed")

    def mousePressEvent(self, event):
        """鼠标按下"""
        if event.button() == Qt.MouseButton.MiddleButton:
            self._middle_panning = True
            self._middle_pan_last_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        if self.mode == CanvasMode.WIRE and event.button() == Qt.MouseButton.RightButton:
            self._handle_wire_right_click(self.mapToScene(event.pos()))
            event.accept()
            return

        if event.button() == Qt.LeftButton:
            scene_pos = self.mapToScene(event.pos())

            if self.mode == CanvasMode.PLACE:
                pos = self.snap_to_grid(scene_pos)
                self._place_component(pos)
            elif self.mode == CanvasMode.WIRE:
                self._handle_wire_left_click(scene_pos)
                event.accept()
                return
            elif self.mode == CanvasMode.DELETE:
                pos = self.snap_to_grid(scene_pos)
                self._handle_delete_click(pos)
                super().mousePressEvent(event)
            else:
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    item = self.get_component_at(scene_pos)
                    if item:
                        self._apply_component_selection(item, additive=True)
                        event.accept()
                        return
                super().mousePressEvent(event)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """鼠标移动 - 拖拽式连线时更新临时线"""
        if self._middle_panning and self._middle_pan_last_pos is not None:
            delta = event.pos() - self._middle_pan_last_pos
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            self._middle_pan_last_pos = event.pos()
            event.accept()
            return

        if self.mode == CanvasMode.WIRE and self._is_drawing_wire() and self._temp_line:
            scene_pos = self.mapToScene(event.pos())
            self._update_temp_wire(scene_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """鼠标释放 - 拖拽式连线时完成或取消"""
        if event.button() == Qt.MouseButton.MiddleButton and self._middle_panning:
            self._middle_panning = False
            self._middle_pan_last_pos = None
            if self.mode == CanvasMode.SELECT:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            elif self.mode in (CanvasMode.PLACE, CanvasMode.WIRE):
                self.setCursor(Qt.CursorShape.CrossCursor)
            elif self.mode == CanvasMode.DELETE:
                self.setCursor(Qt.CursorShape.ForbiddenCursor)
            event.accept()
            return

        if event.button() == Qt.LeftButton and self.mode == CanvasMode.WIRE:
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _place_component(self, pos: QPointF):
        """放置元件"""
        if self._placing_type is None:
            return

        from models.component_lib import create_component_pins, get_default_params

        params = get_default_params(self._placing_type)
        params.update(self._placing_params)
        probe_type = params.get('probe_type') if self._placing_type == ComponentType.PROBE else None
        pin_count = params.get('n_phases', 3)
        if self._placing_type == ComponentType.LCP_OHL:
            from core.lcp_config import get_lcp_ohl_conductor_count
            pin_count = get_lcp_ohl_conductor_count(params)
        elif self._placing_type == ComponentType.LCP_SINGLE_CABLE:
            pin_count = params.get('n_cables', 1)

        comp = ComponentInstance(
            comp_id=self.model.generate_component_id(self._placing_type),
            comp_type=self._placing_type,
            name=f"{self._placing_type.value}{self.model._id_counters.get(self._placing_type.value, 0)}",
            x=int(pos.x()),
            y=int(pos.y()),
            rotation=0,
            params=params,
            pins=create_component_pins(
                self._placing_type,
                pin_count,
                probe_type=probe_type,
                params=params,
            ),
        )

        self._add_component_to_active_design(comp)

        # 放置完成后自动回到选择模式
        self.set_mode(CanvasMode.SELECT)
        self._placing_type = None
        self._placing_params = {}
        self.placement_completed.emit()  # 通知主窗口更新按钮状态

    def _handle_wire_left_click(self, scene_pos: QPointF):
        """PSCAD-style wire input: left click starts or adds a waypoint."""
        pin_info = self.get_pin_at(scene_pos)
        if not self._is_drawing_wire():
            if pin_info:
                self._start_wire_drag(pin_info, scene_pos)
                return
            wire_item = self.get_wire_at(scene_pos)
            if wire_item:
                start_pos = self.snap_to_grid(wire_item.nearest_point(scene_pos))
                self._start_wire_input(start_pos, start_wire_id=wire_item.wire.wire_id)
                return
            self._start_wire_input(self.snap_to_grid(scene_pos))
            return

        if pin_info:
            self._complete_wire_drag(pin_info)
            return

        wire_item = self.get_wire_at(scene_pos)
        if wire_item:
            self._complete_wire_to_existing_wire(wire_item, scene_pos)
            return

        waypoint = self._resolve_wire_point(scene_pos, snap_to_wires=False)
        self._append_wire_vertices_to(waypoint)
        self._update_temp_wire(waypoint)

    def _handle_wire_right_click(self, scene_pos: QPointF):
        """PSCAD-style wire input: right click finishes on a pin/wire or cancels."""
        if not self._is_drawing_wire():
            return

        pin_info = self.get_pin_at(scene_pos)
        if pin_info:
            self._complete_wire_drag(pin_info)
            return

        wire_item = self.get_wire_at(scene_pos)
        if wire_item:
            self._complete_wire_to_existing_wire(wire_item, scene_pos)
            return

        self._complete_wire_to_new_junction(scene_pos)

    def _ensure_temp_wire_node(self) -> QGraphicsEllipseItem:
        if self._temp_wire_node is not None and not isValid(self._temp_wire_node):
            self._temp_wire_node = None
        if self._temp_wire_node is None:
            dot_radius = WireGraphicsItem.ENDPOINT_DOT_DIAMETER / 2
            node = QGraphicsEllipseItem(
                -dot_radius,
                -dot_radius,
                WireGraphicsItem.ENDPOINT_DOT_DIAMETER,
                WireGraphicsItem.ENDPOINT_DOT_DIAMETER,
            )
            node.setPen(QPen(Qt.PenStyle.NoPen))
            node.setBrush(QBrush(WireGraphicsItem.WIRE_COLOR))
            node.setZValue(20)
            self._temp_wire_node = node
            self.scene.addItem(node)
        return self._temp_wire_node

    def _update_temp_wire_node(self, pos: QPointF):
        self._ensure_temp_wire_node().setPos(pos)

    def _remove_temp_wire_node(self):
        if self._temp_wire_node is not None:
            if isValid(self._temp_wire_node) and self._temp_wire_node.scene() is self.scene:
                self.scene.removeItem(self._temp_wire_node)
            self._temp_wire_node = None

    def _remove_temp_wire_items(self):
        if self._temp_line is not None:
            if isValid(self._temp_line) and self._temp_line.scene() is self.scene:
                self.scene.removeItem(self._temp_line)
            self._temp_line = None
        self._remove_temp_wire_node()

    def _clear_wire_input_state(self):
        self._remove_temp_wire_items()
        self._wiring_start = None
        self._wire_start_pos = None
        self._wire_start_wire_id = None
        self._wire_waypoints = []

    def _is_drawing_wire(self) -> bool:
        return self._wire_start_pos is not None

    def _update_temp_wire(self, end_pos: QPointF):
        if not self._temp_line:
            return
        if not isValid(self._temp_line):
            self._clear_wire_input_state()
            return
        preview_points = self._wire_path_to(self._resolve_wire_point(end_pos))
        if len(preview_points) < 2:
            return
        preview_pos = preview_points[-1]
        self._temp_line.wire.waypoints = self._wire_point_tuples(preview_points[1:-1])
        self._temp_line.update_positions(end_pos=preview_pos)
        self._update_temp_wire_node(preview_pos)

    def get_wire_at(self, pos: QPointF, tolerance: float = 10.0) -> Optional[WireGraphicsItem]:
        best_item = None
        best_dist = tolerance
        for item in self.wire_items.values():
            dist = item.distance_to_point(pos)
            if dist <= best_dist:
                best_item = item
                best_dist = dist
        return best_item

    @staticmethod
    def _point_tuple(point: QPointF) -> tuple:
        return (float(point.x()), float(point.y()))

    def _wire_point_tuples(self, points: List[QPointF]) -> List[tuple]:
        return [self._point_tuple(point) for point in points]

    def _wire_start_scene_pos(self) -> Optional[QPointF]:
        if self._wire_start_pos is not None:
            return QPointF(self._wire_start_pos)
        if self._wiring_start is None:
            return None
        start_comp_id, start_pin = self._wiring_start
        comp_item = self.component_items.get(start_comp_id)
        if comp_item is None:
            return None
        return comp_item.get_all_scene_pin_positions().get(start_pin)

    def _wire_last_point(self) -> Optional[QPointF]:
        if self._wire_waypoints:
            return self._wire_waypoints[-1]
        return self._wire_start_scene_pos()

    def _resolve_wire_point(self, pos: QPointF, snap_to_wires: bool = True) -> QPointF:
        pin_info = self.get_pin_at(pos)
        if pin_info:
            comp_item, pin_name = pin_info
            return QPointF(comp_item.get_all_scene_pin_positions()[pin_name])

        if snap_to_wires:
            wire_item = self.get_wire_at(pos)
            if wire_item is not None:
                return self.snap_to_grid(wire_item.nearest_point(pos))

        return self.snap_to_grid(pos)

    @staticmethod
    def _same_wire_point(first: QPointF, second: QPointF) -> bool:
        return WireGraphicsItem._same_point(first, second)

    def _orthogonal_additions(self, start: QPointF, target: QPointF) -> List[QPointF]:
        if self._same_wire_point(start, target):
            return []
        if abs(start.x() - target.x()) <= 0.1 or abs(start.y() - target.y()) <= 0.1:
            return [QPointF(target)]
        return [
            QPointF(target.x(), start.y()),
            QPointF(target),
        ]

    def _normalize_wire_points(self, points: List[QPointF]) -> List[QPointF]:
        deduped: List[QPointF] = []
        for point in points:
            if not deduped or not self._same_wire_point(deduped[-1], point):
                deduped.append(QPointF(point))

        if len(deduped) <= 2:
            return deduped

        normalized = [deduped[0]]
        for index in range(1, len(deduped) - 1):
            prev = normalized[-1]
            curr = deduped[index]
            next_point = deduped[index + 1]
            horizontal = (
                abs(prev.y() - curr.y()) <= 0.1
                and abs(curr.y() - next_point.y()) <= 0.1
            )
            vertical = (
                abs(prev.x() - curr.x()) <= 0.1
                and abs(curr.x() - next_point.x()) <= 0.1
            )
            if horizontal or vertical:
                continue
            normalized.append(QPointF(curr))
        normalized.append(deduped[-1])
        return normalized

    def _current_wire_points(self) -> List[QPointF]:
        start = self._wire_start_scene_pos()
        if start is None:
            return []
        return [QPointF(start), *[QPointF(point) for point in self._wire_waypoints]]

    def _wire_path_to(self, target: QPointF) -> List[QPointF]:
        points = self._current_wire_points()
        if not points:
            return []
        points.extend(self._orthogonal_additions(points[-1], target))
        return self._normalize_wire_points(points)

    def _append_wire_vertices_to(self, target: QPointF):
        points = self._wire_path_to(target)
        if len(points) <= 1:
            return
        self._wire_waypoints = [QPointF(point) for point in points[1:]]

    @staticmethod
    def _points_axis_aligned(first: QPointF, second: QPointF) -> bool:
        return (
            abs(first.x() - second.x()) < 0.1
            or abs(first.y() - second.y()) < 0.1
        )

    def _constrain_wire_point(self, pos: QPointF) -> QPointF:
        return self._resolve_wire_point(pos)

    def _target_reachable_from_last_point(self, target: QPointF) -> bool:
        last = self._wire_last_point()
        return last is not None and self._points_axis_aligned(last, target)

    def _wire_waypoint_tuples(self, end_pos: Optional[QPointF] = None) -> List[tuple]:
        if end_pos is None:
            return [self._point_tuple(point) for point in self._wire_waypoints]
        points = self._wire_path_to(end_pos)
        if len(points) < 2:
            return []
        return self._wire_point_tuples(points[1:-1])

    def _add_wire_between(
        self,
        start_comp_id: str,
        start_pin: str,
        end_comp_id: str,
        end_pin: str,
        waypoints: Optional[List[tuple]] = None,
    ) -> Optional[Wire]:
        if start_comp_id == end_comp_id:
            return None

        active_wires = self._active_wires()
        for existing in active_wires.values():
            same_direction = (
                existing.from_comp == start_comp_id
                and existing.from_pin == start_pin
                and existing.to_comp == end_comp_id
                and existing.to_pin == end_pin
            )
            reverse_direction = (
                existing.from_comp == end_comp_id
                and existing.from_pin == end_pin
                and existing.to_comp == start_comp_id
                and existing.to_pin == start_pin
            )
            if same_direction or reverse_direction:
                return None

        import uuid
        wire = Wire(
            wire_id=f"W_{uuid.uuid4().hex[:8]}",
            from_comp=start_comp_id,
            from_pin=start_pin,
            to_comp=end_comp_id,
            to_pin=end_pin,
            waypoints=list(waypoints or []),
        )
        self._add_wire_to_active_design(wire)
        if self.mode != CanvasMode.SELECT:
            self._set_items_interactive(False)
        return wire

    def _make_junction_at(self, pos: QPointF) -> ComponentInstance:
        junction = ComponentInstance(
            comp_id=self.model.generate_component_id(ComponentType.JUNCTION),
            comp_type=ComponentType.JUNCTION,
            name=f"JUNC{self.model._id_counters.get(ComponentType.JUNCTION.value, 0)}",
            x=int(pos.x()),
            y=int(pos.y()),
            rotation=0,
            params={},
            pins=[Pin("node", 0, 0)],
        )
        self.model._sync_counter_for_component(junction)
        return junction

    def _new_wire(
        self,
        start_comp_id: str,
        start_pin: str,
        end_comp_id: str,
        end_pin: str,
        waypoints: Optional[List[tuple]] = None,
    ) -> Wire:
        import uuid

        return Wire(
            wire_id=f"W_{uuid.uuid4().hex[:8]}",
            from_comp=start_comp_id,
            from_pin=start_pin,
            to_comp=end_comp_id,
            to_pin=end_pin,
            waypoints=list(waypoints or []),
        )

    def _has_duplicate_wire(
        self,
        start_comp_id: str,
        start_pin: str,
        end_comp_id: str,
        end_pin: str,
        active_wires: Dict[str, Wire],
    ) -> bool:
        for wire in active_wires.values():
            same_direction = (
                wire.from_comp == start_comp_id
                and wire.from_pin == start_pin
                and wire.to_comp == end_comp_id
                and wire.to_pin == end_pin
            )
            reverse_direction = (
                wire.from_comp == end_comp_id
                and wire.from_pin == end_pin
                and wire.to_comp == start_comp_id
                and wire.to_pin == start_pin
            )
            if same_direction or reverse_direction:
                return True
        return False

    def _split_wire_to_junction(
        self,
        wire_item: WireGraphicsItem,
        split_pos: QPointF,
        active_components: Dict[str, ComponentInstance],
        active_wires: Dict[str, Wire],
    ) -> Tuple[str, str]:
        original = wire_item.wire
        junction = self._make_junction_at(split_pos)
        first_waypoints, second_waypoints = self._split_wire_waypoints(wire_item, split_pos)

        active_components[junction.comp_id] = junction
        active_wires.pop(original.wire_id, None)
        for wire in (
            self._new_wire(
                original.from_comp,
                original.from_pin,
                junction.comp_id,
                "node",
                first_waypoints,
            ),
            self._new_wire(
                junction.comp_id,
                "node",
                original.to_comp,
                original.to_pin,
                second_waypoints,
            ),
        ):
            active_wires[wire.wire_id] = wire
        return junction.comp_id, "node"

    def _start_anchor_for_commit(
        self,
        active_components: Dict[str, ComponentInstance],
        active_wires: Dict[str, Wire],
    ) -> Tuple[str, str]:
        if self._wiring_start is not None:
            return self._wiring_start

        if self._wire_start_wire_id is not None:
            wire_item = self.wire_items.get(self._wire_start_wire_id)
            if wire_item is not None and self._wire_start_wire_id in active_wires:
                return self._split_wire_to_junction(
                    wire_item,
                    self._wire_start_pos,
                    active_components,
                    active_wires,
                )

        junction = self._make_junction_at(self._wire_start_pos)
        active_components[junction.comp_id] = junction
        return junction.comp_id, "node"

    def _target_anchor_for_commit(
        self,
        target_pos: QPointF,
        active_components: Dict[str, ComponentInstance],
        active_wires: Dict[str, Wire],
        pin_info: Optional[Tuple['ComponentGraphicsItem', str]] = None,
        wire_item: Optional[WireGraphicsItem] = None,
    ) -> Tuple[str, str]:
        if pin_info is not None:
            comp_item, pin_name = pin_info
            return comp_item.component.comp_id, pin_name

        if wire_item is not None and wire_item.wire.wire_id in active_wires:
            return self._split_wire_to_junction(
                wire_item,
                target_pos,
                active_components,
                active_wires,
            )

        junction = self._make_junction_at(target_pos)
        active_components[junction.comp_id] = junction
        return junction.comp_id, "node"

    def _finish_wire_to_target(
        self,
        target_pos: QPointF,
        pin_info: Optional[Tuple['ComponentGraphicsItem', str]] = None,
        wire_item: Optional[WireGraphicsItem] = None,
    ):
        if not self._is_drawing_wire():
            return

        path = self._wire_path_to(target_pos)
        if len(path) < 2 or WireGraphicsItem._same_point(path[0], path[-1]):
            self._cancel_wire_drag()
            return

        self.model._save_undo_state()
        active_components = self._active_components()
        active_wires = self._active_wires()
        start_comp_id, start_pin = self._start_anchor_for_commit(active_components, active_wires)
        end_comp_id, end_pin = self._target_anchor_for_commit(
            path[-1],
            active_components,
            active_wires,
            pin_info=pin_info,
            wire_item=wire_item,
        )

        if start_comp_id != end_comp_id and not self._has_duplicate_wire(
            start_comp_id,
            start_pin,
            end_comp_id,
            end_pin,
            active_wires,
        ):
            wire = self._new_wire(
                start_comp_id,
                start_pin,
                end_comp_id,
                end_pin,
                self._wire_point_tuples(path[1:-1]),
            )
            active_wires[wire.wire_id] = wire

        self._reset_wire_state()
        self.model._notify("component_added")
        if self.mode != CanvasMode.SELECT:
            self._set_items_interactive(False)
        self.wire_created.emit(start_comp_id, start_pin, end_comp_id, end_pin)

    def _complete_wire_to_new_junction(self, scene_pos: QPointF):
        if not self._is_drawing_wire():
            return
        end_pos = self._resolve_wire_point(scene_pos, snap_to_wires=False)
        self._finish_wire_to_target(end_pos)

    def _complete_wire_to_existing_wire(self, wire_item: WireGraphicsItem, scene_pos: QPointF):
        split_pos = self.snap_to_grid(wire_item.nearest_point(scene_pos))
        self._finish_wire_to_target(split_pos, wire_item=wire_item)

    def _split_wire_waypoints(self, wire_item: WireGraphicsItem, split_pos: QPointF) -> Tuple[List[tuple], List[tuple]]:
        pts = wire_item._manhattan_points()
        if len(pts) < 2:
            return [], []

        segment_index = min(
            range(len(pts) - 1),
            key=lambda i: WireGraphicsItem._distance_to_segment(split_pos, pts[i], pts[i + 1])[0],
        )
        first_path = self._dedupe_points([*pts[:segment_index + 1], split_pos])
        second_path = self._dedupe_points([split_pos, *pts[segment_index + 1:]])
        return self._path_waypoints(first_path), self._path_waypoints(second_path)

    @staticmethod
    def _dedupe_points(points: List[QPointF]) -> List[QPointF]:
        result = []
        for point in points:
            if not result or (
                abs(result[-1].x() - point.x()) > 0.1
                or abs(result[-1].y() - point.y()) > 0.1
            ):
                result.append(point)
        return result

    def _path_waypoints(self, points: List[QPointF]) -> List[tuple]:
        if len(points) <= 2:
            return []
        return [self._point_tuple(point) for point in points[1:-1]]

    def _reset_wire_state(self):
        self._clear_wire_input_state()
        self.setCursor(Qt.CrossCursor)

    def _start_wire_drag(self, pin_info: Tuple['ComponentGraphicsItem', str], pos: QPointF):
        """开始拖拽式连线：在引脚上按下鼠标"""
        comp_item, pin_name = pin_info
        pin_pos = comp_item.get_all_scene_pin_positions()[pin_name]
        self._start_wire_input(
            pin_pos,
            start_pin=(comp_item.component.comp_id, pin_name),
        )

    def _start_wire_input(
        self,
        start_pos: QPointF,
        start_pin: Optional[Tuple[str, str]] = None,
        start_wire_id: Optional[str] = None,
    ):
        self._clear_wire_input_state()
        self._wiring_start = start_pin
        self._wire_start_pos = QPointF(start_pos)
        self._wire_start_wire_id = start_wire_id
        self._wire_waypoints = []

        self._temp_line = WireGraphicsItem(
            Wire(wire_id="temp", from_comp="", from_pin="", to_comp="", to_pin=""),
            self._wire_start_pos, self._wire_start_pos
        )
        self._temp_line.pen = QPen(
            WireGraphicsItem.WIRE_COLOR,
            WireGraphicsItem.WIRE_WIDTH,
            Qt.PenStyle.DashLine,
        )
        self.scene.addItem(self._temp_line)
        self._update_temp_wire(self._wire_start_pos)
        self.setCursor(Qt.CrossCursor)

    def _complete_wire_drag(self, pin_info: Tuple['ComponentGraphicsItem', str]):
        """Finish a click-style wire on a component pin."""
        comp_item, pin_name = pin_info
        end_pos = comp_item.get_all_scene_pin_positions()[pin_name]
        self._finish_wire_to_target(end_pos, pin_info=pin_info)

    def _cancel_wire_drag(self):
        """取消拖拽式连线：在空白处释放鼠标"""
        self._clear_wire_input_state()
        self.setCursor(Qt.CrossCursor)

    def _handle_delete_click(self, pos: QPointF):
        """处理删除模式下的点击"""
        item = self.get_item_at(pos)
        if isinstance(item, ComponentGraphicsItem):
            self._remove_component_from_active_design(item.component.comp_id)
        elif isinstance(item, WireGraphicsItem):
            self._remove_wire_from_active_design(item.wire.wire_id)

    def wheelEvent(self, event):
        """鼠标滚轮缩放"""
        zoom_factor = 1.15
        if event.angleDelta().y() > 0:
            self.scale_view(zoom_factor)
        else:
            self.scale_view(1 / zoom_factor)

    def contextMenuEvent(self, event):
        """右键菜单"""
        from PySide6.QtWidgets import QMenu
        scene_pos = self.mapToScene(event.pos())
        if self.mode == CanvasMode.WIRE:
            event.accept()
            return
        item = self.get_component_at(scene_pos)

        menu = QMenu(self)

        if item:
            # 有元件被右击
            if not item.isSelected():
                item.setSelected(True)

            copy_act = menu.addAction("复制 (Ctrl+C)")
            menu.addSeparator()
            delete_act = menu.addAction("删除 (Del)")
            rotate_act = menu.addAction("旋转 (Ctrl+R)")
            menu.addSeparator()
            # 添加探针子菜单
            probe_menu = menu.addMenu("添加探针")
            add_v_probe_act = probe_menu.addAction("⚡ 对地电压探针")
            add_i_probe_act = probe_menu.addAction("⚡ 电流探针")
            # 封装为子电路（选中 >= 2 个元件时可用）
            subcircuit_act = menu.addAction("📦 封装为子电路")
            selected_comps = [item for item in self.scene.selectedItems()
                              if isinstance(item, ComponentGraphicsItem)]
            subcircuit_act.setEnabled(len(selected_comps) >= 2)
            manage_ports_act = None
            if item.component.comp_type == ComponentType.SUBCIRCUIT:
                manage_ports_act = menu.addAction("Manage Ports")
            menu.addSeparator()
            prop_act = menu.addAction("属性")

            action = menu.exec(event.globalPos())
            if action == delete_act:
                self._delete_selected()
            elif action == rotate_act:
                self._rotate_selected()
            elif action == copy_act:
                self._copy_selected()
            elif action == prop_act:
                self.canvas_changed.emit()
            elif action == add_v_probe_act:
                self._add_probe_at_pin(item, 'voltage_ground')
            elif action == add_i_probe_act:
                self._add_probe_at_pin(item, 'branch_current')
            elif action == subcircuit_act:
                self._create_subcircuit_from_selection()
            elif manage_ports_act is not None and action == manage_ports_act:
                sub_name = item.component.params.get("subcircuit_name", "")
                self._manage_subcircuit_ports(sub_name)
        else:
            # 右击空白处 — 检查是否右击了引脚
            pin_info = self.get_pin_at(scene_pos)
            if pin_info:
                pin_menu = QMenu(self)
                add_v_probe_act = pin_menu.addAction("⚡ 在此引脚添加对地电压探针")
                add_i_probe_act = pin_menu.addAction("⚡ 在此引脚添加电流探针")
                action = pin_menu.exec(event.globalPos())
                if action == add_v_probe_act:
                    self._add_probe_at_pin(pin_info[0], 'voltage_ground', pin_info[1])
                elif action == add_i_probe_act:
                    self._add_probe_at_pin(pin_info[0], 'branch_current', pin_info[1])
                return

            # 右击空白处
            paste_act = menu.addAction("粘贴 (Ctrl+V)")
            paste_act.setEnabled(self._clipboard is not None)
            menu.addSeparator()
            # 如果在子电路编辑模式，显示退出选项
            exit_sub_act = None
            if self._editing_subcircuit:
                exit_sub_act = menu.addAction("🔙 退出子电路编辑")
                menu.addSeparator()
            zoom_in_act = menu.addAction("放大")
            zoom_out_act = menu.addAction("缩小")
            reset_act = menu.addAction("重置视图")
            toggle_grid_act = menu.addAction("切换网格")
            menu.addSeparator()
            ground_act = menu.addAction("添加接地")

            action = menu.exec(event.globalPos())
            if action == exit_sub_act:
                self._exit_subcircuit()
            elif action == paste_act:
                self._paste_clipboard(scene_pos)
            elif action == zoom_in_act:
                self.scale_view(1.2)
            elif action == zoom_out_act:
                self.scale_view(0.8)
            elif action == reset_act:
                self.resetTransform()
            elif action == toggle_grid_act:
                self.show_grid = not self.show_grid
                self._refresh_view()
            elif action == ground_act:
                self.add_ground_requested.emit(scene_pos)

    def _add_probe_at_pin(self, comp_item: 'ComponentGraphicsItem',
                          probe_type: str, pin_name: str = None):
        """在元件引脚旁放置探针，自动连线"""
        from models.component_lib import create_component_pins, get_default_params

        comp = comp_item.component
        active_components, _active_wires = self._active_design()
        if comp.comp_id not in active_components:
            return
        if pin_name is None:
            # 默认选第一个非地引脚
            for p in comp.pins:
                if p.name != 'gnd':
                    pin_name = p.name
                    break
            if pin_name is None:
                return

        # 找到目标引脚的场景坐标
        pin_positions = comp_item.get_all_scene_pin_positions()
        target_pin_pos = pin_positions.get(pin_name)
        if target_pin_pos is None:
            return

        # 探针放在引脚旁边（偏移）
        offset_x = 40
        offset_y = -20
        probe_pos = QPointF(target_pin_pos.x() + offset_x, target_pin_pos.y() + offset_y)
        probe_pos = self.snap_to_grid(probe_pos)

        # 确定默认单位
        unit = 'kV' if probe_type in ('voltage', 'voltage_ground', 'voltage_between') else 'A'

        # 创建探针元件
        params = get_default_params(ComponentType.PROBE)
        params['probe_type'] = probe_type
        params['unit'] = unit
        if probe_type == 'branch_current':
            params['branch_name'] = comp.name
            params['target_comp_id'] = comp.comp_id
            params['target_pin'] = pin_name

        probe_comp = ComponentInstance(
            comp_id=self.model.generate_component_id(ComponentType.PROBE),
            comp_type=ComponentType.PROBE,
            name=f"PRB{self.model._id_counters.get('PRB', 0)}",
            x=int(probe_pos.x()),
            y=int(probe_pos.y()),
            rotation=0,
            params=params,
            pins=create_component_pins(ComponentType.PROBE, probe_type=probe_type),
        )

        self._add_component_to_active_design(probe_comp)

        # 自动连线：从探针 sense 引脚到目标引脚
        import uuid
        wire = Wire(
            wire_id=f"W_{uuid.uuid4().hex[:8]}",
            from_comp=probe_comp.comp_id,
            from_pin='sense',
            to_comp=comp.comp_id,
            to_pin=pin_name,
        )
        self._add_wire_to_active_design(wire)
        self._refresh_view()

    def _create_subcircuit_from_selection(self):
        """将选中元件封装为子电路"""
        from PySide6.QtWidgets import QInputDialog

        selected_comps = [item for item in self.scene.selectedItems()
                          if isinstance(item, ComponentGraphicsItem)]
        if len(selected_comps) < 2:
            return

        # 弹出对话框输入子电路名称
        name, ok = QInputDialog.getText(
            self, "封装为子电路", "子电路名称:",
            text=f"Sub{len(self.model.subcircuit_defs) + 1}"
        )
        if not ok or not name.strip():
            return
        name = name.strip()

        # 检查名称是否已存在
        if name in self.model.subcircuit_defs:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "错误", f"子电路名称 '{name}' 已存在")
            return

        comp_ids = [item.component.comp_id for item in selected_comps]
        active_components, active_wires = self._active_design()
        try:
            result = self.model.create_subcircuit_from_design_selection(
                components=active_components,
                wires=active_wires,
                comp_ids=comp_ids,
                name=name,
            )
        except ValueError as exc:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "错误", str(exc))
            return

        if result is None:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "无法封装",
                "封装失败：选中的元件没有外部连线，或元件数量不足。"
            )
            return

        # 刷新画布
        self._refresh_view()

    def _manage_subcircuit_ports(self, sub_name: str):
        """Edit electrical ports for a subcircuit definition."""
        from PySide6.QtWidgets import (
            QAbstractItemView,
            QComboBox,
            QDialog,
            QDialogButtonBox,
            QHeaderView,
            QMessageBox,
            QSpinBox,
            QTableWidget,
            QTableWidgetItem,
            QVBoxLayout,
        )

        subdef = self.model.subcircuit_defs.get(sub_name)
        if subdef is None:
            QMessageBox.warning(
                self,
                "Subcircuit Ports",
                f"Subcircuit definition not found: {sub_name}",
            )
            return

        side_order = {"left": 0, "right": 1, "top": 2, "bottom": 3}
        ports = sorted(
            subdef.ports,
            key=lambda p: (side_order.get(p.side, 99), p.order, p.port_name),
        )

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Manage Ports - {sub_name}")
        dialog.resize(720, 360)
        layout = QVBoxLayout(dialog)

        table = QTableWidget(len(ports), 6, dialog)
        table.setHorizontalHeaderLabels([
            "Name",
            "Side",
            "Order",
            "Description",
            "Internal Component",
            "Internal Pin",
        ])
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

        original_rows = []
        for row, port in enumerate(ports):
            original_rows.append({
                "name": port.port_name,
                "side": port.side,
                "order": int(port.order),
                "description": port.description,
            })

            table.setItem(row, 0, QTableWidgetItem(port.port_name))

            side_combo = QComboBox(table)
            side_combo.addItems(["left", "right", "top", "bottom"])
            if port.side in side_order:
                side_combo.setCurrentText(port.side)
            table.setCellWidget(row, 1, side_combo)

            order_spin = QSpinBox(table)
            order_spin.setRange(-9999, 9999)
            order_spin.setValue(int(port.order))
            table.setCellWidget(row, 2, order_spin)

            table.setItem(row, 3, QTableWidgetItem(port.description))

            comp_item = QTableWidgetItem(port.internal_comp_id)
            comp_item.setFlags(comp_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, 4, comp_item)

            pin_item = QTableWidgetItem(port.internal_pin_name)
            pin_item.setFlags(pin_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, 5, pin_item)

        layout.addWidget(table)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        rows = []
        names = []
        for row, original in enumerate(original_rows):
            name_item = table.item(row, 0)
            desc_item = table.item(row, 3)
            new_name = (name_item.text() if name_item else "").strip()
            if not new_name:
                QMessageBox.warning(self, "Subcircuit Ports", "Port names cannot be empty.")
                return
            names.append(new_name)
            rows.append({
                "old_name": original["name"],
                "old_side": original["side"],
                "old_order": original["order"],
                "old_description": original["description"],
                "new_name": new_name,
                "side": table.cellWidget(row, 1).currentText(),
                "order": table.cellWidget(row, 2).value(),
                "description": desc_item.text() if desc_item else "",
            })

        if len(names) != len(set(names)):
            QMessageBox.warning(self, "Subcircuit Ports", "Port names must be unique.")
            return

        try:
            for row in rows:
                current_name = row["old_name"]
                if row["new_name"] != current_name:
                    self.model.rename_subcircuit_port(sub_name, current_name, row["new_name"])
                    current_name = row["new_name"]
                if row["side"] != row["old_side"]:
                    self.model.update_subcircuit_port_side(sub_name, current_name, row["side"])
                if row["order"] != row["old_order"]:
                    self.model.update_subcircuit_port_order(sub_name, current_name, row["order"])
                if row["description"] != row["old_description"]:
                    self.model.update_subcircuit_port_description(
                        sub_name,
                        current_name,
                        row["description"],
                    )
        except ValueError as exc:
            QMessageBox.warning(self, "Subcircuit Ports", str(exc))
            return

        self._refresh_view()

    def keyPressEvent(self, event):
        """键盘事件"""
        if self._is_any_item_dragging() and event.modifiers() == Qt.ControlModifier:
            if event.key() in (Qt.Key_Z, Qt.Key_Y):
                event.ignore()
                return

        if event.key() == Qt.Key_Delete or event.key() == Qt.Key_Backspace:
            self._delete_selected()
        elif event.key() == Qt.Key_Escape:
            if self.mode != CanvasMode.SELECT:
                self.set_mode(CanvasMode.SELECT)
                self._placing_type = None
                self._placing_params = {}
                self._clear_wire_input_state()
        elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_R:
            self._rotate_selected()
        elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_Z:
            self.model.undo()
        elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_Y:
            self.model.redo()
        elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_C:
            self._copy_selected()
        elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_V:
            # 粘贴到画布中心
            center = self.mapToScene(
                self.viewport().width() // 2,
                self.viewport().height() // 2,
            )
            self._paste_clipboard(center)
        else:
            super().keyPressEvent(event)

    def _is_any_item_dragging(self) -> bool:
        for item in self.scene.selectedItems():
            if isinstance(item, ComponentGraphicsItem) and item._drag_snapshot is not None:
                return True
        return False

    def _delete_selected(self):
        """删除选中的元件和连线"""
        items_to_delete = []

        # 删除选中的元件
        for comp_id, item in list(self.component_items.items()):
            if item.isSelected():
                items_to_delete.append(comp_id)

        for comp_id in items_to_delete:
            self._remove_component_from_active_design(comp_id)

        # 删除选中的连线
        for wire_id, item in list(self.wire_items.items()):
            if item.isSelected():
                self._remove_wire_from_active_design(wire_id)

    def _rotate_selected(self):
        """旋转选中的元件"""
        selected_ids = [
            item.component.comp_id
            for item in self.scene.selectedItems()
            if isinstance(item, ComponentGraphicsItem)
        ]
        if not selected_ids:
            return

        subdef = self._active_subcircuit_def()
        if subdef is None:
            for comp_id in selected_ids:
                self.model.rotate_component(comp_id, 90)
            return

        self.model._save_undo_state()
        rotated = False
        for comp_id in selected_ids:
            comp = subdef.components.get(comp_id)
            if comp is None:
                continue
            comp.rotation = (comp.rotation + 90) % 360
            rotated = True
        if rotated:
            self.model._notify("component_rotated")

    def _copy_selected(self):
        """复制选中的元件（及它们之间的连线）到剪贴板"""
        selected = []
        for comp_id, item in self.component_items.items():
            if item.isSelected():
                selected.append(comp_id)
        if not selected:
            return

        # Bug1 修复：使用 _active_components() 而非 self.model.components
        active_comps = self._active_components()
        active_wrs = self._active_wires()

        clipboard_comps = {}
        for cid in selected:
            if cid in active_comps:
                clipboard_comps[cid] = copy.deepcopy(active_comps[cid])

        if not clipboard_comps:
            return

        # Bug3 修复：同时复制选中元件之间的内部连线
        selected_set = set(clipboard_comps.keys())
        clipboard_wires = {}
        for wid, wire in active_wrs.items():
            if wire.from_comp in selected_set and wire.to_comp in selected_set:
                clipboard_wires[wid] = copy.deepcopy(wire)

        self._clipboard = {
            'components': clipboard_comps,
            'wires': clipboard_wires,
        }

    def _paste_clipboard(self, pos: QPointF):
        """从剪贴板粘贴元件（及连线）"""
        if not self._clipboard:
            return

        clipboard_comps = self._clipboard.get('components', {})
        clipboard_wires = self._clipboard.get('wires', {})
        if not clipboard_comps:
            return

        pos = self.snap_to_grid(pos)

        # Bug5 修复：保留元件之间的相对位置
        # 计算原始选区的包围盒中心
        orig_xs = [c.x for c in clipboard_comps.values()]
        orig_ys = [c.y for c in clipboard_comps.values()]
        center_x = sum(orig_xs) / len(orig_xs)
        center_y = sum(orig_ys) / len(orig_ys)

        # Bug7 修复：使用 _active_components() 计算名称
        active_comps = self._active_components()

        # 建立 old_comp_id → new_comp_id 映射，用于重映射连线
        id_remap: Dict[str, str] = {}

        for old_cid, comp in clipboard_comps.items():
            new_id = self.model.generate_component_id(comp.comp_type)
            id_remap[old_cid] = new_id

            # 名称根据当前活动容器计算（含已粘贴的新元件）
            count = len([c for c in active_comps.values()
                         if c.comp_type == comp.comp_type]) + 1
            new_name = f"{comp.comp_type.value}{count}"

            # Bug5：相对于原中心的偏移 + 粘贴点
            rel_x = comp.x - center_x
            rel_y = comp.y - center_y

            # Bug6 修复：使用 copy.deepcopy 处理嵌套 params
            new_pins = []
            for p in comp.pins:
                new_pin = copy.deepcopy(p)
                # Bug4 修复：清除残留的 node_id
                new_pin.node_id = None
                new_pins.append(new_pin)

            new_comp = ComponentInstance(
                comp_id=new_id,
                comp_type=comp.comp_type,
                name=new_name,
                x=int(pos.x() + rel_x),
                y=int(pos.y() + rel_y),
                rotation=comp.rotation,
                params=copy.deepcopy(comp.params),
                pins=new_pins,
            )
            # Bug2 修复：使用 _add_component_to_active_design 而非 model.add_component
            self._add_component_to_active_design(new_comp)

        # Bug3 修复：复制连线，重映射端点 comp_id
        for old_wid, wire in clipboard_wires.items():
            new_from = id_remap.get(wire.from_comp)
            new_to = id_remap.get(wire.to_comp)
            if new_from and new_to:
                new_wire = Wire(
                    wire_id=f"W_{uuid.uuid4().hex[:8]}",
                    from_comp=new_from,
                    from_pin=wire.from_pin,
                    to_comp=new_to,
                    to_pin=wire.to_pin,
                    waypoints=copy.deepcopy(wire.waypoints),
                )
                self._add_wire_to_active_design(new_wire)

    def _on_model_changed(self, event: str = "changed"):
        """模型变化时重绘"""
        if event == "component_moved":
            # 移动时只更新连线位置，不全量重绘
            self._refresh_wires()
            self.canvas_changed.emit()
        elif event in ["component_added", "component_removed", "component_rotated",
                      "params_updated", "subcircuit_ports_updated",
                      "undone", "redone", "cleared"]:
            self._refresh_view()
        elif event in ["wire_added", "wire_removed"]:
            self._refresh_wires()
        elif event == "component_selected":
            # 选中元件时通知属性面板刷新
            self.canvas_changed.emit()

    def _add_wire_graphics_item(self, wire: Wire, start_pos: QPointF, end_pos: QPointF):
        wire_item = WireGraphicsItem(wire, start_pos, end_pos)
        self.scene.addItem(wire_item)
        self.wire_items[wire.wire_id] = wire_item
        for index, _ in enumerate(wire.waypoints):
            waypoint_item = WireWaypointGraphicsItem(self, wire, index)
            self.scene.addItem(waypoint_item)
            self.wire_waypoint_items[(wire.wire_id, index)] = waypoint_item

    def _clear_wire_intersection_items(self):
        for item in list(self.wire_intersection_items):
            if isValid(item) and item.scene() is self.scene:
                self.scene.removeItem(item)
        self.wire_intersection_items.clear()

    @staticmethod
    def _range_contains(value: float, first: float, second: float) -> bool:
        return min(first, second) - 0.1 <= value <= max(first, second) + 0.1

    def _wire_segment_intersection(
        self,
        first_start: QPointF,
        first_end: QPointF,
        second_start: QPointF,
        second_end: QPointF,
    ) -> Optional[QPointF]:
        first_horizontal = abs(first_start.y() - first_end.y()) <= 0.1
        first_vertical = abs(first_start.x() - first_end.x()) <= 0.1
        second_horizontal = abs(second_start.y() - second_end.y()) <= 0.1
        second_vertical = abs(second_start.x() - second_end.x()) <= 0.1

        if first_horizontal and second_vertical:
            x = second_start.x()
            y = first_start.y()
        elif first_vertical and second_horizontal:
            x = first_start.x()
            y = second_start.y()
        else:
            return None

        if (
            self._range_contains(x, first_start.x(), first_end.x())
            and self._range_contains(y, first_start.y(), first_end.y())
            and self._range_contains(x, second_start.x(), second_end.x())
            and self._range_contains(y, second_start.y(), second_end.y())
        ):
            return QPointF(x, y)
        return None

    def _refresh_wire_intersections(self):
        self._clear_wire_intersection_items()
        segments = []
        for wire_item in self.wire_items.values():
            points = wire_item._manhattan_points()
            for index in range(len(points) - 1):
                segments.append((wire_item.wire.wire_id, points[index], points[index + 1]))

        intersections: Dict[Tuple[int, int], QPointF] = {}
        for first_index, (first_wire_id, first_start, first_end) in enumerate(segments):
            for second_wire_id, second_start, second_end in segments[first_index + 1:]:
                if first_wire_id == second_wire_id:
                    continue
                point = self._wire_segment_intersection(first_start, first_end, second_start, second_end)
                if point is None:
                    continue
                key = (round(point.x() * 10), round(point.y() * 10))
                intersections[key] = point

        for point in intersections.values():
            dot_radius = WireGraphicsItem.ENDPOINT_DOT_DIAMETER / 2
            dot = QGraphicsEllipseItem(
                -dot_radius,
                -dot_radius,
                WireGraphicsItem.ENDPOINT_DOT_DIAMETER,
                WireGraphicsItem.ENDPOINT_DOT_DIAMETER,
            )
            dot.setPen(QPen(Qt.PenStyle.NoPen))
            dot.setBrush(QBrush(WireGraphicsItem.WIRE_COLOR))
            dot.setZValue(11)
            dot.setPos(point)
            self.scene.addItem(dot)
            self.wire_intersection_items.append(dot)

    def _refresh_view(self):
        """刷新整个视图"""
        self._clear_wire_input_state()
        # 保存当前选中的元件 ID，以便重绘后恢复选中状态
        selected_ids = set()
        for item in self.scene.selectedItems():
            if isinstance(item, ComponentGraphicsItem):
                selected_ids.add(item.component.comp_id)

        # 清除现有图形项
        self.scene.clear()
        self.component_items.clear()
        self.wire_items.clear()
        self.wire_waypoint_items.clear()
        self.wire_intersection_items.clear()

        # 重新绘制网格
        self._draw_grid()

        if self._editing_subcircuit:
            # 子电路编辑模式 — 显示子电路内部元件
            subdef = self.model.subcircuit_defs.get(self._editing_subcircuit)
            if subdef:
                for comp in subdef.components.values():
                    item = ComponentGraphicsItem(comp, self.model, self)
                    self.scene.addItem(item)
                    self.component_items[comp.comp_id] = item
                    if comp.comp_id in selected_ids:
                        item.setSelected(True)
                # 绘制内部连线
                for wire in subdef.wires.values():
                    start_item = self.component_items.get(wire.from_comp)
                    end_item = self.component_items.get(wire.to_comp)
                    if start_item and end_item:
                        start_pins = start_item.get_all_scene_pin_positions()
                        end_pins = end_item.get_all_scene_pin_positions()
                        sp = start_pins.get(wire.from_pin)
                        ep = end_pins.get(wire.to_pin)
                        if sp and ep:
                            self._add_wire_graphics_item(wire, sp, ep)
                # 绘制端口标记
                for port in subdef.ports:
                    comp = subdef.components.get(port.internal_comp_id)
                    if comp:
                        # 在端口引脚旁画标记
                        pass  # TODO: 端口高亮
                self._refresh_wire_intersections()
            else:
                # 子电路定义不存在，退出编辑模式
                self._editing_subcircuit = None
                self._subcircuit_breadcrumb.clear()
                # 回退到顶层
                for comp in self.model.components.values():
                    item = ComponentGraphicsItem(comp, self.model, self)
                    self.scene.addItem(item)
                    self.component_items[comp.comp_id] = item
                    if comp.comp_id in selected_ids:
                        item.setSelected(True)
                self._refresh_wires()
        else:
            # 正常模式 — 显示顶层元件
            for comp in self.model.components.values():
                item = ComponentGraphicsItem(comp, self.model, self)
                self.scene.addItem(item)
                self.component_items[comp.comp_id] = item
                if comp.comp_id in selected_ids:
                    item.setSelected(True)

            # 重新绘制连线
            self._refresh_wires()

        self.canvas_changed.emit()

    def _refresh_wires(self):
        """刷新连线（不调用 assign_node_ids，仅在代码生成时需要）"""
        # 清除现有连线
        self._clear_wire_intersection_items()
        for wire_item in list(self.wire_items.values()):
            if isValid(wire_item) and wire_item.scene() is self.scene:
                self.scene.removeItem(wire_item)
        self.wire_items.clear()
        for waypoint_item in list(self.wire_waypoint_items.values()):
            if isValid(waypoint_item) and waypoint_item.scene() is self.scene:
                self.scene.removeItem(waypoint_item)
        self.wire_waypoint_items.clear()

        # 重新绘制连线
        for wire in self._active_wires().values():
            start_item = self.component_items.get(wire.from_comp)
            end_item = self.component_items.get(wire.to_comp)

            if start_item and end_item:
                start_pos = None
                end_pos = None

                start_pins = start_item.get_all_scene_pin_positions()
                end_pins = end_item.get_all_scene_pin_positions()

                if wire.from_pin in start_pins:
                    start_pos = start_pins[wire.from_pin]
                if wire.to_pin in end_pins:
                    end_pos = end_pins[wire.to_pin]

                if start_pos and end_pos:
                    self._add_wire_graphics_item(wire, start_pos, end_pos)

        self._refresh_wire_intersections()
        self.canvas_changed.emit()

    def clear_canvas(self):
        """清空画布"""
        self._clear_wire_input_state()
        self.scene.clear()
        self.component_items.clear()
        self.wire_items.clear()
        self.wire_waypoint_items.clear()
        self.wire_intersection_items.clear()
        self._draw_grid()

    def select_component_by_id(self, comp_id: str):
        """选中并定位到指定元件（用于验证面板跳转）

        Args:
            comp_id: 元件实例 ID
        """
        item = self.component_items.get(comp_id)
        if item is None:
            return

        # 清除现有选中
        for sel in self.scene.selectedItems():
            sel.setSelected(False)

        # 选中目标元件
        item.setSelected(True)

        # 确保元件可见并居中
        self.ensureVisible(item)
        self.centerOn(item)

    def scale_view(self, factor: float):
        """缩放画布视图（不覆盖QGraphicsView.scale）"""
        super().scale(factor, factor)
