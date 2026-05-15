"""
EMTP 电路仿真 GUI - 电路数据模型
核心数据结构：元件、连线、节点分配、Undo/Redo
"""

from dataclasses import dataclass, field
from typing import Optional, Callable, Dict, List, Any, Tuple
from enum import Enum
import uuid


class ComponentType(Enum):
    """元件类型枚举"""
    RESISTOR = "R"
    INDUCTOR = "L"
    CAPACITOR = "C"
    SERIES_RL = "SRL"              # 新增：串联RL
    SWITCH = "SW"
    VOLTAGE_SOURCE = "VS"
    CURRENT_SOURCE = "IS"
    MOA = "MOA"
    LPM = "LPM"                    # 新增：绝缘子闪络
    BERGERON = "BERGERON"
    ULM = "ULM"
    LCP_OHL = "LCP_OHL"            # 新增：LCP架空线
    LCP_SINGLE_CABLE = "LCP_SC"    # 新增：LCP单芯电缆
    LCP_THREE_CABLE = "LCP_3C"     # 新增：LCP三芯电缆
    UMEC_TRANSFORMER = "UMEC"      # 新增：UMEC变压器
    PROBE = "PRB"                  # 新增：探针（画布元件）
    GROUND = "GND"
    JUNCTION = "JUNC"
    SUBCIRCUIT = "SUB"             # 新增：子电路


@dataclass
class Pin:
    """元件的电气端口"""
    name: str           # 引脚名称: "nf", "nt", "node_pos", "node_neg", "nk", "nm"
    local_x: float     # 相对于元件锚点的 X 偏移
    local_y: float     # 相对于元件锚点的 Y 偏移
    node_id: Optional[int] = None  # 连接到的节点编号（None=未连接）

    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'local_x': self.local_x,
            'local_y': self.local_y,
            'node_id': self.node_id,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Pin':
        return cls(
            name=data.get('name', ''),
            local_x=data.get('local_x', 0),
            local_y=data.get('local_y', 0),
            node_id=data.get('node_id'),
        )


@dataclass
class ComponentInstance:
    """画布上的一个元件实例"""
    comp_id: str                    # 唯一 ID，如 "R_001"
    comp_type: ComponentType         # 元件类型
    name: str                        # 用户可见名称，如 "R1"
    x: int                           # 画布网格坐标 x
    y: int                           # 画布网格坐标 y
    rotation: int = 0                # 旋转角度: 0/90/180/270
    params: Dict[str, Any] = field(default_factory=dict)  # 参数字典
    pins: List[Pin] = field(default_factory=list)         # 引脚列表

    def to_dict(self) -> Dict:
        return {
            'comp_id': self.comp_id,
            'comp_type': self.comp_type.value,
            'name': self.name,
            'x': self.x,
            'y': self.y,
            'rotation': self.rotation,
            'params': self.params,
            'pins': [p.to_dict() for p in self.pins],
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'ComponentInstance':
        return cls(
            comp_id=data.get('comp_id', ''),
            comp_type=ComponentType(data.get('comp_type', 'R')),
            name=data.get('name', ''),
            x=data.get('x', 0),
            y=data.get('y', 0),
            rotation=data.get('rotation', 0),
            params=data.get('params', {}),
            pins=[Pin.from_dict(p) for p in data.get('pins', [])],
        )

    def get_pin(self, pin_name: str) -> Optional[Pin]:
        """获取指定名称的引脚"""
        for pin in self.pins:
            if pin.name == pin_name:
                return pin
        return None

    def regenerate_id(self):
        """重新生成唯一ID"""
        self.comp_id = f"{self.comp_type.value}_{uuid.uuid4().hex[:8]}"


@dataclass
class Wire:
    """两个引脚之间的电气连线"""
    wire_id: str           # 唯一 ID
    from_comp: str         # 起始元件 comp_id
    from_pin: str          # 起始引脚 name
    to_comp: str           # 终止元件 comp_id
    to_pin: str             # 终止引脚 name
    waypoints: List[tuple] = field(default_factory=list)  # 折点坐标

    def to_dict(self) -> Dict:
        return {
            'wire_id': self.wire_id,
            'from_comp': self.from_comp,
            'from_pin': self.from_pin,
            'to_comp': self.to_comp,
            'to_pin': self.to_pin,
            'waypoints': self.waypoints,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Wire':
        return cls(
            wire_id=data.get('wire_id', ''),
            from_comp=data.get('from_comp', ''),
            from_pin=data.get('from_pin', ''),
            to_comp=data.get('to_comp', ''),
            to_pin=data.get('to_pin', ''),
            waypoints=data.get('waypoints', []),
        )


@dataclass
class SubcircuitPort:
    """子电路暴露的端口 — 连接内部引脚与外部世界"""
    port_name: str              # 外部端口名，如 "P1", "P2"
    internal_comp_id: str       # 内部元件 comp_id
    internal_pin_name: str      # 内部引脚名
    side: str = "left"          # 端口在盒子上的位置: left / right / top / bottom

    def to_dict(self) -> Dict:
        return {
            'port_name': self.port_name,
            'internal_comp_id': self.internal_comp_id,
            'internal_pin_name': self.internal_pin_name,
            'side': self.side,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'SubcircuitPort':
        return cls(
            port_name=data.get('port_name', ''),
            internal_comp_id=data.get('internal_comp_id', ''),
            internal_pin_name=data.get('internal_pin_name', ''),
            side=data.get('side', 'left'),
        )


@dataclass
class SubcircuitDefinition:
    """子电路定义（蓝图）— 可被多个实例引用"""
    name: str                                           # 子电路名称，如 "RL_filter"
    components: Dict[str, ComponentInstance] = field(default_factory=dict)
    wires: Dict[str, Wire] = field(default_factory=dict)
    ports: List[SubcircuitPort] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'components': {k: v.to_dict() for k, v in self.components.items()},
            'wires': {k: v.to_dict() for k, v in self.wires.items()},
            'ports': [p.to_dict() for p in self.ports],
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'SubcircuitDefinition':
        return cls(
            name=data.get('name', ''),
            components={
                k: ComponentInstance.from_dict(v)
                for k, v in data.get('components', {}).items()
            },
            wires={
                k: Wire.from_dict(v)
                for k, v in data.get('wires', {}).items()
            },
            ports=[SubcircuitPort.from_dict(p) for p in data.get('ports', [])],
        )

    def get_port_pins(self) -> List[Dict]:
        """生成子电路实例的引脚定义列表（基于端口）"""
        # 根据端口数量和 side 自动分配 local_x/local_y
        left_ports = [p for p in self.ports if p.side == 'left']
        right_ports = [p for p in self.ports if p.side == 'right']
        top_ports = [p for p in self.ports if p.side == 'top']
        bottom_ports = [p for p in self.ports if p.side == 'bottom']

        pin_defs = []
        # 左侧引脚
        for i, port in enumerate(left_ports):
            y = -(len(left_ports) - 1) * 10 + i * 20
            pin_defs.append({'name': port.port_name, 'local_x': -40, 'local_y': y})
        # 右侧引脚
        for i, port in enumerate(right_ports):
            y = -(len(right_ports) - 1) * 10 + i * 20
            pin_defs.append({'name': port.port_name, 'local_x': 40, 'local_y': y})
        # 上侧引脚
        for i, port in enumerate(top_ports):
            x = -(len(top_ports) - 1) * 10 + i * 20
            pin_defs.append({'name': port.port_name, 'local_x': x, 'local_y': -30})
        # 下侧引脚
        for i, port in enumerate(bottom_ports):
            x = -(len(bottom_ports) - 1) * 10 + i * 20
            pin_defs.append({'name': port.port_name, 'local_x': x, 'local_y': 30})

        return pin_defs


@dataclass
class SimSettings:
    """仿真参数"""
    dt: float = 1e-6               # 时间步长 (s)
    finish_time: float = 100e-6    # 仿真结束时间 (s)
    verbose: bool = False           # 详细输出
    # --- 新增：新内核参数 ---
    result_mode: str = "probes_only"       # "probes_only" | "full"
    ulm_batch_mode: str = "auto"           # "auto" | "parallel" | "serial" | "off"
    record_node_history: bool = False
    record_branch_history: bool = False
    record_line_history: bool = False
    record_source_history: bool = False
    allow_dense_fallback: bool = True
    dense_fallback_max_size: int = 300
    # 雷电参数保留
    lightning_type: str = "8/20"   # 雷电波形类型
    lightning_peak: float = 10000.0 # 雷电峰值电流 (A)
    lightning_t_start: float = 10e-6  # 雷电起始时间 (s)

    def to_dict(self) -> Dict:
        return {
            'dt': self.dt,
            'finish_time': self.finish_time,
            'verbose': self.verbose,
            'result_mode': self.result_mode,
            'ulm_batch_mode': self.ulm_batch_mode,
            'record_node_history': self.record_node_history,
            'record_branch_history': self.record_branch_history,
            'record_line_history': self.record_line_history,
            'record_source_history': self.record_source_history,
            'allow_dense_fallback': self.allow_dense_fallback,
            'dense_fallback_max_size': self.dense_fallback_max_size,
            'lightning_type': self.lightning_type,
            'lightning_peak': self.lightning_peak,
            'lightning_t_start': self.lightning_t_start,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'SimSettings':
        return cls(
            dt=data.get('dt', 1e-6),
            finish_time=data.get('finish_time', 100e-6),
            verbose=data.get('verbose', False),
            result_mode=data.get('result_mode', 'probes_only'),
            ulm_batch_mode=data.get('ulm_batch_mode', 'auto'),
            record_node_history=data.get('record_node_history', False),
            record_branch_history=data.get('record_branch_history', False),
            record_line_history=data.get('record_line_history', False),
            record_source_history=data.get('record_source_history', False),
            allow_dense_fallback=data.get('allow_dense_fallback', True),
            dense_fallback_max_size=data.get('dense_fallback_max_size', 300),
            lightning_type=data.get('lightning_type', '8/20'),
            lightning_peak=data.get('lightning_peak', 10000.0),
            lightning_t_start=data.get('lightning_t_start', 10e-6),
        )


CURRENT_SCHEMA_VERSION = 3


@dataclass
class ProbeConfig:
    """探针配置，保存在 CircuitModel 中"""
    probe_id: str               # 如 "V_node3"
    probe_type: str             # "voltage" | "branch_current" | "line_current"
    # voltage 探针
    node_pos: Optional[int] = None
    node_neg: Optional[int] = None
    # branch_current 探针
    branch_name: Optional[str] = None
    # line_current 探针
    line_name: Optional[str] = None
    end: Optional[str] = None   # "k" | "m"
    phase: Optional[int] = None
    # 显示
    unit: str = "kV"
    color: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            'probe_id': self.probe_id,
            'probe_type': self.probe_type,
            'node_pos': self.node_pos,
            'node_neg': self.node_neg,
            'branch_name': self.branch_name,
            'line_name': self.line_name,
            'end': self.end,
            'phase': self.phase,
            'unit': self.unit,
            'color': self.color,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'ProbeConfig':
        return cls(
            probe_id=data.get('probe_id', ''),
            probe_type=data.get('probe_type', 'voltage'),
            node_pos=data.get('node_pos'),
            node_neg=data.get('node_neg'),
            branch_name=data.get('branch_name'),
            line_name=data.get('line_name'),
            end=data.get('end'),
            phase=data.get('phase'),
            unit=data.get('unit', 'kV'),
            color=data.get('color'),
        )


class CircuitModel:
    """电路数据模型 - 所有 UI 操作最终都映射为对此模型的增删改查"""

    CURRENT_SCHEMA_VERSION = CURRENT_SCHEMA_VERSION

    def __init__(self):
        self.components: Dict[str, ComponentInstance] = {}
        self.wires: Dict[str, Wire] = {}
        self.probes: List[ProbeConfig] = []      # 新增：探针配置列表
        self.subcircuit_defs: Dict[str, SubcircuitDefinition] = {}  # 子电路定义库
        self.settings = SimSettings()
        self._next_node_id = 1        # 节点编号分配器
        self._undo_stack: List[Dict] = []
        self._redo_stack: List[Dict] = []
        self._observers: List[Callable] = []  # 观察者模式

        # 元件ID计数器
        self._id_counters: Dict[str, int] = {}

    # ---- 观察者模式 ----

    def add_observer(self, callback: Callable):
        """添加观察者"""
        self._observers.append(callback)

    def remove_observer(self, callback: Callable):
        """移除观察者"""
        if callback in self._observers:
            self._observers.remove(callback)

    def _notify(self, event: str = "changed"):
        """通知所有观察者"""
        for callback in self._observers:
            callback(event)

    # ---- 选择状态 ----

    def select_component(self, comp_id: str):
        """选中元件"""
        self._notify("component_selected")
        pass  # 实际选择由画布处理

    def get_selected_components(self) -> List[ComponentInstance]:
        """获取选中的元件列表"""
        # 注：由画布管理选择状态
        return []

    # ---- 元件ID生成 ----

    def generate_component_id(self, comp_type: ComponentType) -> str:
        """生成唯一的元件ID"""
        type_str = comp_type.value
        if type_str not in self._id_counters:
            self._id_counters[type_str] = 0
        self._id_counters[type_str] += 1
        return f"{type_str}_{self._id_counters[type_str]:03d}"

    # ---- 状态快照 (用于Undo/Redo) ----

    def _snapshot(self) -> Dict:
        """获取当前状态快照"""
        return {
            'components': {k: v.to_dict() for k, v in self.components.items()},
            'wires': {k: v.to_dict() for k, v in self.wires.items()},
            'probes': [p.to_dict() for p in self.probes],
            'subcircuit_defs': {k: v.to_dict() for k, v in self.subcircuit_defs.items()},
            'settings': self.settings.to_dict(),
            'id_counters': self._id_counters.copy(),
        }

    def _restore(self, snapshot: Dict):
        """恢复状态"""
        self.components = {
            k: ComponentInstance.from_dict(v)
            for k, v in snapshot['components'].items()
        }
        self.wires = {
            k: Wire.from_dict(v)
            for k, v in snapshot['wires'].items()
        }
        self.probes = [
            ProbeConfig.from_dict(p) for p in snapshot.get('probes', [])
        ]
        self.subcircuit_defs = {
            k: SubcircuitDefinition.from_dict(v)
            for k, v in snapshot.get('subcircuit_defs', {}).items()
        }
        self.settings = SimSettings.from_dict(snapshot['settings'])
        self._id_counters = snapshot['id_counters'].copy()

    def _push_undo_snapshot(self, snapshot: Dict):
        """压入一个指定快照到撤销栈"""
        self._undo_stack.append(snapshot)
        self._redo_stack.clear()
        if len(self._undo_stack) > 50:
            self._undo_stack.pop(0)

    def _rebuild_id_counters(self):
        """根据现有元件重新构建 ID 计数器"""
        self._id_counters = {}
        for comp in self.components.values():
            self._sync_counter_for_component(comp)

    def _sync_counter_for_component(self, comp: ComponentInstance):
        """把一个元件实例的编号信息同步到计数器"""
        type_str = comp.comp_type.value
        suffix = comp.comp_id.rsplit('_', 1)[-1]
        if suffix.isdigit():
            number = int(suffix)
            self._id_counters[type_str] = max(
                self._id_counters.get(type_str, 0),
                number,
            )

    # ---- Undo/Redo ----

    def can_undo(self) -> bool:
        """是否可以撤销"""
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        """是否可以重做"""
        return len(self._redo_stack) > 0

    def undo(self) -> bool:
        """撤销"""
        if not self._undo_stack:
            return False
        current = self._snapshot()
        self._redo_stack.append(current)
        self._restore(self._undo_stack.pop())
        self._notify("undone")
        return True

    def redo(self) -> bool:
        """重做"""
        if not self._redo_stack:
            return False
        current = self._snapshot()
        self._undo_stack.append(current)
        self._restore(self._redo_stack.pop())
        self._notify("redone")
        return True

    def _save_undo_state(self):
        """保存撤销状态"""
        self._push_undo_snapshot(self._snapshot())

    # ---- 元件操作 ----

    def add_component(self, comp: ComponentInstance) -> None:
        """添加元件"""
        self._save_undo_state()
        self.components[comp.comp_id] = comp
        self._sync_counter_for_component(comp)
        self._notify("component_added")

    def remove_component(self, comp_id: str) -> None:
        """移除元件及其相关连线"""
        self._save_undo_state()

        # 移除相关连线
        wires_to_remove = []
        for wire_id, wire in self.wires.items():
            if wire.from_comp == comp_id or wire.to_comp == comp_id:
                wires_to_remove.append(wire_id)

        for wire_id in wires_to_remove:
            del self.wires[wire_id]

        # 移除元件
        if comp_id in self.components:
            del self.components[comp_id]

        self._notify("component_removed")

    def move_component(self, comp_id: str, new_x: int, new_y: int) -> None:
        """移动元件"""
        if comp_id in self.components:
            comp = self.components[comp_id]
            # 不保存撤销状态（频繁调用）
            comp.x = new_x
            comp.y = new_y
            self._notify("component_moved")

    def update_params(self, comp_id: str, params: Dict[str, Any]) -> None:
        """更新元件参数"""
        self._save_undo_state()
        if comp_id in self.components:
            self.components[comp_id].params.update(params)
        self._notify("params_updated")

    def update_settings(self, **kwargs) -> None:
        """更新仿真设置（支持撤销）"""
        self._save_undo_state()
        for key, value in kwargs.items():
            if hasattr(self.settings, key):
                setattr(self.settings, key, value)
        self._notify("settings_updated")

    # ---- 探针操作 ----

    def add_probe(self, probe: ProbeConfig) -> None:
        """添加探针"""
        self._save_undo_state()
        self.probes.append(probe)
        self._notify("probes_updated")

    def remove_probe(self, probe_id: str) -> None:
        """移除探针"""
        self._save_undo_state()
        self.probes = [p for p in self.probes if p.probe_id != probe_id]
        self._notify("probes_updated")

    def get_auto_voltage_probes(self) -> List[ProbeConfig]:
        """获取画布上 PROBE 元件对应的探针。

        支持 voltage_ground / voltage_between / branch_current 三种画布探针类型。
        当 result_mode="probes_only" 时，还会自动为所有非接地节点
        添加电压探针（除非用户已在该节点放置了探针）。
        """
        node_map = self.assign_node_ids()
        probes = []

        # 从画布上的 PROBE 元件构建探针
        for comp in self.components.values():
            if comp.comp_type == ComponentType.PROBE:
                probe_type = comp.params.get('probe_type', 'voltage_ground')
                unit = comp.params.get('unit', 'kV')
                # 找到 sense 引脚连接到的节点
                sense_key = (comp.comp_id, 'sense')
                target_node = node_map.get(sense_key, None)
                if target_node is not None and target_node > 0:
                    if probe_type in ('voltage', 'voltage_ground'):
                        probes.append(ProbeConfig(
                            probe_id=f"{comp.name}_V_n{target_node}",
                            probe_type="voltage",
                            node_pos=target_node,
                            node_neg=0,
                            unit=unit,
                        ))
                    elif probe_type == 'voltage_between':
                        ref_node = node_map.get((comp.comp_id, 'ref'), None)
                        if ref_node is not None and ref_node >= 0:
                            probes.append(ProbeConfig(
                                probe_id=f"{comp.name}_V_n{target_node}_n{ref_node}",
                                probe_type="voltage",
                                node_pos=target_node,
                                node_neg=ref_node,
                                unit=unit,
                            ))
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

                        # 兼容旧文件：没有显式目标时，取同节点第一个非探针元件。
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
                    elif probe_type == 'line_current':
                        # 线路电流探针：需要指定线路名、端和相序
                        line_name = comp.params.get('line_name', '')
                        line_end = comp.params.get('line_end', 'm')
                        line_phase = comp.params.get('line_phase', 0)
                        if line_name:
                            probes.append(ProbeConfig(
                                probe_id=f"{comp.name}_IL_{line_name}_{line_end}{line_phase}",
                                probe_type="line_current",
                                line_name=line_name,
                                end=line_end,
                                phase=int(line_phase),
                                unit=unit,
                            ))

        # probes_only 模式下，自动为尚未覆盖的非接地节点添加电压探针
        if self.settings.result_mode == "probes_only":
            # 收集已有电压探针覆盖的节点
            covered_nodes = set()
            for p in probes:
                if p.probe_type == "voltage" and p.node_pos is not None:
                    covered_nodes.add(p.node_pos)
            # 遍历所有节点，补充缺失的电压探针
            all_nodes = set(node_map.values())
            all_nodes.discard(0)  # 排除地节点
            for node_id in sorted(all_nodes):
                if node_id not in covered_nodes:
                    probes.append(ProbeConfig(
                        probe_id=f"auto_V_n{node_id}",
                        probe_type="voltage",
                        node_pos=node_id,
                        node_neg=0,
                        unit="kV",
                    ))

        return probes

    # ---- 子电路操作 ----

    def add_subcircuit_def(self, subdef: SubcircuitDefinition) -> None:
        """添加子电路定义"""
        self.subcircuit_defs[subdef.name] = subdef
        self._notify("subcircuit_def_added")

    def remove_subcircuit_def(self, name: str) -> None:
        """移除子电路定义"""
        if name in self.subcircuit_defs:
            del self.subcircuit_defs[name]
            self._notify("subcircuit_def_removed")

    def create_subcircuit_from_selection(
        self, selected_comp_ids: List[str], name: str
    ) -> Optional[Tuple['ComponentInstance', 'SubcircuitDefinition']]:
        """
        从选中的元件创建子电路。

        1. 提取选中元件和它们之间的内部连线
        2. 识别连到外部的引脚 → 生成端口
        3. 创建 SubcircuitDefinition
        4. 从画布移除原元件和连线，添加子电路实例

        返回: (子电路实例, 子电路定义) 或 None（如果失败）
        """
        if len(selected_comp_ids) < 2:
            return None

        selected_set = set(selected_comp_ids)

        # 1. 收集内部元件
        internal_comps = {}
        for cid in selected_comp_ids:
            if cid in self.components:
                internal_comps[cid] = self.components[cid]

        # 2. 收集连线：完全内部的 vs 连到外部的
        internal_wires = {}
        external_connections = []  # (wire_id, internal_comp, internal_pin, external_comp, external_pin)

        for wid, wire in list(self.wires.items()):
            from_in = wire.from_comp in selected_set
            to_in = wire.to_comp in selected_set
            if from_in and to_in:
                internal_wires[wid] = wire
            elif from_in and not to_in:
                # from 是内部的，to 是外部的
                external_connections.append(
                    (wid, wire.from_comp, wire.from_pin, wire.to_comp, wire.to_pin)
                )
            elif not from_in and to_in:
                external_connections.append(
                    (wid, wire.to_comp, wire.to_pin, wire.from_comp, wire.from_pin)
                )

        # 3. 创建端口（每个外部连接生成一个端口）
        ports = []
        port_pins = []
        for i, (wid, int_comp, int_pin, ext_comp, ext_pin) in enumerate(
            external_connections
        ):
            # 判断端口在哪一侧：看外部元件相对于内部元件的位置
            int_c = self.components[int_comp]
            ext_c = self.components.get(ext_comp)
            if ext_c:
                dx = ext_c.x - int_c.x
                dy = ext_c.y - int_c.y
                if abs(dx) >= abs(dy):
                    side = "right" if dx > 0 else "left"
                else:
                    side = "bottom" if dy > 0 else "top"
            else:
                side = "left"

            port_name = f"P{i + 1}"
            ports.append(SubcircuitPort(
                port_name=port_name,
                internal_comp_id=int_comp,
                internal_pin_name=int_pin,
                side=side,
            ))
            port_pins.append((wid, port_name, ext_comp, ext_pin))

        if not ports:
            # 没有外部连接 → 不需要子电路封装
            return None

        # 4. 创建子电路定义
        subdef = SubcircuitDefinition(
            name=name,
            components=internal_comps,
            wires=internal_wires,
            ports=ports,
        )

        # 5. 从画布移除原元件和连线
        self._save_undo_state()

        # 移除外部连接线
        for wid, _, _, _ in port_pins:
            if wid in self.wires:
                del self.wires[wid]

        # 移除内部连线
        for wid in internal_wires:
            if wid in self.wires:
                del self.wires[wid]

        # 移除内部元件
        for cid in selected_comp_ids:
            if cid in self.components:
                del self.components[cid]

        # 6. 创建子电路实例
        pin_defs = subdef.get_port_pins()
        pins = [Pin(name=p['name'], local_x=p['local_x'], local_y=p['local_y'])
                for p in pin_defs]

        # 计算子电路的中心位置
        xs = [c.x for c in internal_comps.values()]
        ys = [c.y for c in internal_comps.values()]
        cx = sum(xs) // len(xs) if xs else 0
        cy = sum(ys) // len(ys) if ys else 0

        sub_comp = ComponentInstance(
            comp_id=self.generate_component_id(ComponentType.SUBCIRCUIT),
            comp_type=ComponentType.SUBCIRCUIT,
            name=name,
            x=cx,
            y=cy,
            rotation=0,
            params={'subcircuit_name': name},
            pins=pins,
        )

        # 7. 添加子电路到模型
        self.add_subcircuit_def(subdef)
        self.components[sub_comp.comp_id] = sub_comp

        # 8. 重新连接外部线（从外部元件连到子电路端口引脚）
        import uuid as _uuid
        for wid, port_name, ext_comp, ext_pin in port_pins:
            new_wire = Wire(
                wire_id=f"W_{_uuid.uuid4().hex[:8]}",
                from_comp=sub_comp.comp_id,
                from_pin=port_name,
                to_comp=ext_comp,
                to_pin=ext_pin,
            )
            self.wires[new_wire.wire_id] = new_wire

        self._notify("component_added")
        return sub_comp, subdef

    def rotate_component(self, comp_id: str, angle: int = 90) -> None:
        """旋转元件"""
        self._save_undo_state()
        if comp_id in self.components:
            comp = self.components[comp_id]
            comp.rotation = (comp.rotation + angle) % 360
            self._notify("component_rotated")

    # ---- 连线操作 ----

    def add_wire(self, wire: Wire) -> None:
        """添加连线"""
        self._save_undo_state()
        self.wires[wire.wire_id] = wire
        self._notify("wire_added")

    def remove_wire(self, wire_id: str) -> None:
        """移除连线"""
        self._save_undo_state()
        if wire_id in self.wires:
            del self.wires[wire_id]
            self._notify("wire_removed")

    def get_wires_for_component(self, comp_id: str) -> List[Wire]:
        """获取元件相关的所有连线"""
        return [
            wire for wire in self.wires.values()
            if wire.from_comp == comp_id or wire.to_comp == comp_id
        ]

    # ---- 节点分配 (Union-Find 算法) ----

    def assign_node_ids(self) -> Dict[tuple, int]:
        """
        遍历所有连线，用 Union-Find 合并相连引脚，
        为每个等价类分配一个唯一节点编号。
        接地引脚（GND元件的引脚）固定为节点 0。
        返回: {(comp_id, pin_name): node_id}
        """
        # 1. 收集所有引脚
        parent: Dict[tuple, tuple] = {}

        def find(x: tuple) -> tuple:
            if x not in parent:
                parent[x] = x
            while parent[x] != x:
                parent[x] = parent[parent[x]]  # 路径压缩
                x = parent[x]
            return x

        def union(a: tuple, b: tuple):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        all_pins = []
        for comp in self.components.values():
            for pin in comp.pins:
                key = (comp.comp_id, pin.name)
                parent[key] = key
                all_pins.append((comp, pin))

        # 2. 根据连线合并引脚
        for wire in self.wires.values():
            a = (wire.from_comp, wire.from_pin)
            b = (wire.to_comp, wire.to_pin)
            if a in parent and b in parent:
                union(a, b)

        # 3. 检查哪些等价类包含接地引脚
        ground_roots = set()
        for comp, pin in all_pins:
            if comp.comp_type == ComponentType.GROUND:
                ground_roots.add(find((comp.comp_id, pin.name)))

        # 4. 为每个等价类分配稳定节点编号
        groups: Dict[tuple, List[Tuple[str, str]]] = {}
        for comp, pin in all_pins:
            key = (comp.comp_id, pin.name)
            root = find(key)
            groups.setdefault(root, []).append(key)

        group_to_node: Dict[tuple, int] = {}
        for root in ground_roots:
            group_to_node[root] = 0

        next_id = 1
        sorted_roots = sorted(
            (root for root in groups if root not in ground_roots),
            key=lambda root: min(groups[root]),
        )
        for root in sorted_roots:
            group_to_node[root] = next_id
            next_id += 1

        result: Dict[tuple, int] = {}
        for comp, pin in all_pins:
            key = (comp.comp_id, pin.name)
            result[key] = group_to_node[find(key)]

        # 5. 更新引脚的 node_id
        for comp in self.components.values():
            for pin in comp.pins:
                key = (comp.comp_id, pin.name)
                if key in result:
                    pin.node_id = result[key]

        return result

    # ---- 仿真设置 ----
    # update_settings(**kwargs) 已在上方定义（第315行），支持关键字参数更新

    # ---- 清除/重置 ----

    def clear(self):
        """清空所有数据"""
        self._save_undo_state()
        self.components.clear()
        self.wires.clear()
        self.probes.clear()
        self._id_counters.clear()
        self._next_node_id = 1
        self._notify("cleared")

    # ---- 序列化 ----

    def to_dict(self) -> Dict:
        """导出为字典"""
        return {
            'schema_version': self.CURRENT_SCHEMA_VERSION,
            'version': '3.0',
            'settings': self.settings.to_dict(),
            'components': {
                k: v.to_dict() for k, v in self.components.items()
            },
            'wires': {
                k: v.to_dict() for k, v in self.wires.items()
            },
            'probes': [p.to_dict() for p in self.probes],
            'subcircuit_defs': {
                k: v.to_dict() for k, v in self.subcircuit_defs.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'CircuitModel':
        """从字典导入"""
        if cls._is_legacy_format(data):
            return cls._load_legacy_format(data)
        return cls._load_current_format(data)

    @staticmethod
    def _is_legacy_format(data: Dict) -> bool:
        components = data.get('components')
        if not isinstance(components, dict):
            return False
        if 'simulation_config' in data or 'nodes' in data:
            return True
        if not components:
            return False
        sample = next(iter(components.values()))
        return isinstance(sample, dict) and 'type' in sample and 'node_from' in sample

    @classmethod
    def _load_current_format(cls, data: Dict) -> 'CircuitModel':
        model = cls()

        schema_version = data.get('schema_version')
        if schema_version is not None and schema_version > cls.CURRENT_SCHEMA_VERSION:
            raise ValueError(
                f"不支持的文件 schema_version={schema_version}，"
                f"当前最高支持 {cls.CURRENT_SCHEMA_VERSION}"
            )

        if 'settings' in data:
            model.settings = SimSettings.from_dict(data['settings'])

        if 'components' in data:
            model.components = {
                k: ComponentInstance.from_dict(v)
                for k, v in data['components'].items()
            }

        if 'wires' in data:
            model.wires = {
                k: Wire.from_dict(v)
                for k, v in data['wires'].items()
            }

        if 'probes' in data:
            model.probes = [
                ProbeConfig.from_dict(p) for p in data['probes']
            ]

        if 'subcircuit_defs' in data:
            model.subcircuit_defs = {
                k: SubcircuitDefinition.from_dict(v)
                for k, v in data['subcircuit_defs'].items()
            }

        model._rebuild_id_counters()
        return model

    @classmethod
    def _load_legacy_format(cls, data: Dict) -> 'CircuitModel':
        from .component_lib import create_component_pins

        model = cls()
        if 'simulation_config' in data:
            model.settings = SimSettings.from_dict(data['simulation_config'])

        legacy_components = data.get('components', {})
        node_groups: Dict[int, List[Tuple[str, str]]] = {}

        for comp_key, comp_data in legacy_components.items():
            comp_type = cls._legacy_component_type(comp_data)
            n_phases = cls._legacy_phase_count(comp_type, comp_data)
            pins = create_component_pins(comp_type, n_phases)
            pin_node_ids = cls._legacy_pin_node_ids(comp_type, comp_data, pins)
            for pin in pins:
                pin.node_id = pin_node_ids.get(pin.name)
                if pin.node_id is not None:
                    node_groups.setdefault(pin.node_id, []).append((comp_data.get('id', comp_key), pin.name))

            position = comp_data.get('position', [0, 0])
            x = int(round(position[0])) if len(position) > 0 else 0
            y = int(round(position[1])) if len(position) > 1 else 0
            model.components[comp_data.get('id', comp_key)] = ComponentInstance(
                comp_id=comp_data.get('id', comp_key),
                comp_type=comp_type,
                name=comp_data.get('name', comp_data.get('label', comp_key)),
                x=x,
                y=y,
                rotation=int(comp_data.get('rotation', 0)),
                params=cls._legacy_params_to_current(comp_type, comp_data),
                pins=pins,
            )

        cls._build_legacy_wires(model, node_groups)
        model._rebuild_id_counters()
        return model

    @staticmethod
    def _legacy_component_type(comp_data: Dict) -> ComponentType:
        type_map = {
            'BERGERON_LINE': ComponentType.BERGERON,
            'Berg': ComponentType.BERGERON,
            'SRL': ComponentType.SERIES_RL,
            'SeriesRL': ComponentType.SERIES_RL,
            'LPM': ComponentType.LPM,
            'LCP_OHL': ComponentType.LCP_OHL,
            'LCP_SC': ComponentType.LCP_SINGLE_CABLE,
            'LCP_3C': ComponentType.LCP_THREE_CABLE,
            'UMEC': ComponentType.UMEC_TRANSFORMER,
        }
        raw_type = comp_data.get('type', 'R')
        if raw_type in type_map:
            return type_map[raw_type]
        try:
            return ComponentType(raw_type)
        except ValueError:
            return ComponentType.RESISTOR  # fallback

    @staticmethod
    def _legacy_phase_count(comp_type: ComponentType, comp_data: Dict) -> int:
        if comp_type not in (ComponentType.ULM, ComponentType.LCP_OHL,
                             ComponentType.LCP_SINGLE_CABLE,
                             ComponentType.LCP_THREE_CABLE):
            return 1

        params = comp_data.get('parameters', {})
        candidate = (
            params.get('n_phases')
            or params.get('nc')
            or len(params.get('nodes_k', []))
            or len(params.get('nodes_m', []))
        )
        if not candidate:
            extra_nodes = comp_data.get('extra_nodes', [])
            candidate = max(1, (len(extra_nodes) + 2) // 2)
        return max(1, int(candidate))

    @classmethod
    def _legacy_params_to_current(cls, comp_type: ComponentType, comp_data: Dict) -> Dict[str, Any]:
        params = dict(comp_data.get('parameters', {}))

        if comp_type == ComponentType.VOLTAGE_SOURCE:
            voltage_type = str(params.get('voltage_type', 'DC')).strip().lower()
            if voltage_type == 'ac':
                return {
                    'voltage_func': {
                        'mode': 'ac',
                        'amplitude': params.get('V', 0.0),
                        'frequency': params.get('frequency', 50.0),
                        'phase': params.get('phase', 0.0),
                    }
                }
            if voltage_type == 'custom':
                return {
                    'voltage_func': {
                        'mode': 'custom',
                        'expression': params.get('expression', 'lambda t: 0.0'),
                    }
                }
            return {
                'voltage_func': {
                    'mode': 'dc',
                    'value': params.get('V', 0.0),
                }
            }

        if comp_type == ComponentType.CURRENT_SOURCE:
            current_type = str(params.get('current_type', 'DC')).strip().lower()
            if current_type == 'ac':
                return {
                    'current_func': {
                        'mode': 'ac',
                        'amplitude': params.get('I', 0.0),
                        'frequency': params.get('frequency', 50.0),
                        'phase': params.get('phase', 0.0),
                    }
                }
            if current_type == 'lightning':
                return {
                    'current_func': {
                        'mode': 'lightning',
                        'waveform_type': params.get('lightning_type', '8/20'),
                        'peak': params.get('lightning_peak', params.get('I', 0.0)),
                        't_start': params.get('lightning_t_start', 0.0),
                    }
                }
            if current_type == 'custom':
                return {
                    'current_func': {
                        'mode': 'custom',
                        'expression': params.get('expression', 'lambda t: 0.0'),
                    }
                }
            return {
                'current_func': {
                    'mode': 'dc',
                    'value': params.get('I', 0.0),
                }
            }

        if comp_type == ComponentType.ULM:
            return {
                'fitulm_file': params.get('fitulm_file', params.get('file_path', '')),
                'length': params.get('length', 20000.0),
                'n_phases': cls._legacy_phase_count(comp_type, comp_data),
            }

        if comp_type == ComponentType.SWITCH:
            return {
                't_close': params.get('t_close', 0.0),
                't_open': params.get('t_open', 1e30),
                'R_closed': params.get('R_closed', 1e-6),
                'R_open': params.get('R_open', 1e8),
            }

        if comp_type == ComponentType.BERGERON:
            # 新内核使用 Zc/length，旧格式 tau 或 R/L/C/length 自动迁移
            result = {}
            result['Zc'] = params.get('Zc', 300.0)

            # 新格式：已有 length 则直接用
            if 'length' in params:
                result['length'] = params['length']
            # 旧格式1：已有 tau，length 取默认值（无法从 tau 反算）
            elif 'tau' in params:
                result['length'] = params.get('_legacy_length', 15000.0)
            # 旧格式2：R/L/C/length 计算 Zc，保留原始 length
            else:
                R = params.get('R', 0.03)
                L = params.get('L', 1.0)
                C = params.get('C', 11.0)
                old_length = params.get('length', 15000.0)
                L_henry = L * 1e-3 * (old_length / 1000.0)   # mH/km -> H
                C_farad = C * 1e-9 * (old_length / 1000.0)   # nF/km -> F
                if C_farad > 0 and L_henry > 0:
                    result['Zc'] = (L_henry / C_farad) ** 0.5
                result['length'] = old_length
            return result

        if comp_type == ComponentType.MOA:
            # 新内核使用 V-I 断点或文件，旧格式 Vref/I0/alpha 保留兼容
            return {
                'vi_file': params.get('vi_file', ''),
                'rated_voltage': params.get('rated_voltage', params.get('Vref', 1e3)),
                'voltage_is_pu': params.get('voltage_is_pu', True),
                'breakpoints': params.get('breakpoints', []),
                # 保留旧参数兼容
                '_legacy_Vref': params.get('Vref', 1e3),
                '_legacy_I0': params.get('I0', 1e-3),
                '_legacy_alpha': params.get('alpha', 25.0),
                '_legacy_n_segments': params.get('n_segments', 50),
            }

        if comp_type == ComponentType.SERIES_RL:
            return {
                'R': params.get('R', 10.0),
                'L': params.get('L', 1e-3),
            }

        if comp_type == ComponentType.LPM:
            return {
                'gap_length': params.get('gap_length', 2.5),
                'k': params.get('k', 1e-6),
                'E0': params.get('E0', 600.0),
                'R_arc': params.get('R_arc', 1.0),
                'altitude_m': params.get('altitude_m', 0.0),
                'allow_extinction': params.get('allow_extinction', True),
                'extinction_current': params.get('extinction_current', 0.1),
            }

        if comp_type == ComponentType.UMEC_TRANSFORMER:
            # 新格式：已有 S_mva 则直接用
            if 'S_mva' in params:
                return {k: v for k, v in params.items() if not k.startswith('_')}
            # 旧格式迁移：Sn/f0/V1/V2/Xl_pu/Rm_pu/Xm_pu → 新格式
            result = {
                'S_mva': params.get('Sn', 100.0),
                'freq': params.get('f0', 50.0),
                'V1_kV': params.get('V1', 230.0),
                'V2_kV': params.get('V2', 115.0),
                'wtype1': 'Y_gnd',
                'wtype2': 'Delta',
                'X_leak_pu': params.get('Xl_pu', 0.12),
                'Im_percent': 1.0,
                'NLL_pu': 0.0,
                'CL_pu': 0.0,
            }
            return result

        if comp_type in (ComponentType.LCP_OHL, ComponentType.LCP_SINGLE_CABLE,
                         ComponentType.LCP_THREE_CABLE):
            return params  # LCP 参数直接透传

        allowed_keys = {'R', 'L', 'C', 'Rp'}
        return {key: value for key, value in params.items() if key in allowed_keys}

    @classmethod
    def _legacy_pin_node_ids(
        cls,
        comp_type: ComponentType,
        comp_data: Dict,
        pins: List[Pin],
    ) -> Dict[str, Optional[int]]:
        node_from = comp_data.get('node_from')
        node_to = comp_data.get('node_to')
        params = comp_data.get('parameters', {})

        if comp_type == ComponentType.GROUND:
            return {'gnd': 0}
        if comp_type == ComponentType.VOLTAGE_SOURCE:
            return {'node_pos': node_from, 'node_neg': node_to}
        if comp_type in {
            ComponentType.RESISTOR,
            ComponentType.INDUCTOR,
            ComponentType.CAPACITOR,
            ComponentType.SWITCH,
            ComponentType.CURRENT_SOURCE,
            ComponentType.MOA,
        }:
            return {'nf': node_from, 'nt': node_to}
        if comp_type == ComponentType.BERGERON:
            return {'nk': node_from, 'nm': node_to}
        if comp_type == ComponentType.UMEC_TRANSFORMER:
            # 旧格式：2引脚 (node_pos, node_neg) → 映射到 H_A 和 X_A
            return {
                'H_A': node_from,
                'H_B': node_from,
                'H_C': node_from,
                'X_A': node_to,
                'X_B': node_to,
                'X_C': node_to,
            }
        if comp_type != ComponentType.ULM:
            return {}

        if len(pins) == 2:
            return {pins[0].name: node_from, pins[1].name: node_to}

        nodes_k = list(params.get('nodes_k', []))
        nodes_m = list(params.get('nodes_m', []))
        phase_count = len(pins) // 2

        if not nodes_k or not nodes_m:
            extra_nodes = list(comp_data.get('extra_nodes', []))
            fallback = [node_from] + extra_nodes + [node_to]
            midpoint = min(phase_count, len(fallback))
            nodes_k = fallback[:midpoint]
            nodes_m = fallback[midpoint: midpoint + phase_count]

        pin_nodes: Dict[str, Optional[int]] = {}
        for index in range(phase_count):
            pin_nodes[f'nk_{index}'] = nodes_k[index] if index < len(nodes_k) else None
            pin_nodes[f'nm_{index}'] = nodes_m[index] if index < len(nodes_m) else None
        return pin_nodes

    @classmethod
    def _build_legacy_wires(
        cls,
        model: 'CircuitModel',
        node_groups: Dict[int, List[Tuple[str, str]]],
    ):
        next_wire_id = 1

        def make_wire_id() -> str:
            nonlocal next_wire_id
            wire_id = f"W_{next_wire_id:03d}"
            next_wire_id += 1
            return wire_id

        grounded_pins = sorted(set(node_groups.get(0, [])))
        if grounded_pins:
            ground_components = [
                comp for comp in model.components.values()
                if comp.comp_type == ComponentType.GROUND and comp.get_pin('gnd') is not None
            ]
            if ground_components:
                ground_anchor = (ground_components[0].comp_id, 'gnd')
            else:
                ground_component = ComponentInstance(
                    comp_id='GND_000',
                    comp_type=ComponentType.GROUND,
                    name='GND',
                    x=0,
                    y=0,
                    rotation=0,
                    params={},
                    pins=[Pin(name='gnd', local_x=0, local_y=0, node_id=0)],
                )
                model.components[ground_component.comp_id] = ground_component
                ground_anchor = (ground_component.comp_id, 'gnd')

            for comp_id, pin_name in grounded_pins:
                if (comp_id, pin_name) == ground_anchor:
                    continue
                wire_id = make_wire_id()
                model.wires[wire_id] = Wire(
                    wire_id=wire_id,
                    from_comp=ground_anchor[0],
                    from_pin=ground_anchor[1],
                    to_comp=comp_id,
                    to_pin=pin_name,
                )

        for node_id in sorted(node for node in node_groups if node != 0):
            pins = sorted(set(node_groups[node_id]))
            if len(pins) < 2:
                continue
            anchor_comp, anchor_pin = pins[0]
            for comp_id, pin_name in pins[1:]:
                wire_id = make_wire_id()
                model.wires[wire_id] = Wire(
                    wire_id=wire_id,
                    from_comp=anchor_comp,
                    from_pin=anchor_pin,
                    to_comp=comp_id,
                    to_pin=pin_name,
                )
