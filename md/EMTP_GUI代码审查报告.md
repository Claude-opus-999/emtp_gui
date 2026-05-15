# EMTP GUI 代码审查报告

> 审查日期：2026-05-15  
> 本次更新：基于恢复后的完整 `ui/main_window.py` 和最新 GUI 代码重新审查。  
> 审查范围：`main.py`、`models/`、`core/`、`ui/`、`tests/`、现有 `.emtp` 示例。  
> 审查目标：核对主窗口恢复状态、PSCAD 风格符号、三类探针、UMEC 动态端口、LCP 线路链路、底部输出区和测试覆盖。

## 一、事故和恢复状态

本轮任务中，曾发生一次严重事故：自动子代理写坏了 `ui/main_window.py` 的中文字符串，导致主窗口源码无法导入。这个问题已经被确认，不应归因给用户代码本身。

当前恢复状态如下：

- 已从同级备份目录 `C:\Users\Wangweihong\WorkBuddy\20260402191132\emtp_gui (2)\ui\main_window.py` 恢复完整主窗口代码。
- 事故期间的精简版已备份到 `.recovery_backup/main_window_simplified_after_incident.py`。
- 当前主路径 `ui/main_window.py` 是完整主窗口版本，并在此基础上重新补回了新版布局、三类探针入口、运行控件状态和动态端口重建逻辑。
- 报告中此前“恢复为精简可运行版、后续逐步补回旧菜单”的描述已经废弃，不再代表当前代码状态。

## 二、验证状态

本轮执行：

```powershell
python -m py_compile ui\main_window.py
python -m unittest -v tests.test_gui_smoke
python -m unittest discover -v
```

结果：

```text
Ran 27 tests
OK
```

测试覆盖点包括：

- 主窗口可导入和实例化。
- `run_action` / `run_btn` 存在，运行态可禁用和恢复。
- `right_tabs` 可从菜单聚焦到仿真配置页。
- `main_splitter` 为纵向布局，底部 `output_tabs` 横跨元件库、画布和属性区全宽。
- 主窗口不再挂载 `probe_panel`。
- 左侧元件库包含 `对地电压探针`、`两节点电压探针`、`电流探针`。
- 属性面板切换 `probe_type`、`wtype1`、`wtype2` 时会动态重建端口。
- LCP 架空线、单芯电缆、三芯电缆使用当前内核 API 并清洗 GUI-only 参数。
- PSCAD Hybrid 符号渲染 smoke test 覆盖基础元件、三类探针、线路/电缆和 UMEC 接法变化。

## 三、当前实现核对

### 1. 主窗口布局

位置：

- `ui/main_window.py:1964`
- `ui/main_window.py:1976`
- `ui/main_window.py:1980`
- `ui/main_window.py:1993`
- `tests/test_gui_smoke.py:76`

当前结构：

- 上方 `work_splitter` 为水平布局：左侧元件库、中间画布、右侧属性/仿真配置。
- 下方 `output_tabs` 为底部输出区：代码预览、波形、控制台。
- 最外层 `main_splitter` 为纵向布局，用户可以上下拖动调整工作区和输出区高度。

审查结论：符合“波形图栏目全部在下面，不要和电路编辑区在一列”的需求。

### 2. 三类探针入口

位置：

- `ui/main_window.py:659`
- `ui/main_window.py:666`
- `ui/main_window.py:673`
- `ui/main_window.py:696`
- `ui/main_window.py:725`
- `models/component_lib.py:148`
- `models/circuit_model.py:553`

当前实现：

- `对地电压探针`：`probe_type="voltage_ground"`，默认单位 `kV`。
- `两节点电压探针`：`probe_type="voltage_between"`，默认单位 `kV`，端口包含 `sense` 和 `ref`。
- `电流探针`：`probe_type="branch_current"`，默认单位 `A`。
- 元件库按钮通过 `default_params` 把探针类型传给画布放置逻辑。

审查结论：探针交互已按 PSCAD 风格从“面板管理”改为“作为元件放置”。

### 3. UMEC 动态端口和符号

位置：

- `models/component_lib.py:67`
- `models/component_lib.py:761`
- `models/component_lib.py:811`
- `ui/main_window.py:977`
- `ui/main_window.py:1036`
- `ui/symbols/umec_symbols.py`
- `tests/test_symbol_rendering.py`

当前实现：

- `get_umec_pins(params)` 根据 `wtype1` / `wtype2` 动态决定是否显示 `H_N` / `X_N`。
- `Y` 和 `Y_gnd` 侧显示底部端点，`Y_gnd` 额外显示接地符号，`Delta` 不显示中性点端口。
- 属性面板修改 `wtype1` / `wtype2` 后会重建端口，并清理连接到失效端口的连线。

审查结论：UMEC 已按 PSCAD 风格进入可迭代状态，动态端口主路径已被回归测试覆盖。

### 4. LCP 线路和电缆链路

位置：

- `core/lcp_config.py:153`
- `core/lcp_config.py:168`
- `core/lcp_config.py:195`
- `core/solver_builder.py:376`
- `core/solver_builder.py:392`
- `core/solver_builder.py:403`
- `core/code_generator.py:322`
- `core/code_generator.py:337`
- `core/code_generator.py:351`

当前实现：

- 架空线、单芯电缆、三芯电缆都通过 `core/lcp_config.py` 统一清洗参数。
- GUI 运行和导出 Python 代码使用同一套 helper，降低两条路径不一致的风险。
- 单芯/三芯电缆使用当前内核接口：`add_lcp_single_core_cable_line`、`add_lcp_three_core_cable_line`。

审查结论：用户反馈“添加线路后报错”涉及的同类 LCP 问题已有回归覆盖。

## 四、剩余建议

### P2：旧 `ui/probe_panel.py` 容易误导维护

当前主窗口不再挂载 `ProbePanel`，但文件仍存在。建议后续二选一：

- 删除 `ui/probe_panel.py`；
- 或在文件顶部标注 deprecated，并说明探针现在从左侧元件库放置。

### P2：底部输出区后续可补验证/统计 Tab

当前恢复后的完整主窗口底部输出区包含代码预览、波形和控制台。旧报告里提到的验证/统计底部 Tab 暂不属于当前主路径。若后续需要恢复，可以在当前 `output_tabs` 上逐步补回，并为面板增加 smoke tests。

### P3：`right_dock` 是兼容别名

`right_dock` 当前指向 `right_tabs`，不是 `QDockWidget`。这是为了兼容旧测试和旧调用。后续可以统一改名为 `right_panel` 或直接使用 `right_tabs`。

### P3：文档里的 ProbePanel 旧计划需要同步清理

`md/EMTP_GUI修复计划.md` 中仍有“接入 ProbePanel”的历史计划，这和当前 PSCAD 风格探针交互相冲突。建议下一轮文档整理时同步更新。

## 五、结论

当前 GUI 已恢复到完整主窗口版本，并重新通过 27 个测试。主路径重点功能，包括底部可拖动输出区、三类探针元件、UMEC 动态端口、PSCAD Hybrid 符号和 LCP 线路/电缆链路，均已有测试支撑。

下一轮更适合做小步加固：清理旧 ProbePanel 文档、补回可选的验证/统计底部 Tab、继续细化 PSCAD 风格符号细节。
