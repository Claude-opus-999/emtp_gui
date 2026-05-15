# EMTP 电磁暂态仿真器 — 使用指南

## 1. 概述

EMTP 是一个基于 Python 的电磁暂态仿真求解器，融合以下核心能力：

- **MNA（修正节点分析）** 处理理想电压源，构建 (n+m)×(n+m) 稀疏增广矩阵
- **SuperLU 稀疏求解**，矩阵不变时复用 LU 分解缓存
- **隐式梯形积分** 离散 L/C 动态元件为诺顿等效
- **PSCAD 分段线性法** 求解非线性避雷器（MOA）
- **Bergeron / ULM 传输线** 模型（支持多相）
- **CIGRE 先导发展法（LPM）** 绝缘子闪络模型
- **UMEC 变压器** 模型
- **ATP 兼容雷电流源**（TWOEXPF / HEIDLERF）

### 包导入

```python
from emtp import EMTPSolver
```

## 2. 快速入门：RLC 电路

```python
from emtp import EMTPSolver

# 创建求解器：步长 1 μs，仿真 1 ms
solver = EMTPSolver(dt=1e-6, finish_time=1e-3)

# 添加元件
solver.add_VS("V1", "src", "GND", lambda t: 1000 * np.sin(2 * np.pi * 50 * t))
solver.add_R("R1", "src", "mid", 10.0)
solver.add_L("L1", "mid", "out", 1e-3)
solver.add_C("C1", "out", "GND", 10e-6)
solver.add_voltage_probe("V_out", "out", "GND")

# 运行仿真
solver.run()

# 获取结果
t = solver.get_time("ms")              # 时间轴（毫秒）
V_out = solver.get_probe("V_out")       # 默认 probe-only 模式下读取探针

# 打印统计
solver.print_solver_statistics()
```

## 3. 节点系统

### 3.1 节点命名

节点支持**字符串名**或**整数编号**。字符串名首次出现时自动分配整数编号，地节点统一为 0。

| 节点表示 | 含义 |
|----------|------|
| `"GND"`, `"gnd"`, `"ground"`, `0` | 地（节点 0） |
| `"T1.tower_top"` | 自动分配编号，如 1 |
| `3` | 直接使用整数 3 |

### 3.2 节点管理 API

```python
# 命名节点 → 整数编号
n = solver.node("T1.tower_top")    # 返回 int，自动分配

# 编号 → 名称
name = solver.node_name(5)          # 返回 str 或 None

# 手动绑定（与已有整数编号共存）
solver.bind_node("bus_A", 10)       # 绑定 bus_A → 10

# 别名（多个名字指向同一节点）
solver.alias_node("Vout", "out")    # "Vout" 与 "out" 是同一节点
```

## 4. 基本元件

### 4.1 电阻

```python
solver.add_R("R_load", "out", "GND", 50.0)
#            name    from    to    R(Ω)
```

### 4.2 电感

```python
solver.add_L("L1", "mid", "out", 1e-3)
#            name  from   to    L(H)

# 带并联阻尼电阻（抑制数值振荡）
solver.add_L("L_damped", "a", "b", 1e-3, Rp=1e6)
```

> 离散公式：G_eq = Δt/(2L)，I_hist 按梯形递推。

### 4.3 电容

```python
solver.add_C("C1", "out", "GND", 10e-6)
#            name  from   to    C(F)

# 带并联泄漏电阻
solver.add_C("C_damped", "a", "b", 10e-6, Rp=1e8)
```

> 离散公式：G_eq = 2C/Δt。

### 4.4 串联 RL（无中间节点）

```python
solver.add_series_RL("RL1", "a", "b", R=10.0, L=1e-3)
```

> 合并为单一二端诺顿支路，不引入中间节点，缩减 MNA 矩阵规模。

### 4.5 定时开关

```python
solver.add_SW("SW1", "a", "b",
              t_close=100e-6,    # 闭合时刻 (s)，<0 表示不动作
              t_open=500e-6,     # 断开时刻 (s)
              R_closed=1e-6,     # 闭合电阻 (默认 1 μΩ)
              R_open=1e9,        # 断开电阻 (默认 1 GΩ)
              initially_closed=False)
```

### 4.6 独立电流源

```python
import numpy as np

# 方式 1：函数
solver.add_IS("I1", "a", "GND", lambda t: 100 * np.sin(2 * np.pi * 50 * t))

# 方式 2：常数
solver.add_IS("Idc", "a", "GND", 10.0)

# 方式 3：ATP 雷电流源（见第 6 节）
```

### 4.7 理想电压源（MNA 增广）

```python
solver.add_VS("V1", "src", "GND", lambda t: 1000 * np.sin(2 * np.pi * 50 * t))
#            name  pos    neg    voltage_func(t)→V
```

> 电压源通过 MNA 增广方程处理，正端不能接地（node_pos > 0）。

## 5. 传输线

### 5.1 Bergeron 无损线路

```python
# Zc: 特性阻抗 (Ω), tau: 传播延时 (s)
solver.add_bergeron_line("TL1", node_k=1, node_m=2, Zc=300.0, tau=50e-6)
```

> 使用环形缓冲区 + 线性插值处理非整数倍 Δt 的延时。

### 5.2 ULM 宽频线路

ULM 使用频域矢量拟合模型，适用于频变参数线路。

```python
# 单相 ULM
line = solver.add_ulm_line(
    "ULM_1ph",
    nodes_k=1,            # 单节点：int
    nodes_m=2,
    fitulm_file="line_model.fitULM",
    length=20000.0,       # 线路长度 (m)
)

# 多相 ULM（例如 6 相电缆）
line = solver.add_ulm_line(
    "Cable_1",
    nodes_k=[1, 15, 16, 2, 17, 18],   # 6 个节点列表
    nodes_m=[3, 19, 20, 4, 21, 22],
    fitulm_file="cable_model.pch",
    length=20000.0,
)
```

> ULM 模型依赖 `numba`；未安装时自动回退并提示。

### 5.3 LCP 参数直接生成 ULM

除直接读取已有 `fitULM/.pch` 文件外，也可以让求解器调用 `LCP` 模块从线路参数生成 fitULM，再自动添加 ULM 线路。这个流程等价于：

```text
线路几何/土壤/频率配置 -> LCP 计算 Z/Y -> Vector Fitting -> 生成 fitULM -> add_ulm_line()
```

通用入口是 `add_lcp_ulm_line()`：

```python
line = solver.add_lcp_ulm_line(
    name="Line_1",
    nodes_k=[...],
    nodes_m=[...],
    line_type="overhead",       # "overhead" / "single_core_cable" / "three_core_cable"
    length=900.0,               # m；如果 config 中已有 line_length，也可以省略
    output_dir="case/generated_lcp",
    force_rebuild=True,         # 建议案例中设 True，避免复用旧 fitULM 缓存
    save_npz=False,             # True 时额外保存 Z/Y/拟合结果 npz
    fitulm_precision=16,
    verbose=False,
)
```

也可以使用三类便捷方法。便捷方法内部仍然调用 `add_lcp_ulm_line()`，只是自动填好 `line_type`：

| 类型 | line_type | 便捷方法 |
|---|---|---|
| 架空线 | `"overhead"` / `"ohl"` | `add_lcp_ohl_line()` |
| 单芯电缆 | `"single_core_cable"` | `add_lcp_single_core_cable_line()` |
| 三芯电缆 | `"three_core_cable"` / `"3core"` | `add_lcp_three_core_cable_line()` |

常用参数说明：

| 参数 | 说明 |
|---|---|
| `name` | 添加到电路中的 ULM 线路名 |
| `nodes_k` / `nodes_m` | 线路两端节点列表，长度必须等于生成的 fitULM 导体数 |
| `line_type` | 仅通用方法需要；决定调用哪类 LCP 线路参数模型 |
| `length` | 线路长度，单位 m；会传给 LCP 并用于 ULM 线路 |
| `config` | 可传入配置对象或 `dict`，字段名与对应 LCP clean_test 配置类一致 |
| `fitulm_file` | 指定输出 fitULM 文件；不传时自动写入 `output_dir` |
| `output_dir` | 自动生成 fitULM 的目录，默认 `case/generated_lcp/` |
| `force_rebuild` | 是否忽略已有 hash 文件并强制重新计算；推荐参数调试案例设为 `True` |
| `save_npz` | 是否额外保存 LCP 中间计算结果 |
| `fitulm_precision` | 导出 fitULM 的浮点精度 |
| `verbose` | 是否打印 LCP 计算和拟合日志 |

> 注意：`add_lcp_ulm_line()` 的 API 默认值仍是 `force_rebuild=False`，用于正式批量算例复用已生成的 fitULM 文件。`lcp_case/` 中的教学和对比案例统一设置 `LCP_FORCE_REBUILD=True`，因为这些案例把半径、位置、材料参数直接写在脚本里，调参数时应确保 LCP 重新计算而不是复用旧缓存。

下面列出三类线路 `config` 中可以填写的全部字段。`config` 可以传 `dict`，也可以传对应配置类对象；如果同时传了外层 `length=` 和 `config["line_length"]`，以外层 `length=` 为准。

#### 5.3.1 架空线 `config` 字段

对应 `LCP.clean_test.ulm_ohl_core_independent.OHLLineConfig`。

| 字段 | 默认值 | 含义 |
|---|---:|---|
| `line_name` | `"TLine_2"` | LCP/fitULM 线路名 |
| `freq_min` | `0.01` | 最小拟合频率，Hz |
| `freq_max` | `1e5` | 最大拟合频率，Hz |
| `n_freq` | `201` | 频率采样点数 |
| `line_length` | `900.0` | 线路长度，m |
| `ground_resistivity` | `1000.0` | 土壤电阻率，欧姆·m |
| `ground_permeability` | `1.0` | 土壤相对磁导率 |
| `ground_permittivity` | `1.0` | 土壤相对介电常数 |
| `phase_radius` | `0.03` | 相导线半径，m |
| `phase_dc_resistance` | `0.05741` | 相导线直流电阻，欧姆/km |
| `phase_mu_r` | `1.0` | 相导线相对磁导率 |
| `phase_bundle_n` | `4` | 每相分裂导线数 |
| `phase_bundle_spacing` | `0.5` | 分裂导线间距，m |
| `phase_positions` | `[(-11.777, 41.8667), (11.777, 41.8667)]` | 相导线坐标列表 `(x, height)`，单位 m |
| `gw_radius` | `0.00875` | 地线半径，m |
| `gw_dc_resistance` | `0.7098` | 地线直流电阻，欧姆/km |
| `gw_mu_r` | `1.0` | 地线相对磁导率 |
| `gw_positions` | `[(-19.25, 58.9333), (19.25, 58.9333)]` | 地线坐标列表 `(x, height)`，单位 m |
| `kron_reduction` | `False` | 是否对地线做 Kron 消元，只保留相导线矩阵 |
| `Yc_poles_min` | `6` | `tr(Yc)` 最小极点数 |
| `Yc_poles_max` | `20` | `tr(Yc)` 最大极点数 |
| `Yc_target_error` | `0.002` | `tr(Yc)` 拟合目标误差 |
| `H_poles_min` | `8` | 传播函数 `H` 最小极点数 |
| `H_poles_max` | `20` | 传播函数 `H` 最大极点数 |
| `H_target_error` | `0.002` | `H` 拟合目标误差 |

导体顺序为 `phase_positions` 中的相导线，随后是 `gw_positions` 中的地线。如果 `kron_reduction=True`，fitULM 导体数会变成保留下来的相导线数，`nodes_k/nodes_m` 也要相应减少。

#### 5.3.2 单芯电缆 `config` 字段

对应 `emtp.models.lcp.SingleCoreCableConfig`。每根单芯铠装电缆生成 3 个 ULM 导体，顺序为 `core, sheath, armor`；多根电缆按 `cables` 列表顺序拼接。

| 字段 | 默认值 | 含义 |
|---|---:|---|
| `line_name` | `"single_core_cable"` | LCP/fitULM 线路名 |
| `line_length` | `100000.0` | 线路长度，m |
| `freq_min` | `0.1` | 最小拟合频率，Hz |
| `freq_max` | `1e6` | 最大拟合频率，Hz |
| `n_freq` | `201` | 频率采样点数 |
| `soil_rho` | `100.0` | 土壤电阻率，欧姆·m |
| `soil_epsilon_r` | `1.0` | 土壤相对介电常数 |
| `soil_mu_r` | `1.0` | 土壤相对磁导率 |
| `Yc_poles_min` | `12` | `tr(Yc)` 最小极点数 |
| `Yc_poles_max` | `20` | `tr(Yc)` 最大极点数 |
| `Yc_target_error` | `0.002` | `tr(Yc)` 拟合目标误差 |
| `H_poles_min` | `12` | 传播函数 `H` 最小极点数 |
| `H_poles_max` | `20` | 传播函数 `H` 最大极点数 |
| `H_target_error` | `0.002` | `H` 拟合目标误差 |
| `enforce_passivity` | `True` | 是否对拟合结果做无源性处理 |
| `use_freq_dependent` | `"auto"` | 是否使用频变传播速度，可为 `"auto"` 或布尔值 |
| `cables` | `None` | 电缆几何列表；`None` 时使用 clean_test 中两根默认铠装电缆 |

`cables` 的每个元素是一个字典，对应 `LCP.cable_model.ArmoredCableGeometry`，可填字段如下：

| 字段 | 默认值 | 含义 |
|---|---:|---|
| `core_radius` | 必填 | 芯线半径，m |
| `core_rho` | 必填 | 芯线电阻率，欧姆·m |
| `core_mu_r` | `1.0` | 芯线相对磁导率 |
| `insulation_radius` | `0.0` | 主绝缘外半径，m |
| `insulation_epsilon_r` | `2.3` | 主绝缘相对介电常数 |
| `insulation_tan_delta` | `0.001` | 主绝缘损耗角正切 |
| `insulation_mu_r` | `1.0` | 主绝缘相对磁导率 |
| `sheath_inner_radius` | `0.0` | 金属护套内半径，m；为 0 时可由 `insulation_radius` 推断 |
| `sheath_outer_radius` | `0.0` | 金属护套外半径，m |
| `sheath_rho` | `2.2e-7` | 金属护套电阻率，欧姆·m |
| `sheath_mu_r` | `1.0` | 金属护套相对磁导率 |
| `sheath_insulation_radius` | `0.0` | 护套绝缘外半径，m；为 0 时可由 `sheath_outer_radius` 推断 |
| `sheath_insulation_epsilon_r` | `2.3` | 护套绝缘相对介电常数 |
| `sheath_insulation_mu_r` | `1.0` | 护套绝缘相对磁导率 |
| `armor_inner_radius` | `0.0` | 铠装层内半径，m；为 0 时可由 `sheath_insulation_radius` 推断 |
| `armor_outer_radius` | `0.0` | 铠装层外半径，m |
| `armor_rho` | `1.4e-7` | 铠装层电阻率，欧姆·m |
| `armor_mu_r` | `100.0` | 铠装层相对磁导率 |
| `jacket_radius` | `0.0` | 外护套外半径，m |
| `jacket_epsilon_r` | `2.3` | 外护套相对介电常数 |
| `jacket_tan_delta` | `0.01` | 外护套损耗角正切 |
| `jacket_mu_r` | `1.0` | 外护套相对磁导率 |
| `burial_depth` | `1.5` | 埋深，m |
| `horizontal_pos` | `0.0` | 水平位置，m |

#### 5.3.3 三芯电缆 `config` 字段

对应 `LCP.clean_test.ulm_three_core_cable_core.CableLineConfig`。导体顺序为 `Core1, Sheath1, Core2, Sheath2, Core3, Sheath3, Pipe`。

| 字段 | 默认值 | 含义 |
|---|---:|---|
| `line_name` | `"Cable_14"` | LCP/fitULM 线路名 |
| `n_inner_cables` | `3` | 管内单芯数，当前三芯模型通常保持 3 |
| `n_total_conductors` | `7` | 总导体数，默认 3 芯 + 3 护套 + 管道 |
| `line_length` | `5000.0` | 线路长度，m |
| `steady_state_freq` | `50.0` | 参考工频，Hz |
| `freq_min` | `0.5` | 最小拟合频率，Hz |
| `freq_max` | `1e6` | 最大拟合频率，Hz |
| `n_freq` | `200` | 频率采样点数 |
| `ground_resistivity` | `100.0` | 土壤电阻率，欧姆·m |
| `ground_permeability` | `1.0` | 土壤相对磁导率 |
| `ground_permittivity` | `1.0` | 土壤相对介电常数 |
| `pipe_inner_radius` | `0.0665` | 金属管内半径，m |
| `pipe_outer_radius` | `0.0715` | 金属管外半径，m |
| `pipe_rho` | `9.78e-8` | 金属管电阻率，欧姆·m |
| `pipe_mu_r` | `200.0` | 金属管相对磁导率 |
| `jacket_radius` | `0.0745` | 管外护套外半径，m |
| `pipe_inner_insulation_epsilon_r` | `2.3` | 管内绝缘相对介电常数 |
| `pipe_outer_insulation_epsilon_r` | `2.3` | 管外绝缘相对介电常数 |
| `burial_depth` | `1.0` | 埋深，m |
| `horizontal_pos` | `0.0` | 管道中心水平位置，m |
| `core_radius` | `0.001175` | 芯线半径，m |
| `core_rho` | `1.72e-8` | 芯线电阻率，欧姆·m |
| `core_mu_r` | `1.0` | 芯线相对磁导率 |
| `insulation_radius` | `0.02505` | 芯线绝缘外半径，m |
| `insulation_epsilon_r` | `2.3` | 芯线绝缘相对介电常数 |
| `sheath_outer_radius` | `0.02715` | 护套外半径，m |
| `sheath_rho` | `2.2e-7` | 护套电阻率，欧姆·m |
| `sheath_mu_r` | `1.0` | 护套相对磁导率 |
| `outer_insulation_radius` | `0.02955` | 单芯外绝缘外半径，m |
| `outer_insulation_epsilon_r` | `2.3` | 单芯外绝缘相对介电常数 |
| `cable_angles_deg` | `[270.0, 30.0, 150.0]` | 三根单芯在管内的角位置，度 |
| `distance_from_center` | `0.03415` | 单芯中心到管道中心距离，m |
| `Yc_poles_min` | `12` | `tr(Yc)` 最小极点数 |
| `Yc_poles_max` | `20` | `tr(Yc)` 最大极点数 |
| `Yc_target_error` | `0.002` | `tr(Yc)` 拟合目标误差 |
| `H_poles_min` | `12` | 传播函数 `H` 最小极点数 |
| `H_poles_max` | `20` | 传播函数 `H` 最大极点数 |
| `H_target_error` | `0.002` | `H` 拟合目标误差 |

`config` 中的字段也可以直接作为关键字参数传入。下面两种写法等价：

```python
solver.add_lcp_ohl_line(
    "OHL_1",
    nodes_k=["A_k", "B_k", "GW1_k", "GW2_k"],
    nodes_m=["A_m", "B_m", "GW1_m", "GW2_m"],
    length=900.0,
    config={"ground_resistivity": 1000.0, "n_freq": 201},
)

solver.add_lcp_ohl_line(
    "OHL_1",
    nodes_k=["A_k", "B_k", "GW1_k", "GW2_k"],
    nodes_m=["A_m", "B_m", "GW1_m", "GW2_m"],
    length=900.0,
    ground_resistivity=1000.0,
    n_freq=201,
)
```

使用通用方法添加架空线：

```python
line = solver.add_lcp_ulm_line(
    "OHL_generic",
    nodes_k=["A_k", "B_k", "GW1_k", "GW2_k"],
    nodes_m=["A_m", "B_m", "GW1_m", "GW2_m"],
    line_type="overhead",
    length=900.0,
    ground_resistivity=1000.0,
    n_freq=201,
    force_rebuild=True,
)
```

架空线示例：

```python
line = solver.add_lcp_ohl_line(
    "OHL_1",
    nodes_k=["A_k", "B_k", "GW1_k", "GW2_k"],
    nodes_m=["A_m", "B_m", "GW1_m", "GW2_m"],
    length=20000.0,
    force_rebuild=True,
    config={
        "phase_positions": [(-11.777, 41.866), (11.777, 41.866)],
        "gw_positions": [(-19.25, 58.933), (19.25, 58.933)],
        "ground_resistivity": 1000.0,
        "n_freq": 201,
    },
)
```

单芯电缆示例。每根单芯铠装电缆对应 3 个导体节点：core、sheath、armor；下面示例使用两根单芯电缆，因此两端各提供 6 个节点：

```python
base_cable = {
    "core_radius": 0.0286,
    "core_rho": 3.6e-8,
    "insulation_radius": 0.061,
    "sheath_outer_radius": 0.0677,
    "armor_outer_radius": 0.0868,
    "jacket_radius": 0.0908,
    "burial_depth": 2.0,
}

line = solver.add_lcp_single_core_cable_line(
    "SC_1",
    nodes_k=["c1_k", "s1_k", "a1_k", "c2_k", "s2_k", "a2_k"],
    nodes_m=["c1_m", "s1_m", "a1_m", "c2_m", "s2_m", "a2_m"],
    length=100000.0,
    force_rebuild=True,
    config={
        "soil_rho": 100.0,
        "cables": [
            {**base_cable, "horizontal_pos": -6.0},
            {**base_cable, "horizontal_pos": 6.0},
        ],
    },
)
```

三芯电缆示例：

```python
line = solver.add_lcp_three_core_cable_line(
    "TC_1",
    nodes_k=["c1_k", "s1_k", "c2_k", "s2_k", "c3_k", "s3_k", "pipe_k"],
    nodes_m=["c1_m", "s1_m", "c2_m", "s2_m", "c3_m", "s3_m", "pipe_m"],
    length=5000.0,
    force_rebuild=True,
    config={
        "ground_resistivity": 100.0,
        "core_radius": 0.001175,
        "insulation_radius": 0.02505,
        "sheath_outer_radius": 0.02715,
    },
)
```

默认生成的 fitULM 文件会放在 `case/generated_lcp/`，文件名带参数 hash；相同参数会复用已有文件。需要强制重算时传 `force_rebuild=True`，需要指定文件路径时传 `fitulm_file="..."`。如果传了固定的 `fitulm_file` 路径，尤其建议在参数修改阶段打开 `force_rebuild=True`，否则文件名不变时更容易误用旧模型。

#### 5.3.4 `lcp_case/` 显式参数案例

`lcp_case/` 目录中的案例是“直接在案例代码里写线路参数，然后一键调用 LCP 生成 ULM”的推荐参考。它们和 `case/` 中读取现成 fitULM/PCH 的旧案例分开保存，便于对比。

| 文件 | 线路类型 | 调用方式 | 参数位置 |
|---|---|---|---|
| `lcp_DC_CABLE_TEST_0201_probe_fast.py` | 单芯铠装电缆，两根电缆共 6 导体 | `add_lcp_ulm_line(..., line_type="single_core_cable")` | `SINGLE_CORE_CABLE_BASE` + `LCP_FIT_CONFIG["cables"]` |
| `lcp_DC_CABLE_TEST_0201_probe_strict.py` | 单芯铠装电缆，两根电缆共 6 导体 | `add_lcp_ulm_line(..., line_type="single_core_cable")` | `SINGLE_CORE_CABLE_BASE` + `LCP_FIT_CONFIG["cables"]` |
| `lcp_cascaded_cable_6seg_probe_latest.py` | 6 段单芯铠装电缆串联 | `add_lcp_ulm_line(..., line_type="single_core_cable")` | `SINGLE_CORE_CABLE_BASE` + `LCP_FIT_CONFIG["cables"]` |
| `lcp_emtp_multiphase_verification_probe_fast.py` | 架空线，2 相导线 + 2 根地线 | `add_lcp_ulm_line(..., line_type="overhead")` | `PHASE_POSITIONS`、`GROUND_WIRE_POSITIONS`、`LCP_FIT_CONFIG` |
| `lcp_emtp_multiphase_verification_probe_strict.py` | 架空线，2 相导线 + 2 根地线 | `add_lcp_ulm_line(..., line_type="overhead")` | `PHASE_POSITIONS`、`GROUND_WIRE_POSITIONS`、`LCP_FIT_CONFIG` |
| `lcp_three_core_cable_explicit_config_case.py` | 三芯管型电缆，7 导体 | `add_lcp_three_core_cable_line()` | `LCP_FIT_CONFIG` |

这些案例都包含：

```python
LCP_OUTPUT_DIR = PROJECT_DIR / "lcp_case" / "generated_lcp"
LCP_FORCE_REBUILD = True
```

也就是说，每次运行都会按当前脚本里的几何和材料参数重新生成 fitULM。若要切换为复用缓存，可以把 `LCP_FORCE_REBUILD` 改为 `False`，但参数调试阶段不建议这样做。

### 5.4 线路信息查询

```python
info = line.get_info()
print(info['Zc'])       # 等效特性阻抗
print(info['tau'])      # 等效传播时延
print(info['nc'])       # 相数
print(info['model_type'])
```

### 5.5 线路结果获取

```python
# 需要 record_line_history=True 时才有历史记录
I_k = solver.get_line_current_k("TL1", unit="A", phase=0)
V_m = solver.get_line_voltage_m("TL1", unit="kV", phase=1)
```

## 6. 雷电流源

内置 ATP 兼容的双指数 (TWOEXPF) 和 Heidler (HEIDLERF) 雷电流源。

### 6.1 标准波形库

```python
from emtp.models.lightning import create_standard_twoexpf_current_source

# 使用标准波形名（跳过数值拟合）
src = create_standard_twoexpf_current_source(
    waveform_type="8/20",     # 8/20 μs 标准雷电流波
    peak=30e3,                # 峰值 30 kA
    PERC=30,                  # ATP PERC 定义
    Tstart=0.0,
)
solver.add_IS("Lightning", "phase_a", "GND", src)
```

可选标准波形：`"1.2/50"`, `"2/20"`, `"8/20"`, `"4/10"`, `"10/350"`, `"0.25/100"`, `"10/700"`, `"30/80"`, `"250/2500"`, `"1/200"`。

### 6.2 自定义参数

```python
from emtp.models.lightning import (
    create_twoexpf_current_source,
    create_heidlerf_current_source,
)

# 双指数：指定 T1/T2，自动拟合 tau1/tau2
src_de = create_twoexpf_current_source(
    peak=50e3, T1=8e-6, T2=20e-6, PERC=30,
)

# Heidler：指定 T1/T2/n
src_h = create_heidlerf_current_source(
    peak=200e3, T1=10e-6, T2=350e-6, n=10,
)
```

### 6.3 直接指定模型参数

```python
# 直接给定 tau1/tau2
src_de2 = create_twoexpf_current_source(
    peak=30e3, T1=8e-6, T2=20e-6,
    tau1=20.37e-6, tau2=3.91e-6,
)
```

## 7. 非线性元件

### 7.1 分段线性避雷器（MOA）

```python
# 从 PSCAD 格式 V-I 数据文件加载
solver.add_MOA_from_file(
    "MOA1", "line", "GND",
    file_path="V_I_old.txt",
    rated_voltage=1.0,        # 额定电压 (标幺基准)
    voltage_is_pu=True,        # 文件中电压是标幺值
)

# 从断点列表创建
from emtp.models.moa import SegmentedMOAResistor
moa = SegmentedMOAResistor.from_breakpoints(
    "MyMOA",
    [(0, 0), (1000, 1e-6), (2000, 1e-3), (3000, 1.0), (4000, 100)],
)
```

> PSCAD 分段线性法：预离散 V-I 曲线为多段，每段用诺顿等效求解，仅在段切换时更新矩阵。

### 7.2 LPM 绝缘子闪络模型

CIGRE 先导发展法模型：

```python
lpm = solver.add_insulator_LPM(
    "Insulator_1",
    node_from="tower_top",
    node_to="phase_conductor",
    gap_length=2.5,            # 间隙长度 (m)
    k=1.0e-6,                  # CIGRE 速度系数
    E0=600.0,                  # 临界场强 (kV/m)
    R_arc=1.0,                 # 闪络后电弧电阻 (Ω)
    altitude_m=1500.0,         # 海拔修正（m）
    allow_extinction=True,     # 允许电弧熄灭
    extinction_current=0.1,    # 熄灭电流阈值 (A)
)

# 获取 LPM 结果
leader_len = solver.get_insulator_leader_length("Insulator_1", unit="cm")
velocity   = solver.get_insulator_leader_velocity("Insulator_1")
voltage    = solver.get_insulator_voltage("Insulator_1", unit="kV")
state      = solver.get_insulator_state("Insulator_1")      # 0=开路, 1=闪络
flashover_log = solver.get_flashover_log()                   # 闪络事件列表
```

预定义绝缘子类型：

```python
from emtp.models.lpm import LPMInsulatorType

lpm = solver.add_insulator_LPM(
    "Ins_glass", "top", "cond", gap_length=2.0,
    **LPMInsulatorType.GLASS_NEG.value,  # 使用预定义参数
)
```

## 8. UMEC 变压器

```python
from emtp.models.transformer import (
    UMECTransformerData, WindingType, create_umec_transformer_3ph_bank,
)

# 三相组变压器（三台独立单相）
data = create_umec_transformer_3ph_bank(
    name="T1",
    S_rated=100e6,                     # 100 MVA
    freq=50.0,
    V_rated_LL=[220e3, 110e3],         # 高压/低压线电压 (V)
    winding_types=[WindingType.Y_GND, WindingType.DELTA],
    X_leak_pu=0.10,                    # 漏抗 10%
    nodes=[...],                       # 端口节点列表
)
xfmr = solver.add_UMEC_transformer("T1", data)
```

> UMEC 模块需要 `umec_transformer.py` 存在；缺失时 `import` 不阻断包导入。

## 9. 探针系统

探针是**轻量级**的结果采样机制。注册探针后，每步自动记录——不依赖全节点电压历史。

### 9.1 电压探针

```python
# 注册：记录 V(node_pos) - V(node_neg)
solver.add_voltage_probe("V_Cp", node_pos=1, node_neg=0)
solver.add_voltage_probe("V_ac", "phase_a", "phase_b")

# 获取结果
V = solver.get_voltage_probe("V_Cp", unit="kV")    # 返回 np.ndarray
V = solver.get_probe("V_ac", unit="V")              # 通用接口
```

### 9.2 支路电流探针

```python
solver.add_branch_current_probe("I_R", "R_load")
I = solver.get_branch_current_probe("I_R", unit="A")
```

### 9.3 线路端口电流探针

```python
solver.add_line_current_probe(
    "I_TL_k", line_name="TL_multiphase", end="k", phase=0,
)
I = solver.get_line_current_probe("I_TL_k", unit="A")
```

### 9.4 列出探针

```python
probes = solver.list_probes()
# {'voltage': ['V_Cp', 'V_Cn'], 'branch_current': ['I_R'], 'line_current': [...]}
```

## 10. 结果获取

### 10.1 全节点电压历史

默认是低内存的 `result_mode="probes_only"`，不保存全节点电压历史。小系统调试时如需 `get_node_voltage()`，需要显式打开 full 模式：

```python
solver = EMTPSolver(
    dt=1e-6,
    finish_time=1e-3,
    result_mode="full",
    record_node_history=True,
)
solver.run()

V1 = solver.get_node_voltage(1, unit="kV")        # 节点 1
V2 = solver.get_node_voltage("bus_A", unit="V")   # 命名节点
t  = solver.get_time(unit="us")                    # 时间轴
```

### 10.2 支路结果

```python
# 需要 record_branch_history=True
solver = EMTPSolver(dt=1e-6, finish_time=1e-3, record_branch_history=True)

I = solver.get_branch_current("R_load", unit="A")
V = solver.get_branch_voltage("R_load", unit="V")
```

### 10.3 电压源结果

```python
# 需要 record_source_history=True
I_vs = solver.get_vs_current("V1", unit="A")
V_vs = solver.get_vs_voltage("V1", unit="kV")
```

### 10.4 传输线结果

```python
# 需要 record_line_history=True
I_k = solver.get_line_current_k("TL1", unit="A", phase=0)
V_m = solver.get_line_voltage_m("TL1", unit="kV", phase=1)
info = solver.get_line_info("TL1")
```

## 11. 求解器配置

### 11.1 完整参数列表

```python
solver = EMTPSolver(
    dt=1e-6,                              # 时间步长 (s)
    finish_time=100e-6,                   # 仿真结束时间 (s)
    verbose=True,                         # 详细日志输出

    # 线路编译
    line_compile_workers=4,               # 并行编译线程数（默认自动）
    compile_lines_on_add=False,           # 添加线路时立即编译（默认延后批量编译）

    # ULM 批量模式
    ulm_batch_mode="auto",                # "auto" / "parallel" / "serial" / "off"
    ulm_batch_parallel_threshold_factor=2,# 并行阈值因子

    # 历史记录控制
    record_node_history=False,            # 默认不记录全节点电压；full 调试时设 True
    record_line_history=False,            # 记录传输线历史
    record_branch_history=False,          # 记录支路历史
    record_source_history=False,          # 记录源电流历史

    # 结果模式
    result_mode="probes_only",            # 默认 "probes_only"；小系统调试可设 "full"

    # 稀疏求解失败后的 dense 回退保护
    allow_dense_fallback=True,            # 是否允许小矩阵 dense lstsq 回退
    dense_fallback_max_size=300,          # 超过该阶数直接报 MatrixSingularError
)
```

### 11.2 result_mode 说明

| 值 | 含义 |
|----|------|
| `None` 或 `"full"` | 保留 `record_*_history` 的原有语义 |
| `"probes_only"` | 强制关闭全局节点电压历史；仅保留探针数据，大幅减少内存 |

> 推荐组合：`result_mode="probes_only"` + `record_node_history=False` + `add_voltage_probe()`，仅记录关注的波形。

### 11.3 ULM Batch 模式

| 值 | 行为 |
|----|------|
| `"auto"` | 根据线路数与 CPU 线程数自动选择串行/并行 batch |
| `"parallel"` | 强制 Numba parallel kernel |
| `"serial"` | Numba serial kernel |
| `"off"` | 逐线 Python fallback（无 numba 时自动使用） |

## 12. 运行与控制

### 12.1 线路编译

```python
# 批量并行编译全部传输线
solver.compile_transmission_lines(max_workers=4, reserve_cores=1, force=True)
```

> 在 `run()` 调用前可手动触发编译；`run()` 内部也会自动编译。

### 12.2 主仿真

```python
solver.run()                                         # 标准运行（自动重置状态）
solver.run(continue_from_current_state=True)         # 从当前状态续算
```

> 默认每次 `run()` 会重置动态状态，保证可重入性。续算需显式传 `True`。

### 12.3 统计与报告

```python
solver.print_circuit_summary()      # 电路结构摘要
solver.print_solver_statistics()    # 求解统计（MNA 维度、重构次数、命中率等）
solver.print_timing_report()        # 模块级性能剖析（TOP-3 耗时模块）

stats = solver.get_solver_statistics()
# {'total_steps': 10000, 'segment_switches': 3, 'G_rebuilds': 5, 'G_cache_hits': 9995, ...}

timing = solver.get_timing_report()
# {'switch_update': 0.01, 'solve_step_total': 2.5, 'line_combined_update': 0.8, ...}
```

统计中还会包含 `matrix_build_count`、`lu_factorization_count`、`rhs_build_count`、`linear_solve_count`、`dense_fallback_count` 等性能计数，用于判断瓶颈来自矩阵重建、LU 分解、RHS 装配还是结果存储。

## 13. 绘图工具

`emtp.plotting` 提供了基于 matplotlib 的轻量探针绘图。

```python
from emtp.plotting import (
    add_voltage_probe,
    add_branch_current_probe,
    plot_voltage_probes,
    plot_current_probes,
    plot_probes,
)

# 注册探针
add_voltage_probe(solver, "V_Cp", 1, 0)
add_branch_current_probe(solver, "I_R", "R_load")

solver.run()

# 绘制
plot_voltage_probes(solver, ["V_Cp"], unit="kV", time_unit="us")
plot_current_probes(solver, ["I_R"], unit="kA")

# 保存到文件
plot_probes(solver, ["V_Cp", "I_R"], unit="kV",
            save_path="result.png", show=True)
```

## 14. 完整案例

### 14.1 RC 充放电

```python
import numpy as np
from emtp import EMTPSolver

solver = EMTPSolver(dt=1e-9, finish_time=1e-6, verbose=False)

# 直流电压源 + RC 串联
solver.add_VS("Vdc", "src", "GND", lambda t: 100.0 if t < 500e-9 else 0.0)
solver.add_R("R1", "src", "mid", 50.0)
solver.add_C("C1", "mid", "GND", 1e-9)

solver.run()

t = solver.get_time("ns")
Vc = solver.get_node_voltage("mid")

solver.print_circuit_summary()
solver.print_timing_report()
```

### 14.2 多相 ULM 线路雷击仿真

```python
from emtp import EMTPSolver
from emtp.models.lightning import create_standard_twoexpf_current_source

solver = EMTPSolver(
    dt=1e-8, finish_time=1e-3,
    verbose=True,
    result_mode="probes_only",
    record_node_history=False,
    ulm_batch_mode="auto",
)

# 4 相架空线路
nodes_k = [1, 2, 3, 4]
nodes_m = [5, 6, 7, 8]

solver.add_ulm_line(
    "TL_4ph",
    nodes_k=nodes_k, nodes_m=nodes_m,
    fitulm_file="line_model.fitULM",
    length=20000.0,
)

# 雷击第 1 相
src = create_standard_twoexpf_current_source(
    waveform_type="2/20", peak=10e3, PERC=30,
)
solver.add_IS("Lightning", "GND", nodes_k[0], src)
solver.add_R("Rs", nodes_k[0], "GND", 800.0)

# 非雷击相接地
for node in nodes_k[1:]:
    solver.add_R(f"Rg_k{node}", node, "GND", 1e-6)

# 终端电阻
for node in nodes_m:
    solver.add_R(f"Rl_m{node}", node, "GND", 20.0)

# 注册探针
for i, node in enumerate(nodes_k):
    solver.add_voltage_probe(f"Vk_Ph{i+1}", node, "GND")
for i, node in enumerate(nodes_m):
    solver.add_voltage_probe(f"Vm_Ph{i+1}", node, "GND")

solver.run()

# 提取数据
t = solver.get_time("us")
Vk_phase1 = solver.get_probe("Vk_Ph1", unit="kV")

import matplotlib.pyplot as plt
plt.plot(t, Vk_phase1)
plt.xlabel("Time (μs)")
plt.ylabel("Voltage (kV)")
plt.grid(True)
plt.show()
```

### 14.3 带 MOA 避雷器 + LPM 绝缘子的回路

```python
solver = EMTPSolver(dt=1e-7, finish_time=500e-6, verbose=True)

# 线路
solver.add_bergeron_line("Line", 1, 2, Zc=300, tau=100e-6)

# 避雷器
solver.add_MOA_from_file("MOA", 1, "GND", "moa_vi.txt", rated_voltage=1.0)

# 绝缘子
lpm = solver.add_insulator_LPM(
    "Ins", 1, "GND", gap_length=1.5,
    k=1.0e-6, E0=600.0,
    altitude_m=1000.0,
)

solver.run()

# 查看闪络事件
for event in solver.get_flashover_log():
    print(f"闪络: t={event['time_us']:.1f} μs, V={event['voltage_kV']:.1f} kV")

# 求解统计
solver.print_solver_statistics()
```

## 15. 依赖要求

| 包 | 用途 | 必需 |
|----|------|------|
| `numpy` | 数组计算 | 是 |
| `scipy` | 稀疏矩阵 LU 分解 (SuperLU)、雷电流拟合 | 是 |
| `matplotlib` | 绘图（plotting 模块） | 否 |
| `numba` | ULM batch 加速 | 否（缺失时回退串行） |

## 16. 常见问题

**Q: 为什么 `record_node_history=False` 后 `get_node_voltage()` 报错？**

全局节点电压历史需要 `record_node_history=True`。推荐使用探针系统：`add_voltage_probe()` + `get_probe()`，内存开销更低。

**Q: ULM 线路导入报错？**

ULM 依赖 `numba`。确认 `numba` 安装，或检查 `FitULM` 文件路径是否正确。

**Q: 仿真很慢怎么办？**

- 使用 `result_mode="probes_only"` 关闭不必要的全量历史记录
- 多条 ULM 线路设置 `ulm_batch_mode="auto"` 启用批量路径
- 查看 `solver.print_timing_report()` 定位瓶颈

**Q: MNA 矩阵奇异？**

- 检查是否有浮空节点（无任何对地阻抗）
- 接地或添加大电阻（如 1e8 Ω）至地
- 电压源正端不能为地（node_pos > 0）
- 大矩阵不会再静默进入 dense `lstsq()`；超过 `dense_fallback_max_size` 会抛出 `MatrixSingularError`，错误信息会给出矩阵规模、非零元数量和排查方向
