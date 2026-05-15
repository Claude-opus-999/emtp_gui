# EMTP GUI 审查问题修复实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 修复 `md/EMTP_GUI代码审查报告.md` 中影响 GUI 可用性、导出一致性、探针语义和测试可靠性的 P1/P2 问题。

**架构：** 先把可复用 UI 控件、测试发现和 smoke test 打牢，再修 LCP 导出、运行状态、探针绑定、探针面板接入和仿真取消提示。所有变更保持现有 PySide6 架构，不引入新框架，不重写主窗口。

**技术栈：** Python 3、PySide6、unittest、matplotlib、现有 `CircuitModel` / `CodeGenerator` / `SolverBuilder`。

---

## 文件结构

- 创建：`ui/scientific_spin_box.py`  
  共享 `ScientificSpinBox`，解除 `lpm_param_dialog.py` 对 `main_window.py` 内部类的依赖。

- 修改：`ui/main_window.py`  
  从共享模块导入 `ScientificSpinBox`；保存 `self.run_action`、`self.run_btn`、`self.right_tabs`、`self.right_dock`；增加统一运行状态切换；接入 `ProbePanel`；修复仿真设置菜单聚焦。

- 修改：`ui/lpm_param_dialog.py`  
  从 `ui.scientific_spin_box` 导入 `ScientificSpinBox`。

- 修改：`ui/probe_panel.py`  
  将自动探针复选框连接到 `model.settings.result_mode`；在模型变更后同步 UI。

- 修改：`ui/circuit_canvas.py`  
  画布添加 branch current 探针时写入明确目标支路信息。

- 修改：`models/circuit_model.py`  
  `get_auto_voltage_probes()` 优先使用显式 `branch_name` / `target_comp_id`，避免一个画布电流探针生成多个支路电流探针。

- 修改：`core/code_generator.py`  
  为三类 LCP 元件导出 `config` 参数，使代码预览/导出和 `SolverBuilder` 保持一致。

- 修改：`core/sim_runner.py`  
  检测内核 `solver.run` 是否支持 `step_callback`，不支持时给出明确日志，避免取消按钮造成误导。

- 创建：`ui/mpl_config.py`  
  统一 matplotlib 中文字体配置入口。

- 修改：`main.py`、`ui/lcp_preview_widgets.py`、`ui/main_window.py`  
  改为调用统一字体配置，移除重复配置。

- 修改：`core/solver_builder.py`  
  删除子电路展平中的无意义赋值。

- 创建：`tests/__init__.py`  
  修复默认 unittest discovery。

- 创建：`tests/test_gui_smoke.py`  
  覆盖参数对话框导入、主窗口关键 UI 引用、仿真设置聚焦、探针面板挂载。

- 修改：`tests/test_regressions.py`  
  增加 LCP 导出、branch current 探针绑定、运行状态切换等回归测试。

---

## 任务 1：修复 LPM 对话框导入失败并补齐 smoke test

**文件：**
- 创建：`ui/scientific_spin_box.py`
- 修改：`ui/main_window.py`
- 修改：`ui/lpm_param_dialog.py`
- 创建：`tests/__init__.py`
- 创建：`tests/test_gui_smoke.py`

- [ ] **步骤 1：编写失败的导入测试**

在 `tests/__init__.py` 创建空文件。

在 `tests/test_gui_smoke.py` 写入：

```python
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class GuiSmokeTests(unittest.TestCase):
    def test_parameter_dialog_imports(self):
        from ui.moa_param_dialog import MOAParamDialog
        from ui.lpm_param_dialog import LPMParamDialog
        from ui.lcp_param_dialog import LCPOHLDialog, LCPSingleCableDialog, LCPThreeCoreCableDialog
        from ui.umec_param_dialog import UMECTransformerDialog

        self.assertIsNotNone(MOAParamDialog)
        self.assertIsNotNone(LPMParamDialog)
        self.assertIsNotNone(LCPOHLDialog)
        self.assertIsNotNone(LCPSingleCableDialog)
        self.assertIsNotNone(LCPThreeCoreCableDialog)
        self.assertIsNotNone(UMECTransformerDialog)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **步骤 2：运行测试验证失败**

运行：

```powershell
python -m unittest -v tests.test_gui_smoke
```

预期：失败，错误包含：

```text
ImportError: cannot import name 'ScientificSpinBox'
```

- [ ] **步骤 3：创建共享控件模块**

创建 `ui/scientific_spin_box.py`：

```python
from PySide6.QtWidgets import QDoubleSpinBox


class ScientificSpinBox(QDoubleSpinBox):
    """支持科学计数法显示的 QDoubleSpinBox。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(1e-15, 1e6)
        self.setDecimals(12)
        self.setMinimumWidth(130)

    def textFromValue(self, val: float) -> str:
        if val == 0:
            return "0"
        if abs(val) < 1e-3 or abs(val) >= 1e6:
            return f"{val:.6e}"
        return f"{val:.6g}"

    def valueFromText(self, text: str) -> float:
        try:
            return float(text.replace(",", ""))
        except ValueError:
            return self.value()
```

- [ ] **步骤 4：替换导入路径**

在 `ui/main_window.py` 顶部 PySide6 imports 后加入：

```python
from ui.scientific_spin_box import ScientificSpinBox
```

删除 `ui/main_window.py` 内部原 `class ScientificSpinBox(QDoubleSpinBox)` 定义。

在 `ui/lpm_param_dialog.py` 将：

```python
from models.component_lib import ScientificSpinBox
```

替换为：

```python
from ui.scientific_spin_box import ScientificSpinBox
```

- [ ] **步骤 5：运行测试验证通过**

运行：

```powershell
python -m unittest -v tests.test_gui_smoke
python -m unittest -v tests.test_regressions
python -m unittest discover -v
```

预期：

```text
tests.test_gui_smoke ... OK
tests.test_regressions ... OK
Ran 6+ tests
OK
```

---

## 任务 2：修复 LCP 导出配置丢失

**文件：**
- 修改：`core/code_generator.py`
- 修改：`tests/test_regressions.py`

- [ ] **步骤 1：添加 LCP 导出一致性测试**

在 `tests/test_regressions.py` 的 `RegressionTests` 中新增：

```python
    def test_lcp_ohl_export_includes_config_fields(self):
        model = CircuitModel()
        comp = ComponentInstance(
            comp_id="LCP_OHL_001",
            comp_type=ComponentType.LCP_OHL,
            name="LCP1",
            x=0,
            y=0,
            params=get_default_params(ComponentType.LCP_OHL) | {
                "length": 1200.0,
                "force_rebuild": False,
                "n_phases": 3,
                "n_gw": 1,
                "ground_resistivity": 500.0,
                "phase_positions": [[0.0, 10.0], [4.0, 10.0], [8.0, 10.0]],
                "gw_positions": [[4.0, 16.0]],
                "phase_radius": 0.015,
                "phase_dc_resistance": 0.08,
                "phase_bundle_n": 2,
                "phase_bundle_spacing": 0.4,
                "gw_radius": 0.008,
                "gw_dc_resistance": 0.2,
            },
            pins=create_component_pins(ComponentType.LCP_OHL, 4),
        )
        model.add_component(comp)

        code = generate_code(model)

        self.assertIn("_config_LCP1", code)
        self.assertIn("'phase_positions': [[0.0, 10.0], [4.0, 10.0], [8.0, 10.0]]", code)
        self.assertIn("'gw_positions': [[4.0, 16.0]]", code)
        self.assertIn("'ground_resistivity': 500.0", code)
        self.assertIn("config=_config_LCP1", code)
```

- [ ] **步骤 2：运行测试验证失败**

运行：

```powershell
python -m unittest -v tests.test_regressions.RegressionTests.test_lcp_ohl_export_includes_config_fields
```

预期：失败，提示找不到 `_config_LCP1` 或 `config=_config_LCP1`。

- [ ] **步骤 3：增加 Python 字面量格式化辅助方法**

在 `core/code_generator.py` 的 `CodeGenerator` 类中增加：

```python
    def _format_literal(self, value):
        if isinstance(value, float):
            return self._format_num(value)
        if isinstance(value, list):
            return "[" + ", ".join(self._format_literal(v) for v in value) + "]"
        if isinstance(value, tuple):
            return "(" + ", ".join(self._format_literal(v) for v in value) + ")"
        if isinstance(value, dict):
            items = [
                f"{key!r}: {self._format_literal(val)}"
                for key, val in value.items()
            ]
            return "{" + ", ".join(items) + "}"
        return repr(value)

    def _safe_var_name(self, name: str) -> str:
        return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name)
```

- [ ] **步骤 4：为 LCP 生成 config 变量**

在 `core/code_generator.py` 中替换三类 LCP 分支。

LCP 架空线使用：

```python
        elif ct == ComponentType.LCP_OHL:
            nk_list, nm_list = self._gen_multipin_nodes(comp, 'nk', 'nm', node_map)
            config = {
                'n_phases': p.get('n_phases', 2),
                'n_gw': p.get('n_gw', 2),
                'ground_resistivity': p.get('ground_resistivity', 1000.0),
            }
            for key in (
                'phase_positions', 'gw_positions', 'phase_radius',
                'phase_dc_resistance', 'phase_bundle_n',
                'phase_bundle_spacing', 'gw_radius', 'gw_dc_resistance',
            ):
                if key in p:
                    config[key] = p[key]
            var_name = f"_config_{self._safe_var_name(comp.name)}"
            return (
                f"{var_name} = {self._format_literal(config)}\n"
                f'solver.add_lcp_ohl_line("{comp.name}", '
                f'nodes_k=[{", ".join(nk_list)}], '
                f'nodes_m=[{", ".join(nm_list)}], '
                f'length={self._format_num(p.get("length", 900.0))}, '
                f'force_rebuild={p.get("force_rebuild", True)}, '
                f'config={var_name})'
            )
```

LCP 单芯电缆使用：

```python
        elif ct == ComponentType.LCP_SINGLE_CABLE:
            nk_list, nm_list = self._gen_cable_nodes(comp, 'nk', 'nm', node_map)
            var_name = f"_config_{self._safe_var_name(comp.name)}"
            return (
                f"{var_name} = {self._format_literal(p)}\n"
                f'solver.add_lcp_single_cable_line("{comp.name}", '
                f'nodes_k=[{", ".join(nk_list)}], '
                f'nodes_m=[{", ".join(nm_list)}], '
                f'length={self._format_num(p.get("length", 1000.0))}, '
                f'force_rebuild={p.get("force_rebuild", True)}, '
                f'config={var_name})'
            )
```

LCP 三芯电缆使用：

```python
        elif ct == ComponentType.LCP_THREE_CABLE:
            nk_list, nm_list = self._gen_cable_nodes(comp, 'nk', 'nm', node_map)
            var_name = f"_config_{self._safe_var_name(comp.name)}"
            return (
                f"{var_name} = {self._format_literal(p)}\n"
                f'solver.add_lcp_three_core_cable_line("{comp.name}", '
                f'nodes_k=[{", ".join(nk_list)}], '
                f'nodes_m=[{", ".join(nm_list)}], '
                f'length={self._format_num(p.get("length", 1000.0))}, '
                f'force_rebuild={p.get("force_rebuild", True)}, '
                f'config={var_name})'
            )
```

- [ ] **步骤 5：运行测试验证通过**

运行：

```powershell
python -m unittest -v tests.test_regressions.RegressionTests.test_lcp_ohl_export_includes_config_fields
python -m unittest -v tests.test_regressions
```

预期：新增测试和既有测试均通过。

---

## 任务 3：统一仿真运行状态并修复仿真设置菜单聚焦

**文件：**
- 修改：`ui/main_window.py`
- 修改：`tests/test_gui_smoke.py`

- [ ] **步骤 1：添加主窗口 UI smoke test**

在 `tests/test_gui_smoke.py` 增加：

```python
from PySide6.QtWidgets import QApplication


def get_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app
```

在 `GuiSmokeTests` 中增加：

```python
    def test_main_window_exposes_run_and_right_tab_controls(self):
        get_app()
        from ui.main_window import MainWindow

        window = MainWindow()
        try:
            self.assertTrue(hasattr(window, "run_action"))
            self.assertTrue(hasattr(window, "run_btn"))
            self.assertTrue(hasattr(window, "right_tabs"))
            self.assertTrue(hasattr(window, "right_dock"))
        finally:
            window.close()

    def test_sim_settings_selects_simulation_config_tab(self):
        get_app()
        from ui.main_window import MainWindow

        window = MainWindow()
        try:
            window.right_tabs.setCurrentWidget(window.property_panel)
            window._on_sim_settings()
            self.assertIs(window.right_tabs.currentWidget(), window.simulation_config)
        finally:
            window.close()

    def test_set_running_ui_toggles_run_controls(self):
        get_app()
        from ui.main_window import MainWindow

        window = MainWindow()
        try:
            window._set_running_ui(True)
            self.assertFalse(window.run_action.isEnabled())
            self.assertFalse(window.run_btn.isEnabled())

            window._set_running_ui(False)
            self.assertTrue(window.run_action.isEnabled())
            self.assertTrue(window.run_btn.isEnabled())
        finally:
            window.close()
```

- [ ] **步骤 2：运行测试验证失败**

运行：

```powershell
python -m unittest -v tests.test_gui_smoke
```

预期：失败，提示 `run_action`、`run_btn`、`right_tabs` 或 `_set_running_ui` 不存在。

- [ ] **步骤 3：保存运行 action 和工具栏按钮**

在 `_setup_menu_bar()` 中将局部变量改为实例变量：

```python
        self.run_action = QAction("运行仿真", self)
        self.run_action.setShortcut("F5")
        self.run_action.triggered.connect(self._on_run_simulation)
        sim_menu.addAction(self.run_action)
```

在 `_setup_tool_bar()` 中将局部变量改为实例变量：

```python
        self.run_btn = QPushButton("▶ 运行")
        self.run_btn.setToolTip("运行仿真 (F5)")
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #059669; color: white; border: none;
                border-radius: 4px; padding: 6px 14px; font-weight: bold;
            }
            QPushButton:hover { background-color: #047857; }
            QPushButton:disabled { background-color: #94a3b8; color: #e2e8f0; }
        """)
        self.run_btn.clicked.connect(self._on_run_simulation)
        toolbar.addWidget(self.run_btn)
```

- [ ] **步骤 4：增加统一运行状态方法**

在 `MainWindow` 中增加：

```python
    def _is_simulation_running(self) -> bool:
        return (
            hasattr(self, "_sim_runner")
            and self._sim_runner is not None
            and self._sim_runner.isRunning()
        )

    def _set_running_ui(self, running: bool):
        if hasattr(self, "run_action"):
            self.run_action.setEnabled(not running)
        if hasattr(self, "run_btn"):
            self.run_btn.setEnabled(not running)
        if running:
            self.status_label.setText("正在运行仿真...")
        else:
            self.status_label.setText("就绪")
```

在 `_on_run_simulation()` 开头加入：

```python
        if self._is_simulation_running():
            QMessageBox.information(self, "仿真进行中", "当前仿真尚未结束。")
            return
```

将原有 `for action in self.findChildren(QAction)` 禁用/恢复逻辑替换为：

```python
        self._set_running_ui(True)
```

在 `_on_sim_finished()` 和 `_on_sim_error()` 中恢复为：

```python
        self._set_running_ui(False)
```

- [ ] **步骤 5：保存右侧 Dock 和 Tab 引用**

在 `_setup_dock_widgets()` 中将局部变量改为实例变量：

```python
        self.right_dock = QDockWidget("属性 / 配置", self)
        self.right_dock.setMinimumWidth(260)
        self.right_dock.setMaximumWidth(300)
        self.right_tabs = QTabWidget()
        self.property_panel = PropertyPanel(self.model, self.canvas)
        self.simulation_config = SimulationConfigPanel(self.model)
        self.right_tabs.addTab(self.property_panel, "🔧 属性编辑")
        self.right_tabs.addTab(self.simulation_config, "⚙️ 仿真配置")
        self.right_dock.setWidget(self.right_tabs)
        self.addDockWidget(Qt.RightDockWidgetArea, self.right_dock)
```

将 `_on_sim_settings()` 改为：

```python
    def _on_sim_settings(self):
        """聚焦到仿真配置面板"""
        self.right_tabs.setCurrentWidget(self.simulation_config)
        self.right_dock.show()
        self.right_dock.raise_()
```

- [ ] **步骤 6：运行测试验证通过**

运行：

```powershell
python -m unittest -v tests.test_gui_smoke
python -m unittest -v tests.test_regressions
```

预期：全部通过。

---

## 任务 4：修复画布 branch current 探针绑定语义

**文件：**
- 修改：`ui/circuit_canvas.py`
- 修改：`models/circuit_model.py`
- 修改：`tests/test_regressions.py`

- [ ] **步骤 1：添加多支路节点探针绑定测试**

在 `tests/test_regressions.py` 中新增：

```python
    def test_branch_current_probe_uses_explicit_branch_name_once(self):
        model = CircuitModel()

        r1 = ComponentInstance(
            comp_id="R_001",
            comp_type=ComponentType.RESISTOR,
            name="R1",
            x=0,
            y=0,
            pins=create_component_pins(ComponentType.RESISTOR),
        )
        c1 = ComponentInstance(
            comp_id="C_001",
            comp_type=ComponentType.CAPACITOR,
            name="C1",
            x=0,
            y=0,
            pins=create_component_pins(ComponentType.CAPACITOR),
        )
        gnd = ComponentInstance(
            comp_id="GND_001",
            comp_type=ComponentType.GROUND,
            name="GND",
            x=0,
            y=0,
            pins=create_component_pins(ComponentType.GROUND),
        )
        probe = ComponentInstance(
            comp_id="PRB_001",
            comp_type=ComponentType.PROBE,
            name="PRB1",
            x=0,
            y=0,
            params={"probe_type": "branch_current", "unit": "A", "branch_name": "R1"},
            pins=create_component_pins(ComponentType.PROBE),
        )

        for comp in (r1, c1, gnd, probe):
            model.add_component(comp)

        model.add_wire(Wire("W1", "R_001", "nf", "C_001", "nf"))
        model.add_wire(Wire("W2", "PRB_001", "sense", "R_001", "nf"))
        model.add_wire(Wire("W3", "R_001", "nt", "GND_001", "gnd"))

        probes = [
            p for p in model.get_auto_voltage_probes()
            if p.probe_type == "branch_current"
        ]

        self.assertEqual(len(probes), 1)
        self.assertEqual(probes[0].branch_name, "R1")
```

- [ ] **步骤 2：运行测试验证失败**

运行：

```powershell
python -m unittest -v tests.test_regressions.RegressionTests.test_branch_current_probe_uses_explicit_branch_name_once
```

预期：失败，当前逻辑可能生成多个 branch current probe，或未使用显式 `branch_name`。

- [ ] **步骤 3：画布创建探针时写入目标信息**

在 `ui/circuit_canvas.py` 的 `_add_probe_at_pin()` 中，设置 `params` 后加入：

```python
        if probe_type == "branch_current":
            params["branch_name"] = comp.name
            params["target_comp_id"] = comp.comp_id
            params["target_pin"] = pin_name
```

- [ ] **步骤 4：模型优先使用显式 branch_name**

在 `models/circuit_model.py` 的 `get_auto_voltage_probes()` 中，将 `probe_type == 'branch_current'` 分支改为：

```python
                    elif probe_type == 'branch_current':
                        explicit_branch = comp.params.get('branch_name')
                        target_comp_id = comp.params.get('target_comp_id')

                        if explicit_branch:
                            probes.append(ProbeConfig(
                                probe_id=f"{comp.name}_I_{explicit_branch}",
                                probe_type="branch_current",
                                branch_name=explicit_branch,
                                unit=unit,
                            ))
                            continue

                        if target_comp_id and target_comp_id in self.components:
                            target_comp = self.components[target_comp_id]
                            probes.append(ProbeConfig(
                                probe_id=f"{comp.name}_I_{target_comp.name}",
                                probe_type="branch_current",
                                branch_name=target_comp.name,
                                unit=unit,
                            ))
                            continue

                        matched_branch = None
                        for other_comp in self.components.values():
                            if other_comp.comp_type == ComponentType.PROBE:
                                continue
                            for pin in other_comp.pins:
                                other_key = (other_comp.comp_id, pin.name)
                                if node_map.get(other_key) == target_node:
                                    matched_branch = other_comp.name
                                    break
                            if matched_branch:
                                break

                        if matched_branch:
                            probes.append(ProbeConfig(
                                probe_id=f"{comp.name}_I_{matched_branch}",
                                probe_type="branch_current",
                                branch_name=matched_branch,
                                unit=unit,
                            ))
```

- [ ] **步骤 5：运行测试验证通过**

运行：

```powershell
python -m unittest -v tests.test_regressions.RegressionTests.test_branch_current_probe_uses_explicit_branch_name_once
python -m unittest -v tests.test_regressions
```

预期：全部通过。

---

## 任务 5：接入 ProbePanel 并让自动探针开关影响模型

**文件：**
- 修改：`ui/main_window.py`
- 修改：`ui/probe_panel.py`
- 修改：`tests/test_gui_smoke.py`

- [ ] **步骤 1：添加 ProbePanel 挂载和开关测试**

在 `tests/test_gui_smoke.py` 的 `GuiSmokeTests` 中新增：

```python
    def test_probe_panel_is_mounted_and_auto_probe_updates_result_mode(self):
        get_app()
        from ui.main_window import MainWindow

        window = MainWindow()
        try:
            self.assertTrue(hasattr(window, "probe_panel"))

            window.probe_panel.auto_probe_check.setChecked(False)
            self.assertEqual(window.model.settings.result_mode, "full")

            window.probe_panel.auto_probe_check.setChecked(True)
            self.assertEqual(window.model.settings.result_mode, "probes_only")
        finally:
            window.close()
```

- [ ] **步骤 2：运行测试验证失败**

运行：

```powershell
python -m unittest -v tests.test_gui_smoke.GuiSmokeTests.test_probe_panel_is_mounted_and_auto_probe_updates_result_mode
```

预期：失败，当前 `MainWindow` 没有 `probe_panel`。

- [ ] **步骤 3：在主窗口右侧 Tab 挂载 ProbePanel**

在 `ui/main_window.py` 顶部加入：

```python
from ui.probe_panel import ProbePanel
```

在 `_setup_dock_widgets()` 创建 `simulation_config` 后加入：

```python
        self.probe_panel = ProbePanel(self.model)
```

并加入右侧 Tab：

```python
        self.right_tabs.addTab(self.probe_panel, "📍 探针")
```

- [ ] **步骤 4：让 ProbePanel 自动探针开关更新模型**

在 `ui/probe_panel.py` 的 `_setup_ui()` 中，`auto_probe_check` 创建后加入：

```python
        self.auto_probe_check.setChecked(self.model.settings.result_mode == "probes_only")
        self.auto_probe_check.toggled.connect(self._on_auto_probe_toggled)
```

在 `ProbePanel` 中增加：

```python
    def _on_auto_probe_toggled(self, checked: bool):
        self.model.update_settings(result_mode="probes_only" if checked else "full")

    def _sync_auto_probe_check(self):
        checked = self.model.settings.result_mode == "probes_only"
        self.auto_probe_check.blockSignals(True)
        self.auto_probe_check.setChecked(checked)
        self.auto_probe_check.blockSignals(False)
```

在 `refresh_list()` 开头调用：

```python
        self._sync_auto_probe_check()
```

- [ ] **步骤 5：运行测试验证通过**

运行：

```powershell
python -m unittest -v tests.test_gui_smoke.GuiSmokeTests.test_probe_panel_is_mounted_and_auto_probe_updates_result_mode
python -m unittest -v tests.test_gui_smoke
python -m unittest -v tests.test_regressions
```

预期：全部通过。

---

## 任务 6：明确仿真取消在旧内核上的行为

**文件：**
- 修改：`core/sim_runner.py`

- [ ] **步骤 1：增加运行签名检测**

在 `core/sim_runner.py` 顶部加入：

```python
import inspect
```

在 `solver, node_map = builder.build(self.model)` 后加入：

```python
            run_signature = inspect.signature(solver.run)
            supports_step_callback = "step_callback" in run_signature.parameters
```

- [ ] **步骤 2：不支持 step_callback 时输出明确日志**

将原来的：

```python
            try:
                solver.run(step_callback=on_step)
            except TypeError:
                solver.run()
```

替换为：

```python
            if supports_step_callback:
                solver.run(step_callback=on_step)
            else:
                self.log_received.emit("[仿真] 当前内核不支持 step_callback，取消将在本次求解返回后生效。")
                solver.run()
```

- [ ] **步骤 3：运行导入和回归测试**

运行：

```powershell
python -m py_compile core\sim_runner.py
python -m unittest -v tests.test_regressions
```

预期：编译通过，回归测试通过。

---

## 任务 7：统一 matplotlib 中文字体配置并清理重复代码

**文件：**
- 创建：`ui/mpl_config.py`
- 修改：`main.py`
- 修改：`ui/main_window.py`
- 修改：`ui/lcp_preview_widgets.py`

- [ ] **步骤 1：创建统一配置函数**

创建 `ui/mpl_config.py`：

```python
def configure_matplotlib_fonts():
    """配置 matplotlib 中文字体和负号显示。"""
    import matplotlib

    matplotlib.rcParams["font.family"] = "sans-serif"
    matplotlib.rcParams["font.sans-serif"] = [
        "SimHei",
        "Microsoft YaHei",
        "STHeiti",
        "KaiTi",
        "DejaVu Sans",
    ]
    matplotlib.rcParams["axes.unicode_minus"] = False
```

- [ ] **步骤 2：替换 main.py 中的重复配置**

在 `main.py` 中删除两段直接设置 `matplotlib.rcParams` 的代码，改为：

```python
from ui.mpl_config import configure_matplotlib_fonts

configure_matplotlib_fonts()
```

这段调用必须放在创建 `MainWindow` 前。

- [ ] **步骤 3：在 PlotPanel 使用前配置字体**

在 `ui/main_window.py` 导入：

```python
from ui.mpl_config import configure_matplotlib_fonts
```

在 `PlotPanel.__init__()` 创建 Figure 前调用：

```python
        configure_matplotlib_fonts()
```

- [ ] **步骤 4：让 LCP 预览使用同一配置**

在 `ui/lcp_preview_widgets.py` 中替换本地字体配置逻辑为：

```python
from ui.mpl_config import configure_matplotlib_fonts
```

并在创建 Figure 前调用：

```python
        configure_matplotlib_fonts()
```

- [ ] **步骤 5：运行测试并检查警告**

运行：

```powershell
python -W default -m unittest -v tests.test_regressions
```

预期：测试通过；如果系统没有中文字体，仍可能出现 glyph 警告，但字体配置入口已经统一，不再依赖 `main.py`。

---

## 任务 8：清理子电路展平无意义赋值

**文件：**
- 修改：`core/solver_builder.py`
- 修改：`tests/test_regressions.py`

- [ ] **步骤 1：添加源码清理回归测试**

在 `tests/test_regressions.py` 中新增：

```python
    def test_solver_builder_has_no_dead_wire_type_assignment(self):
        with open("core/solver_builder.py", "r", encoding="utf-8") as f:
            source = f.read()

        self.assertNotIn("type(flat.wires.get", source)
```

- [ ] **步骤 2：运行测试验证失败**

运行：

```powershell
python -m unittest -v tests.test_regressions.RegressionTests.test_solver_builder_has_no_dead_wire_type_assignment
```

预期：失败，当前源码仍包含 `type(flat.wires.get`。

- [ ] **步骤 3：删除无意义赋值**

在 `core/solver_builder.py` 中删除：

```python
                    flat.wires[gnd_wire_id] = type(flat.wires.get('_', Wire(
                        wire_id=gnd_wire_id,
                        from_comp=inner_comp_id,
                        from_pin=port.internal_pin_name,
                        to_comp=gnd_id,
                        to_pin='gnd',
                    )))  # Wire already imported
```

保留下一段真正创建 `Wire(...)` 的赋值。

- [ ] **步骤 4：运行测试验证通过**

运行：

```powershell
python -m unittest -v tests.test_regressions.RegressionTests.test_solver_builder_has_no_dead_wire_type_assignment
python -m unittest -v tests.test_regressions
```

预期：全部通过。

---

## 任务 9：最终验证清单

**文件：**
- 不新增代码文件
- 更新：`md/EMTP_GUI代码审查报告.md`

- [ ] **步骤 1：运行完整测试**

运行：

```powershell
python -m unittest discover -v
```

预期：发现并运行 `tests.test_gui_smoke` 与 `tests.test_regressions` 中的全部测试，结果为 `OK`。

- [ ] **步骤 2：运行关键导入检查**

运行：

```powershell
python -c "from ui.lpm_param_dialog import LPMParamDialog; print('lpm import ok')"
python -c "from ui.moa_param_dialog import MOAParamDialog; print('moa import ok')"
python -c "from ui.main_window import MainWindow; print('main window import ok')"
```

预期：

```text
lpm import ok
moa import ok
main window import ok
```

- [ ] **步骤 3：运行最小 RC 案例**

运行：

```powershell
python -c "import main; from core.file_io import load_project; from core.solver_builder import SolverBuilder; model=load_project('example_circuit.emtp'); solver,node_map=SolverBuilder().build(model); solver.run(); print('solver ok', sorted(set(node_map.values())), solver.list_probes())"
```

预期包含：

```text
solver ok [0, 1, 2]
auto_V_n1
auto_V_n2
```

- [ ] **步骤 4：更新审查报告状态**

在 `md/EMTP_GUI代码审查报告.md` 中将已修复条目标记为“已修复”，并保留验证命令输出摘要：

```markdown
### 已修复

- LPM 配置对话框导入失败：已通过 `tests.test_gui_smoke` 覆盖。
- LCP 导出配置丢失：已通过 LCP OHL 导出测试覆盖。
- 运行按钮防重入：已通过主窗口 smoke test 覆盖。
- 画布 branch current 目标绑定：已通过多支路节点测试覆盖。
- unittest discovery：已通过 `python -m unittest discover -v` 覆盖。
```

---

## 执行顺序建议

1. 任务 1：先修 LPM 导入和测试发现，这是后续验证基础。
2. 任务 2：修 LCP 导出一致性，避免导出脚本误导用户。
3. 任务 3：修运行状态和仿真设置菜单，这是主窗口高频路径。
4. 任务 4：修 branch current 探针语义，避免结果含义错误。
5. 任务 5：接入 ProbePanel，让已写好的探针管理 UI 可用。
6. 任务 6：明确取消按钮行为，降低长仿真误解。
7. 任务 7：统一 matplotlib 配置，减少入口差异。
8. 任务 8：清理子电路展平死代码。
9. 任务 9：完整验证并同步审查报告。

当前目录未检测到 `.git`，本计划不安排提交步骤。若后续在 Git 仓库中执行，建议每完成一个任务并通过对应测试后提交一次。
