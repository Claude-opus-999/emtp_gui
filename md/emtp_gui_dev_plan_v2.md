# EMTP_GUI 升级开发计划

> **基于**：`C:\Users\Wangweihong\WorkBuddy\20260402191132\emtp_gui`
> **参考**：`D:/浏览器下载/emtp-web-frontend-dev-plan.md`（Web 版规划） + `D:/pythonproject/emtp_0508/`（最新内核求解器）
> **文档版本**：v2.3（2026-05-15）
> **定位**：将现有 PySide6 桌面 GUI 从"可运行原型"升级为"完整工程工具"

---

## 一、现有代码审计结论

### 1.1 已完成模块（✅ 可用）

| 模块 | 文件 | 状态 | 说明 |
|------|------|------|------|
| 画布 | `ui/circuit_canvas.py` | ✅ 成熟 | QGraphicsView，4种交互模式，拖拽连线，引脚吸附，网格对齐，缩放平移，子电路编辑模式，UMEC三相符号（Y/Delta绕组图） |
| 数据模型 | `models/circuit_model.py` | ✅ 成熟 | 元件/连线/Undo-Redo(50步)/Union-Find节点分配/观察者模式/序列化/子电路定义/UMEC旧格式迁移 |
| 元件库 | `models/component_lib.py` | ✅ 完整 | 14种元件的图形绘制/参数模板/API映射（含 LCP_OHL/LCP_SINGLE_CABLE/LCP_THREE_CABLE/LPM/UMEC 8引脚10参数/SUBCIRCUIT） |
| 代码生成器 | `core/code_generator.py` | ✅ 可用 | 生成 Python 脚本，支持 R/L/C/SW/VS/IS/MOA/Bergeron/ULM/LCP电缆/UMEC变压器 |
| 求解器构建器 | `core/solver_builder.py` | ✅ 可用 | 6种雷电源模型分派/LCP电缆节点生成/子电路递归展平/UMEC三相组节点映射 |
| 验证引擎 | `core/validator.py` | ✅ 可用 | 8种校验规则：空电路/浮空节点/接地检查/电压源冲突/参数范围/探针引用/连线完整性/仿真设置 |
| 文件 I/O | `core/file_io.py` | ✅ 可用 | JSON 序列化，v1 旧格式迁移，雷电源模型向后兼容 |
| 主窗口 | `ui/main_window.py` | ✅ 可用 | 菜单/工具栏/属性面板/代码预览/仿真配置/Python语法高亮/SourceFuncEditor 6模型/UMEC配置按钮 |
| 仿真运行器 | `core/sim_runner.py` | ✅ 基础可用 | QThread 子进程运行 + 取消功能 |
| 波形查看器 | `ui/main_window.py` PlotPanel | ✅ 基础可用 | matplotlib 嵌入 + 导出 CSV/PNG |
| UMEC参数对话框 | `ui/umec_param_dialog.py` | ✅ 完成 | 3标签页：基本参数(S_mva/freq/V1/V2/wtype1/wtype2)/阻抗参数/端口映射预览 |
| LCP参数对话框 | `ui/lcp_param_dialog.py` | ✅ 完成 | 3种对话框：架空线(5标签页)/单芯电缆(2标签页)/三芯电缆(2标签页)，含截面预览 |
| MOA参数对话框 | `ui/moa_param_dialog.py` | ✅ 完成 | 3标签页：基本参数(额定电压/pu选择/输入模式)/V-I特性(断点表格+增删行+文件加载)/配置预览 |
| LPM参数对话框 | `ui/lpm_param_dialog.py` | ✅ 完成 | 3标签页：几何与场强(间隙/E0/k/海拔)/电弧参数(R_arc/熄弧控制)/配置预览 |
| LCP截面预览 | `ui/lcp_preview_widgets.py` | ✅ 完成 | 架空线/电缆截面可视化预览画布 |
| 探针面板 | `ui/probe_panel.py` | ✅ 可用 | 电压/支路电流/线路电流探针添加，完整表单 |
| 回归测试 | `tests/test_regressions.py` | ✅ 可用 | 节点分配稳定性/旧格式兼容/ULM引脚名 |
| 案例文件 | `case*.emtp` | ✅ 5个 | RC/RLC/Switching/Lightning-Cable/Example |

### 1.2 待建设模块（❌ 缺失）

| 优先级 | 模块 | 对应 Web 计划 | 影响 |
|--------|------|--------------|------|
| P0 | **仿真运行器增强**（QProcess 替代方案、子进程隔离） | Phase 3 | 大算例稳定性 |
| P1 | **验证引擎 UI 集成**（工具栏按钮 + 持久化错误面板） | Phase 1 | 用户体验 |
| P2 | **仿真统计面板**（timing/memory） | Phase 5 | 用户体验 |
| P2 | **撤销栈 UX 改进**（工具栏按钮/快捷键提示） | Phase 2 | 用户体验 |
| P3 | **信号命名层**（双击连线改名） | 额外规划 | 可读性 |

### 1.3 已完成的内核对齐工作

#### ✅ 雷电源模型全面适配（S0 核心）

根据 `EMTP电流源雷电源与ULM线路方法说明.md` 规范，已完成全部 6 种雷电源子模型的 UI + 求解器 + 代码生成：

| 子模型 | 工厂函数 | UI 面板 | 状态 |
|--------|---------|---------|------|
| 标准双指数（10种标准波形 + PERC） | `create_standard_twoexpf_current_source(PERC=...)` | `ln_std_widget` | ✅ |
| 自定义双指数（T1/T2 + PERC） | `create_twoexpf_current_source(T1=..., T2=..., PERC=...)` | `ln_twoexpf_custom_widget` | ✅ |
| 直接 τ1/τ2 双指数 | `create_twoexpf_current_source(tau1=..., tau2=...)` | `ln_twoexpf_tau_widget` | ✅ |
| ATP A/B 双指数 | `create_twoexpf_current_source(A=..., B=...)` | `ln_twoexpf_ab_widget` | ✅ |
| Heidler（T1/T2/n + PERC） | `create_heidlerf_current_source(n=..., PERC=...)` | `ln_heidler_custom_widget` | ✅ |
| Heidler 直接（Tf/τ） | `create_heidlerf_current_source(Tf=..., tau=...)` | `ln_heidler_direct_widget` | ✅ |

10 种标准波形：1.2/50, 2/20, 8/20, 4/10, 10/350, 0.25/100, 10/700, 30/80, 250/2500, 1/200
PERC 参数：0 / 10 / 30 / 50

向后兼容处理：旧 `.emtp` 文件无 `lightning_model` 字段时，自动回退为 `twoexpf_standard`。

#### ✅ LCP 电缆线路适配

| 电缆类型 | 元件类型 | 引脚数 | 代码生成 | 状态 |
|----------|---------|--------|---------|------|
| 单芯电缆 | `LCP_SINGLE_CABLE` | 3×n_cables (芯/护套/铠装) | `_gen_cable_nodes()` | ✅ |
| 三芯电缆 | `LCP_THREE_CABLE` | 7 (芯1/护套1/芯2/护套2/芯3/护套3/管道) | `_gen_cable_nodes()` | ✅ |

#### ✅ LCP 参数对话框（三种线路完整实现）

| 对话框 | 文件 | 标签页 | 特性 | 状态 |
|--------|------|--------|------|------|
| `LCPOHLDialog` | `ui/lcp_param_dialog.py` | 通用参数/导线配置/地线配置/拟合配置/截面预览 | 动态增删行、分裂数、Kron消元、截面可视化、150ms防抖 | ✅ |
| `LCPSingleCableDialog` | `ui/lcp_param_dialog.py` | 参数配置/截面预览 | 8列表电缆表(芯/护套/铠装)、埋深位置、动态表重建 | ✅ |
| `LCPThreeCoreCableDialog` | `ui/lcp_param_dialog.py` | 参数配置/截面预览 | 管道参数、角度位置[270°/30°/150°]、土壤参数 | ✅ |

辅助文件：`ui/lcp_preview_widgets.py`（架空线/电缆截面预览画布）

#### ✅ UMEC 变压器三相组模型（完整重构）

从旧版 2 端口简化模型重构为符合 PSCAD 规范的两绕组三相组模型：

| 层 | 变更 | 说明 | 状态 |
|---|------|------|------|
| **引脚** | `PINS['umec']` 2→8 | H_A/B/C/N + X_A/B/C/N | ✅ |
| **参数** | `PARAM_TEMPLATES` 7→10 | S_mva/freq/V1_kV/V2_kV/wtype1/wtype2/X_leak_pu/Im_percent/NLL_pu/CL_pu | ✅ |
| **API** | `api_method` → `add_UMEC_transformer` | 匹配内核 `solver.add_UMEC_transformer(name, data)` | ✅ |
| **画布符号** | `_draw_umec()` 重写 | 矩形框 + Y/Delta内部图形 + 中性点引线 + 绕组标签 | ✅ |
| **绕组符号** | `_draw_winding_symbol()` 新增 | Y形(三臂+中性线)/Y_gnd(+接地符)/Delta(三角形) | ✅ |
| **求解器** | `_build_umec_transformer()` | `create_umec_transformer_3ph_bank()` + 节点映射(Y_gnd→to=0, Delta→to=next_phase) | ✅ |
| **代码生成** | UMEC 多行生成 | 导入 + nodes 列表构建 + `create_umec_transformer_3ph_bank()` 调用 | ✅ |
| **向后兼容** | `_legacy_params_to_current()` | Sn→S_mva, f0→freq, V1→V1_kV, V2→V2_kV, Xl_pu→X_leak_pu + 默认值 | ✅ |
| **旧引脚迁移** | `_legacy_pin_node_ids()` | node_pos→H_A/B/C, node_neg→X_A/B/C | ✅ |
| **参数对话框** | `UMECTransformerDialog` | 3标签页：基本参数/阻抗参数/端口映射预览 | ✅ |
| **配置按钮** | PropertyPanel 集成 | "⚙ UMEC 参数配置" 按钮，紫色样式 | ✅ |

**⚠️ 已知 BUG**：`circuit_canvas.py` 的 `_draw_winding_symbol()` 使用了 `np.radians()` 但未 `import numpy as np`，绘制 UMEC 元件时会 `NameError`。

#### ✅ 验证引擎

`core/validator.py`（286行）已实现 8 种校验规则：

| 校验方法 | 级别 | 说明 |
|---------|------|------|
| `_check_empty_circuit()` | ERROR | 空电路检测 |
| `_check_floating_nodes()` | WARNING | 单连接节点浮空（排除 VS/Probe/GND） |
| `_check_ground_connection()` | ERROR | 无接地元件 |
| `_check_voltage_source_conflict()` | ERROR | 并联电压源冲突 |
| `_check_parameter_ranges()` | ERROR | 参数越界（基于 PARAM_TEMPLATES min/max） |
| `_check_probe_references()` | ERROR | 探针引用不存在的支路/线路 |
| `_check_wire_connectivity()` | ERROR | 连线端点元件缺失 |
| `_check_simulation_settings()` | ERROR | dt≤0/T_end≤0/dt>T_end/ULM缺fitulm_file |

#### ✅ 子电路系统

- `SubcircuitPort` / `SubcircuitDefinition` 数据模型
- `ComponentType.SUBCIRCUIT` 元件类型
- 画布：圆角矩形 + 端口标签、双击进入编辑、面包屑导航、右键封装/退出
- SolverBuilder：`_flatten_subcircuits()` 递归展平，前缀式 ID 重映射 + 桥接线

#### ✅ UX 修复

- **属性面板焦点丢失问题**：修改元件参数后不再需要重新点击元件
  - `_refresh_view()` 保存并恢复选中状态
  - `_on_selection_changed()` 编辑同一元件时跳过重建

#### ❌ 尚未完成的内核对齐

| 项目 | 说明 | 状态 |
|------|------|------|
| 验证清单 | 5 个现有案例 + emtp_0508 运行 | ❌ |

---

## 二、技术架构（保持 PySide6 路线）

### 2.1 为什么不换成 Web

| 维度 | Web 方案 | 现有 PySide6 |
|------|---------|-------------|
| 离线能力 | ❌ 需要网络 | ✅ 完全离线 |
| Python 集成 | ❌ 需 IPC/进程通信 | ✅ 同进程直接调用 |
| 打包体积 | >200 MB | ~50 MB |
| matplotlib 集成 | 需 Web 图表库 | ✅ 原生无缝 |
| 开发进度 | 从零开始 | **已有完整基础** |
| **结论** | — | **继续 PySide6，效率最高** |

### 2.2 目标架构

```
┌─────────────────────────────────────────────────────┐
│                  Presentation Layer                    │
│  MainWindow / CircuitCanvas(QGraphicsView) / Panels  │
│    ✅ SourceFuncEditor(6模型) / ✅ PlotPanel(光标+多曲线)│
│    ✅ UMECTransformerDialog / ✅ LCP*Dialog(3种)      │
│    ✅ MOAParamDialog / ✅ LPMParamDialog              │
│    ✅ ValidationPanel(定位跳转) / ✅ StatisticsPanel    │
├─────────────────────────────────────────────────────┤
│                    Model Layer                        │
│  CircuitModel / ComponentLib(14种) / SubcircuitDef   │
│    ✅ 14种元件类型 / ✅ 子电路 / ✅ 雷电源6模型       │
│    ✅ UMEC 8引脚三相组 / ✅ LCP三种线路参数           │
│    ✅ 探针系统(3种类型) / ✅ result_mode=probes_only  │
│    ✅ can_undo/can_redo / ✅ 撤销栈UX                │
├─────────────────────────────────────────────────────┤
│                   Core Layer                          │
│  ✅ CodeGenerator(含UMEC/LCP电缆/雷电源/MOA/LPM)     │
│  ✅ SolverBuilder(6模型分派/子电路展平/UMEC三相组)    │
│  ✅ Validator(8种校验) / ✅ SimRunner(结果序列化)     │
│  ✅ FileIO(含UMEC向后兼容)                            │
└─────────────────────────────────────────────────────┘
```

---

## 三、分阶段开发计划

### 3.1 总览

| 阶段 | 名称 | 工期 | 核心价值 | 交付门槛 | 状态 |
|------|------|------|---------|---------|------|
| **S0** | 内核对齐 | 3–5 天 | 接入 emtp_0508，API 全部兼容 | 现有案例重新运行通过 | 🔶 95% |
| **S1** | 仿真运行器增强 | 1–2 周 | 子进程运行 + 实时日志 + 进度条 + 取消 | 雷击案例完整运行并出波形 | ✅ 基本完成 |
| **S2** | 结果查看器增强 | 1 周 | 多曲线 + 单位切换 + 光标测量 | GUI 内查看探针曲线 | ✅ 已完成 |
| **S3** | 验证引擎 | 1 周 | 拓扑校验 + 参数范围 + 探针完整性 | Validate 按钮给出结构化错误列表 | ✅ 已完成 |
| **S4** | LCP 参数表单 | 2–3 周 | 架空线/单芯/三芯参数对话框 | 对话框填参数 → 生成 fitULM → 运行仿真 | ✅ 已完成 |
| **S5** | 高级组件表单 | 1–2 周 | MOA / LPM / UMEC 参数表单 | 非线性元件可视化配置 | ✅ 已完成 |
| **S6** | 统计与导出 | 1 周 | timing 报告 + CSV 导出 + 脚本导出 | 仿真后可导出数据和代码 | 🔶 基本完成 |
| **S7** | 打磨与示例 | 持续 | 10 个示例项目 + 错误提示优化 | 外部用户可独立走通端到端 | ❌ 未开始 |

**预计总工期**：5–7 周（单人兼职，较原计划缩短）

### 3.2 S0 内核对齐 — 详细进度

| 任务 | 状态 | 说明 |
|------|------|------|
| S0.1 更新求解器导入 | ✅ | `main.py` 已支持 emtp_0508 多路径导入策略 |
| S0.2 雷电源 6 模型适配 | ✅ | SolverBuilder `_build_source_func` 6 路分派 |
| S0.3 雷电源 UI 面板 | ✅ | SourceFuncEditor 6 子面板 + 标准10波形 + PERC |
| S0.4 雷电源代码生成 | ✅ | CodeGenerator 智能导入检测 |
| S0.5 LCP 电缆引脚/代码生成 | ✅ | `_gen_cable_nodes()` + `PARAM_TEMPLATES` |
| S0.6 子电路展平 | ✅ | `_flatten_subcircuits()` 递归展平 + 桥接线 |
| S0.7 向后兼容 | ✅ | 旧 .emtp 文件自动回退 `twoexpf_standard` |
| S0.8 LCP 参数对话框 | ✅ | `LCPOHLDialog`/`LCPSingleCableDialog`/`LCPThreeCoreCableDialog` + 截面预览 |
| S0.9 探针系统适配 | ✅ | 3种探针(voltage/branch_current/line_current) 代码生成+求解器+UI面板 |
| S0.10 result_mode 适配 | ✅ | `probes_only` 模式 + `record_source_history` + UI选择器 |
| S0.11 验证清单 | ❌ | 5 个现有案例 + emtp_0508 运行 |

### 3.3 S5 高级组件表单 — 详细进度

| 任务 | 状态 | 说明 |
|------|------|------|
| S5.1 UMEC 变压器表单 | ✅ | `UMECTransformerDialog` 3标签页 + 8引脚10参数 + Y/Delta节点映射 + 配置按钮 |
| S5.2 MOA 避雷器表单 | ✅ | `MOAParamDialog` 3标签页：基本参数(额定电压/pu/输入模式)/V-I特性(断点表格+文件加载)/配置预览 |
| S5.3 LPM 绝缘子表单 | ✅ | `LPMParamDialog` 3标签页：几何与场强(间隙/E0/k/海拔)/电弧参数(R_arc/熄弧控制)/配置预览 |

---

## 四、阶段详细设计

### S0：内核对齐（仅剩验证清单）

**已完成**：雷电源 6 模型、LCP 电缆、LCP 参数对话框(3种)、UMEC 变压器三相组、验证引擎、子电路、向后兼容、UX 修复、探针系统适配、result_mode 适配、numpy BUG 修复

**待完成**：

#### S0.11 验证清单（5案例端到端运行）

用 5 个现有 `case*.emtp` 文件通过 GUI → 代码生成 → emtp_0508 运行，确认输出正确。

#### ✅ S0.9 探针系统适配（已完成）

emtp_0508 默认 `probes_only` 模式，所有观测量必须通过探针：

```python
# core/code_generator.py 已生成：
solver.add_voltage_probe("V_n1", "n1", "GND")
solver.add_branch_current_probe("I_R1", "R1")
solver.add_line_current_probe("I_TL_k", "TL_6ph", end="k", phase=0)
```

#### ✅ S0.10 result_mode 适配（已完成）

```python
solver = EMTPSolver(
    dt=dt,
    finish_time=finish_time,
    result_mode="probes_only",       # 默认 probes_only
    verbose=verbose,
    ulm_batch_mode="auto",           # ULM 批量加速
    record_node_history=False,
)
```

#### ✅ UMEC numpy 缺失 BUG 已修复

```python
# circuit_canvas.py 已将 np.radians() 替换为 math.radians()
```

---

### S1：仿真运行器增强（第 1–2 周）

**现状**：`core/sim_runner.py` 已有基础版 SimulationRunner（QThread），`PlotPanel` 已有基础波形显示。

**待增强**：

#### S1.1 SimRunner 增强

```python
# core/sim_runner.py — 增强点

class SimulationRunner(QThread):
    """仿真运行器 - 子进程隔离"""

    # 信号定义
    started = Signal()
    progress_updated = Signal(float, str)  # 百分比, 状态文本  ← 新增
    log_received = Signal(str)              # 日志行
    completed = Signal(dict)               # 探针数据
    error_occurred = Signal(str)          # 错误信息
    cancelled = Signal()

    # 增强点：
    # 1. 使用 QProcess 替代 QThread + subprocess（更可靠的 stdout 流式读取）
    # 2. 进度解析（从 stdout 提取 step/total）
    # 3. 结果序列化（probes_only 模式的 JSON 输出）
    # 4. 运行目录管理（每次运行独立目录）
```

#### S1.2 MainWindow 集成

```python
# ui/main_window.py - 增强仿真面板

class MainWindow:
    def _setup_run_panel(self):
        """设置仿真运行面板"""
        # 状态标签
        self.run_status_label = QLabel("就绪")
        self.progress_bar = QProgressBar()        # ← 新增
        self.progress_bar.setVisible(False)

        # 日志文本框
        self.log_text = QPlainTextEdit()
        self.log_text.setMaximumHeight(150)
        self.log_text.setReadOnly(True)

        # 运行/取消按钮
        self.run_btn = QPushButton("▶ 运行仿真")
        self.cancel_btn = QPushButton("■ 取消")
```

---

### S2：结果查看器增强（第 2–3 周）

**现状**：`PlotPanel` 已有基础 matplotlib 嵌入 + CSV/PNG 导出。

**待增强**：

#### S2.1 ProbePlotWidget 增强

```python
# ui/probe_plot_widget.py 或在 main_window.py 内增强

class ProbePlotWidget(QWidget):
    """探针波形查看器 — 增强版"""

    # 新增功能：
    # 1. 时间单位切换（s/ms/us/ns）
    # 2. 探针选择下拉框（全部/单个）
    # 3. 多曲线叠加 + 图例
    # 4. 光标测量（十字线 + 数值显示）
    # 5. probes_only 模式结果自动解析
```

---

### S3：验证引擎（✅ 已完成）

已实现在 `core/validator.py`（286行），包含 8 种校验规则：

```python
class CircuitValidator:
    def validate(self, model: CircuitModel) -> List[ValidationError]:
        errors = []
        errors.extend(self._check_empty_circuit(model))
        errors.extend(self._check_floating_nodes(model))
        errors.extend(self._check_ground_connection(model))
        errors.extend(self._check_voltage_source_conflict(model))
        errors.extend(self._check_parameter_ranges(model))
        errors.extend(self._check_probe_references(model))
        errors.extend(self._check_wire_connectivity(model))
        errors.extend(self._check_simulation_settings(model))
        return errors
```

**待集成**：需要将 Validate 按钮集成到 MainWindow，并添加 `ui/validation_panel.py` 错误列表面板。

---

### S4：LCP 参数表单（✅ 已完成）

三种 LCP 线路参数对话框已全部实现：

#### S4.1 ✅ LCPOHLDialog（架空线）

5 个标签页：通用参数(长度/土壤电阻率) / 导线配置(动态增删行) / 地线配置 / 拟合配置(Yc/H极点数/误差/Kron) / 截面预览(LCPCrossSectionCanvas)

#### S4.2 ✅ LCPSingleCableDialog（单芯电缆）

2 个标签页：参数配置(8列表电缆表：芯/护套/铠装半径+电阻率，埋深/水平位置) / 截面预览

#### S4.3 ✅ LCPThreeCoreCableDialog（三芯电缆）

2 个标签页：参数配置(管道参数/导体配置/角度位置[270°/30°/150°]/土壤参数) / 截面预览

辅助：`ui/lcp_preview_widgets.py`（截面预览画布，含 `_PreviewDebounceMixin` 150ms 防抖）

---

### S5：高级组件表单（✅ 已完成）

| 任务 | 状态 | 说明 |
|------|------|------|
| S5.1 UMEC 变压器表单 | ✅ | `UMECTransformerDialog` 3标签页 + 8引脚10参数 + Y/Delta节点映射 + 配置按钮 |
| S5.2 MOA 避雷器表单 | ✅ | `MOAParamDialog` 3标签页：基本参数(额定电压/pu/输入模式)/V-I特性(断点表格+文件加载)/配置预览 |
| S5.3 LPM 绝缘子表单 | ✅ | `LPMParamDialog` 3标签页：几何与场强(间隙/E0/k/海拔)/电弧参数(R_arc/熄弧控制/物理说明)/配置预览 |

---

### S6：统计与导出（第 9–10 周）

#### S6.1 仿真统计面板

```python
class StatisticsPanel(QWidget):
    def display(self, results: dict):
        stats = results.get('statistics', {})
        timing = results.get('timing', {})

        html = """
        <table>
        <tr><td>总步数</td><td>{total_steps}</td></tr>
        <tr><td>矩阵构建</td><td>{matrix_build}</td></tr>
        <tr><td>LU 分解</td><td>{lu_factorization}</td></tr>
        <tr><td>RHS 构建</td><td>{rhs_build}</td></tr>
        <tr><td>线性求解</td><td>{linear_solve}</td></tr>
        <tr><td>MOA 段切换</td><td>{segment_switches}</td></tr>
        <tr><td>LPM 重解</td><td>{lpm_resolves}</td></tr>
        </table>
        """.format(**stats)
```

#### S6.2 导出功能

```python
def _export_csv(self, results: dict):
    """导出探针数据为 CSV"""
    import csv
    path, _ = QFileDialog.getSaveFileName(self, "导出 CSV", "", "CSV (*.csv)")
    if not path:
        return

    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['time'] + list(results['probes'].keys()))
        time = results['time']
        for i in range(len(time)):
            row = [time[i]] + [results['probes'][p][i] for p in results['probes']]
            writer.writerow(row)

def _export_script(self):
    """导出 Python 脚本"""
    code = generate_code(self.model)
    path, _ = QFileDialog.getSaveFileName(self, "导出脚本", "", "Python (*.py)")
    if path:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(code)
```

---

## 五、目录结构（更新后）

```
emtp_gui/
├── __init__.py
├── main.py                    # 入口 ✅（emtp_0508 多路径导入策略）
├── requirements.txt
├── models/
│   ├── __init__.py
│   ├── circuit_model.py       # ✅ 成熟（含子电路/UMEC旧格式迁移/14种元件类型）
│   └── component_lib.py       # ✅ 完整（14种元件参数模板 + UMEC 8引脚10参数）
├── core/
│   ├── __init__.py
│   ├── code_generator.py      # ✅ 已适配（LCP电缆/雷电源6模型/UMEC三相组/智能导入）
│   ├── file_io.py             # ✅ 可用
│   ├── solver_builder.py      # ✅ 已适配（6模型分派/子电路展平/LCP电缆/UMEC三相组）
│   ├── sim_runner.py          # ✅ 增强版（QThread + progress + log_received + 取消）
│   ├── validator.py           # ✅ 8种校验规则（空电路/浮空/接地/VS冲突/参数/探针/连线/仿真设置）
│   └── lcp_compiler.py        # ❌ S4 可选（直接用求解器 API）
├── ui/
│   ├── __init__.py
│   ├── main_window.py         # ✅ 可用（SourceFuncEditor/UMEC配置按钮/PlotPanel/属性面板修复）
│   ├── circuit_canvas.py      # ✅ 成熟（子电路/UMEC三相符号/Y-Delta绕组图/选中状态保持/定位跳转）
│   ├── lcp_param_dialog.py    # ✅ 3种对话框（架空线5标签页/单芯2标签页/三芯2标签页）
│   ├── lcp_preview_widgets.py # ✅ 截面预览画布（架空线/电缆）
│   ├── umec_param_dialog.py   # ✅ 3标签页（基本参数/阻抗参数/端口映射预览）
│   ├── moa_param_dialog.py    # ✅ 3标签页（基本参数/V-I特性/配置预览）
│   ├── lpm_param_dialog.py    # ✅ 3标签页（几何与场强/电弧参数/配置预览）
│   ├── probe_panel.py         # ✅ 探针面板（电压/支路电流/线路电流）
│   ├── validation_panel.py    # ✅ S3 验证结果列表面板（级别图标+定位跳转）
│   ├── statistics_panel.py    # ✅ S6 仿真统计面板（timing+探针摘要）
│   └── scientific_spin_box.py # ✅ 科学计数法输入框
├── tests/
│   ├── __init__.py
│   └── test_regressions.py    # ✅ 可用
└── examples/                   # ❌ S7 新增
    ├── rlc_charge_discharge.emtp
    ├── lightning_ulm_line.emtp
    ├── lcp_overhead_line.emtp
    ├── lcp_single_core_cable.emtp
    ├── lcp_three_core_cable.emtp
    ├── moa_protection.emtp
    ├── lpm_insulator.emtp
    ├── cascaded_cable_6seg.emtp
    ├── multiphase_verification.emtp
    └── umec_transformer.emtp
```

---

## 六、关键风险与缓解

| 风险 | 概率 | 影响 | 缓解方案 |
|------|------|------|---------|
| LCP 参数表单复杂度过高 | ~~中~~ ✅ 已解决 | ~~高~~ | 已实现3种对话框+截面预览 |
| 子进程 stdout 编码问题 | 中 | 中 | 使用 `QProcess` + `setProcessChannelMode` |
| 大算例 GUI 冻结 | 低 | 中 | 仿真始终在子进程，S1 已规划 |
| emtp_0508 API 变化 | 低 | 中 | S0 先锁定 API 版本，不跟进最新 commit |
| 波形图性能（10万点） | 中 | 低 | 使用 `matplotlib` 的 `Line2D` 足够；极端情况做降采样 |
| UMEC numpy 缺失 | ~~高~~ ✅ 已修复 | ~~中~~ | ✅ 已修复：`np.` → `math.` |

---

## 七、验收标准

每个阶段完成的门槛：

| 阶段 | 门槛 | 状态 |
|------|------|------|
| S0 | 所有 5 个现有案例重新运行成功，代码生成与 emtp_0508 API 完全匹配 | 🔶 95% |
| S1 | 雷击案例可在子进程中运行，有实时日志，有取消按钮，有进度条 | ✅ 基本完成 |
| S2 | GUI 内查看探针波形，支持单位切换，支持多曲线叠加+光标测量 | ✅ 已完成 |
| S3 | Validate 按钮检测出浮空节点、未接地等问题，列表面板+定位跳转 | ✅ 已完成 |
| S4 | LCP 架空线对话框 → 生成 fitULM → 仿真出波形 | ✅ 已完成 |
| S5 | MOA/LPM/UMEC 参数完整配置，代码正确生成 | ✅ 已完成 |
| S6 | 仿真后可查看 timing 统计，可导出 CSV 和 Python 脚本 | 🔶 基本完成 |
| S7 | 10 个示例覆盖主要功能，错误提示友好 | ❌ |

---

## 八、变更记录

| 日期 | 版本 | 变更内容 |
|------|------|---------|
| 2026-05-14 | v2.0 | 初始版本，完整审计 + 7阶段规划 |
| 2026-05-15 | v2.1 | 更新 S0 进度：雷电源6模型✅、LCP电缆✅、子电路✅、属性面板焦点修复✅ |
| 2026-05-15 | v2.2 | **重大更新**：① UMEC变压器从2端口→8引脚三相组完整重构✅（含画布符号/求解器/代码生成/对话框/配置按钮/向后兼容）；② LCP参数对话框3种全部完成✅（含截面预览）；③ 验证引擎8种校验✅；④ 更新1.1已完成模块表、1.2待建设模块表、2.2架构图、3.1总览状态、目录结构、风险表、验收标准；⑤ 发现numpy缺失BUG⚠️ |
| 2026-05-15 | v2.3 | **完成 S5 + 探针面板 + 仿真运行器增强**：① 新建 `ui/moa_param_dialog.py` 3标签页(基本参数/V-I特性/配置预览)✅；② 新建 `ui/lpm_param_dialog.py` 3标签页(几何与场强/电弧参数/配置预览)✅；③ PropertyPanel 添加 MOA/LPM 配置按钮✅；④ 探针面板添加"+ 线路电流"按钮和表单✅；⑤ SimRunner 添加 `log_received` 信号✅；⑥ 修复 UMEC numpy BUG (`np.` → `math.`)✅；⑦ S0 进度 85%→95%，S5 标记完成 |
| 2026-05-15 | v2.4 | **完成 S2/S3/S6 多项 + UX 改进**：① 新建 `ui/validation_panel.py` 验证结果面板(级别图标+定位跳转)✅；② MainWindow 集成验证面板+工具栏验证按钮✅；③ PlotPanel 光标测量(十字线+数值显示)✅；④ PlotPanel 多曲线颜色分配+图例优化✅；⑤ SimRunner 结果序列化(`extract_probe_results`/`extract_timing_report`)✅；⑥ 新建 `ui/statistics_panel.py` 仿真统计面板✅；⑦ CSV 批量导出增强(line_current+缓存数据)✅；⑧ PlotPanel 脚本导出按钮✅；⑨ 撤销/重做工具栏按钮+状态同步✅；⑩ `CircuitModel.can_undo/can_redo` 方法✅；⑪ `CircuitCanvas.select_component_by_id` 定位跳转✅；⑫ S2→已完成，S3→已完成，S6→基本完成 |

---

## 九、与 Web 前端计划的对照

| Web 前端计划 | 对应桌面 GUI 实现 | 状态 |
|-------------|-----------------|------|
| Phase 1 Schema + 编译器 | `code_generator.py` + `solver_builder.py` + `validator.py` | ✅ 编译器+验证器完成 |
| Phase 2 React Flow 画布 | `circuit_canvas.py` (已有) | ✅ QGraphicsView 成熟方案 |
| Phase 3 运行器 + WebSocket | `sim_runner.py` | 🔶 基础版，待增强 |
| Phase 4 全组件表单 | `lcp_param_dialog.py` + `umec_param_dialog.py` + `moa_param_dialog.py` + `lpm_param_dialog.py` | ✅ 全部完成 |
| Phase 5 曲线查看器 | `PlotPanel` | 🔶 基础版，待增强 |
| WebSocket 日志流 | `SimRunner.log_received` Signal | 🔶 待增强 |

**核心结论**：桌面 PySide6 方案在功能上完全可以覆盖 Web 方案，且集成度更高、开发路径更短。S3(验证引擎)、S4(LCP表单)、S5(高级组件表单)已全部完成，S0 进度 95%。剩余核心工作：S6(统计与导出)、S7(打磨与示例)。
