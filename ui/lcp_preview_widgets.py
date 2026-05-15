"""
EMTP GUI - LCP 截面预览共享组件

提供三种 LCP 线路类型的可视化截面渲染引擎、预览窗口和端口映射工具函数。
- LCPCrossSectionCanvas: matplotlib 嵌入画布，根据实际几何参数精确渲染
- LCPPreviewWindow: 可调尺寸的独立预览窗口（含工具栏）
- build_port_preview_text: 端口映射文本生成工具
"""

import numpy as np
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFileDialog,
)
from PySide6.QtCore import Qt
from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg, NavigationToolbar2QT,
)
from matplotlib.figure import Figure
from matplotlib.patches import Circle, FancyArrowPatch, Wedge
from matplotlib.collections import PatchCollection
import matplotlib.patches as mpatches

from models.component_lib import ComponentType
from ui.mpl_config import configure_matplotlib_fonts


configure_matplotlib_fonts()


# ================================================================
#  颜色常量
# ================================================================

LAYER_COLORS = {
    'core':        '#dc2626',   # 铜/铝芯 — 红色
    'insulation':  '#fbbf24',   # 绝缘层 — 黄色
    'sheath':      '#6b7280',   # 护套 — 灰色
    'armor':       '#374151',   # 铠装 — 深灰
    'jacket':      '#7c3aed',   # 外护套 — 紫色
    'pipe':        '#9ca3af',   # 管道 — 浅灰
    'soil':        '#d2b48c',   # 土壤 — 棕褐色
    'ground':      '#8b4513',   # 地面 — 深棕
}

PHASE_COLORS = ['#2563eb', '#dc2626', '#16a34a', '#f59e0b', '#8b5cf6', '#ec4899']


# ================================================================
#  LCPCrossSectionCanvas — 共享渲染引擎
# ================================================================

class LCPCrossSectionCanvas(FigureCanvasQTAgg):
    """Matplotlib 画布，根据实际几何参数渲染 LCP 截面图。"""

    # OHL 导线最小可视半径（实际半径太小时保证可见，单位 m）
    # 在典型 50m 跨度下，1.2m 约对应 15~20 像素，肉眼可辨识
    OHL_MIN_VISUAL_RADIUS = 1.2

    def __init__(self, parent=None, width=5, height=4, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi, facecolor='white')
        super().__init__(self.fig)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_aspect('equal')
        self._nav_toolbar = None
        self.fig.tight_layout(pad=1.5)

    # ================================================================
    #  架空线截面渲染
    # ================================================================

    def draw_ohl(self, config: dict):
        """绘制架空线截面图。

        读取 config 中的:
          phase_positions, phase_radius, phase_sag,
          phase_bundle_n, phase_bundle_spacing,
          gw_positions, gw_radius, gw_sag,
          eliminate_ground_wires, ground_resistivity
        """
        ax = self.ax
        ax.clear()
        ax.set_aspect('equal')
        ax.set_title("架空线截面示意图", fontsize=11, fontweight='bold')

        phase_positions = config.get('phase_positions', [])
        phase_radius = config.get('phase_radius', 0.03)
        phase_sag = config.get('phase_sag', 9.2)
        bundle_n = config.get('phase_bundle_n', 1)
        bundle_spacing = config.get('phase_bundle_spacing', 0.5)

        gw_positions = config.get('gw_positions', [])
        gw_radius = config.get('gw_radius', 0.00875)
        gw_sag = config.get('gw_sag', 6.1)
        eliminate_gw = config.get('eliminate_ground_wires', False)

        ground_rho = config.get('ground_resistivity', 1000.0)

        # 1) 地面
        ax.axhline(y=0, color=LAYER_COLORS['ground'], linewidth=2.5, label='地面')
        ax.fill_between([-100, 100], -100, 0, color=LAYER_COLORS['soil'],
                        alpha=0.15, label='土壤')

        # 2) 塔架轮廓
        if phase_positions:
            x_left = min(p[0] for p in phase_positions) - 3
            x_right = max(p[0] for p in phase_positions) + 3
            tower_top = max(p[1] for p in phase_positions) + 5
            # 两根塔柱
            ax.plot([x_left, x_left], [0, tower_top], 'k--', linewidth=1.0, alpha=0.4)
            ax.plot([x_right, x_right], [0, tower_top], 'k--', linewidth=1.0, alpha=0.4)
            # 横担
            for pos in phase_positions:
                ax.plot([x_left, pos[0]], [pos[1], pos[1]], 'k-', linewidth=0.8, alpha=0.3)
                ax.plot([pos[0], x_right], [pos[1], pos[1]], 'k-', linewidth=0.8, alpha=0.3)

        # 3) 导线
        for i, (px, ph) in enumerate(phase_positions):
            y_cond = ph - phase_sag  # 弧垂后的高度
            color = PHASE_COLORS[i % len(PHASE_COLORS)]

            # 分裂导线
            if bundle_n > 1:
                r_bundle = bundle_spacing / 2
                for j in range(bundle_n):
                    angle = 2 * np.pi * j / bundle_n
                    bx = px + r_bundle * np.cos(angle)
                    by = y_cond + r_bundle * np.sin(angle)
                    vis_r = max(self.OHL_MIN_VISUAL_RADIUS * 0.4, phase_radius)
                    c = Circle((bx, by), vis_r, color=color, alpha=0.6, zorder=5)
                    ax.add_patch(c)
                # 分裂圆虚线
                bundle_circle = Circle((px, y_cond), r_bundle, fill=False,
                                       edgecolor=color, linewidth=0.8, linestyle=':', alpha=0.5)
                ax.add_patch(bundle_circle)
            else:
                vis_r = max(self.OHL_MIN_VISUAL_RADIUS, phase_radius)
                c = Circle((px, y_cond), vis_r, color=color, alpha=0.75, zorder=5)
                ax.add_patch(c)

            # 标签
            ax.text(px, y_cond, f'P{i+1}', ha='center', va='center',
                    fontsize=8, fontweight='bold', color='white', zorder=6)

            # 弧垂曲线
            span = 10  # 示意跨度
            xs = np.linspace(px - span, px + span, 60)
            catenary = ph - (4 * phase_sag / (2 * span) ** 2) * (xs - px) ** 2
            ax.plot(xs, catenary, color=color, linewidth=0.7, linestyle=':', alpha=0.4)

            # 高度标注
            ax.annotate(f'{y_cond:.1f}m', xy=(px, y_cond),
                        xytext=(px + 3, y_cond + 1),
                        fontsize=7, color=color, alpha=0.8,
                        arrowprops=dict(arrowstyle='->', color=color, alpha=0.4, lw=0.5))

        # 4) 地线
        if not eliminate_gw:
            for i, (gx, gh) in enumerate(gw_positions):
                y_gw = gh - gw_sag
                vis_r = max(self.OHL_MIN_VISUAL_RADIUS * 0.6, gw_radius)
                c = Circle((gx, y_gw), vis_r, color='gray', alpha=0.5, zorder=5)
                ax.add_patch(c)
                ax.text(gx, y_gw, f'GW{i+1}', ha='center', va='center',
                        fontsize=6, color='white', zorder=6)

        # 5) 信息框
        n_ph = len(phase_positions)
        n_gw = len(gw_positions)
        info_text = (f"导线: {n_ph}  地线: {n_gw}\n"
                     f"土壤ρ: {ground_rho:.1f} Ω·m\n"
                     f"导线半径: {phase_radius*1000:.1f} mm")
        if bundle_n > 1:
            info_text += f"\n分裂: {bundle_n}×{bundle_spacing*1000:.0f} mm"
        ax.text(0.02, 0.98, info_text, transform=ax.transAxes,
                fontsize=8, verticalalignment='top',
                bbox=dict(boxstyle='round,pad=0.4', facecolor='white', alpha=0.85))

        # 6) 图例
        handles = [
            mpatches.Patch(color=PHASE_COLORS[0], label='导线'),
            mpatches.Patch(color='gray', label='地线'),
            mpatches.Patch(color=LAYER_COLORS['soil'], alpha=0.3, label='土壤'),
        ]
        ax.legend(handles=handles, loc='upper right', fontsize=7, framealpha=0.85)

        # 7) 自适应范围
        all_x = [p[0] for p in phase_positions] + [g[0] for g in gw_positions]
        all_y = [p[1] - phase_sag for p in phase_positions]
        if not eliminate_gw:
            all_y += [g[1] - gw_sag for g in gw_positions]

        if all_x and all_y:
            x_margin = max(5, (max(all_x) - min(all_x)) * 0.2)
            y_margin = max(5, (max(all_y) - min(all_y)) * 0.2)
            ax.set_xlim(min(all_x) - x_margin, max(all_x) + x_margin)
            ax.set_ylim(min(-3, min(all_y) - y_margin), max(all_y) + y_margin + 5)

        ax.set_xlabel("水平位置 (m)", fontsize=9)
        ax.set_ylabel("高度 (m)", fontsize=9)
        ax.grid(True, alpha=0.2)
        self.fig.tight_layout(pad=1.5)
        self.draw()

    # ================================================================
    #  单芯电缆截面渲染
    # ================================================================

    def draw_single_cable(self, config: dict):
        """绘制单芯电缆截面图。

        读取 config 中的:
          cables: list of dict (core_radius, insulation_outer_radius, sheath_outer_radius,
                  armor_outer_radius, outer_jacket_radius, burial_depth, horizontal_pos)
          soil_resistivity, soil_permittivity, n_cables, length
        """
        ax = self.ax
        ax.clear()
        ax.set_aspect('equal')
        ax.set_title("单芯电缆截面示意图", fontsize=11, fontweight='bold')

        cables = config.get('cables', [])
        n_cables = config.get('n_cables', len(cables))
        soil_rho = config.get('soil_resistivity', 100.0)

        if not cables:
            ax.text(0.5, 0.5, "暂无电缆数据", transform=ax.transAxes,
                    ha='center', va='center', fontsize=12, color='gray')
            self.draw()
            return

        # 计算布局参数
        max_jacket_r = max(c.get('outer_jacket_radius', 0.05) for c in cables)
        burial_depths = [c.get('burial_depth', 1.0) for c in cables]
        h_positions = [c.get('horizontal_pos', 0.0) for c in cables]

        # 1) 土壤背景
        soil_top = 0
        soil_bottom = -max(burial_depths) - max_jacket_r * 3
        soil_left = min(h_positions) - max_jacket_r * 4
        soil_right = max(h_positions) + max_jacket_r * 4
        ax.fill_between([soil_left - 1, soil_right + 1], soil_bottom - 0.5, soil_top,
                        color=LAYER_COLORS['soil'], alpha=0.2, label='土壤')
        ax.axhline(y=0, color=LAYER_COLORS['ground'], linewidth=2, label='地面')

        # 2) 绘制每根电缆
        legend_handles = []
        layer_names = [
            ('outer_jacket_radius', LAYER_COLORS['jacket'], '外护套', 0.3),
            ('armor_outer_radius',  LAYER_COLORS['armor'],  '铠装',  0.4),
            ('sheath_outer_radius', LAYER_COLORS['sheath'], '护套',  0.5),
            ('insulation_outer_radius', LAYER_COLORS['insulation'], '绝缘层', 0.5),
            ('core_radius',         LAYER_COLORS['core'],   '芯线',  0.8),
        ]

        for i, cable in enumerate(cables):
            cx = cable.get('horizontal_pos', 0.0)
            cy = -cable.get('burial_depth', 1.0)

            # 从外到内绘制同心圆
            for j, (key, color, name, alpha) in enumerate(layer_names):
                r = cable.get(key, 0.0)
                if r <= 0:
                    continue
                circle = Circle((cx, cy), r, color=color, alpha=alpha, zorder=3 + j)
                ax.add_patch(circle)

                # 只为第一根电缆添加图例
                if i == 0:
                    legend_handles.append(mpatches.Patch(color=color, alpha=alpha, label=name))

            # 芯线标签
            core_r = cable.get('core_radius', 0.02)
            ax.text(cx, cy, f'C{i+1}', ha='center', va='center',
                    fontsize=8, fontweight='bold', color='white', zorder=10)

            # 埋深标注
            ax.annotate(
                f'埋深: {cable.get("burial_depth", 1.0):.2f}m',
                xy=(cx, cy - cable.get('outer_jacket_radius', 0.05)),
                xytext=(cx, cy - cable.get('outer_jacket_radius', 0.05) - 0.05),
                fontsize=7, ha='center', color='#475569',
            )

        # 3) 信息框
        info_text = f"电缆数: {n_cables}\n土壤ρ: {soil_rho:.1f} Ω·m"
        ax.text(0.02, 0.98, info_text, transform=ax.transAxes,
                fontsize=8, verticalalignment='top',
                bbox=dict(boxstyle='round,pad=0.4', facecolor='white', alpha=0.85))

        # 4) 图例
        ax.legend(handles=legend_handles, loc='upper right', fontsize=7, framealpha=0.85)

        # 5) 自适应范围（强制 X/Y 范围平衡，避免图被拉成细条）
        all_cx = [c.get('horizontal_pos', 0.0) for c in cables]
        all_cy = [-c.get('burial_depth', 1.0) for c in cables]
        all_r = [c.get('outer_jacket_radius', 0.05) for c in cables]

        max_r = max(all_r) if all_r else 0.05
        # 计算各轴的跨度需求
        x_span_need = max(all_cx) - min(all_cx) + max_r * 6 if len(cables) > 1 else max_r * 8
        y_span_need = max(all_cy) - min(all_cy) + max_r * 6 if len(cables) > 1 else max_r * 8
        # 取两者较大值作为统一跨度，保证图不会过扁或过高
        min_span = max(x_span_need, y_span_need, 0.25)

        x_center = (min(all_cx) + max(all_cx)) / 2 if len(cables) > 1 else all_cx[0]
        y_center = (min(all_cy) + max(all_cy)) / 2 if len(cables) > 1 else all_cy[0]

        ax.set_xlim(x_center - min_span / 2, x_center + min_span / 2)
        ax.set_ylim(y_center - min_span / 2, y_center + min_span / 2)

        ax.set_xlabel("水平位置 (m)", fontsize=9)
        ax.set_ylabel("深度 (m)", fontsize=9)
        ax.grid(True, alpha=0.2)
        self.fig.tight_layout(pad=1.5)
        self.draw()

    # ================================================================
    #  三芯电缆截面渲染
    # ================================================================

    def draw_three_core_cable(self, config: dict):
        """绘制三芯电缆截面图。

        读取 config 中的:
          pipe_inner_radius, pipe_outer_radius,
          core_radius, insulation_radius, sheath_radius,
          dist_from_center, conductor_angles (list of 3 floats, degrees),
          burial_depth, soil_resistivity
        """
        ax = self.ax
        ax.clear()
        ax.set_aspect('equal')
        ax.set_title("三芯电缆截面示意图", fontsize=11, fontweight='bold')

        pipe_inner_r = config.get('pipe_inner_radius', 0.065)
        pipe_outer_r = config.get('pipe_outer_radius', 0.07)
        core_r = config.get('core_radius', 0.0165)
        insul_r = config.get('insulation_radius', 0.027)
        sheath_r = config.get('sheath_radius', 0.03)
        dist = config.get('dist_from_center', 0.03415)
        angles = config.get('conductor_angles', [270.0, 30.0, 150.0])
        burial_depth = config.get('burial_depth', 1.0)

        # 1) 管道截面
        # 外壁（实线填充）
        pipe_outer = Circle((0, 0), pipe_outer_r, fill=True,
                            facecolor=LAYER_COLORS['pipe'], alpha=0.2,
                            edgecolor='#4b5563', linewidth=2, label='管道')
        ax.add_patch(pipe_outer)
        # 内壁（虚线）
        pipe_inner = Circle((0, 0), pipe_inner_r, fill=False,
                            edgecolor='#4b5563', linewidth=1.0, linestyle='--')
        ax.add_patch(pipe_inner)

        # 管壁填充（用 Wedge 环形近似）
        for angle_start in range(0, 360, 10):
            wedge = Wedge((0, 0), pipe_outer_r, angle_start, angle_start + 10,
                          width=pipe_outer_r - pipe_inner_r,
                          facecolor='#9ca3af', alpha=0.3, edgecolor='none')
            ax.add_patch(wedge)

        # 2) 三相导体
        phase_labels = ['A', 'B', 'C']
        conductor_layers = [
            (sheath_r, LAYER_COLORS['sheath'], '护套', 0.5),
            (insul_r,  LAYER_COLORS['insulation'], '绝缘层', 0.5),
            (core_r,   LAYER_COLORS['core'], '芯线', 0.8),
        ]

        legend_handles = [
            mpatches.Patch(color=LAYER_COLORS['pipe'], alpha=0.3, label='管道'),
        ]

        for i, angle in enumerate(angles[:3]):
            rad = np.radians(angle)
            cx = dist * np.cos(rad)
            cy = dist * np.sin(rad)
            color = PHASE_COLORS[i % len(PHASE_COLORS)]

            # 从外到内绘制同心圆
            for j, (r, layer_color, name, alpha) in enumerate(conductor_layers):
                circle = Circle((cx, cy), r, color=layer_color, alpha=alpha, zorder=5 + j)
                ax.add_patch(circle)

            # 芯线标签
            ax.text(cx, cy, phase_labels[i], ha='center', va='center',
                    fontsize=9, fontweight='bold', color='white', zorder=12)

            # 角度标注线
            ax.plot([0, cx * 0.3], [0, cy * 0.3], color=color, linewidth=0.8,
                    linestyle=':', alpha=0.5)

        # 添加导体层图例
        for _, color, name, alpha in conductor_layers:
            legend_handles.append(mpatches.Patch(color=color, alpha=alpha, label=name))

        # 3) 尺寸标注
        # 管道半径
        ax.annotate(f'管道外径: {pipe_outer_r*1000:.1f}mm',
                    xy=(pipe_outer_r, 0),
                    xytext=(pipe_outer_r + 0.01, pipe_outer_r * 0.6),
                    fontsize=7, color='#475569',
                    arrowprops=dict(arrowstyle='->', color='#94a3b8', lw=0.5))
        ax.annotate(f'管道内径: {pipe_inner_r*1000:.1f}mm',
                    xy=(pipe_inner_r, 0),
                    xytext=(pipe_inner_r + 0.015, -pipe_outer_r * 0.4),
                    fontsize=7, color='#475569',
                    arrowprops=dict(arrowstyle='->', color='#94a3b8', lw=0.5))

        # 导体距中心
        ax.annotate(f'偏心距: {dist*1000:.1f}mm',
                    xy=(dist * 0.5, 0),
                    xytext=(dist * 0.5, -pipe_outer_r - 0.02),
                    fontsize=7, ha='center', color='#475569',
                    arrowprops=dict(arrowstyle='<->', color='#94a3b8', lw=0.5))

        # 4) 信息框
        angles_str = ', '.join(f'{a:.0f}°' for a in angles[:3])
        info_text = (f"导体角度: {angles_str}\n"
                     f"芯线半径: {core_r*1000:.1f}mm\n"
                     f"绝缘外径: {insul_r*1000:.1f}mm\n"
                     f"护套外径: {sheath_r*1000:.1f}mm")
        ax.text(0.02, 0.98, info_text, transform=ax.transAxes,
                fontsize=8, verticalalignment='top',
                bbox=dict(boxstyle='round,pad=0.4', facecolor='white', alpha=0.85))

        # 5) 图例
        ax.legend(handles=legend_handles, loc='upper right', fontsize=7, framealpha=0.85)

        # 6) 自适应范围
        margin = pipe_outer_r * 0.4
        ax.set_xlim(-pipe_outer_r - margin, pipe_outer_r + margin + 0.02)
        ax.set_ylim(-pipe_outer_r - margin, pipe_outer_r + margin)

        ax.set_xlabel("X (m)", fontsize=9)
        ax.set_ylabel("Y (m)", fontsize=9)
        ax.grid(True, alpha=0.2)
        self.fig.tight_layout(pad=1.5)
        self.draw()

    # ================================================================
    #  工具方法
    # ================================================================

    def export_png(self, filepath: str):
        """导出当前图形为 PNG 文件。"""
        self.fig.savefig(filepath, dpi=150, bbox_inches='tight',
                         facecolor='white', edgecolor='none')

    def enable_zoom_pan(self, parent_layout=None):
        """启用 matplotlib NavigationToolbar 缩放/平移功能。"""
        if self._nav_toolbar is not None:
            return  # 已启用
        self._nav_toolbar = NavigationToolbar2QT(self, self.parent())
        if parent_layout is not None:
            parent_layout.insertWidget(0, self._nav_toolbar)


# ================================================================
#  LCPPreviewWindow — 独立预览窗口
# ================================================================

class LCPPreviewWindow(QDialog):
    """可调尺寸的 LCP 截面预览窗口，含工具栏和参数摘要。"""

    def __init__(self, comp_name: str, comp_type, config: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{comp_name} - 截面预览")
        self.setMinimumSize(600, 500)
        self.resize(800, 650)
        self._comp_type = comp_type
        self._config = config
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # 工具栏
        toolbar = QHBoxLayout()

        export_btn = QPushButton("📷 导出图片")
        export_btn.setStyleSheet("""
            QPushButton {
                background-color: #0d948815; color: #0d9488;
                border: 1px solid #0d948840; border-radius: 4px;
                padding: 5px 12px; font-weight: bold;
            }
            QPushButton:hover { background-color: #0d948830; border-color: #0d9488; }
        """)
        export_btn.clicked.connect(self._export_png)
        toolbar.addWidget(export_btn)

        zoom_btn = QPushButton("🔍 缩放/平移")
        zoom_btn.setStyleSheet("""
            QPushButton {
                background-color: #2563eb15; color: #2563eb;
                border: 1px solid #2563eb40; border-radius: 4px;
                padding: 5px 12px; font-weight: bold;
            }
            QPushButton:hover { background-color: #2563eb30; border-color: #2563eb; }
        """)
        zoom_btn.clicked.connect(self._toggle_zoom_pan)
        toolbar.addWidget(zoom_btn)

        toolbar.addStretch()

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        toolbar.addWidget(close_btn)

        layout.addLayout(toolbar)

        # Canvas
        self.canvas = LCPCrossSectionCanvas(self, width=7, height=5.5)
        layout.addWidget(self.canvas, stretch=1)

        # 参数摘要
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(
            "font-size: 11px; "
            "background: #f8fafc; padding: 6px; border: 1px solid #e2e8f0; "
            "border-radius: 4px;"
        )
        self.summary_label.setMaximumHeight(80)
        layout.addWidget(self.summary_label)

        # 渲染
        self._draw()

    def _draw(self):
        if self._comp_type == ComponentType.LCP_OHL:
            self.canvas.draw_ohl(self._config)
        elif self._comp_type == ComponentType.LCP_SINGLE_CABLE:
            self.canvas.draw_single_cable(self._config)
        elif self._comp_type == ComponentType.LCP_THREE_CABLE:
            self.canvas.draw_three_core_cable(self._config)
        self.summary_label.setText(self._build_summary())

    def _build_summary(self) -> str:
        """根据元件类型生成参数摘要文本。"""
        cfg = self._config
        if self._comp_type == ComponentType.LCP_OHL:
            n_ph = cfg.get('n_phases', len(cfg.get('phase_positions', [])))
            n_gw = cfg.get('n_gw', len(cfg.get('gw_positions', [])))
            return (f"架空线 | 长度: {cfg.get('length', 0):.1f}m | "
                    f"导线: {n_ph} | 地线: {n_gw} | "
                    f"土壤ρ: {cfg.get('ground_resistivity', 0):.1f} Ω·m")
        elif self._comp_type == ComponentType.LCP_SINGLE_CABLE:
            n = cfg.get('n_cables', len(cfg.get('cables', [])))
            return (f"单芯电缆 | 长度: {cfg.get('length', 0):.1f}m | "
                    f"电缆数: {n} | "
                    f"土壤ρ: {cfg.get('soil_resistivity', 0):.1f} Ω·m")
        elif self._comp_type == ComponentType.LCP_THREE_CABLE:
            angles = cfg.get('conductor_angles', [270, 30, 150])
            angles_str = '/'.join(f'{a:.0f}°' for a in angles[:3])
            return (f"三芯电缆 | 长度: {cfg.get('length', 0):.1f}m | "
                    f"管道外径: {cfg.get('pipe_outer_radius', 0)*1000:.1f}mm | "
                    f"角度: {angles_str}")
        return ""

    def _export_png(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, "导出截面图", "lcp_cross_section.png", "PNG Files (*.png)"
        )
        if filepath:
            if not filepath.lower().endswith('.png'):
                filepath += '.png'
            self.canvas.export_png(filepath)

    def _toggle_zoom_pan(self):
        """切换 matplotlib NavigationToolbar 缩放/平移。"""
        if self.canvas._nav_toolbar is not None:
            self.canvas._nav_toolbar.setVisible(
                not self.canvas._nav_toolbar.isVisible()
            )
        else:
            self.canvas.enable_zoom_pan(self.layout())


# ================================================================
#  build_port_preview_text — 端口映射文本生成工具
# ================================================================

def build_port_preview_text(comp_type, config: dict) -> str:
    """根据元件类型和配置生成端口映射预览文本。

    Args:
        comp_type: ComponentType 枚举值
        config: 包含 n_phases/n_gw/n_cables/eliminate_ground_wires 等键的字典

    Returns:
        多行文本字符串
    """
    if comp_type == ComponentType.LCP_OHL:
        n_phases = config.get('n_phases', len(config.get('phase_positions', [])))
        n_gw = config.get('n_gw', len(config.get('gw_positions', [])))
        eliminate = config.get('eliminate_ground_wires', False)

        lines = [f"导线数: {n_phases}，地线数: {n_gw}", ""]

        k_ports = []
        for i in range(n_phases):
            k_ports.append(f"nk_{i} (Phase_{i+1})")
        if not eliminate:
            for i in range(n_gw):
                k_ports.append(f"nk_{n_phases + i} (GW_{i+1})")

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

        return "\n".join(lines)

    elif comp_type == ComponentType.LCP_SINGLE_CABLE:
        n_cables = config.get('n_cables', len(config.get('cables', [])))
        lines = [f"电缆数: {n_cables}", ""]

        lines.append("K 端端口:")
        for i in range(n_cables):
            for conductor in ['core', 'sheath', 'armor']:
                lines.append(f"  nk_{i}_{conductor}")
        lines.append("")
        lines.append("M 端端口:")
        for i in range(n_cables):
            for conductor in ['core', 'sheath', 'armor']:
                lines.append(f"  nm_{i}_{conductor}")

        return "\n".join(lines)

    elif comp_type == ComponentType.LCP_THREE_CABLE:
        conductor_names = [
            'core_a', 'core_b', 'core_c',
            'sheath_a', 'sheath_b', 'sheath_c',
            'pipe'
        ]
        lines = ["三芯电缆端口映射", ""]

        lines.append("K 端端口:")
        for cn in conductor_names:
            lines.append(f"  nk_{cn}")
        lines.append("")
        lines.append("M 端端口:")
        for cn in conductor_names:
            lines.append(f"  nm_{cn}")

        return "\n".join(lines)

    return "未知元件类型"
