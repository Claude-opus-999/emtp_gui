# EMTP 电流源、雷电流源与 ULM 线路方法说明

本文整理当前求解器中三类常用入口：

- 独立电流源有哪些生成和添加方式。
- ATP 兼容雷电流源有哪些生成方式。
- ULM 频变线路有哪些添加方式。

内容参考了已有的 `EMTP_使用指南.md`、`EMTP代码讲解.md`，并按当前实现核对了 `solver.py`、`core/circuit.py`、`models/sources.py`、`models/lightning.py`、`models/lcp.py` 和 `models/ulm/model.py`。

## 1. 总览

| 目标 | 推荐入口 | 核心实现 | 适用场景 |
|---|---|---|---|
| 添加普通电流源 | `solver.add_IS(name, node_from, node_to, current_func)` | `Circuit.add_IS()`、`CurrentSource` | 正弦、阶跃、常数、任意自定义 `i(t)` |
| 添加标准雷电流源 | `create_standard_twoexpf_current_source()` 后传给 `add_IS()` | `TWOEXPFCurrentSource` | 直接使用 `"8/20"`、`"2/20"`、`"10/350"` 等标准双指数波形 |
| 添加自定义双指数雷电流源 | `create_twoexpf_current_source()` 后传给 `add_IS()` | `TWOEXPFCurrentSource` | 通过 `T1/T2/PERC` 拟合，或直接给 `tau1/tau2`、`A/B` |
| 添加自定义 Heidler 雷电流源 | `create_heidlerf_current_source()` 后传给 `add_IS()` | `HEIDLERFCurrentSource` | 通过 `T1/T2/n/PERC` 拟合，或直接给 `Tf/tau` |
| 统一雷电流源工厂 | `create_lightning_current_source(model=...)` 后传给 `add_IS()` | 两类雷电源统一分发 | 想用一个入口在双指数和 Heidler 之间切换 |
| 读取现成 ULM 模型 | `solver.add_ulm_line()` | `FitULMReader`、`ULMModel`、`ULMLine` | 已经有 `.fitULM` 或 `.pch` 文件 |
| 由 LCP 参数生成并添加 ULM | `solver.add_lcp_ulm_line()` | `generate_lcp_fitulm()` 再回到 `add_ulm_line()` | 案例脚本中直接写几何、土壤、频率、拟合参数 |
| LCP 便捷 ULM 入口 | `add_lcp_ohl_line()` 等 | `add_lcp_ulm_line()` 包装 | 固定线路类型，少写 `line_type` |

## 2. 独立电流源的生成与添加

### 2.1 `add_IS()` 的统一入口

主类 `EMTPSolver` 对外暴露：

```python
solver.add_IS(name, node_from, node_to, current_func)
```

其中：

- `name` 是电流源名称。
- `node_from`、`node_to` 可以是整数节点号，也可以是字符串节点名。
- `current_func` 支持三类输入：可调用函数、实数常数、雷电流源对象。
- 正方向是 `node_from -> node_to`。装配右端项时，求解器会在 `node_from` 减去电流，在 `node_to` 加上电流。

因此，如果希望一个正峰值电流注入到某个相导体节点，常见写法是：

```python
solver.add_IS("Iinj", "GND", "phase_a", lambda t: 30e3)
```

如果写成：

```python
solver.add_IS("Iout", "phase_a", "GND", lambda t: 30e3)
```

则正电流方向表示从 `phase_a` 流向地，节点注入符号会相反。

### 2.2 方式一：传入任意函数 `i(t)`

这是最通用的方式。函数接收当前仿真时间 `t`，单位是秒，返回当前源电流，单位是安培。

```python
import numpy as np

solver.add_IS(
    "I_sine",
    "src",
    "GND",
    lambda t: 100.0 * np.sin(2 * np.pi * 50 * t),
)
```

适用场景：

- 正弦源、方波、指数衰减、分段函数。
- 需要把外部数据插值成 `i(t)`。
- 需要快速测试某个理想注入电流。

实现要点：

- `models/sources.py::CurrentSource.current_at(t)` 只是调用 `current_func(t)`。
- 每个时间步构造 RHS 时，`MNAAssembler` 调用 `source.current_at(time)`。
- 函数本身不做单位转换，所以用户应保证返回值单位为 A。

### 2.3 方式二：传入常数电流

`add_IS()` 允许 `current_func` 是实数，内部会包装成常数函数。

```python
solver.add_IS("Idc", "GND", "bus", 10.0)
```

等价于：

```python
solver.add_IS("Idc", "GND", "bus", lambda t: 10.0)
```

适用场景：

- 直流偏置电流。
- 调试节点符号和支路方向。
- 作为暂时代替真实波形的占位源。

### 2.4 方式三：传入雷电流源对象

雷电源对象继承 `BaseLightningCurrentSource`。`add_IS()` 检测到这类对象后，会调用它的 `as_current_function()`，最终仍然注册为普通 `CurrentSource`。

```python
from emtp.models.lightning import create_standard_twoexpf_current_source

src = create_standard_twoexpf_current_source(
    waveform_type="8/20",
    peak=30e3,
    PERC=30,
    Tstart=0.0,
)

solver.add_IS("Lightning", "GND", "phase_a", src)
```

好处是雷电源保留了 `current_at(t)`、`get_info()`、`print_info()` 等方法，同时可以直接进入求解器的独立电流源路径。

### 2.5 电流源历史记录

默认配置下，求解器不保存每个电流源的完整历史。需要后处理电流源波形时，创建求解器时打开：

```python
solver = EMTPSolver(
    dt=0.1e-6,
    finish_time=100e-6,
    record_source_history=True,
)
```

运行后读取：

```python
i_lightning = solver.get_source_current("Lightning")
```

如果只关心节点电压或线路电流探针，大规模 ULM 算例中通常保持 `record_source_history=False`，避免额外存储。

## 3. 雷电流源的生成方式

雷电流源实现位于 `models/lightning.py`。当前支持 ATP TYPE-15 风格的两类模型：

- `TWOEXPFCurrentSource`：双指数模型。
- `HEIDLERFCurrentSource`：Heidler 函数模型。

两类对象都支持：

- `current_at(t)`：返回绝对仿真时刻 `t` 的电流。
- `as_current_function()`：转换成 `add_IS()` 可以接收的函数。
- `get_info()`：返回模型、峰值、PERC、拟合误差、起止时间等信息。
- `print_info()`：打印雷电源参数摘要。

### 3.1 标准双指数波形库

入口：

```python
from emtp.models.lightning import create_standard_twoexpf_current_source

src = create_standard_twoexpf_current_source(
    waveform_type="8/20",
    peak=30e3,
    PERC=30,
    Tstart=0.0,
    Tstop=None,
)

solver.add_IS("Lightning_8_20", "GND", "phase_a", src)
```

特点：

- 只生成 `TWOEXPFCurrentSource`。
- 直接使用内置 `tau1/tau2`，跳过数值拟合。
- `waveform_type` 会被解析成名义 `T1/T2`，例如 `"8/20"` 表示 `8 us / 20 us`。
- 可识别 `"8/20 us"`、`"8/20 μs"` 这类带单位写法，内部会归一化。

当前标准波形库包括：

| 波形名 | 说明 |
|---|---|
| `"1.2/50"` | 标准雷电电压冲击形状 |
| `"2/20"` | 后续雷击电流冲击 |
| `"8/20"` | 标准雷电流冲击 |
| `"4/10"` | 快速雷电流冲击 |
| `"10/350"` | 首次雷击电流冲击 |
| `"0.25/100"` | 后续雷击电流冲击 |
| `"10/700"` | 通信线路雷电冲击 |
| `"30/80"` | 操作电流冲击 |
| `"250/2500"` | 长波头电压冲击形状 |
| `"1/200"` | 后续雷击电流冲击 |

辅助函数：

```python
from emtp.models.lightning import (
    list_standard_waveforms,
    get_standard_waveform_params,
    parse_standard_waveform_T1_T2,
)

print(list_standard_waveforms())
tau1, tau2, desc = get_standard_waveform_params("8/20")
T1, T2 = parse_standard_waveform_T1_T2("8/20")
```

### 3.2 双指数雷电流源：按 `T1/T2` 自动拟合

入口：

```python
from emtp.models.lightning import create_twoexpf_current_source

src = create_twoexpf_current_source(
    peak=50e3,
    T1=8e-6,
    T2=20e-6,
    PERC=30,
    Tstart=0.0,
)

solver.add_IS("Lightning_custom_de", "GND", "phase_a", src)
```

特点：

- 根据目标 `T1/T2/PERC` 自动拟合双指数参数 `tau1/tau2`，并换算 ATP 形式的 `A/B`。
- 自动拟合依赖 `scipy.optimize.least_squares`。如果没有 `scipy`，需要改用直接参数方式。
- `PERC` 支持 `0`、`10`、`30`、`50`。
- `atp_compatible=True` 时，会检查 ATP 限制。双指数模型要求 `T2/T1` 至少满足不同 PERC 下的下限：`PERC=0` 为 `2.8`，`10` 为 `3.9`，`30` 为 `3.5`，`50` 为 `4.4`。

### 3.3 双指数雷电流源：直接给 `tau1/tau2`

如果已经知道双指数时间常数，可以直接给 `tau1/tau2`：

```python
src = create_twoexpf_current_source(
    peak=30e3,
    T1=8e-6,
    T2=20e-6,
    tau1=20.37e-6,
    tau2=3.91e-6,
)

solver.add_IS("Lightning_de_tau", "GND", "phase_a", src)
```

约束：

- `tau1` 和 `tau2` 必须成对提供。
- 必须满足 `tau1 > tau2 > 0`。
- `T1/T2` 仍然需要提供，用于目标参数记录、校验和 `get_info()` 输出。

### 3.4 双指数雷电流源：直接给 ATP `A/B`

如果手中已有 ATP 形式参数，也可以直接传入 `A/B`：

```python
src = create_twoexpf_current_source(
    peak=30e3,
    T1=8e-6,
    T2=20e-6,
    A=-1.0 / 20.37e-6,
    B=-1.0 / 3.91e-6,
)

solver.add_IS("Lightning_de_ab", "GND", "phase_a", src)
```

约束：

- `A` 和 `B` 必须成对提供。
- 必须满足 `A < 0`、`B < 0` 且 `A > B`。
- 内部会反推 `tau1=-1/A`、`tau2=-1/B`。

### 3.5 Heidler 雷电流源：按 `T1/T2/n` 自动拟合

入口：

```python
from emtp.models.lightning import create_heidlerf_current_source

src = create_heidlerf_current_source(
    peak=200e3,
    T1=10e-6,
    T2=350e-6,
    n=10,
    PERC=30,
    Tstart=0.0,
)

solver.add_IS("Lightning_heidler", "GND", "phase_a", src)
```

特点：

- 根据 `T1/T2/n/PERC` 自动拟合 `Tf/tau`。
- 自动拟合同样依赖 `scipy`。
- `n` 必须大于 `0`，常用值是 `10`。
- `atp_compatible=True` 时，Heidler 模型要求 `2.0 <= T2/T1 <= 100.0`。

### 3.6 Heidler 雷电流源：直接给 `Tf/tau`

如果已经有 Heidler 参数，可以绕过拟合：

```python
src = create_heidlerf_current_source(
    peak=200e3,
    T1=10e-6,
    T2=350e-6,
    n=10,
    Tf=2.5e-6,
    tau=350e-6,
)

solver.add_IS("Lightning_heidler_direct", "GND", "phase_a", src)
```

约束：

- `Tf` 和 `tau` 必须成对提供。
- `Tf > 0` 且 `tau > 0`。

### 3.7 统一工厂 `create_lightning_current_source()`

如果希望通过一个参数切换模型，可以使用统一工厂：

```python
from emtp.models.lightning import create_lightning_current_source

src = create_lightning_current_source(
    model="twoexpf",
    peak=30e3,
    T1=8e-6,
    T2=20e-6,
    PERC=30,
)

solver.add_IS("Lightning_factory", "GND", "phase_a", src)
```

`model` 支持的常用写法：

- 双指数：`"twoexpf"`、`"two_exp"`、`"double_exp"`、`"double_exponential"`、`"de"`。
- Heidler：`"heidlerf"`、`"heidler"`、`"h"`。

统一工厂会把参数分发给 `create_twoexpf_current_source()` 或 `create_heidlerf_current_source()`。

### 3.8 直接实例化类

也可以直接实例化：

```python
from emtp.models.lightning import TWOEXPFCurrentSource, HEIDLERFCurrentSource

src = TWOEXPFCurrentSource(
    peak=30e3,
    T1=8e-6,
    T2=20e-6,
)
```

一般不必这样做。工厂函数更清楚，也更适合案例脚本。

### 3.9 旧案例兼容入口 `add_standard_twoexpf_IS()`

`EMTPSolver` 主类当前没有直接定义 `add_standard_twoexpf_IS()`。已有案例中的这个方法来自 `case/emtp_fixed_case_compat.py` 的兼容补丁。

兼容方法等价于：

```python
source = create_standard_twoexpf_current_source(
    waveform_type=waveform_type,
    peak=peak,
    PERC=PERC,
    Tstart=Tstart,
    Tstop=Tstop,
    atp_compatible=atp_compatible,
    description=description,
)
solver.add_IS(name, node_from, node_to, source)
```

也就是说，新代码更推荐显式写成“先创建 `src`，再 `add_IS()`”。旧案例为了少改代码，可以继续通过兼容模块使用 `solver.add_standard_twoexpf_IS()`。

## 4. ULM 线路的添加方法

ULM 频变线路最终都会进入 `ULMLine`。当前求解器对外主要有两大类添加方式：

1. 直接读取已经生成好的 `.fitULM` 或 `.pch` 文件。
2. 先用 LCP 根据线路参数生成 fitULM，再把生成文件交给同一个 ULM 加载路径。

### 4.1 方式一：直接读取现成文件 `add_ulm_line()`

入口：

```python
line = solver.add_ulm_line(
    name="TL_1",
    nodes_k=[1, 2, 3],
    nodes_m=[4, 5, 6],
    fitulm_file="case/my_line.fitULM",
    length=20000.0,
)
```

参数说明：

| 参数 | 说明 |
|---|---|
| `name` | 添加到电路中的线路名 |
| `nodes_k` | k 端节点。单相可传单个节点，多相传节点列表 |
| `nodes_m` | m 端节点。长度必须与 `nodes_k` 一致 |
| `fitulm_file` | `.fitULM` 或 `.pch` 文件路径 |
| `length` | 线路长度，单位 m |

内部流程：

1. `Circuit.add_ulm_line()` 先把 `nodes_k/nodes_m` 统一成节点列表。
2. 用 `FitULMReader(fitulm_file).read()` 读取频域拟合数据。
3. 用 `ULMModel(fit_data, length, dt, verbose)` 离散成时域递归卷积模型。
4. 根据 `ulm_model.nc` 判断单相或多相。
5. 单相时使用 `ULMLine.create_from_fitulm()`。
6. 多相时创建 `ULMLine(name, ulm_model)`，并设置 `nodes_k/nodes_m`。
7. 调用 `_attach_ulm_equivalents()` 缓存等效 `Zc` 和 `tau`。
8. 调用 `add_line(line)` 注册到 `transmission_lines`。

节点数量校验：

- 如果 fitULM 是单相，`nodes_k` 和 `nodes_m` 都只能有 1 个节点。
- 如果 fitULM 是 `nc` 相，`nodes_k` 和 `nodes_m` 都必须有 `nc` 个节点。
- 节点顺序必须与 fitULM 文件中的导体顺序一致。

单相示例：

```python
line = solver.add_ulm_line(
    "ULM_1ph",
    nodes_k="line_k",
    nodes_m="line_m",
    fitulm_file="line_model.fitULM",
    length=20000.0,
)
```

多相示例：

```python
line = solver.add_ulm_line(
    "Cable_6ph",
    nodes_k=[1, 15, 16, 2, 17, 18],
    nodes_m=[3, 19, 20, 4, 21, 22],
    fitulm_file="cable_model.pch",
    length=20000.0,
)
```

适用场景：

- 已经用外部工具或 `LCP/clean_test` 生成了 fitULM/PCH 文件。
- 想复用固定线路模型。
- 想把 LCP 生成和时间域仿真分成两个步骤，便于缓存和对比。

### 4.2 方式二：通用 LCP 入口 `add_lcp_ulm_line()`

入口：

```python
line = solver.add_lcp_ulm_line(
    name="Line_1",
    nodes_k=[...],
    nodes_m=[...],
    line_type="overhead",
    length=900.0,
    output_dir="case/generated_lcp",
    force_rebuild=True,
    save_npz=False,
    fitulm_precision=16,
    verbose=False,
    **line_config,
)
```

`line_type` 支持别名：

| 归一化类型 | 可用写法 |
|---|---|
| `overhead` | `"overhead"`、`"ohl"`、`"overhead_line"` |
| `single_core_cable` | `"single_core"`、`"single_core_cable"`、`"sc_cable"`、`"armored_cable"` |
| `three_core_cable` | `"three_core"`、`"three_core_cable"`、`"3core"`、`"pipe_type_cable"` |

常用参数：

| 参数 | 说明 |
|---|---|
| `length` | 线路长度，单位 m。若同时传入 `config.line_length`，外层 `length` 优先 |
| `config` | 配置对象或字典 |
| `fitulm_file` | 指定输出 fitULM 文件路径 |
| `output_dir` | 不指定 `fitulm_file` 时的输出目录，默认是 `case/generated_lcp/` |
| `force_rebuild` | 是否忽略已有 hash 文件并强制重算 |
| `save_npz` | 是否保存 LCP 中间计算结果 |
| `fitulm_precision` | 导出 fitULM 的浮点精度 |
| `verbose` | 是否打印 LCP 计算和拟合过程 |
| `**config_overrides` | 直接覆盖配置字段，例如 `ground_resistivity=...` |

内部流程：

1. `Circuit.add_lcp_ulm_line()` 调用 `models.lcp.generate_lcp_fitulm()`。
2. `generate_lcp_fitulm()` 归一化 `line_type`。
3. 按线路类型选择 LCP 计算路径。
4. 计算 `Z/Y`，执行 Vector Fitting，写出 fitULM。
5. 如果目标 fitULM 已存在且 `force_rebuild=False`，直接复用。
6. `Circuit.add_lcp_ulm_line()` 把 `lcp_result.fitulm_path` 交给 `add_ulm_line()`。
7. 返回的 `line` 上会挂载 `line.lcp_result` 和 `line.lcp_line_type`。

适用场景：

- 线路几何、土壤和拟合参数直接写在案例脚本里。
- 调参时希望每次运行自动生成最新 fitULM。
- 需要统一比较不同线路类型的 LCP 到 ULM 流程。

推荐设置：

```python
# 调参和教学案例：避免误用旧缓存
force_rebuild=True

# 正式批量算例：参数稳定后复用已有 fitULM
force_rebuild=False
```

### 4.3 方式三：LCP 架空线便捷方法

入口：

```python
line = solver.add_lcp_ohl_line(
    name="OHL_1",
    nodes_k=[...],
    nodes_m=[...],
    length=900.0,
    output_dir="case/generated_lcp",
    force_rebuild=True,
    phase_positions=[(-11.777, 41.8667), (11.777, 41.8667)],
    gw_positions=[(-19.25, 58.9333), (19.25, 58.9333)],
)
```

等价于：

```python
solver.add_lcp_ulm_line(..., line_type="overhead")
```

对应配置类：

```text
LCP.clean_test.ulm_ohl_core_independent.OHLLineConfig
```

导体顺序：

1. `phase_positions` 中的相导线。
2. `gw_positions` 中的地线。
3. 如果 `kron_reduction=True`，地线会被 Kron 消元，fitULM 导体数会减少，`nodes_k/nodes_m` 也要按保留下来的导体数填写。

### 4.4 方式四：LCP 单芯铠装电缆便捷方法

入口：

```python
line = solver.add_lcp_single_core_cable_line(
    name="Cable_1",
    nodes_k=[1, 15, 16, 2, 17, 18],
    nodes_m=[3, 19, 20, 4, 21, 22],
    length=100000.0,
    output_dir="case/generated_lcp",
    force_rebuild=True,
    cables=[...],
)
```

等价于：

```python
solver.add_lcp_ulm_line(..., line_type="single_core_cable")
```

对应配置类：

```text
emtp.models.lcp.SingleCoreCableConfig
```

导体顺序：

- 每根单芯铠装电缆生成 3 个 ULM 导体，顺序为 `core, sheath, armor`。
- 多根电缆按 `cables` 列表顺序拼接。
- 例如 2 根单芯铠装电缆会生成 6 个导体，所以 `nodes_k/nodes_m` 都需要 6 个节点。

### 4.5 方式五：LCP 三芯管型电缆便捷方法

入口：

```python
line = solver.add_lcp_three_core_cable_line(
    name="TL_three_core",
    nodes_k=[1, 2, 3, 4, 5, 6, 7],
    nodes_m=[11, 12, 13, 14, 15, 16, 17],
    length=5000.0,
    output_dir="case/generated_lcp",
    force_rebuild=True,
    **LCP_FIT_CONFIG,
)
```

等价于：

```python
solver.add_lcp_ulm_line(..., line_type="three_core_cable")
```

对应配置类：

```text
LCP.clean_test.ulm_three_core_cable_core.CableLineConfig
```

导体顺序：

```text
Core1, Sheath1, Core2, Sheath2, Core3, Sheath3, Pipe
```

因此 `nodes_k/nodes_m` 通常都需要 7 个节点。

### 4.6 方式六：别名方法

`solver.py` 中还保留了三组别名，便于用更短的名称表达“添加某类 ULM 线”：

| 别名 | 等价方法 |
|---|---|
| `add_ohl_ulm_line` | `add_lcp_ohl_line` |
| `add_single_core_cable_ulm_line` | `add_lcp_single_core_cable_line` |
| `add_three_core_cable_ulm_line` | `add_lcp_three_core_cable_line` |

示例：

```python
line = solver.add_ohl_ulm_line(
    "OHL_alias",
    nodes_k=[...],
    nodes_m=[...],
    length=900.0,
    force_rebuild=True,
)
```

### 4.7 低层方式：手动构造 `ULMLine` 后 `add_line()`

`EMTPSolver` 也暴露了通用传输线注册入口：

```python
solver.add_line(line)
```

理论上可以手动创建 `FitULMData`、`ULMModel`、`ULMLine` 后注册。但这不是常规用法，因为需要自行保证：

- `ULMModel` 已用正确 `dt` 初始化。
- 多相线路的 `nodes_k/nodes_m` 已正确设置。
- 等效 `Zc/tau`、状态初始化和编译阶段与求解器一致。

实际案例中建议优先使用 `add_ulm_line()` 或 LCP 系列入口。

## 5. 方法选择建议

### 5.1 电流源怎么选

| 需求 | 建议 |
|---|---|
| 已有数学表达式 | 用 `add_IS(..., lambda t: ...)` |
| 常数电流 | 直接传实数 |
| 标准雷电波形 | `create_standard_twoexpf_current_source()` 后 `add_IS()` |
| 自定义双指数雷电波形，只知道 `T1/T2` | `create_twoexpf_current_source()` 自动拟合 |
| 自定义双指数雷电波形，已有参数 | `create_twoexpf_current_source(..., tau1/tau2=...)` 或 `A/B=...` |
| Heidler 波形，只知道 `T1/T2/n` | `create_heidlerf_current_source()` 自动拟合 |
| Heidler 波形，已有参数 | `create_heidlerf_current_source(..., Tf=..., tau=...)` |
| 想用一个入口切换模型 | `create_lightning_current_source(model=...)` |

### 5.2 ULM 线路怎么选

| 需求 | 建议 |
|---|---|
| 已有 `.fitULM` 或 `.pch` | 用 `add_ulm_line()` |
| 想从架空线参数直接生成模型 | 用 `add_lcp_ohl_line()` 或 `add_lcp_ulm_line(line_type="overhead")` |
| 想从单芯铠装电缆参数直接生成模型 | 用 `add_lcp_single_core_cable_line()` 或 `line_type="single_core_cable"` |
| 想从三芯管型电缆参数直接生成模型 | 用 `add_lcp_three_core_cable_line()` 或 `line_type="three_core_cable"` |
| 想写统一脚本比较多种 LCP 线路类型 | 用 `add_lcp_ulm_line()`，把 `line_type` 作为变量 |
| 参数已经稳定，运行很多算例 | `force_rebuild=False` 复用 hash 缓存 |
| 正在调参数或教学演示 | `force_rebuild=True` 强制生成新 fitULM |

## 6. 常见注意事项

1. 电流源方向很重要。正电流方向是 `node_from -> node_to`，节点注入符号由这个方向决定。
2. `GND` 和 `0` 都可用于接地，但同一脚本中最好保持风格统一。
3. 雷电流源的 `peak` 不能为 0，`T1/T2` 必须为正且 `T2 > T1`。
4. 自动拟合需要 `scipy`。没有 `scipy` 时，标准波形库和直接参数方式仍然可用。
5. `waveform_type` 不能和双指数直接参数 `tau1/tau2` 或 `A/B` 混用。
6. ULM 多相节点数必须与 fitULM 中的导体数 `nc` 一致。
7. LCP 生成的导体顺序决定 `nodes_k/nodes_m` 的顺序，接错顺序会让相别或护层电流含义错位。
8. `add_lcp_ulm_line()` 最终仍然走 `add_ulm_line()`，所以时间域求解逻辑只有一套。
9. 大规模多条 ULM 线路可以通过 `ulm_batch_mode="auto"`、`"serial"`、`"parallel"` 或 `"off"` 控制批量更新策略。
10. 后处理优先用 probe。只有确实需要完整历史时，再打开 `record_source_history`、`record_line_history` 或 `record_node_history`。

## 7. 相关文件索引

| 文件 | 作用 |
|---|---|
| `solver.py` | `EMTPSolver` 外观 API，包含 `add_IS()`、`add_ulm_line()`、LCP 便捷别名 |
| `core/circuit.py` | 电源和线路注册的真实实现 |
| `core/mna_assembler.py` | 电流源和线路历史源如何进入 RHS |
| `models/sources.py` | `CurrentSource`、`VoltageSource` 数据结构 |
| `models/lightning.py` | ATP 兼容 TWOEXPF / HEIDLERF 雷电流源 |
| `models/ulm/model.py` | fitULM 读取、ULM 模型、`ULMLine`、batch 更新结构 |
| `models/lcp.py` | LCP 参数到 fitULM 文件的适配层 |
| `case/emtp_fixed_case_compat.py` | 旧案例 `add_standard_twoexpf_IS()` 兼容补丁 |
| `EMTP_使用指南.md` | 面向用户的 API 示例 |
| `EMTP代码讲解.md` | 面向代码结构的模块说明 |
