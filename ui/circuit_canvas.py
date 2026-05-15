"""
EMTP 电路仿真 GUI - 电路画布
基于 QGraphicsView + QGraphicsScene 实现
支持选择/放置/连线/拖拽等交互模式
"""

import copy

from PySide6.QtWidgets import (QGraphicsView, QGraphicsScene, QGraphicsItem,
                              QGraphicsLineItem, QGraphicsEllipseItem,
                              QGraphicsTextItem, QGraphicsRectItem,
                              QGraphicsPathItem, QApplication)
from PySide6.QtCore import Qt, QPointF, Signal, QRectF, QLineF, QPoint
from PySide6.QtGui import (QPen, QBrush, QColor, QPainter, QPainterPath,
                           QFont, QKeyEvent, QMouseEvent, QWheelEvent)
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

    def __init__(self, component: ComponentInstance, model: CircuitModel):
        super().__init__()
        self.component = component
        self.model = model
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
        if ct != ComponentType.UMEC_TRANSFORMER:
            painter.setPen(QColor("#1e2a3a"))
            font = QFont("Arial", 9)
            painter.setFont(font)
            painter.drawText(QPointF(-15, 35), self.component.name)

        # 绘制引脚
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

    def mouseReleaseEvent(self, event):
        """鼠标释放 - 拖拽结束时保存撤销状态"""
        if self._drag_snapshot is not None:
            if self._drag_started and self.flags() & QGraphicsItem.ItemIsMovable:
                self.model._push_undo_snapshot(self._drag_snapshot)
                self.model._notify("component_moved")
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
        return super().itemChange(change, value)

    def _snap_pos(self, pos: QPointF) -> QPointF:
        """将位置吸附到网格"""
        grid = 10
        x = round(pos.x() / grid) * grid
        y = round(pos.y() / grid) * grid
        return QPointF(x, y)


class WireGraphicsItem(QGraphicsItem):
    """连线图形项 — Manhattan 折线路由（只允许水平/垂直线段）"""

    def __init__(self, wire: Wire, start_pos: QPointF, end_pos: QPointF):
        super().__init__()
        self.wire = wire
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.pen = QPen(QColor("#dc2626"), 2)
        self.selected_pen = QPen(QColor("#f59e0b"), 3)
        self._update_bounds()

    def _manhattan_points(self) -> list:
        """计算 Manhattan 折线路径的关键点列表（只含水平/垂直线段）"""
        sx, sy = self.start_pos.x(), self.start_pos.y()
        ex, ey = self.end_pos.x(), self.end_pos.y()

        # 同一水平线或垂直线 → 直线
        if abs(sx - ex) < 1 or abs(sy - ey) < 1:
            return [self.start_pos, self.end_pos]

        # L 形折线：先水平到中点，再垂直到终点
        mid_x = (sx + ex) / 2
        return [
            self.start_pos,
            QPointF(mid_x, sy),   # 水平段终点
            QPointF(mid_x, ey),   # 垂直段终点
            self.end_pos,
        ]

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
        painter.setBrush(QBrush(QColor("#dc2626")))
        painter.drawEllipse(self.start_pos.x() - 3, self.start_pos.y() - 3, 6, 6)
        painter.drawEllipse(self.end_pos.x() - 3, self.end_pos.y() - 3, 6, 6)

    def update_positions(self, start_pos: QPointF = None, end_pos: QPointF = None):
        if start_pos:
            self.start_pos = start_pos
        if end_pos:
            self.end_pos = end_pos
        self._update_bounds()
        self.update()


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

    GRID_SIZE = 10  # 网格间距

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
        self._temp_line: Optional[WireGraphicsItem] = None
        self._middle_panning = False
        self._middle_pan_last_pos: Optional[QPoint] = None

        # 子电路编辑模式
        self._editing_subcircuit: Optional[str] = None  # 当前正在编辑的子电路名
        self._subcircuit_breadcrumb: List[str] = []     # 面包屑路径

        # 图形项映射
        self.component_items: Dict[str, ComponentGraphicsItem] = {}
        self.wire_items: Dict[str, WireGraphicsItem] = {}

        # 复制粘贴剪贴板
        self._clipboard: Optional[Dict[str, ComponentInstance]] = None

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
        pen = QPen(QColor("#e2e8f0"), 0.5)
        painter.setPen(pen)
        # 只绘制可见区域的网格
        left = int(rect.left()) - (int(rect.left()) % self.GRID_SIZE)
        top = int(rect.top()) - (int(rect.top()) % self.GRID_SIZE)
        for x in range(left, int(rect.right()) + 1, self.GRID_SIZE):
            painter.drawLine(x, int(rect.top()), x, int(rect.bottom()))
        for y in range(top, int(rect.bottom()) + 1, self.GRID_SIZE):
            painter.drawLine(int(rect.left()), y, int(rect.right()), y)

    def _draw_grid(self):
        """不再使用 — 网格已改由 drawBackground 绘制"""
        pass

    def set_mode(self, mode: CanvasMode):
        """设置交互模式"""
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
            if isinstance(item, (ComponentGraphicsItem, WireGraphicsItem, NodeGraphicsItem)):
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
        items = self.scene.items(pos)
        best = None
        best_dist = 20  # 最大引脚吸附距离（像素）
        for item in items:
            if isinstance(item, ComponentGraphicsItem):
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

    def mousePressEvent(self, event):
        """鼠标按下"""
        if event.button() == Qt.MouseButton.MiddleButton:
            self._middle_panning = True
            self._middle_pan_last_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.LeftButton:
            scene_pos = self.mapToScene(event.pos())

            if self.mode == CanvasMode.PLACE:
                pos = self.snap_to_grid(scene_pos)
                self._place_component(pos)
            elif self.mode == CanvasMode.WIRE:
                # 拖动式连线：按下时检测是否在引脚上
                pin_info = self.get_pin_at(scene_pos)
                if pin_info:
                    self._start_wire_drag(pin_info, scene_pos)
                    # 必须调用 super 让 Qt 追踪鼠标按下状态，否则 mouseMoveEvent 收不到
                    super().mousePressEvent(event)
                else:
                    super().mousePressEvent(event)
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

        if self.mode == CanvasMode.WIRE and self._wiring_start:
            scene_pos = self.mapToScene(event.pos())
            self._temp_line.update_positions(end_pos=scene_pos)
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

        if event.button() == Qt.LeftButton and self.mode == CanvasMode.WIRE and self._wiring_start:
            scene_pos = self.mapToScene(event.pos())
            pin_info = self.get_pin_at(scene_pos)
            if pin_info:
                self._complete_wire_drag(pin_info)
            else:
                self._cancel_wire_drag()
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

        self.model.add_component(comp)

        # 放置完成后自动回到选择模式
        self.set_mode(CanvasMode.SELECT)
        self._placing_type = None
        self._placing_params = {}
        self.placement_completed.emit()  # 通知主窗口更新按钮状态

    def _start_wire_drag(self, pin_info: Tuple['ComponentGraphicsItem', str], pos: QPointF):
        """开始拖拽式连线：在引脚上按下鼠标"""
        comp_item, pin_name = pin_info
        self._wiring_start = (comp_item.component.comp_id, pin_name)

        pin_pos = comp_item.get_all_scene_pin_positions()[pin_name]
        self._temp_line = WireGraphicsItem(
            Wire(wire_id="temp", from_comp="", from_pin="", to_comp="", to_pin=""),
            pin_pos, pos
        )
        self._temp_line.pen = QPen(QColor("#2563eb"), 2, Qt.PenStyle.DashLine)
        self.scene.addItem(self._temp_line)
        self.setCursor(Qt.CrossCursor)

    def _complete_wire_drag(self, pin_info: Tuple['ComponentGraphicsItem', str]):
        """完成拖拽式连线：在引脚上释放鼠标"""
        comp_item, pin_name = pin_info
        start_comp_id, start_pin = self._wiring_start
        end_comp_id, end_pin = comp_item.component.comp_id, pin_name

        # 清除临时线
        if self._temp_line:
            self.scene.removeItem(self._temp_line)
            self._temp_line = None
        self._wiring_start = None
        self.setCursor(Qt.CrossCursor)

        if start_comp_id == end_comp_id:
            # 自己连自己 → 取消
            return

        # 检查是否已有相同连线
        for w in self.model.wires.values():
            if (w.from_comp == start_comp_id and w.from_pin == start_pin
                    and w.to_comp == end_comp_id and w.to_pin == end_pin):
                return
            if (w.from_comp == end_comp_id and w.from_pin == end_pin
                    and w.to_comp == start_comp_id and w.to_pin == start_pin):
                return

        import uuid
        wire = Wire(
            wire_id=f"W_{uuid.uuid4().hex[:8]}",
            from_comp=start_comp_id,
            from_pin=start_pin,
            to_comp=end_comp_id,
            to_pin=end_pin,
        )
        self.model.add_wire(wire)
        self.wire_created.emit(start_comp_id, start_pin, end_comp_id, end_pin)

    def _cancel_wire_drag(self):
        """取消拖拽式连线：在空白处释放鼠标"""
        if self._temp_line:
            self.scene.removeItem(self._temp_line)
            self._temp_line = None
        self._wiring_start = None
        self.setCursor(Qt.CrossCursor)

    def _handle_delete_click(self, pos: QPointF):
        """处理删除模式下的点击"""
        item = self.get_item_at(pos)
        if isinstance(item, ComponentGraphicsItem):
            self.model.remove_component(item.component.comp_id)
        elif isinstance(item, WireGraphicsItem):
            self.model.remove_wire(item.wire.wire_id)

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

        self.model.add_component(probe_comp)

        # 自动连线：从探针 sense 引脚到目标引脚
        import uuid
        wire = Wire(
            wire_id=f"W_{uuid.uuid4().hex[:8]}",
            from_comp=probe_comp.comp_id,
            from_pin='sense',
            to_comp=comp.comp_id,
            to_pin=pin_name,
        )
        self.model.add_wire(wire)

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
        result = self.model.create_subcircuit_from_selection(comp_ids, name)

        if result is None:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "无法封装",
                "封装失败：选中的元件没有外部连线，或元件数量不足。"
            )
            return

        # 刷新画布
        self._refresh_view()

    def keyPressEvent(self, event):
        """键盘事件"""
        if event.key() == Qt.Key_Delete or event.key() == Qt.Key_Backspace:
            self._delete_selected()
        elif event.key() == Qt.Key_Escape:
            if self.mode != CanvasMode.SELECT:
                self.set_mode(CanvasMode.SELECT)
                self._placing_type = None
                self._placing_params = {}
                if self._temp_line:
                    self.scene.removeItem(self._temp_line)
                    self._temp_line = None
                self._wiring_start = None
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

    def _delete_selected(self):
        """删除选中的元件和连线"""
        items_to_delete = []

        # 删除选中的元件
        for comp_id, item in list(self.component_items.items()):
            if item.isSelected():
                items_to_delete.append(comp_id)

        for comp_id in items_to_delete:
            self.model.remove_component(comp_id)

        # 删除选中的连线
        for wire_id, item in list(self.wire_items.items()):
            if item.isSelected():
                self.model.remove_wire(wire_id)

    def _rotate_selected(self):
        """旋转选中的元件"""
        for item in self.scene.selectedItems():
            if isinstance(item, ComponentGraphicsItem):
                self.model.rotate_component(item.component.comp_id, 90)

    def _copy_selected(self):
        """复制选中的元件到剪贴板"""
        selected = []
        for comp_id, item in self.component_items.items():
            if item.isSelected():
                selected.append(comp_id)
        if selected:
            self._clipboard = {
                cid: copy.deepcopy(self.model.components[cid])
                for cid in selected
                if cid in self.model.components
            }

    def _paste_clipboard(self, pos: QPointF):
        """从剪贴板粘贴元件"""
        if not self._clipboard:
            return
        pos = self.snap_to_grid(pos)
        for comp in self._clipboard.values():
            new_comp = ComponentInstance(
                comp_id=self.model.generate_component_id(comp.comp_type),
                comp_type=comp.comp_type,
                name=f"{comp.comp_type.value}{len([c for c in self.model.components.values() if c.comp_type == comp.comp_type]) + 1}",
                x=int(pos.x()),
                y=int(pos.y()),
                rotation=comp.rotation,
                params=comp.params.copy(),
                pins=[copy.deepcopy(p) for p in comp.pins],
            )
            self.model.add_component(new_comp)
            pos = QPointF(pos.x() + 40, pos.y() + 40)  # 偏移避免重叠

    def _on_model_changed(self, event: str = "changed"):
        """模型变化时重绘"""
        if event == "component_moved":
            # 移动时只更新连线位置，不全量重绘
            self._refresh_wires()
            self.canvas_changed.emit()
        elif event in ["component_added", "component_removed", "component_rotated",
                      "params_updated", "undone", "redone", "cleared"]:
            self._refresh_view()
        elif event in ["wire_added", "wire_removed"]:
            self._refresh_wires()
        elif event == "component_selected":
            # 选中元件时通知属性面板刷新
            self.canvas_changed.emit()

    def _refresh_view(self):
        """刷新整个视图"""
        # 保存当前选中的元件 ID，以便重绘后恢复选中状态
        selected_ids = set()
        for item in self.scene.selectedItems():
            if isinstance(item, ComponentGraphicsItem):
                selected_ids.add(item.component.comp_id)

        # 清除现有图形项
        self.scene.clear()
        self.component_items.clear()
        self.wire_items.clear()

        # 重新绘制网格
        self._draw_grid()

        if self._editing_subcircuit:
            # 子电路编辑模式 — 显示子电路内部元件
            subdef = self.model.subcircuit_defs.get(self._editing_subcircuit)
            if subdef:
                for comp in subdef.components.values():
                    item = ComponentGraphicsItem(comp, self.model)
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
                            wire_item = WireGraphicsItem(wire, sp, ep)
                            self.scene.addItem(wire_item)
                            self.wire_items[wire.wire_id] = wire_item
                # 绘制端口标记
                for port in subdef.ports:
                    comp = subdef.components.get(port.internal_comp_id)
                    if comp:
                        # 在端口引脚旁画标记
                        pass  # TODO: 端口高亮
            else:
                # 子电路定义不存在，退出编辑模式
                self._editing_subcircuit = None
                self._subcircuit_breadcrumb.clear()
                # 回退到顶层
                for comp in self.model.components.values():
                    item = ComponentGraphicsItem(comp, self.model)
                    self.scene.addItem(item)
                    self.component_items[comp.comp_id] = item
                    if comp.comp_id in selected_ids:
                        item.setSelected(True)
                self._refresh_wires()
        else:
            # 正常模式 — 显示顶层元件
            for comp in self.model.components.values():
                item = ComponentGraphicsItem(comp, self.model)
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
        for wire_item in list(self.wire_items.values()):
            self.scene.removeItem(wire_item)
        self.wire_items.clear()

        # 重新绘制连线
        for wire in self.model.wires.values():
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
                    wire_item = WireGraphicsItem(wire, start_pos, end_pos)
                    self.scene.addItem(wire_item)
                    self.wire_items[wire.wire_id] = wire_item

        self.canvas_changed.emit()

    def clear_canvas(self):
        """清空画布"""
        self.scene.clear()
        self.component_items.clear()
        self.wire_items.clear()
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
