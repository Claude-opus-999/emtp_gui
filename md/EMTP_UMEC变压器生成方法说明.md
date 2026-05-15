# EMTP UMEC 变压器生成方法说明

本文整理当前求解器中 UMEC 变压器的生成、注册和使用方式。内容参考了已有的 `EMTP_使用指南.md`、`EMTP代码讲解.md`，并按当前实现核对了 `models/transformer.py`、`core/circuit.py`、`core/mna_assembler.py`、`core/time_stepper.py`、`solver.py` 和 `io/results.py`。

## 1. 当前 UMEC 能力总览

当前 `models/transformer.py` 实现的是三相组式 UMEC 变压器：

- 三相组等价于三台独立单相变压器。
- 各相之间没有磁耦合。
- 每相可以有两个或多个绕组。
- 每个绕组在 MNA 中表现为一个端口 `(node_from, node_to)`。
- 动态部分用隐式梯形法离散成多端口 Norton 等效。
- 饱和模型已有数据和计算路径，但主时间循环当前没有做饱和段切换后的非线性重解，工程使用时应谨慎。

核心入口可以分成三类：

| 目标 | 推荐入口 | 返回对象 | 适用场景 |
|---|---|---|---|
| 快速创建两绕组三相组数据 | `create_umec_transformer_3ph_bank()` | `UMECTransformerData` | 常见双绕组变压器，参数更短 |
| 手动创建完整数据 | `UMECTransformerData(...)` | `UMECTransformerData` | 三绕组、更多自定义字段、饱和参数 |
| 注册进求解器 | `solver.add_UMEC_transformer(name, data)` | `UMECTransformer` | 正式参与 EMT 仿真 |
| 低层直接实例化 | `UMECTransformer(data, dt, verbose=False)` | `UMECTransformer` | 单独检查 Norton 等效、调试模型，不是常规入网方式 |

## 2. UMEC 模块的主要对象

### 2.1 `WindingType`

`WindingType` 是绕组接法常量：

```python
from emtp.models.transformer import WindingType

WindingType.Y       # "Y"
WindingType.Y_GND   # "Y_gnd"
WindingType.DELTA   # "Delta"
```

当前实现中，接法主要用于额定线电压到相电压的换算：

| 接法 | 相电压计算 |
|---|---|
| `Y` | `V_phase = V_LL / sqrt(3)` |
| `Y_gnd` | `V_phase = V_LL / sqrt(3)` |
| `Delta` | `V_phase = V_LL` |

注意：`WindingType` 不会自动替用户创建中性点、接地节点或三角形环路节点。实际端口连接仍由 `nodes` 显式决定。

### 2.2 `UMECTransformerData`

`UMECTransformerData` 是 UMEC 变压器的输入参数数据类。求解器注册 UMEC 时接收的就是这个对象。

主要字段：

| 字段 | 默认值 | 说明 |
|---|---:|---|
| `name` | 必填 | 变压器名称 |
| `S_rated` | `1e6` | 三相额定容量，单位 VA |
| `freq` | `50.0` | 额定频率，单位 Hz |
| `V_rated_LL` | `[690.0, 35000.0]` | 各绕组额定线电压，单位 V RMS |
| `winding_types` | `["Y", "Delta"]` | 各绕组接法 |
| `X_leak_pu` | `0.08` | 一次侧测得漏抗标幺值 |
| `Im_percent` | `1.0` | 额定电压下励磁电流百分比 |
| `NLL_pu` | `0.0` | 空载损耗标幺值 |
| `CL_pu` | `0.0` | 铜损标幺值 |
| `enable_saturation` | `False` | 是否初始化饱和模型 |
| `sat_V_pu` | `[]` | 饱和曲线电压点，单位 pu |
| `sat_I_percent` | `[]` | 饱和曲线电流点，单位百分比 |
| `nodes` | `None` | 端口节点映射 |
| `n_phases` | `3` | 相数，当前常规路径按三相组使用 |

派生属性：

```python
data.num_windings_per_phase  # 每相绕组数，等于 len(V_rated_LL)
data.total_windings          # 总端口数，等于 n_phases * num_windings_per_phase
```

### 2.3 `UMECTransformer`

`UMECTransformer` 是实际仿真对象。它由 `UMECTransformerData`、时间步长 `dt` 和 `verbose` 构造：

```python
xfmr = UMECTransformer(data, dt=50e-6, verbose=False)
```

内部会完成：

1. 根据绕组接法计算额定相电压。
2. 构造等效匝数向量 `N`。
3. 根据励磁电流估算磁导 `Pw`。
4. 构造多绕组电感矩阵 `L`。
5. 根据铜损构造绕组电阻矩阵 `R`。
6. 根据空载损耗构造并联铁损电导 `G_core`。
7. 用梯形法离散出 `G_eq` 和历史项递推矩阵。
8. 可选初始化饱和模型。

常用接口：

| 方法 | 说明 |
|---|---|
| `get_norton_equivalent()` | 返回 `(G_total, I_hist)` |
| `get_port_nodes()` | 返回展平后的端口节点对 |
| `update_history(V_ports)` | 每步结束后更新历史电流和磁链 |
| `check_saturation(V_ports)` | 检查饱和段是否变化 |
| `get_info()` | 返回变压器参数摘要 |

## 3. 节点映射规则

UMEC 最容易写错的是 `nodes`。当前实现要求：

```python
nodes[phase][winding] = (node_from, node_to)
```

也就是：

- 第一层按相排列，通常是 A、B、C 三相。
- 第二层按绕组排列，例如高压绕组、低压绕组、第三绕组。
- 每个 `(node_from, node_to)` 表示该绕组端口电压 `v_from - v_to`。
- `0` 或 `"GND"` 表示接地。

内部展平顺序是：

```text
A相绕组1, A相绕组2, ...
B相绕组1, B相绕组2, ...
C相绕组1, C相绕组2, ...
```

两绕组三相组示例：

```python
nodes = [
    [("A_H", "N_H"), ("A_L1", "A_L2")],
    [("B_H", "N_H"), ("B_L1", "B_L2")],
    [("C_H", "N_H"), ("C_L1", "C_L2")],
]
```

这里每相有两个绕组：

- 绕组 1 是高压侧，按相到中性点写成 `("A_H", "N_H")` 等。
- 绕组 2 是低压侧，示例中按两个线端写成 `("A_L1", "A_L2")` 等。

如果希望接地星形高压侧，可以直接写：

```python
nodes = [
    [("A_H", "GND"), ("A_L1", "A_L2")],
    [("B_H", "GND"), ("B_L1", "B_L2")],
    [("C_H", "GND"), ("C_L1", "C_L2")],
]
```

重点：`WindingType.Y_GND` 只影响额定相电压换算，不会自动把节点接地。接地必须通过 `nodes` 显式表达。

## 4. 方法一：便捷函数创建两绕组三相组

最常用方法是先调用 `create_umec_transformer_3ph_bank()` 创建 `UMECTransformerData`，再注册到求解器。

```python
from emtp.solver import EMTPSolver
from emtp.models.transformer import (
    WindingType,
    create_umec_transformer_3ph_bank,
)

solver = EMTPSolver(dt=50e-6, finish_time=0.1, verbose=True)

nodes = [
    [("A_H", "GND"), ("A_L1", "A_L2")],
    [("B_H", "GND"), ("B_L1", "B_L2")],
    [("C_H", "GND"), ("C_L1", "C_L2")],
]

data = create_umec_transformer_3ph_bank(
    name="T1",
    S_mva=100.0,
    V1_kV=220.0,
    V2_kV=110.0,
    wtype1=WindingType.Y_GND,
    wtype2=WindingType.DELTA,
    X_leak_pu=0.10,
    Im_percent=1.0,
    freq=50.0,
    NLL_pu=0.002,
    CL_pu=0.005,
    nodes=nodes,
)

xfmr = solver.add_UMEC_transformer("T1", data)
```

便捷函数签名：

```python
create_umec_transformer_3ph_bank(
    name,
    S_mva,
    V1_kV,
    V2_kV,
    wtype1="Y",
    wtype2="Delta",
    X_leak_pu=0.08,
    Im_percent=1.0,
    freq=50.0,
    NLL_pu=0.0,
    CL_pu=0.0,
    nodes=None,
    **kwargs,
)
```

它内部等价于构造：

```python
UMECTransformerData(
    name=name,
    S_rated=S_mva * 1e6,
    freq=freq,
    V_rated_LL=[V1_kV * 1e3, V2_kV * 1e3],
    winding_types=[wtype1, wtype2],
    X_leak_pu=X_leak_pu,
    Im_percent=Im_percent,
    NLL_pu=NLL_pu,
    CL_pu=CL_pu,
    nodes=nodes,
    **kwargs,
)
```

适用场景：

- 每相两个绕组。
- 参数来自常规铭牌和短路、空载试验。
- 希望示例代码更短。

## 5. 方法二：直接创建 `UMECTransformerData`

如果需要更完整的控制，可以直接创建数据对象。

```python
from emtp.models.transformer import UMECTransformerData, WindingType

data = UMECTransformerData(
    name="T_manual",
    S_rated=100e6,
    freq=50.0,
    V_rated_LL=[220e3, 110e3],
    winding_types=[WindingType.Y_GND, WindingType.DELTA],
    X_leak_pu=0.10,
    Im_percent=1.0,
    NLL_pu=0.002,
    CL_pu=0.005,
    nodes=[
        [("A_H", "GND"), ("A_L1", "A_L2")],
        [("B_H", "GND"), ("B_L1", "B_L2")],
        [("C_H", "GND"), ("C_L1", "C_L2")],
    ],
)

xfmr = solver.add_UMEC_transformer("T_manual", data)
```

适用场景：

- 想以 VA、V 为单位直接填参数。
- 想创建三绕组或更多绕组。
- 想显式传入饱和参数。
- 不想使用便捷函数的 `S_mva/V_kV` 单位包装。

### 5.1 三绕组示例

每相三个绕组时，`V_rated_LL` 和 `winding_types` 都要有三个元素，`nodes[phase]` 也要有三个端口。

```python
data = UMECTransformerData(
    name="T_3w",
    S_rated=150e6,
    freq=50.0,
    V_rated_LL=[220e3, 110e3, 35e3],
    winding_types=[
        WindingType.Y_GND,
        WindingType.Y_GND,
        WindingType.DELTA,
    ],
    X_leak_pu=0.12,
    Im_percent=0.8,
    nodes=[
        [("A_H", "GND"), ("A_M", "GND"), ("A_T1", "A_T2")],
        [("B_H", "GND"), ("B_M", "GND"), ("B_T1", "B_T2")],
        [("C_H", "GND"), ("C_M", "GND"), ("C_T1", "C_T2")],
    ],
)

xfmr = solver.add_UMEC_transformer("T_3w", data)
```

当前漏感分配逻辑对三绕组及更多绕组采用通用平均分配。若需要精确的三绕组短路试验等值，需要进一步扩展模型参数和漏抗分配方式。

## 6. 方法三：带饱和参数的数据创建

`UMECTransformerData` 支持饱和曲线字段：

```python
data = UMECTransformerData(
    name="T_sat",
    S_rated=100e6,
    freq=50.0,
    V_rated_LL=[220e3, 110e3],
    winding_types=[WindingType.Y_GND, WindingType.DELTA],
    X_leak_pu=0.10,
    Im_percent=1.0,
    enable_saturation=True,
    sat_V_pu=[0.0, 1.0, 1.1, 1.2, 1.4],
    sat_I_percent=[0.0, 1.0, 2.0, 5.0, 20.0],
    nodes=[
        [("A_H", "GND"), ("A_L1", "A_L2")],
        [("B_H", "GND"), ("B_L1", "B_L2")],
        [("C_H", "GND"), ("C_L1", "C_L2")],
    ],
)

xfmr = solver.add_UMEC_transformer("T_sat", data)
```

也可以通过便捷函数的 `**kwargs` 传入：

```python
data = create_umec_transformer_3ph_bank(
    name="T_sat",
    S_mva=100.0,
    V1_kV=220.0,
    V2_kV=110.0,
    wtype1=WindingType.Y_GND,
    wtype2=WindingType.DELTA,
    nodes=nodes,
    enable_saturation=True,
    sat_V_pu=[0.0, 1.0, 1.1, 1.2, 1.4],
    sat_I_percent=[0.0, 1.0, 2.0, 5.0, 20.0],
)
```

饱和实现现状：

- `UMECTransformer.__init__()` 会为每相创建一个 `UMECSaturationModel`。
- `check_saturation(V_ports)` 可以根据磁链检查分段是否切换。
- 分段切换后 `_update_saturation_parameters()` 会更新磁导、电感矩阵并重新离散化。
- 但当前主时间循环只调用 `update_history()`，没有在 MNA 单步求解里自动调用 `check_saturation()` 并做矩阵重建、重解。

因此，当前饱和参数更适合模型开发和验证。若要在正式暂态仿真中依赖饱和段切换，需要补齐主循环中的非线性重解路径。

## 7. 方法四：低层直接实例化 `UMECTransformer`

低层调试时可以不进入 `EMTPSolver`，直接创建模型对象：

```python
from emtp.models.transformer import UMECTransformer

xfmr = UMECTransformer(data, dt=50e-6, verbose=True)
G_total, I_hist = xfmr.get_norton_equivalent()
ports = xfmr.get_port_nodes()
info = xfmr.get_info()
```

适用场景：

- 检查 `G_eq`、`I_hist`、`L`、`R` 等内部参数。
- 单元测试或离线验证。
- 调试节点映射和端口顺序。

正式仿真不建议手动把对象塞进 `solver.circuit.transformers`。推荐始终使用：

```python
solver.add_UMEC_transformer("T1", data)
```

这样求解器会自动：

- 使用当前 `solver.dt` 构造 `UMECTransformer`。
- 注册到 `circuit.transformers`。
- 更新节点数量。
- 标记 MNA 矩阵需要重建。

## 8. 注册入网后的求解流程

注册入口：

```python
xfmr = solver.add_UMEC_transformer("T1", data)
```

内部流程：

1. `EMTPSolver.add_UMEC_transformer()` 转发到 `Circuit.add_UMEC_transformer()`。
2. `Circuit.add_UMEC_transformer()` 检查 UMEC 模块是否可用。
3. 用 `UMECTransformer(data, self.dt, self.verbose)` 创建仿真对象。
4. 保存到 `circuit.transformers[name]`。
5. 如果 `data.nodes` 不为空，遍历节点对并更新节点数量。
6. 标记矩阵为 dirty，下一次装配会加入变压器贡献。

MNA 中的贡献：

- `MNAAssembler.build_matrix()` 调用 `xfmr.get_norton_equivalent()` 取得 `G_total`，再按多端口导纳矩阵 stamp 到节点导纳矩阵。
- `MNAAssembler.build_rhs()` 取得 `I_hist`，按端口方向注入 RHS。
- `TimeStepper._update_transformer_history()` 在每步求解后读取端口电压 `v_from - v_to`，调用 `xfmr.update_history(V_ports)`。

离散公式对应已有代码讲解中的形式：

```text
Z_eq = 2L / dt + R
G_eq = inv(Z_eq)
H    = G_eq * (2L / dt - R)
i(t) = G_eq * V(t) + I_hist(t)
```

## 9. 结果和信息查询

添加后可以查询变压器信息：

```python
info = solver.get_transformer_info("T1")
```

返回字段来自 `UMECTransformer.get_info()`，主要包括：

| 字段 | 含义 |
|---|---|
| `name` | 变压器名称 |
| `S_rated` | 三相额定容量，VA |
| `freq` | 额定频率 |
| `n_phases` | 相数 |
| `n_windings` | 每相绕组数 |
| `V_phase` | 各绕组额定相电压 |
| `N` | 展平后的等效匝数向量 |
| `Pw` | 名义磁导 |
| `Pw_per_phase` | 各相磁导 |
| `L_diag` | 电感矩阵对角元素 |
| `has_saturation` | 是否初始化了饱和模型 |

目前没有专门的 `get_transformer_current()` 历史结果接口。如果需要观察变压器端口相关波形，通常做法是：

- 用节点电压探针记录端口两端电压。
- 在需要的支路上添加测量支路或探针。
- 调试阶段直接读取 `xfmr.I_prev`、`xfmr.I_hist` 等对象属性，但这属于内部状态，不建议作为稳定 API。

## 10. 方法选择建议

| 需求 | 建议 |
|---|---|
| 两绕组三相组，参数来自铭牌 | 用 `create_umec_transformer_3ph_bank()` |
| 三绕组或更多绕组 | 直接创建 `UMECTransformerData` |
| 想清楚控制单位为 VA/V | 直接创建 `UMECTransformerData` |
| 想用 MVA/kV 简写 | 用 `create_umec_transformer_3ph_bank()` |
| 想注册入网参与仿真 | 用 `solver.add_UMEC_transformer()` |
| 想检查等效导纳矩阵 | 低层创建 `UMECTransformer(data, dt)` |
| 想使用饱和曲线 | 可以传饱和参数，但正式仿真前需补齐饱和重解调用链 |

## 11. 常见注意事项

1. 当前 UMEC 文件标题和实现都指向“三相组”模型，三相三柱、三相五柱不是当前 `models/transformer.py` 的实际磁耦合实现。
2. `nodes` 必须显式给出每相每个绕组的端口节点。
3. `WindingType.Y_GND` 不会自动接地，接地要在 `nodes` 中写成 `("A", "GND")` 或 `("A", 0)`。
4. `WindingType.DELTA` 不会自动生成三角形内部拓扑，只影响相电压按线电压计算。
5. `V_rated_LL`、`winding_types`、`nodes[phase]` 的长度必须和每相绕组数一致。
6. `S_rated` 是三相总容量；便捷函数的 `S_mva` 会自动乘以 `1e6`。
7. `V_rated_LL` 使用 V；便捷函数的 `V1_kV/V2_kV` 使用 kV，会自动乘以 `1e3`。
8. `X_leak_pu` 当前按一次侧测量值推导漏感，双绕组时分到两侧，多绕组时使用通用分配。
9. `CL_pu=0` 时绕组电阻会退化为很小的默认电阻 `1e-6`。
10. `NLL_pu=0` 时不加入铁损并联电导。
11. 饱和模型初始化不等于主循环已经完整支持饱和非线性重解。
12. `data.nodes=None` 时模型可以低层构造，但入网装配时 `get_port_nodes()` 会报“节点未设置”。

## 12. 相关文件索引

| 文件 | 作用 |
|---|---|
| `models/transformer.py` | UMEC 数据类、饱和模型、仿真对象、便捷工厂 |
| `solver.py` | `EMTPSolver.add_UMEC_transformer()` 外观入口 |
| `core/circuit.py` | UMEC 注册到 `circuit.transformers` 的实现 |
| `core/mna_assembler.py` | UMEC 多端口 Norton 导纳和历史源 stamp |
| `core/time_stepper.py` | 每步结束更新 UMEC 历史项 |
| `io/results.py` | `get_transformer_info()` 查询入口 |
| `EMTP_使用指南.md` | 简短用户示例 |
| `EMTP代码讲解.md` | UMEC 求解流程说明 |
