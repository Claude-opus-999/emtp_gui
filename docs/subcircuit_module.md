# GUI 子电路模块说明

本文档说明当前 `emtp_gui` 的子电路模块实现，包括数据模型、GUI 操作、封装流程、端口管理、仿真展平、校验机制和当前边界。

当前子电路模块的目标是：

```text
把一组普通电气元件封装成一个可复用的黑盒实例，
在 GUI 中可进入内部编辑，
在仿真前可递归展平成普通电气元件和连线，
并保证端口、连线和定义的一致性。
```

本阶段只覆盖电气端口，不覆盖控制信号端口。

## 1. 核心概念

当前实现把子电路拆成两层：

```text
SubcircuitDefinition
  子电路定义，也可以理解为蓝图。
  保存内部 components、内部 wires、ports。

ComponentInstance(comp_type = SUBCIRCUIT)
  顶层或另一个子电路内部的子电路实例。
  params["subcircuit_name"] 指向某个 SubcircuitDefinition。
```

也就是说，真正的内部电路不直接存放在 `SUBCIRCUIT` 实例里，而是存放在全局定义表：

```python
CircuitModel.subcircuit_defs: dict[str, SubcircuitDefinition]
```

一个定义可以被多个实例引用。

## 2. 相关代码位置

主要实现文件如下：

| 文件 | 作用 |
| --- | --- |
| `models/circuit_model.py` | 子电路数据结构、封装、端口管理、校验、保存加载辅助 |
| `core/solver_builder.py` | 仿真前递归展平子电路 |
| `ui/circuit_canvas.py` | 封装入口、进入子电路编辑、右键端口管理 |
| `ui/main_window.py` | 保存前非阻塞子电路校验，仿真入口会走求解器校验 |
| `tests/test_regressions.py` | 子电路封装、展平、校验、端口同步回归测试 |

## 3. 数据模型

### 3.1 `SubcircuitDefinition`

定义位于 `models/circuit_model.py`。

```python
@dataclass
class SubcircuitDefinition:
    name: str
    components: dict[str, ComponentInstance]
    wires: dict[str, Wire]
    ports: list[SubcircuitPort]
    exposed_params: dict[str, str]
```

字段含义：

| 字段 | 含义 |
| --- | --- |
| `name` | 子电路定义名，例如 `FILTER` |
| `components` | 子电路内部元件，包括普通元件和 `SUBCIRCUIT_PORT` |
| `wires` | 子电路内部连线 |
| `ports` | 对外暴露的电气端口列表 |
| `exposed_params` | 已有的参数暴露映射，当前 GUI 还没有完整参数管理界面 |

`SubcircuitDefinition` 会被序列化到工程文件的 `subcircuit_defs` 字段中。

### 3.2 `SubcircuitPort`

端口结构为：

```python
@dataclass
class SubcircuitPort:
    port_name: str
    internal_comp_id: str
    internal_pin_name: str
    side: str = "left"
    order: int = 0
    description: str = ""
```

字段含义：

| 字段 | 含义 |
| --- | --- |
| `port_name` | 黑盒实例外部看到的端口名，例如 `P1`、`IN` |
| `internal_comp_id` | 子电路内部端口节点元件 ID，通常类似 `PORT_001` |
| `internal_pin_name` | 内部端口节点的引脚名，当前通常为 `node` |
| `side` | 黑盒外观上的端口方向：`left`、`right`、`top`、`bottom` |
| `order` | 同侧端口排序 |
| `description` | 端口说明文本 |

端口不是直接绑定某个电阻或电容的 pin，而是绑定到一个内部 `SUBCIRCUIT_PORT` 节点。这一点很重要，因为它让端口成为一个明确的电气边界节点。

### 3.3 子电路实例

顶层黑盒使用普通 `ComponentInstance` 表示：

```python
ComponentInstance(
    comp_type=ComponentType.SUBCIRCUIT,
    params={"subcircuit_name": "FILTER"},
    pins=[Pin("P1", ...), Pin("P2", ...)]
)
```

实例的 pins 由 `SubcircuitDefinition.get_port_pins()` 生成。端口显示位置由 `side` 和 `order` 决定。

## 4. 端口显示排序

`SubcircuitDefinition.get_port_pins()` 会按以下规则生成实例 pins：

```python
side_order = {
    "left": 0,
    "right": 1,
    "top": 2,
    "bottom": 3,
}

ports = sorted(
    self.ports,
    key=lambda p: (side_order.get(p.side, 99), p.order, p.port_name),
)
```

效果：

```text
1. 同侧端口显示顺序稳定。
2. 修改 order 后，实例 pin 位置会重新排布。
3. 保存再加载后，order 和 description 会保留。
```

## 5. GUI 操作入口

### 5.1 封装为子电路

入口：

```text
画布选择多个元件
右键菜单
封装为子电路
输入子电路名称
```

代码入口：

```python
ui/circuit_canvas.py
CircuitCanvas._create_subcircuit_from_selection()

models/circuit_model.py
CircuitModel.create_subcircuit_from_selection()
```

封装成功后：

```text
1. 顶层选中元件会被移入 SubcircuitDefinition.components。
2. 选中元件之间的连线会移入 SubcircuitDefinition.wires。
3. 跨边界连线会变成子电路端口。
4. 顶层原元件会被一个 SUBCIRCUIT 实例替换。
5. 原外部连线会重新接到 SUBCIRCUIT 实例端口。
```

### 5.2 进入子电路编辑

入口：

```text
双击 SUBCIRCUIT 实例
```

代码入口：

```python
ui/circuit_canvas.py
CircuitCanvas.mouseDoubleClickEvent()
CircuitCanvas._enter_subcircuit()
CircuitCanvas._exit_subcircuit()
```

进入编辑模式后，画布显示的是当前 `SubcircuitDefinition.components` 和 `SubcircuitDefinition.wires`，不是顶层模型。

### 5.3 管理端口

入口：

```text
右键 SUBCIRCUIT 实例
Manage Ports
```

当前端口管理弹窗支持：

| 字段 | 是否可编辑 |
| --- | --- |
| Name | 可编辑 |
| Side | 可编辑 |
| Order | 可编辑 |
| Description | 可编辑 |
| Internal Component | 只读 |
| Internal Pin | 只读 |

保存后调用模型层 API：

```python
rename_subcircuit_port()
update_subcircuit_port_side()
update_subcircuit_port_order()
update_subcircuit_port_description()
```

这些 API 会同步所有引用该定义的子电路实例，包括嵌套子电路内部的实例。

## 6. 封装算法

封装逻辑在：

```python
CircuitModel.create_subcircuit_from_selection()
```

核心步骤如下：

```text
1. 收集选中元件。
2. 调用 assign_node_ids() 获取当前顶层电气节点。
3. 区分内部连线和跨边界连线。
4. 按边界电气节点分组。
5. 对每个边界电气节点创建一个内部 SUBCIRCUIT_PORT。
6. 将该边界节点上的所有内部 pins 都连接到对应 SUBCIRCUIT_PORT.node。
7. 创建 SubcircuitDefinition。
8. 删除顶层原始元件和原始内部/边界连线。
9. 创建 SUBCIRCUIT 实例。
10. 将原外部连接重新接到实例端口。
```

这里最重要的是第 6 步：一个边界电气节点可能连接多个内部 pin，当前实现会把这些内部 pin 全部接到同一个内部端口节点，而不是只接代表 pin。

示意：

```text
封装前：

          R1
J.node ---nf
       \
        \ nf
          R2

封装后内部：

PORT_001.node --- R1.nf
              \
               \-- R2.nf
```

这保证封装不会破坏边界节点的电气等价性。

## 7. 端口同步机制

### 7.1 遍历实例

模型层提供：

```python
iter_subcircuit_instances(subdef_name: str | None = None)
```

它会遍历：

```text
1. 顶层 CircuitModel.components 中的 SUBCIRCUIT 实例。
2. 所有 SubcircuitDefinition.components 中的嵌套 SUBCIRCUIT 实例。
```

返回值包含实例所在的 `components`、`wires` 容器和实例本身，因此端口重命名时可以同步修改该实例所在层级的 wires。

### 7.2 同步 pins

```python
sync_subcircuit_instance_pins(subdef_name)
```

作用：

```text
根据定义的 ports 重新生成所有引用该定义的实例 pins。
```

它会保留同名端口已有的 `node_id`，但不会负责 wire 迁移。wire 迁移由 `rename_subcircuit_port()` 处理。

### 7.3 重命名端口

```python
rename_subcircuit_port(subdef_name, old_name, new_name)
```

同步内容：

```text
1. 修改 SubcircuitPort.port_name。
2. 如果内部端口元件存在，更新 PORT 元件 name 和 params["port_name"]。
3. 修改所有引用该定义的实例 pins。
4. 修改所有连接到这些实例端口的 wires。
5. 重新同步实例 pins。
6. 发送 subcircuit_ports_updated 事件刷新画布。
```

### 7.4 修改方向和排序

```python
update_subcircuit_port_side(subdef_name, port_name, side)
update_subcircuit_port_order(subdef_name, port_name, order)
```

这两个操作不会改变端口名，所以外部连线仍然按同名端口保持连接。操作完成后会重新生成实例 pins，改变黑盒端口位置。

## 8. 仿真前展平

展平逻辑位于：

```python
core/solver_builder.py
SolverBuilder._flatten_subcircuits()
SolverBuilder._flatten_subcircuits_by_nodes()
```

`SolverBuilder.build()` 会先执行：

```python
validation = model.validate_all_subcircuits()
if validation.has_errors:
    raise ValueError(model.format_validation_errors(validation))
```

也就是说，严重的子电路错误会在仿真前被阻止。

### 8.1 展平目标

展平后的模型满足：

```text
1. flat.components 中不再包含 ComponentType.SUBCIRCUIT。
2. 子电路内部普通元件被复制到 flat.components。
3. 内部元件 ID 使用实例路径前缀避免冲突。
4. 顶层节点、子电路端口节点、子电路之间直连节点都保持电气等价。
```

实例路径前缀示例：

```text
TOP_SUB__R_001
OUTER_INST__INNER_INST__R_001
```

### 8.2 节点式展平

当前展平不是简单扫描端口外部 wire，而是按电气节点组做映射：

```text
原始模型 assign_node_ids()
    ↓
得到每个顶层节点上的所有 pins
    ↓
把普通元件 pin 和子电路端口映射到 flat model 中的真实内部 pin
    ↓
同一节点里的 flat pins 用虚拟 flat wire 串起来
```

这使以下情况可以保持连接：

```text
普通元件 - 子电路
子电路 - 子电路
子电路 - Junction - 子电路
子电路 - Ground
多个子电路端口共节点
```

### 8.3 递归嵌套

展平函数内部使用：

```python
instantiate_subcircuit(instance, subdef, prefix, stack)
```

如果子电路内部还有 `SUBCIRCUIT` 实例，会递归展开。

支持：

```text
OUTER 内部包含 INNER
```

展平后：

```text
flat.components 中不应再有 ComponentType.SUBCIRCUIT
```

### 8.4 循环引用检测

递归展平使用 `stack` 检测循环引用：

```text
A -> A
A -> B -> A
```

如果检测到循环，会抛出：

```text
Detected circular subcircuit reference: A -> B -> A
```

这样仿真不会陷入无限递归。

### 8.5 缺失定义检测

如果实例引用了不存在的定义，例如：

```python
ComponentInstance(
    comp_type=ComponentType.SUBCIRCUIT,
    params={"subcircuit_name": "MISSING"}
)
```

展平会抛出：

```text
Subcircuit instance SUB_001 references missing definition: MISSING
```

不会静默跳过，也不会生成错误的 flat model。

## 9. 子电路校验

校验结果结构：

```python
ValidationIssue(
    level: "error" | "warning",
    code: str,
    message: str,
    location: str = "",
)

ValidationResult(
    issues: list[ValidationIssue]
)
```

主要入口：

```python
validate_subcircuit_definition(subdef_name)
validate_subcircuit_instances()
validate_subcircuit_cycles()
validate_all_subcircuits()
format_validation_errors(validation)
```

### 9.1 定义校验

`validate_subcircuit_definition()` 检查：

| 问题 | 级别 | code |
| --- | --- | --- |
| 定义不存在 | error | `subcircuit_definition_not_found` |
| 端口名重复 | error | `duplicate_port_name` |
| 端口引用不存在内部元件 | error | `port_missing_component` |
| 端口引用不存在内部引脚 | error | `port_missing_pin` |
| 内部 wire 引用不存在元件 | error | `wire_missing_component` |
| 内部 wire 引用不存在引脚 | error | `wire_missing_pin` |
| 内部端口悬空 | warning | `floating_internal_port` |
| 子电路为空 | warning | `empty_subcircuit` |
| 子电路只有端口 | warning | `subcircuit_has_only_ports` |

### 9.2 实例校验

`validate_subcircuit_instances()` 检查顶层和嵌套实例：

| 问题 | 级别 | code |
| --- | --- | --- |
| 实例缺少 `subcircuit_name` | error | `instance_missing_subcircuit_name` |
| 实例引用不存在定义 | error | `instance_missing_definition` |
| 实例端口集合与定义不一致 | error | `instance_ports_mismatch` |
| 实例端口顺序与定义不一致 | warning | `instance_ports_order_mismatch` |
| wire 引用不存在实例端口 | error | `wire_missing_instance_port` |

### 9.3 循环引用校验

`validate_subcircuit_cycles()` 会遍历所有定义之间的引用关系，发现：

```text
A -> A
A -> B -> A
```

并生成 `subcircuit_cycle` error。

## 10. 保存、加载和清空

### 10.1 保存

`CircuitModel.to_dict()` 会保存：

```text
components
wires
probes
subcircuit_defs
settings
```

`SubcircuitPort` 的以下字段都会保存：

```text
port_name
internal_comp_id
internal_pin_name
side
order
description
```

`ui/main_window.py` 的保存入口会调用 `validate_all_subcircuits()`。如果有 error，工程仍会保存，但会提示：

```text
当前工程存在子电路错误，文件已保存，但可能无法仿真。
```

### 10.2 加载

`CircuitModel.from_dict()` 会恢复 `subcircuit_defs`，并调用 `_rebuild_id_counters()`。

`SubcircuitPort.from_dict()` 对旧工程兼容：

```text
缺少 order 时，默认使用端口列表 index。
缺少 description 时，默认使用空字符串。
```

### 10.3 清空

`CircuitModel.clear()` 会清空：

```text
components
wires
probes
subcircuit_defs
_id_counters
_selected_ids
```

这样新建工程或清空画布后，不会残留旧子电路定义。

### 10.4 ID 计数器

`_rebuild_id_counters()` 会扫描：

```text
1. 顶层 components
2. 所有 SubcircuitDefinition.components
3. 顶层 wires
4. 所有 SubcircuitDefinition.wires
```

因此加载含子电路的工程后，继续添加元件或 wire 不会和子电路内部已有 ID 冲突。

## 11. 当前支持能力

当前已经支持：

```text
1. 从选中元件封装子电路。
2. 每个边界电气节点生成一个端口。
3. 一个边界节点连接多个内部 pin 时，全部内部 pin 会连接到同一端口节点。
4. 子电路实例可显示为黑盒。
5. 双击进入子电路内部编辑。
6. 右键实例管理端口名、方向、顺序、说明。
7. 端口修改后同步所有实例和相关 wires。
8. 支持子电路实例之间直接相连。
9. 支持嵌套子电路递归展平。
10. 支持循环引用和缺失定义错误检测。
11. 支持仿真前强制校验。
12. 支持保存、加载、清空时维护子电路定义一致性。
```

## 12. 当前边界和未覆盖内容

当前没有完整实现：

```text
1. 控制信号端口。
2. 非电气端口。
3. 子电路库导入导出。
4. 参数暴露 GUI。
5. 新增/删除端口的管理界面。
6. 子电路定义版本迁移工具。
7. 求解器原生模块化，当前仍然是仿真前展平。
```

已有 `exposed_params` 和实例 `params["param_overrides"]` 的基础支持，但这属于更高层的参数管理能力，当前 GUI 子电路端口管理面板不负责这部分。

## 13. 开发注意事项

后续继续改子电路模块时，建议遵守这些规则：

```text
1. 不要让 SUBCIRCUIT 实例直接保存内部 components/wires。
   内部结构应始终保存在 SubcircuitDefinition。

2. 修改端口名时，必须同步实例 pins 和连接到实例端口的 wires。
   不要只改 SubcircuitPort.port_name。

3. 修改 side/order 时，可以只同步实例 pins。
   因为 wire 连接依赖端口名，不依赖端口坐标。

4. 仿真前必须先 validate_all_subcircuits()。
   不要把缺失定义、端口不一致或循环引用交给展平过程碰运气。

5. 展平时应继续以电气节点为中心。
   不要退回到“扫描某个端口直接连了谁”的做法，否则子电路之间直连会丢失。

6. 对封装边界节点，应连接该节点上的所有内部 pins。
   不要只选择第一个 representative pin。

7. 保存/加载结构变更时，要保持旧工程兼容。
   新增字段应在 from_dict() 中提供默认值。
```

## 14. 回归测试覆盖

当前 `tests/test_regressions.py` 中覆盖了这些关键行为：

```text
1. clear() 清空 subcircuit_defs。
2. ID 计数器扫描子电路内部 components/wires。
3. 直接循环引用 A -> A 报错。
4. 间接循环引用 A -> B -> A 报错。
5. 缺失定义报错。
6. 重复端口名校验。
7. 端口引用缺失元件/引脚校验。
8. 内部 wire 引用缺失元件/引脚校验。
9. 内部端口悬空 warning。
10. 实例端口不一致校验。
11. 端口重命名同步实例 pins 和 wires。
12. 端口重命名同步嵌套实例 wires。
13. 修改 side 后实例 pin 重定位。
14. 修改 order 后显示顺序变化且可保存加载。
15. 子电路之间直接相连后展平仍保持同一电气节点。
16. 嵌套子电路展平后不再包含 SUBCIRCUIT 元件。
```

建议后续新增功能时，优先补充以下测试：

```text
1. 新增端口。
2. 删除端口。
3. 参数暴露 GUI。
4. 子电路库导入导出。
5. 子电路定义重命名。
6. 多层嵌套下端口排序和重命名同步。
```

