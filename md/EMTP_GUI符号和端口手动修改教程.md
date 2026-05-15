# EMTP GUI 符号和端口手动修改教程

本文说明如何手动修改当前 GUI 里的元件符号、端口位置、动态端口规则和画布显示尺寸。适用于当前 PSCAD Hybrid 符号实现。

## 一、先看整体结构

当前符号和端口分成三层：

1. 端口数据层：`models/component_lib.py`

   这里决定每类元件有哪些端口、端口名是什么、端口相对元件中心的位置在哪里。

2. 符号绘制层：`ui/symbols/`

   这里决定元件在画布上长什么样。每个绘制函数只负责画图，不应该修改模型、参数或端口。

3. 画布外壳层：`ui/circuit_canvas.py`

   这里决定元件外接矩形大小、选中状态、通用名称标签和蓝色端口圆点。

最常见的修改路径是：

- 只改符号形状：改 `ui/symbols/*.py`。
- 只改端口数量或位置：改 `models/component_lib.py`。
- 符号变大或端口被裁剪：改 `ui/circuit_canvas.py` 里的 `_bounding_rect`。
- 新增元件类型：同时改 `models/circuit_model.py`、`models/component_lib.py`、`ui/symbols/` 和左侧元件库。

## 二、坐标系统怎么理解

所有符号和端口都使用元件中心作为原点：

```text
          y 负方向
             ^
             |
 x 负 <------0------> x 正
             |
             v
          y 正方向
```

例如：

```python
{"name": "nf", "local_x": -30, "local_y": 0}
{"name": "nt", "local_x": 30, "local_y": 0}
```

表示左端口在元件中心左侧 30，右端口在元件中心右侧 30。

画符号时也使用同一个坐标。比如电阻：

```python
painter.drawLine(-30, 0, -15, 0)
...
painter.drawLine(15, 0, 30, 0)
```

这两段线刚好接到 `nf` 和 `nt` 的端口位置。

## 三、修改普通二端口元件端口

普通 R/L/C/Switch/SeriesRL 等默认使用 `PINS["two_port"]`。

位置：`models/component_lib.py`

```python
PINS = {
    "two_port": [
        {"name": "nf", "local_x": -30, "local_y": 0},
        {"name": "nt", "local_x": 30, "local_y": 0},
    ],
}
```

如果你想把普通二端口拉宽，可以改成：

```python
{"name": "nf", "local_x": -40, "local_y": 0}
{"name": "nt", "local_x": 40, "local_y": 0}
```

同时要去对应符号绘制函数里把线也拉到 `-40` / `40`，否则端口圆点会和符号线条脱开。

例如电阻在 `ui/symbols/primitive_symbols.py`：

```python
def draw_resistor(painter, component=None):
    painter.drawLine(-30, 0, -15, 0)
    ...
    painter.drawLine(15, 0, 30, 0)
```

如果端口改为 `-40` / `40`，这里也要跟着改到 `-40` / `40`。

## 四、修改三种探针端口

探针端口在 `models/component_lib.py`：

```python
"probe": [
    {"name": "sense", "local_x": 0, "local_y": -15},
],
"probe_between": [
    {"name": "sense", "local_x": -12, "local_y": -15},
    {"name": "ref", "local_x": 12, "local_y": -15},
],
```

规则在 `get_pins()` 里：

```python
elif comp_type == ComponentType.PROBE:
    if probe_type == "voltage_between":
        return PINS["probe_between"]
    return PINS["probe"]
```

含义：

- 对地电压探针：使用 `probe`，只有 `sense`。
- 电流探针：也使用 `probe`，只有 `sense`。
- 两节点电压探针：使用 `probe_between`，有 `sense` 和 `ref`。

如果你想让电流探针改成左右两个端口，需要新增一种 pin 表，例如：

```python
"probe_current": [
    {"name": "from", "local_x": -20, "local_y": 0},
    {"name": "to", "local_x": 20, "local_y": 0},
],
```

然后修改 `get_pins()`：

```python
elif comp_type == ComponentType.PROBE:
    if probe_type == "voltage_between":
        return PINS["probe_between"]
    if probe_type == "branch_current":
        return PINS["probe_current"]
    return PINS["probe"]
```

注意：这会影响求解器如何识别电流探针，改前要同步检查 `models/circuit_model.py` 里的 `get_auto_voltage_probes()`。

## 五、修改探针符号画法

探针符号在 `ui/symbols/probe_symbols.py`：

```python
def draw_probe(painter, component):
    probe_type = component.params.get("probe_type", "voltage_ground")
    ...
```

三种分支：

```python
if probe_type == "branch_current":
    ...
elif probe_type == "voltage_between":
    ...
else:
    ...
```

你可以这样调整：

- 改颜色：修改 `ui/symbols/style.py` 里的 `MEASURE_BLUE`。
- 改箭头长度：改 `_draw_arrow_up()` 的 `y_top` / `y_bottom`。
- 改标签位置：改 `draw_text(painter, label, x, y, size)` 的 `x` 和 `y`。
- 改接地符号位置：改 `draw_ground(painter, 0, 39)` 的第二个参数。

如果符号变大后被裁剪，改 `ui/circuit_canvas.py`：

```python
elif component.comp_type == ComponentType.PROBE:
    self._bounding_rect = QRectF(-45, -45, 90, 100)
```

`QRectF(left, top, width, height)` 控制画布认为这个元件占多大区域。

## 六、修改 UMEC 动态端口

UMEC 的动态端口在 `models/component_lib.py` 的 `get_umec_pins()`：

```python
def get_umec_pins(params=None):
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

    ...
```

当前规则：

- `H_A/H_B/H_C` 始终存在。
- `X_A/X_B/X_C` 始终存在。
- `H_N` 只在 `wtype1` 是 `Y` 或 `Y_gnd` 时存在。
- `X_N` 只在 `wtype2` 是 `Y` 或 `Y_gnd` 时存在。
- `Delta` 不显示中性端。

如果你想把 UMEC 三相端口间距调大，例如从 `-30/0/30` 改成 `-36/0/36`，需要同时改：

1. `get_umec_pins()` 里的 `local_y`。
2. `ui/symbols/umec_symbols.py` 里 `for y, label in [(-30, "A"), ...]`。
3. 必要时改 `ui/circuit_canvas.py` 里的 UMEC `_bounding_rect`。

## 七、修改 UMEC 符号画法

UMEC 画法在 `ui/symbols/umec_symbols.py`：

```python
def draw_umec(painter, component):
    params = component.params
    wtype1 = params.get("wtype1", "Y_gnd")
    wtype2 = params.get("wtype2", "Delta")
```

关键函数：

```python
def _draw_wye(painter, cx, cy):
    ...

def _draw_delta(painter, cx, cy):
    ...

def _draw_bottom_terminal(painter, x, grounded=False):
    ...
```

每侧绕组选择逻辑：

```python
if wtype1 == "Delta":
    _draw_delta(painter, -26, 6)
else:
    _draw_wye(painter, -26, 3)
    _draw_bottom_terminal(painter, -30, grounded=(wtype1 == "Y_gnd"))
```

如果你想让 `Y_gnd` 不画接地符号，只保留底部端点，改成：

```python
_draw_bottom_terminal(painter, -30, grounded=False)
```

如果你想让 Delta 三角更大，改 `_draw_delta()` 里的坐标，例如 `26` 改成 `32`。

如果你想让 UMEC 主体更宽，改：

```python
painter.drawRect(QRectF(-52, -55, 104, 110))
```

同时检查：

```python
ComponentGraphicsItem.__init__()
```

里的：

```python
self._bounding_rect = QRectF(-100, -75, 200, 160)
```

确保画布外框足够大。

## 八、修改线路和电缆符号

线路和电缆在 `ui/symbols/line_symbols.py`：

```python
def draw_bergeron(painter, component):
    ...

def draw_ulm(painter, component):
    ...

def draw_lcp_ohl(painter, component):
    ...

def draw_lcp_cable(painter, component, label):
    ...
```

常见修改：

- 改工程块大小：改 `_block(painter, QRectF(...))` 里的矩形。
- 改内部平行线数量：改 `min(n, 5)` 或 `min(n, 7)`。
- 改文字：改 `draw_text()` 的内容。
- 改电缆小圆圈大小：改 `painter.drawEllipse(-34, int(y) - 4, 8, 8)`。

线路/电缆端口仍由 `models/component_lib.py` 动态生成：

- `ULM` / `LCP_OHL`：根据相数生成 `nk_i` / `nm_i`。
- `LCP_SINGLE_CABLE`：每根电缆生成 `core/sheath/armor`。
- `LCP_THREE_CABLE`：生成 `core_a/core_b/core_c/sheath_a/sheath_b/sheath_c/pipe`。

## 九、修改符号入口映射

所有符号最终从 `ui/symbols/__init__.py` 分发：

```python
def draw_component_symbol(painter, component) -> bool:
    drawers = {
        ComponentType.RESISTOR: draw_resistor,
        ...
        ComponentType.UMEC_TRANSFORMER: draw_umec,
    }
```

如果新增了绘制函数，必须在这里接入。比如新增 `draw_my_device()`：

```python
from ui.symbols.primitive_symbols import draw_my_device

drawers = {
    ComponentType.MY_DEVICE: draw_my_device,
}
```

返回 `True` 表示新符号模块已经处理；返回 `False` 时，画布会走旧的 fallback 逻辑。

## 十、修改画布外接矩形

画布外接矩形在 `ui/circuit_canvas.py` 的 `ComponentGraphicsItem.__init__()`：

```python
if component.comp_type == ComponentType.SUBCIRCUIT:
    self._bounding_rect = QRectF(-50, -35, 100, 70)
elif component.comp_type == ComponentType.UMEC_TRANSFORMER:
    self._bounding_rect = QRectF(-100, -75, 200, 160)
elif component.comp_type == ComponentType.PROBE:
    self._bounding_rect = QRectF(-45, -45, 90, 100)
...
```

什么时候要改它：

- 符号被裁剪。
- 端口圆点点不到。
- 选中框太小。
- 文字标签超出元件区域。

一般原则：

- 符号最大 x 坐标是 `+60`，外接矩形右边至少要大于 `60`。
- 符号最小 x 坐标是 `-60`，外接矩形左边至少要小于 `-60`。
- UMEC 这种有底部端点和接地符号的元件，要给底部多留空间。

## 十一、修改参数变化后的端口重建

属性面板里参数变化后重建端口的位置在 `ui/main_window.py`：

```python
if param_name in {"n_phases", "n_cables", "probe_type", "wtype1", "wtype2"}:
    self.model._save_undo_state()
    comp.params[param_name] = value
    self._rebuild_component_pins(comp)
    self.model._notify("params_updated")
```

真正重建在：

```python
def _rebuild_component_pins(self, comp):
    ...
    comp.pins = create_component_pins(
        comp.comp_type,
        pin_count,
        probe_type=probe_type,
        params=comp.params,
    )
    return self._remove_wires_with_invalid_pins(comp)
```

如果你新增了某个会影响端口的参数，例如 `terminal_layout`，需要把它加进集合：

```python
{"n_phases", "n_cables", "probe_type", "wtype1", "wtype2", "terminal_layout"}
```

否则用户在属性面板里改了参数，端口不会马上变化。

## 十二、改完后如何验证

每次改完符号或端口，建议至少运行：

```powershell
python -m unittest -v tests.test_symbol_rendering
python -m unittest -v tests.test_regressions
python -m unittest discover -v
```

如果只改了 UMEC 端口，重点跑：

```powershell
python -m unittest -v tests.test_regressions.RegressionTests.test_umec_pins_follow_winding_types
python -m unittest -v tests.test_regressions.RegressionTests.test_property_param_change_rebuilds_probe_and_umec_pins
```

如果只改了符号绘制，重点跑：

```powershell
python -m unittest -v tests.test_symbol_rendering
```

最后手动启动 GUI：

```powershell
python main.py
```

在 GUI 里检查：

- 放置元件后符号是否非空。
- 端口圆点是否贴合符号线条。
- 连线是否能吸附到端口。
- 改 UMEC `wtype1/wtype2` 后底部端点是否增删。
- 改探针 `probe_type` 后 `sense/ref` 是否按预期出现。

## 十三、常见修改案例

### 案例 1：把电阻画得更长

1. 修改 `models/component_lib.py` 中 `PINS["two_port"]` 的 x 坐标。
2. 修改 `ui/symbols/primitive_symbols.py` 中 `draw_resistor()` 的左右端线。
3. 如果超过默认外框，修改 `ui/circuit_canvas.py` 的默认 `_bounding_rect`。
4. 跑 `tests.test_symbol_rendering`。

### 案例 2：让 UMEC 的 Y_gnd 只显示端点不显示接地

1. 打开 `ui/symbols/umec_symbols.py`。
2. 找到：

   ```python
   _draw_bottom_terminal(painter, -30, grounded=(wtype1 == "Y_gnd"))
   ```

3. 改成：

   ```python
   _draw_bottom_terminal(painter, -30, grounded=False)
   ```

4. 右侧 #2 同理。
5. 跑 `tests.test_symbol_rendering`。

### 案例 3：让两节点电压探针端口更分开

1. 修改 `models/component_lib.py`：

   ```python
   {"name": "sense", "local_x": -18, "local_y": -15}
   {"name": "ref", "local_x": 18, "local_y": -15}
   ```

2. 修改 `ui/symbols/probe_symbols.py`：

   ```python
   painter.drawLine(-18, -15, -18, -3)
   painter.drawLine(18, -15, 18, -3)
   ```

3. 跑探针相关回归测试。

### 案例 4：新增一种 UMEC 接法

假设新增 `Zigzag`：

1. 在 UMEC 参数模板里给 `wtype1/wtype2` 的 choices 增加 `Zigzag`。
2. 在 `get_umec_pins()` 里决定 `Zigzag` 是否有中性端。
3. 在 `ui/symbols/umec_symbols.py` 新增 `_draw_zigzag()`。
4. 在 `draw_umec()` 的两侧接法分支里处理 `Zigzag`。
5. 在 `tests/test_regressions.py` 增加端口测试。
6. 在 `tests/test_symbol_rendering.py` 增加渲染差异测试。

## 十四、注意事项

- 不要只改符号不改端口，否则连线点会和视觉符号错位。
- 不要只改端口不改符号，否则用户看到的线条和真实连接点不一致。
- 动态端口一定要保证属性变化时会重建。
- 删除端口时要清理旧连线，否则会出现连接到不存在 pin 的线。
- `ui/symbols/` 里的绘制函数不要直接修改 `component.params` 或 `component.pins`。
- 画布符号坐标和端口坐标必须使用同一套局部坐标。
