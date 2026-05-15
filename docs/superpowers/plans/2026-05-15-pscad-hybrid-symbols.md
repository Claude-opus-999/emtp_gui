# PSCAD Hybrid 元件符号实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将 EMTP GUI 画布元件符号改造成 PSCAD Hybrid 风格：基础元件为工程线稿，复杂元件为端口块，UMEC 根据接法动态显示端点，三种探针使用 PSCAD 式测量箭头。

**架构：** 先修模型层动态引脚，保证 UMEC 和探针的可见端点与电气含义一致；再将符号绘制从 `ui/circuit_canvas.py` 提取到 `ui/symbols/`；最后按 5 类符号替换绘制实现，并用渲染 smoke test 验证。画布交互、求解器构建和文件格式语义保持不变。

**技术栈：** Python、PySide6 `QPainter` / `QImage`、`unittest`、现有 `CircuitModel` / `ComponentInstance` / `create_component_pins`。

---

## 文件结构

- 修改：`models/component_lib.py`  
  职责：根据 `ComponentType` 和参数生成动态引脚；新增 UMEC 专用引脚 helper；让探针和 UMEC 的引脚生成 API 支持参数驱动。
- 修改：`ui/main_window.py`  
  职责：属性面板和参数对话框修改 `probe_type` / `wtype1` / `wtype2` 后重建引脚，并删除连接到失效引脚的连线。
- 修改：`ui/circuit_canvas.py`  
  职责：缩小 `ComponentGraphicsItem` 中的绘制职责，分派到 `ui/symbols`；更新 bounding rect 和通用端口/标签绘制。
- 创建：`ui/symbols/__init__.py`  
  职责：导出符号绘制入口。
- 创建：`ui/symbols/style.py`  
  职责：统一画笔、字体、颜色、箭头/接地/端口等小工具。
- 创建：`ui/symbols/primitive_symbols.py`  
  职责：基础二端口、源类、接地、子电路符号。
- 创建：`ui/symbols/probe_symbols.py`  
  职责：对地电压、两节点电压、电流探针符号。
- 创建：`ui/symbols/line_symbols.py`  
  职责：Bergeron、ULM、LCP-OHL、LCP 单芯/三芯电缆工程块符号。
- 创建：`ui/symbols/umec_symbols.py`  
  职责：PSCAD 风格 UMEC 矩形块、Y/Delta 绕组和接法动态端点。
- 修改：`tests/test_regressions.py`  
  职责：模型行为和参数变更回归测试。
- 创建：`tests/test_symbol_rendering.py`  
  职责：符号渲染 smoke tests，验证典型元件非空、UMEC 接法不同、探针符号不同。

---

### 任务 1：UMEC 动态引脚生成

**文件：**
- 修改：`models/component_lib.py`
- 测试：`tests/test_regressions.py`

- [ ] **步骤 1：编写失败的 UMEC 动态引脚测试**

在 `tests/test_regressions.py` 的 `RegressionTests` 中加入：

```python
    def test_umec_pins_follow_winding_types(self):
        from models.component_lib import create_component_pins

        yg_delta = create_component_pins(
            ComponentType.UMEC_TRANSFORMER,
            params={"wtype1": "Y_gnd", "wtype2": "Delta"},
        )
        self.assertEqual(
            [pin.name for pin in yg_delta],
            ["H_A", "H_B", "H_C", "H_N", "X_A", "X_B", "X_C"],
        )

        y_y = create_component_pins(
            ComponentType.UMEC_TRANSFORMER,
            params={"wtype1": "Y", "wtype2": "Y"},
        )
        self.assertIn("H_N", [pin.name for pin in y_y])
        self.assertIn("X_N", [pin.name for pin in y_y])

        delta_delta = create_component_pins(
            ComponentType.UMEC_TRANSFORMER,
            params={"wtype1": "Delta", "wtype2": "Delta"},
        )
        self.assertEqual(
            [pin.name for pin in delta_delta],
            ["H_A", "H_B", "H_C", "X_A", "X_B", "X_C"],
        )
```

- [ ] **步骤 2：运行测试验证失败**

运行：

```powershell
python -m unittest -v tests.test_regressions.RegressionTests.test_umec_pins_follow_winding_types
```

预期：失败，报错类似 `TypeError: create_component_pins() got an unexpected keyword argument 'params'`。

- [ ] **步骤 3：实现 UMEC 引脚 helper 和参数化 API**

在 `models/component_lib.py` 中修改 `get_pins()` 和 `create_component_pins()` 签名，新增 `params`：

```python
def get_pins(
    comp_type: ComponentType,
    n_phases: int = 1,
    probe_type: str = None,
    params: Dict[str, Any] = None,
) -> List[Dict]:
```

在 `PINS` 后新增：

```python
def get_umec_pins(params: Dict[str, Any] = None) -> List[Dict]:
    params = params or {}
    wtype1 = params.get("wtype1", "Y_gnd")
    wtype2 = params.get("wtype2", "Delta")

    pins = [
        {"name": "H_A", "local_x": -60, "local_y": -30},
        {"name": "H_B", "local_x": -60, "local_y": 0},
        {"name": "H_C", "local_x": -60, "local_y": 30},
    ]
    if wtype1 in ("Y", "Y_gnd"):
        pins.append({"name": "H_N", "local_x": -30, "local_y": 58})

    pins.extend([
        {"name": "X_A", "local_x": 60, "local_y": -30},
        {"name": "X_B", "local_x": 60, "local_y": 0},
        {"name": "X_C", "local_x": 60, "local_y": 30},
    ])
    if wtype2 in ("Y", "Y_gnd"):
        pins.append({"name": "X_N", "local_x": 30, "local_y": 58})

    return pins
```

将 `get_pins()` 中 UMEC 分支改为：

```python
    elif comp_type == ComponentType.UMEC_TRANSFORMER:
        return get_umec_pins(params)
```

将 `create_component_pins()` 改为：

```python
def create_component_pins(
    comp_type: ComponentType,
    n_phases: int = 3,
    probe_type: str = None,
    params: Dict[str, Any] = None,
) -> List:
    """从模板创建元件引脚"""
    from .circuit_model import Pin
    pin_defs = get_pins(comp_type, n_phases, probe_type=probe_type, params=params)
    return [Pin(name=p["name"], local_x=p["local_x"], local_y=p["local_y"]) for p in pin_defs]
```

将 `COMPONENT_REGISTRY[ComponentType.UMEC_TRANSFORMER]` 的 `pins` 改为：

```python
        "pins": lambda params=None: get_umec_pins(params),
        "dynamic_pins": True,
```

- [ ] **步骤 4：运行测试验证通过**

运行：

```powershell
python -m unittest -v tests.test_regressions.RegressionTests.test_umec_pins_follow_winding_types
```

预期：通过。

- [ ] **步骤 5：运行现有回归测试**

运行：

```powershell
python -m unittest discover -v
```

预期：所有测试通过；如旧测试假设 UMEC 固定 8 引脚，更新测试以匹配动态引脚设计。

- [ ] **步骤 6：Commit**

如果仓库已初始化 git：

```bash
git add models/component_lib.py tests/test_regressions.py
git commit -m "feat: make UMEC pins follow winding types"
```

---

### 任务 2：参数变化时重建 UMEC 和探针引脚

**文件：**
- 修改：`ui/main_window.py`
- 测试：`tests/test_regressions.py`

- [ ] **步骤 1：编写失败的参数变更测试**

在 `tests/test_regressions.py` 中加入：

```python
    def test_property_param_change_rebuilds_probe_and_umec_pins(self):
        get_app()
        window = MainWindow()
        try:
            probe = ComponentInstance(
                comp_id="PRB_001",
                comp_type=ComponentType.PROBE,
                name="PRB1",
                x=0,
                y=0,
                params={"probe_type": "voltage_ground", "unit": "kV"},
                pins=create_component_pins(ComponentType.PROBE, probe_type="voltage_ground"),
            )
            window.model.add_component(probe)
            window.property_panel._current_comp_id = probe.comp_id
            window.property_panel._on_param_changed("probe_type", "voltage_between")
            self.assertEqual(
                [pin.name for pin in window.model.components[probe.comp_id].pins],
                ["sense", "ref"],
            )

            umec = ComponentInstance(
                comp_id="UMEC_001",
                comp_type=ComponentType.UMEC_TRANSFORMER,
                name="UMEC1",
                x=0,
                y=0,
                params=get_default_params(ComponentType.UMEC_TRANSFORMER) | {
                    "wtype1": "Y",
                    "wtype2": "Y",
                },
                pins=create_component_pins(
                    ComponentType.UMEC_TRANSFORMER,
                    params={"wtype1": "Y", "wtype2": "Y"},
                ),
            )
            gnd = ComponentInstance(
                comp_id="GND_001",
                comp_type=ComponentType.GROUND,
                name="GND",
                x=0,
                y=0,
                pins=create_component_pins(ComponentType.GROUND),
            )
            window.model.add_component(umec)
            window.model.add_component(gnd)
            window.model.add_wire(Wire("W_UMEC_N", "UMEC_001", "X_N", "GND_001", "gnd"))
            window.property_panel._current_comp_id = umec.comp_id
            window.property_panel._on_param_changed("wtype2", "Delta")

            updated = window.model.components[umec.comp_id]
            self.assertNotIn("X_N", [pin.name for pin in updated.pins])
            self.assertNotIn("W_UMEC_N", window.model.wires)
        finally:
            window.close()
```

- [ ] **步骤 2：运行测试验证失败**

运行：

```powershell
python -m unittest -v tests.test_regressions.RegressionTests.test_property_param_change_rebuilds_probe_and_umec_pins
```

预期：失败，探针仍只有 `sense`，或 UMEC 改 `wtype2` 后仍保留 `X_N` / 连线。

- [ ] **步骤 3：在属性面板中增加通用重建 helper**

在 `ui/main_window.py` 的 `PropertyPanel` 类中新增方法：

```python
    def _remove_wires_with_invalid_pins(self, comp: ComponentInstance) -> int:
        valid_pins = {pin.name for pin in comp.pins}
        wires_to_remove = [
            wire_id for wire_id, wire in self.model.wires.items()
            if (
                wire.from_comp == comp.comp_id and wire.from_pin not in valid_pins
            ) or (
                wire.to_comp == comp.comp_id and wire.to_pin not in valid_pins
            )
        ]
        for wire_id in wires_to_remove:
            del self.model.wires[wire_id]
        return len(wires_to_remove)

    def _rebuild_component_pins(self, comp: ComponentInstance) -> int:
        probe_type = comp.params.get("probe_type") if comp.comp_type == ComponentType.PROBE else None
        pin_count = comp.params.get("n_phases", 3)
        if comp.comp_type == ComponentType.LCP_SINGLE_CABLE:
            pin_count = comp.params.get("n_cables", 1)
        elif comp.comp_type == ComponentType.LCP_OHL:
            from core.lcp_config import get_lcp_ohl_conductor_count
            pin_count = get_lcp_ohl_conductor_count(comp.params)
        comp.pins = create_component_pins(
            comp.comp_type,
            pin_count,
            probe_type=probe_type,
            params=comp.params,
        )
        return self._remove_wires_with_invalid_pins(comp)
```

- [ ] **步骤 4：使用 helper 处理 `probe_type`、`wtype1`、`wtype2`**

在 `PropertyPanel._on_param_changed()` 中，在 `n_cables` 分支之前加入：

```python
            elif param_name in ("probe_type", "wtype1", "wtype2"):
                comp = self.model.components[self._current_comp_id]
                self.model._save_undo_state()
                comp.params[param_name] = value
                self._rebuild_component_pins(comp)
                self.model._notify("params_updated")
```

将现有 `n_phases` 和 `n_cables` 分支中重复的重建/删线逻辑改为调用 `_rebuild_component_pins(comp)`。

- [ ] **步骤 5：UMEC 参数对话框接受后重建引脚**

在 `PropertyPanel._open_umec_config()` 的 `comp.params.update(config)` 后加入：

```python
            self._rebuild_component_pins(comp)
```

确保 `self.model._notify("params_updated")` 仍在最后执行。

- [ ] **步骤 6：运行测试验证通过**

运行：

```powershell
python -m unittest -v tests.test_regressions.RegressionTests.test_property_param_change_rebuilds_probe_and_umec_pins
```

预期：通过。

- [ ] **步骤 7：运行相关回归测试**

运行：

```powershell
python -m unittest -v tests.test_gui_smoke tests.test_regressions
```

预期：通过。

- [ ] **步骤 8：Commit**

如果仓库已初始化 git：

```bash
git add ui/main_window.py tests/test_regressions.py
git commit -m "fix: rebuild pins after probe and UMEC type changes"
```

---

### 任务 3：创建符号绘制模块骨架并接入画布

**文件：**
- 创建：`ui/symbols/__init__.py`
- 创建：`ui/symbols/style.py`
- 创建：`ui/symbols/primitive_symbols.py`
- 修改：`ui/circuit_canvas.py`
- 测试：`tests/test_symbol_rendering.py`

- [ ] **步骤 1：编写失败的基础渲染测试**

创建 `tests/test_symbol_rendering.py`：

```python
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage, QPainter, QColor
from PySide6.QtWidgets import QApplication

from models.circuit_model import CircuitModel, ComponentInstance, ComponentType
from models.component_lib import create_component_pins, get_default_params
from ui.circuit_canvas import ComponentGraphicsItem


def get_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def render_component(comp):
    get_app()
    image = QImage(180, 150, QImage.Format.Format_ARGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.translate(90, 70)
    item = ComponentGraphicsItem(comp, CircuitModel())
    item.paint(painter, None, None)
    painter.end()
    return image


def non_white_pixels(image):
    count = 0
    for x in range(image.width()):
        for y in range(image.height()):
            if image.pixelColor(x, y) != QColor("white"):
                count += 1
    return count


class SymbolRenderingTests(unittest.TestCase):
    def test_resistor_symbol_renders_nonblank(self):
        comp = ComponentInstance(
            comp_id="R_001",
            comp_type=ComponentType.RESISTOR,
            name="R1",
            x=0,
            y=0,
            params=get_default_params(ComponentType.RESISTOR),
            pins=create_component_pins(ComponentType.RESISTOR),
        )

        image = render_component(comp)

        self.assertGreater(non_white_pixels(image), 120)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **步骤 2：运行测试验证当前基线**

运行：

```powershell
python -m unittest -v tests.test_symbol_rendering.SymbolRenderingTests.test_resistor_symbol_renders_nonblank
```

预期：通过。这个测试建立渲染工具基线，不要求失败。

- [ ] **步骤 3：创建 `ui/symbols/style.py`**

写入：

```python
from PySide6.QtGui import QColor, QFont, QPen, QBrush


INK = QColor("#111827")
MUTED = QColor("#475569")
MEASURE_BLUE = QColor("#0000d4")
SELECTED = QColor("#f59e0b")


def line_pen(width: float = 2.0) -> QPen:
    pen = QPen(INK, width)
    pen.setCosmetic(True)
    return pen


def thin_pen() -> QPen:
    return line_pen(1.2)


def measure_pen(width: float = 2.0) -> QPen:
    pen = QPen(MEASURE_BLUE, width)
    pen.setCosmetic(True)
    return pen


def no_brush() -> QBrush:
    return QBrush(Qt.NoBrush)
```

如果 `Qt` 未导入，加入：

```python
from PySide6.QtCore import Qt
```

- [ ] **步骤 4：创建 `ui/symbols/primitive_symbols.py`**

先迁移电阻绘制：

```python
from PySide6.QtCore import QPointF


def draw_resistor(painter):
    painter.drawLine(-30, 0, -15, 0)
    points = [
        QPointF(-15, 0), QPointF(-12, -8), QPointF(-6, 8),
        QPointF(0, -8), QPointF(6, 8), QPointF(12, -8), QPointF(15, 0),
    ]
    for i in range(len(points) - 1):
        painter.drawLine(points[i], points[i + 1])
    painter.drawLine(15, 0, 30, 0)
```

- [ ] **步骤 5：创建 `ui/symbols/__init__.py` 并接入入口**

写入：

```python
from models.circuit_model import ComponentType
from ui.symbols.primitive_symbols import draw_resistor


def draw_component_symbol(painter, component):
    if component.comp_type == ComponentType.RESISTOR:
        draw_resistor(painter)
        return True
    return False
```

- [ ] **步骤 6：在 `ComponentGraphicsItem.paint()` 中接入模块入口**

在 `ui/circuit_canvas.py` 顶部加入：

```python
from ui.symbols import draw_component_symbol
```

在 `paint()` 中 `ct = self.component.comp_type` 后加入：

```python
        if draw_component_symbol(painter, self.component):
            pass
        elif ct == ComponentType.RESISTOR:
            self._draw_resistor(painter)
```

并删除原来的第一段 `if ct == ComponentType.RESISTOR:`，避免电阻重复绘制。保留其他旧 `_draw_*` 分支作为过渡。

- [ ] **步骤 7：运行测试验证通过**

运行：

```powershell
python -m unittest -v tests.test_symbol_rendering.SymbolRenderingTests.test_resistor_symbol_renders_nonblank
```

预期：通过。

- [ ] **步骤 8：运行全量测试**

运行：

```powershell
python -m unittest discover -v
```

预期：通过。

- [ ] **步骤 9：Commit**

如果仓库已初始化 git：

```bash
git add ui/circuit_canvas.py ui/symbols tests/test_symbol_rendering.py
git commit -m "refactor: introduce symbol rendering module"
```

---

### 任务 4：实现基础二端口和源类 PSCAD 风格线稿

**文件：**
- 修改：`ui/symbols/primitive_symbols.py`
- 修改：`ui/symbols/__init__.py`
- 修改：`ui/circuit_canvas.py`
- 测试：`tests/test_symbol_rendering.py`

- [ ] **步骤 1：编写基础元件渲染差异测试**

在 `tests/test_symbol_rendering.py` 中加入：

```python
    def test_core_primitive_symbols_render_distinct_shapes(self):
        rendered = {}
        for comp_type in (
            ComponentType.RESISTOR,
            ComponentType.INDUCTOR,
            ComponentType.CAPACITOR,
            ComponentType.VOLTAGE_SOURCE,
            ComponentType.CURRENT_SOURCE,
            ComponentType.SWITCH,
            ComponentType.MOA,
            ComponentType.LPM,
            ComponentType.SERIES_RL,
        ):
            comp = ComponentInstance(
                comp_id=f"{comp_type.value}_001",
                comp_type=comp_type,
                name=comp_type.value,
                x=0,
                y=0,
                params=get_default_params(comp_type),
                pins=create_component_pins(comp_type),
            )
            image = render_component(comp)
            self.assertGreater(non_white_pixels(image), 100, comp_type)
            rendered[comp_type] = image

        self.assertNotEqual(rendered[ComponentType.RESISTOR], rendered[ComponentType.INDUCTOR])
        self.assertNotEqual(rendered[ComponentType.VOLTAGE_SOURCE], rendered[ComponentType.CURRENT_SOURCE])
```

- [ ] **步骤 2：运行测试验证当前状态**

运行：

```powershell
python -m unittest -v tests.test_symbol_rendering.SymbolRenderingTests.test_core_primitive_symbols_render_distinct_shapes
```

预期：当前实现可能通过，因为旧符号也能渲染出不同图形；无论结果如何，保留该测试作为防回归测试，并继续执行后续 PSCAD 线稿替换步骤。

- [ ] **步骤 3：迁移基础符号绘制函数**

在 `ui/symbols/primitive_symbols.py` 中加入以下函数，使用黑白线稿：

```python
def draw_inductor(painter):
    painter.drawLine(-30, 0, -15, 0)
    for i in range(4):
        x = -14 + i * 8
        painter.drawArc(int(x), -8, 10, 16, 0, 180 * 16)
    painter.drawLine(18, 0, 30, 0)


def draw_capacitor(painter):
    painter.drawLine(-30, 0, -5, 0)
    painter.drawLine(-5, -13, -5, 13)
    painter.drawLine(5, -13, 5, 13)
    painter.drawLine(5, 0, 30, 0)


def draw_voltage_source(painter):
    painter.drawLine(-30, 0, -12, 0)
    painter.drawEllipse(-12, -12, 24, 24)
    painter.drawLine(0, -6, 0, 6)
    painter.drawLine(-6, 0, 6, 0)
    painter.drawLine(12, 0, 30, 0)
    painter.drawText(QPointF(-22, -9), "+")
    painter.drawText(QPointF(17, -9), "-")


def draw_current_source(painter):
    painter.drawLine(-30, 0, -12, 0)
    painter.drawEllipse(-12, -12, 24, 24)
    painter.drawLine(0, 8, 0, -8)
    painter.drawLine(0, -8, -5, -2)
    painter.drawLine(0, -8, 5, -2)
    painter.drawLine(12, 0, 30, 0)
```

继续加入 `draw_switch`、`draw_moa`、`draw_lpm`、`draw_series_rl`，可先从 `ui/circuit_canvas.py` 迁移旧逻辑并统一黑色画笔。

- [ ] **步骤 4：更新 `draw_component_symbol()` 分派**

在 `ui/symbols/__init__.py` 中导入并分派：

```python
from ui.symbols.primitive_symbols import (
    draw_capacitor,
    draw_current_source,
    draw_inductor,
    draw_lpm,
    draw_moa,
    draw_resistor,
    draw_series_rl,
    draw_switch,
    draw_voltage_source,
)

PRIMITIVE_DRAWERS = {
    ComponentType.RESISTOR: draw_resistor,
    ComponentType.INDUCTOR: draw_inductor,
    ComponentType.CAPACITOR: draw_capacitor,
    ComponentType.SERIES_RL: draw_series_rl,
    ComponentType.SWITCH: draw_switch,
    ComponentType.MOA: draw_moa,
    ComponentType.LPM: draw_lpm,
    ComponentType.VOLTAGE_SOURCE: draw_voltage_source,
    ComponentType.CURRENT_SOURCE: draw_current_source,
}
```

在入口中：

```python
    drawer = PRIMITIVE_DRAWERS.get(component.comp_type)
    if drawer:
        drawer(painter)
        return True
```

- [ ] **步骤 5：从 `paint()` 删除已迁移旧分支**

删除或绕开 `ComponentGraphicsItem.paint()` 中基础元件对应的旧 `_draw_*` 分支，确保新模块负责绘制。

- [ ] **步骤 6：运行测试验证通过**

运行：

```powershell
python -m unittest -v tests.test_symbol_rendering.SymbolRenderingTests.test_core_primitive_symbols_render_distinct_shapes
```

预期：通过。

- [ ] **步骤 7：运行全量测试**

运行：

```powershell
python -m unittest discover -v
```

预期：通过。

- [ ] **步骤 8：Commit**

如果仓库已初始化 git：

```bash
git add ui/circuit_canvas.py ui/symbols tests/test_symbol_rendering.py
git commit -m "feat: render primitive symbols in PSCAD line style"
```

---

### 任务 5：实现三种 PSCAD 式探针符号

**文件：**
- 创建：`ui/symbols/probe_symbols.py`
- 修改：`ui/symbols/__init__.py`
- 修改：`ui/circuit_canvas.py`
- 测试：`tests/test_symbol_rendering.py`

- [ ] **步骤 1：编写探针符号差异测试**

在 `tests/test_symbol_rendering.py` 中加入：

```python
    def test_probe_symbols_render_distinct_pscad_measurement_shapes(self):
        images = {}
        for probe_type in ("voltage_ground", "voltage_between", "branch_current"):
            comp = ComponentInstance(
                comp_id=f"PRB_{probe_type}",
                comp_type=ComponentType.PROBE,
                name={"voltage_ground": "Ea_2", "voltage_between": "Ea_1", "branch_current": "Ia_1"}[probe_type],
                x=0,
                y=0,
                params={"probe_type": probe_type, "unit": "kV"},
                pins=create_component_pins(ComponentType.PROBE, probe_type=probe_type),
            )
            image = render_component(comp)
            self.assertGreater(non_white_pixels(image), 80, probe_type)
            images[probe_type] = image

        self.assertNotEqual(images["voltage_ground"], images["voltage_between"])
        self.assertNotEqual(images["voltage_between"], images["branch_current"])
```

- [ ] **步骤 2：运行测试验证当前状态**

运行：

```powershell
python -m unittest -v tests.test_symbol_rendering.SymbolRenderingTests.test_probe_symbols_render_distinct_pscad_measurement_shapes
```

预期：失败或只弱通过。若通过，继续实现 PSCAD 测量箭头风格，并保留测试防回归。

- [ ] **步骤 3：创建探针绘制函数**

创建 `ui/symbols/probe_symbols.py`：

```python
from PySide6.QtCore import QPointF
from PySide6.QtGui import QFont, QPen

from ui.symbols.style import MEASURE_BLUE, measure_pen


def _draw_arrow_up(painter, x=0, y_top=-18, y_bottom=18):
    painter.drawLine(x, y_bottom, x, y_top)
    painter.drawLine(x, y_top, x - 7, y_top + 8)
    painter.drawLine(x, y_top, x + 7, y_top + 8)


def _draw_ground(painter, x=0, y=24):
    painter.drawLine(x - 12, y, x + 12, y)
    painter.drawLine(x - 8, y + 5, x + 8, y + 5)
    painter.drawLine(x - 4, y + 10, x + 4, y + 10)


def _draw_label(painter, text, x=-18, y=0):
    old_font = painter.font()
    font = QFont("Arial", 10)
    painter.setFont(font)
    painter.drawText(QPointF(x, y), text)
    painter.setFont(old_font)


def draw_probe(painter, component):
    probe_type = component.params.get("probe_type", "voltage_ground")
    label = component.name or {
        "voltage_ground": "Vg",
        "voltage_between": "V",
        "branch_current": "I",
    }.get(probe_type, "V")

    old_pen = painter.pen()
    painter.setPen(measure_pen())

    if probe_type == "branch_current":
        painter.drawLine(-28, -3, 28, -3)
        painter.drawLine(-14, 10, 18, 10)
        painter.drawLine(18, 10, 8, 5)
        painter.drawLine(18, 10, 8, 15)
        _draw_label(painter, label, -16, -12)
    elif probe_type == "voltage_between":
        _draw_arrow_up(painter, 0, -22, 18)
        _draw_label(painter, label, -16, 34)
    else:
        _draw_arrow_up(painter, 0, -22, 14)
        _draw_label(painter, label, -16, 30)
        _draw_ground(painter, 0, 38)

    painter.setPen(old_pen)
```

- [ ] **步骤 4：接入 `draw_component_symbol()`**

在 `ui/symbols/__init__.py` 中加入：

```python
from ui.symbols.probe_symbols import draw_probe
```

在入口分派中加入：

```python
    if component.comp_type == ComponentType.PROBE:
        draw_probe(painter, component)
        return True
```

- [ ] **步骤 5：调整探针 bounding rect**

在 `ComponentGraphicsItem.__init__()` 中对探针设置更适合的边界：

```python
        elif component.comp_type == ComponentType.PROBE:
            self._bounding_rect = QRectF(-45, -45, 90, 95)
```

- [ ] **步骤 6：运行探针测试验证通过**

运行：

```powershell
python -m unittest -v tests.test_symbol_rendering.SymbolRenderingTests.test_probe_symbols_render_distinct_pscad_measurement_shapes
```

预期：通过。

- [ ] **步骤 7：运行 GUI smoke 和全量测试**

运行：

```powershell
python -m unittest -v tests.test_gui_smoke.GuiSmokeTests.test_palette_has_pscad_style_probe_buttons
python -m unittest discover -v
```

预期：通过。

- [ ] **步骤 8：Commit**

如果仓库已初始化 git：

```bash
git add ui/circuit_canvas.py ui/symbols tests/test_symbol_rendering.py
git commit -m "feat: render PSCAD-style measurement probes"
```

---

### 任务 6：实现 UMEC PSCAD 风格动态符号

**文件：**
- 创建：`ui/symbols/umec_symbols.py`
- 修改：`ui/symbols/__init__.py`
- 修改：`ui/circuit_canvas.py`
- 测试：`tests/test_symbol_rendering.py`

- [ ] **步骤 1：编写 UMEC 接法渲染差异测试**

在 `tests/test_symbol_rendering.py` 中加入：

```python
    def test_umec_symbol_changes_with_winding_types(self):
        def make_umec(wtype1, wtype2):
            params = get_default_params(ComponentType.UMEC_TRANSFORMER) | {
                "S_mva": 16.85,
                "V1_kV": 1.14,
                "V2_kV": 69.0,
                "wtype1": wtype1,
                "wtype2": wtype2,
            }
            return ComponentInstance(
                comp_id=f"UMEC_{wtype1}_{wtype2}",
                comp_type=ComponentType.UMEC_TRANSFORMER,
                name="umec",
                x=0,
                y=0,
                params=params,
                pins=create_component_pins(ComponentType.UMEC_TRANSFORMER, params=params),
            )

        yg_delta = render_component(make_umec("Y_gnd", "Delta"))
        y_y = render_component(make_umec("Y", "Y"))
        delta_delta = render_component(make_umec("Delta", "Delta"))

        self.assertGreater(non_white_pixels(yg_delta), 180)
        self.assertNotEqual(yg_delta, y_y)
        self.assertNotEqual(y_y, delta_delta)
```

- [ ] **步骤 2：运行测试验证当前状态**

运行：

```powershell
python -m unittest -v tests.test_symbol_rendering.SymbolRenderingTests.test_umec_symbol_changes_with_winding_types
```

预期：失败或弱通过。若弱通过，继续实现 PSCAD 风格，并保留测试。

- [ ] **步骤 3：创建 UMEC 绘制模块**

创建 `ui/symbols/umec_symbols.py`：

```python
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QFont


def _draw_text(painter, text, x, y, size=9):
    old_font = painter.font()
    font = QFont("Arial", size)
    painter.setFont(font)
    painter.drawText(QPointF(x, y), text)
    painter.setFont(old_font)


def _draw_wye(painter, cx, cy):
    painter.drawLine(cx, cy, cx - 22, cy - 14)
    painter.drawLine(cx, cy, cx + 22, cy - 14)
    painter.drawLine(cx, cy, cx, cy + 24)


def _draw_delta(painter, cx, cy):
    painter.drawLine(cx, cy - 28, cx - 28, cy + 24)
    painter.drawLine(cx - 28, cy + 24, cx + 28, cy + 24)
    painter.drawLine(cx + 28, cy + 24, cx, cy - 28)


def _draw_bottom_terminal(painter, x):
    painter.drawLine(x, 52, x, 82)


def draw_umec(painter, component):
    p = component.params
    wtype1 = p.get("wtype1", "Y_gnd")
    wtype2 = p.get("wtype2", "Delta")
    s_mva = p.get("S_mva", 100.0)
    v1 = p.get("V1_kV", 220.0)
    v2 = p.get("V2_kV", 110.0)

    painter.drawRect(QRectF(-60, -55, 120, 110))
    _draw_text(painter, "umec", -56, -38, 11)
    _draw_text(painter, f"{s_mva:g} [MVA]", -24, -20, 10)

    for y, label in [(-32, "A"), (0, "B"), (32, "C")]:
        painter.drawLine(-78, y, -60, y)
        painter.drawLine(60, y, 78, y)
        _draw_text(painter, label, -92, y + 5, 10)
        _draw_text(painter, label, 82, y + 5, 10)

    _draw_text(painter, "#1", -52, 8, 10)
    _draw_text(painter, "#2", 32, 8, 10)

    if wtype1 == "Delta":
        _draw_delta(painter, -26, 9)
    else:
        _draw_wye(painter, -26, 5)
        _draw_bottom_terminal(painter, -40)

    if wtype2 == "Delta":
        _draw_delta(painter, 28, 9)
    else:
        _draw_wye(painter, 28, 5)
        _draw_bottom_terminal(painter, 40)

    _draw_text(painter, f"{v1:g} [kV]", -52, 38, 9)
    _draw_text(painter, f"{v2:g} [kV]", 10, 50, 9)
```

- [ ] **步骤 4：接入 `draw_component_symbol()`**

在 `ui/symbols/__init__.py` 中加入：

```python
from ui.symbols.umec_symbols import draw_umec
```

在入口分派中加入：

```python
    if component.comp_type == ComponentType.UMEC_TRANSFORMER:
        draw_umec(painter, component)
        return True
```

- [ ] **步骤 5：调整 UMEC bounding rect 和标签策略**

在 `ComponentGraphicsItem.__init__()` 中将 UMEC 边界改为：

```python
        elif component.comp_type == ComponentType.UMEC_TRANSFORMER:
            self._bounding_rect = QRectF(-100, -70, 200, 160)
```

在 `paint()` 的通用标签绘制前加条件，避免 UMEC 外部再画重复名称：

```python
        if ct != ComponentType.UMEC_TRANSFORMER:
            painter.setPen(QColor("#1e2a3a"))
            font = QFont("Arial", 9)
            painter.setFont(font)
            painter.drawText(QPointF(-15, 35), self.component.name)
```

- [ ] **步骤 6：运行 UMEC 测试验证通过**

运行：

```powershell
python -m unittest -v tests.test_symbol_rendering.SymbolRenderingTests.test_umec_symbol_changes_with_winding_types
```

预期：通过。

- [ ] **步骤 7：运行 UMEC 动态引脚相关测试**

运行：

```powershell
python -m unittest -v tests.test_regressions.RegressionTests.test_umec_pins_follow_winding_types
python -m unittest -v tests.test_regressions.RegressionTests.test_property_param_change_rebuilds_probe_and_umec_pins
```

预期：通过。

- [ ] **步骤 8：Commit**

如果仓库已初始化 git：

```bash
git add ui/circuit_canvas.py ui/symbols tests/test_symbol_rendering.py
git commit -m "feat: render PSCAD-style UMEC transformer symbol"
```

---

### 任务 7：实现线路、电缆和子电路工程块符号

**文件：**
- 创建：`ui/symbols/line_symbols.py`
- 修改：`ui/symbols/primitive_symbols.py`
- 修改：`ui/symbols/__init__.py`
- 修改：`ui/circuit_canvas.py`
- 测试：`tests/test_symbol_rendering.py`

- [ ] **步骤 1：编写线路/电缆渲染测试**

在 `tests/test_symbol_rendering.py` 中加入：

```python
    def test_line_and_block_symbols_render_nonblank(self):
        cases = [
            (ComponentType.BERGERON, {}),
            (ComponentType.ULM, {"n_phases": 3}),
            (ComponentType.LCP_OHL, {"n_phases": 3, "n_gw": 1}),
            (ComponentType.LCP_SINGLE_CABLE, {"n_cables": 2}),
            (ComponentType.LCP_THREE_CABLE, {}),
            (ComponentType.SUBCIRCUIT, {"subcircuit_name": "SUB1"}),
        ]
        for comp_type, overrides in cases:
            params = get_default_params(comp_type) | overrides
            pin_count = params.get("n_phases", params.get("n_cables", 3))
            comp = ComponentInstance(
                comp_id=f"{comp_type.value}_001",
                comp_type=comp_type,
                name=comp_type.value,
                x=0,
                y=0,
                params=params,
                pins=create_component_pins(comp_type, pin_count, params=params),
            )
            image = render_component(comp)
            self.assertGreater(non_white_pixels(image), 120, comp_type)
```

- [ ] **步骤 2：运行测试验证当前状态**

运行：

```powershell
python -m unittest -v tests.test_symbol_rendering.SymbolRenderingTests.test_line_and_block_symbols_render_nonblank
```

预期：通过或失败。若失败，记录具体失败元件并继续实现。

- [ ] **步骤 3：创建线路工程块绘制模块**

创建 `ui/symbols/line_symbols.py`：

```python
from PySide6.QtCore import QRectF, QPointF


def _draw_block_label(painter, text, x=-20, y=-30):
    painter.drawText(QPointF(x, y), text)


def draw_bergeron(painter, component):
    painter.drawRect(QRectF(-45, -18, 90, 36))
    painter.drawLine(-45, -6, 45, -6)
    painter.drawLine(-45, 6, 45, 6)
    painter.drawText(QPointF(-18, -24), "Berg")


def draw_ulm(painter, component):
    n = int(component.params.get("n_phases", 3) or 1)
    painter.drawRect(QRectF(-45, -28, 90, 56))
    spacing = 14
    start = -(n - 1) * spacing / 2
    for i in range(n):
        y = start + i * spacing
        painter.drawLine(-45, int(y), 45, int(y))
    painter.drawText(QPointF(-18, -34), f"ULM {n}ph")


def draw_lcp_ohl(painter, component):
    n = len([p for p in component.pins if p.name.startswith("nk")])
    n = max(1, n)
    painter.drawRect(QRectF(-48, -30, 96, 60))
    spacing = 12
    start = -(min(n, 5) - 1) * spacing / 2
    for i in range(min(n, 5)):
        y = start + i * spacing
        painter.drawLine(-48, int(y), 48, int(y))
    painter.drawText(QPointF(-24, -36), "LCP-OHL")


def draw_lcp_cable(painter, component, label):
    n = len([p for p in component.pins if p.name.startswith("nk")])
    n = max(1, min(n, 7))
    painter.drawRect(QRectF(-50, -32, 100, 64))
    spacing = 10
    start = -(n - 1) * spacing / 2
    for i in range(n):
        y = start + i * spacing
        painter.drawEllipse(-34, int(y) - 4, 8, 8)
        painter.drawLine(-22, int(y), 36, int(y))
    painter.drawText(QPointF(-24, -38), f"LCP-{label}")
```

- [ ] **步骤 4：接入线路分派**

在 `ui/symbols/__init__.py` 中加入：

```python
from ui.symbols.line_symbols import (
    draw_bergeron,
    draw_lcp_cable,
    draw_lcp_ohl,
    draw_ulm,
)
```

在入口中加入：

```python
    if component.comp_type == ComponentType.BERGERON:
        draw_bergeron(painter, component)
        return True
    if component.comp_type == ComponentType.ULM:
        draw_ulm(painter, component)
        return True
    if component.comp_type == ComponentType.LCP_OHL:
        draw_lcp_ohl(painter, component)
        return True
    if component.comp_type == ComponentType.LCP_SINGLE_CABLE:
        draw_lcp_cable(painter, component, "SC")
        return True
    if component.comp_type == ComponentType.LCP_THREE_CABLE:
        draw_lcp_cable(painter, component, "3C")
        return True
```

- [ ] **步骤 5：更新子电路符号为黑白工程块**

在 `ui/symbols/primitive_symbols.py` 中加入：

```python
from PySide6.QtCore import Qt, QRectF


def draw_subcircuit(painter, component):
    rect = QRectF(-45, -28, 90, 56)
    painter.drawRect(rect)
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, component.name)
```

在 `ui/symbols/__init__.py` 中接入：

```python
    if component.comp_type == ComponentType.SUBCIRCUIT:
        draw_subcircuit(painter, component)
        return True
```

- [ ] **步骤 6：调整复杂块 bounding rect**

在 `ComponentGraphicsItem.__init__()` 中对线路和 LCP 设置：

```python
        elif component.comp_type in (
            ComponentType.BERGERON,
            ComponentType.ULM,
            ComponentType.LCP_OHL,
            ComponentType.LCP_SINGLE_CABLE,
            ComponentType.LCP_THREE_CABLE,
        ):
            self._bounding_rect = QRectF(-65, -50, 130, 100)
```

- [ ] **步骤 7：运行测试验证通过**

运行：

```powershell
python -m unittest -v tests.test_symbol_rendering.SymbolRenderingTests.test_line_and_block_symbols_render_nonblank
```

预期：通过。

- [ ] **步骤 8：运行全量测试**

运行：

```powershell
python -m unittest discover -v
```

预期：通过。

- [ ] **步骤 9：Commit**

如果仓库已初始化 git：

```bash
git add ui/circuit_canvas.py ui/symbols tests/test_symbol_rendering.py
git commit -m "feat: render line and cable symbols as engineering blocks"
```

---

### 任务 8：最终视觉核验和文档同步

**文件：**
- 修改：`md/EMTP_GUI代码审查报告.md`
- 修改：`docs/superpowers/specs/2026-05-15-pscad-hybrid-symbol-design.md`，仅当实现偏离设计时修改
- 测试：`tests/test_symbol_rendering.py`、`tests/test_gui_smoke.py`、`tests/test_regressions.py`

- [ ] **步骤 1：运行全量自动测试**

运行：

```powershell
python -m unittest discover -v
```

预期：所有测试通过。

- [ ] **步骤 2：运行 GUI 手动视觉核验**

运行：

```powershell
python main.py
```

在 GUI 中检查：

- 左侧放置 R/L/C/电压源/电流源，符号为黑白工程线稿。
- 放置三种探针，符号分别为水平 I 箭头、双端 V 箭头、对地 Vg 箭头。
- 放置 UMEC，修改 `wtype1` / `wtype2`，底部端点和内部 Y/Delta 图随参数变化。
- 放置 ULM/LCP，确认工程块端口不遮挡标签。

预期：无异常弹窗，画布不出现空白元件，连线端口可点击。

- [ ] **步骤 3：更新审查报告中的符号状态**

在 `md/EMTP_GUI代码审查报告.md` 中加入当前实现状态：

```markdown
### 符号风格

第一阶段 PSCAD Hybrid 符号已接入：基础元件改为黑白工程线稿，三种探针使用 PSCAD 式测量箭头，UMEC 根据 `wtype1` / `wtype2` 动态显示 Y/Delta 绕组和底部端点，线路/电缆使用工程块。
```

- [ ] **步骤 4：如果实现偏离设计，更新设计文档**

仅当代码实现为了兼容现有系统调整了文件名、helper 名称或测试策略时，更新：

```powershell
notepad docs\superpowers\specs\2026-05-15-pscad-hybrid-symbol-design.md
```

不要改动已经满足的设计内容。

- [ ] **步骤 5：最终验证**

运行：

```powershell
python -m unittest discover -v
```

预期：所有测试通过。

- [ ] **步骤 6：Commit**

如果仓库已初始化 git：

```bash
git add md/EMTP_GUI代码审查报告.md docs/superpowers/specs/2026-05-15-pscad-hybrid-symbol-design.md tests ui models
git commit -m "docs: record PSCAD hybrid symbol implementation status"
```

---

## 自检清单

- 规格覆盖：计划覆盖基础元件、源、探针、线路/电缆、UMEC、子电路、动态引脚、测试和最终验证。
- 类型一致性：统一使用 `create_component_pins(..., params=...)`、`probe_type`、`wtype1`、`wtype2`、`H_N`、`X_N`。
- TDD 顺序：行为变化任务都先写测试，再实现。
- 依赖控制：不引入新第三方库；继续使用 PySide6。
- Git 说明：当前目录未检测到 `.git`，计划保留 commit 步骤，但执行时仅在仓库初始化 git 后运行。
