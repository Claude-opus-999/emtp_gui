"""
EMTP 电路仿真 GUI - 电路数据模型
核心数据结构：元件、连线、节点分配、Undo/Redo
"""

from dataclasses import dataclass, field
from typing import Optional, Callable, Dict, List, Any, Tuple
from enum import Enum
import uuid

PIN_GRID_SIZE = 5


def _snap_pin_coord(value: float) -> float:
    return round(float(value) / PIN_GRID_SIZE) * PIN_GRID_SIZE


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
    SUBCIRCUIT_PORT = "PORT"
    SUBCIRCUIT = "SUB"             # 新增：子电路


@dataclass
class Pin:
    """元件的电气端口"""
    name: str           # 引脚名称: "nf", "nt", "node_pos", "node_neg", "nk", "nm"
    local_x: float     # 相对于元件锚点的 X 偏移
    local_y: float     # 相对于元件锚点的 Y 偏移
    node_id: Optional[int] = None  # 连接到的节点编号（None=未连接）
    display_name: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'local_x': self.local_x,
            'local_y': self.local_y,
            'node_id': self.node_id,
            'display_name': self.display_name,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Pin':
        return cls(
            name=data.get('name', ''),
            local_x=_snap_pin_coord(data.get('local_x', 0)),
            local_y=_snap_pin_coord(data.get('local_y', 0)),
            node_id=data.get('node_id'),
            display_name=data.get('display_name'),
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
class ValidationIssue:
    level: str
    code: str
    message: str
    location: str = ""


@dataclass
class ValidationResult:
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(issue.level == "error" for issue in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(issue.level == "warning" for issue in self.issues)


@dataclass
class SubcircuitPort:
    """子电路暴露的端口 — 连接内部引脚与外部世界"""
    port_name: str              # 外部端口名，如 "P1", "P2"
    internal_comp_id: str       # 内部元件 comp_id
    internal_pin_name: str      # 内部引脚名
    side: str = "left"          # 端口在盒子上的位置: left / right / top / bottom
    order: int = 0
    description: str = ""
    port_id: str = ""
    kind: str = "electrical"
    default_side: str = ""
    default_offset: Optional[float] = None
    default_order: Optional[int] = None
    visible: bool = True

    def __post_init__(self):
        if not self.port_id:
            self.port_id = self.port_name
        if not self.default_side:
            self.default_side = self.side
        if self.default_order is None:
            self.default_order = self.order

    @property
    def name(self) -> str:
        return self.port_name

    @name.setter
    def name(self, value: str):
        self.port_name = value

    @property
    def internal_pin(self) -> str:
        return self.internal_pin_name

    @internal_pin.setter
    def internal_pin(self, value: str):
        self.internal_pin_name = value

    def pin_name(self) -> str:
        return self.port_id

    def to_dict(self) -> Dict:
        return {
            'port_name': self.port_name,
            'internal_comp_id': self.internal_comp_id,
            'internal_pin_name': self.internal_pin_name,
            'side': self.side,
            'order': self.order,
            'description': self.description,
            'port_id': self.port_id,
            'name': self.port_name,
            'kind': self.kind,
            'internal_pin': self.internal_pin_name,
            'default_side': self.default_side,
            'default_offset': self.default_offset,
            'default_order': self.default_order,
            'visible': self.visible,
        }

    @classmethod
    def from_dict(cls, data: Dict, index: int = 0) -> 'SubcircuitPort':
        port_name = data.get('name', data.get('port_name', ''))
        port_id = data.get('port_id') or f"P_{index + 1:03d}"
        default_side = data.get('default_side', data.get('side', 'left'))
        default_order = data.get('default_order', data.get('order', index))
        return cls(
            port_name=port_name,
            internal_comp_id=data.get('internal_comp_id', ''),
            internal_pin_name=data.get('internal_pin', data.get('internal_pin_name', '')),
            side=data.get('side', default_side),
            order=data.get('order', default_order),
            description=data.get('description', ''),
            port_id=port_id,
            kind=data.get('kind', 'electrical'),
            default_side=default_side,
            default_offset=data.get('default_offset'),
            default_order=default_order,
            visible=data.get('visible', True),
        )


@dataclass
class SubcircuitDefinition:
    """子电路定义（蓝图）— 可被多个实例引用"""
    name: str                                           # 子电路名称，如 "RL_filter"
    components: Dict[str, ComponentInstance] = field(default_factory=dict)
    wires: Dict[str, Wire] = field(default_factory=dict)
    ports: List[SubcircuitPort] = field(default_factory=list)
    exposed_params: Dict[str, str] = field(default_factory=dict)
    symbol_width: float = 140.0
    symbol_height: float = 100.0

    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'components': {k: v.to_dict() for k, v in self.components.items()},
            'wires': {k: v.to_dict() for k, v in self.wires.items()},
            'ports': [p.to_dict() for p in self.ports],
            'exposed_params': self.exposed_params,
            'symbol_width': self.symbol_width,
            'symbol_height': self.symbol_height,
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
            ports=[
                SubcircuitPort.from_dict(p, index=i)
                for i, p in enumerate(data.get('ports', []))
            ],
            exposed_params=data.get('exposed_params', {}),
            symbol_width=data.get('symbol_width', 140.0),
            symbol_height=data.get('symbol_height', 100.0),
        )

    def get_port(self, port_id: str) -> Optional[SubcircuitPort]:
        for port in self.ports:
            if port.port_id == port_id:
                return port
        return None

    def get_port_by_name(self, name: str) -> Optional[SubcircuitPort]:
        for port in self.ports:
            if port.port_name == name:
                return port
        return None

    def find_port(self, identity: str) -> Optional[SubcircuitPort]:
        return self.get_port(identity) or self.get_port_by_name(identity)

    def next_port_id(self) -> str:
        used = {port.port_id for port in self.ports}
        i = 1
        while True:
            port_id = f"P_{i:03d}"
            if port_id not in used:
                return port_id
            i += 1

    def get_effective_port_layout(
        self,
        port: SubcircuitPort,
        instance: Optional[ComponentInstance] = None,
    ) -> Dict[str, Any]:
        override = {}
        if instance is not None:
            override = (
                instance.params.get("port_layout_overrides", {}) or {}
            ).get(port.port_id, {})
        return {
            "side": override.get("side", port.side or port.default_side),
            "offset": override.get("offset", port.default_offset),
            "order": override.get(
                "order",
                port.order if port.order is not None else port.default_order,
            ),
        }

    def get_port_pins(self, instance: Optional[ComponentInstance] = None) -> List[Dict]:
        """Generate external SUBCIRCUIT instance pins using stable port_id names."""
        side_order = {
            "left": 0,
            "right": 1,
            "top": 2,
            "bottom": 3,
        }
        rows = []
        for port in self.ports:
            if not port.visible:
                continue
            layout = self.get_effective_port_layout(port, instance)
            rows.append((port, layout["side"], layout["offset"], int(layout["order"])))
        rows.sort(key=lambda row: (side_order.get(row[1], 99), row[3], row[0].port_id))

        grouped = {"left": [], "right": [], "top": [], "bottom": []}
        for row in rows:
            grouped.setdefault(row[1], []).append(row)

        pin_defs = []
        half_w = float(self.symbol_width) / 2.0
        half_h = float(self.symbol_height) / 2.0

        def distributed_offset(index: int, count: int) -> float:
            if count <= 1:
                return 0.5
            return (index + 1) / (count + 1)

        for side in ("left", "right", "top", "bottom"):
            side_rows = grouped.get(side, [])
            for i, (port, _side, offset, _order) in enumerate(side_rows):
                actual_offset = distributed_offset(i, len(side_rows)) if offset is None else float(offset)
                actual_offset = max(0.0, min(1.0, actual_offset))
                if side == "left":
                    x = -half_w
                    y = -half_h + actual_offset * self.symbol_height
                elif side == "right":
                    x = half_w
                    y = -half_h + actual_offset * self.symbol_height
                elif side == "top":
                    x = -half_w + actual_offset * self.symbol_width
                    y = -half_h
                else:
                    x = -half_w + actual_offset * self.symbol_width
                    y = half_h
                pin_defs.append({
                    'name': port.port_id,
                    'display_name': port.port_name,
                    'local_x': x,
                    'local_y': y,
                    'kind': port.kind,
                })

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
    auto_voltage_probes: bool = False
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
            'auto_voltage_probes': self.auto_voltage_probes,
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
            auto_voltage_probes=data.get('auto_voltage_probes', False),
            allow_dense_fallback=data.get('allow_dense_fallback', True),
            dense_fallback_max_size=data.get('dense_fallback_max_size', 300),
            lightning_type=data.get('lightning_type', '8/20'),
            lightning_peak=data.get('lightning_peak', 10000.0),
            lightning_t_start=data.get('lightning_t_start', 10e-6),
        )


CURRENT_SCHEMA_VERSION = 4


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
    COMPACT_SYMBOL_PIN_TYPES = frozenset({
        ComponentType.RESISTOR,
        ComponentType.INDUCTOR,
        ComponentType.CAPACITOR,
        ComponentType.SERIES_RL,
        ComponentType.SWITCH,
        ComponentType.VOLTAGE_SOURCE,
        ComponentType.CURRENT_SOURCE,
        ComponentType.MOA,
        ComponentType.LPM,
        ComponentType.GROUND,
    })

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
        self._selected_ids: List[str] = []

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
        self._selected_ids = [comp_id] if comp_id in self.components else []
        self._notify("component_selected")

    def select_components(self, comp_ids: List[str]):
        """选中多个元件"""
        self._selected_ids = [cid for cid in comp_ids if cid in self.components]
        self._notify("component_selected")

    def clear_selection(self):
        """清除选择"""
        self._selected_ids.clear()
        self._notify("component_selected")

    def get_selected_components(self) -> List[ComponentInstance]:
        """获取选中的元件列表"""
        return [
            self.components[cid]
            for cid in self._selected_ids
            if cid in self.components
        ]

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
        self._migrate_subcircuit_ports_to_stable_ids()

    def _push_undo_snapshot(self, snapshot: Dict):
        """压入一个指定快照到撤销栈"""
        self._undo_stack.append(snapshot)
        self._redo_stack.clear()
        if len(self._undo_stack) > 50:
            self._undo_stack.pop(0)

    def _rebuild_id_counters(self):
        """根据现有元件重新构建 ID 计数器"""
        self._id_counters = {}
        for comp in self.iter_all_components():
            self._sync_counter_for_component(comp)
        for wire in self.iter_all_wires():
            self._sync_counter_for_object_id(wire.wire_id)

    def _sync_counter_for_component(self, comp: ComponentInstance):
        """把一个元件实例的编号信息同步到计数器"""
        self._sync_counter_for_object_id(comp.comp_id, comp.comp_type.value)

    def _sync_counter_for_object_id(self, object_id: str, expected_prefix: Optional[str] = None):
        prefix, number = self._parse_id(object_id)
        if prefix is None:
            return
        if expected_prefix is not None:
            prefix = expected_prefix
        self._id_counters[prefix] = max(
            self._id_counters.get(prefix, 0),
            number,
        )

    @staticmethod
    def _parse_id(object_id: str) -> Tuple[Optional[str], Optional[int]]:
        if not object_id or "_" not in object_id:
            return None, None
        prefix, suffix = object_id.rsplit('_', 1)
        if suffix.isdigit():
            return prefix, int(suffix)
        return None, None

    def iter_all_components(self):
        for comp in self.components.values():
            yield comp
        for subdef in self.subcircuit_defs.values():
            for comp in subdef.components.values():
                yield comp

    def iter_all_wires(self):
        for wire in self.wires.values():
            yield wire
        for subdef in self.subcircuit_defs.values():
            for wire in subdef.wires.values():
                yield wire

    def _normalize_compact_symbol_pins(self):
        from .component_lib import create_component_pins

        for comp in self.iter_all_components():
            if comp.comp_type not in self.COMPACT_SYMBOL_PIN_TYPES:
                continue
            template_pins = create_component_pins(
                comp.comp_type,
                params=comp.params,
            )
            existing_by_name = {pin.name: pin for pin in comp.pins}
            if set(existing_by_name) != {pin.name for pin in template_pins}:
                continue
            comp.pins = [
                Pin(
                    name=pin.name,
                    local_x=pin.local_x,
                    local_y=pin.local_y,
                    node_id=existing_by_name[pin.name].node_id,
                    display_name=existing_by_name[pin.name].display_name,
                )
                for pin in template_pins
            ]

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
        当 auto_voltage_probes=True 时，还会自动为所有非接地节点
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

        # 用户启用自动电压探针时，补充尚未覆盖的非接地节点。
        if self.settings.auto_voltage_probes:
            # 收集已有电压探针覆盖的节点
            covered_nodes = set()
            for p in probes:
                if p.probe_type == "voltage" and p.node_pos is not None:
                    covered_nodes.add(p.node_pos)
            for p in self.probes:
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

    def _pin_names(self, comp: ComponentInstance) -> set:
        return {pin.name for pin in comp.pins}

    def _issue(
        self,
        level: str,
        code: str,
        message: str,
        location: str = "",
    ) -> ValidationIssue:
        return ValidationIssue(level=level, code=code, message=message, location=location)

    def format_validation_errors(self, validation: ValidationResult) -> str:
        return "\n".join(
            f"[{issue.level}] {issue.code}: {issue.message}"
            for issue in validation.issues
        )

    def validate_subcircuit_definition(self, subdef_name: str) -> ValidationResult:
        issues: List[ValidationIssue] = []
        subdef = self.subcircuit_defs.get(subdef_name)
        if subdef is None:
            return ValidationResult([
                self._issue(
                    "error",
                    "subcircuit_definition_not_found",
                    f"Subcircuit definition not found: {subdef_name}",
                    subdef_name,
                )
            ])

        if not subdef.components:
            issues.append(self._issue(
                "warning",
                "empty_subcircuit",
                f"Subcircuit {subdef_name} has no internal components.",
                subdef_name,
            ))
        elif not any(
            comp.comp_type != ComponentType.SUBCIRCUIT_PORT
            for comp in subdef.components.values()
        ):
            issues.append(self._issue(
                "warning",
                "subcircuit_has_only_ports",
                f"Subcircuit {subdef_name} contains only ports.",
                subdef_name,
            ))

        seen_port_ids = set()
        duplicate_port_ids = set()
        seen_ports = set()
        duplicate_ports = set()
        for port in subdef.ports:
            if port.port_id in seen_port_ids:
                duplicate_port_ids.add(port.port_id)
            seen_port_ids.add(port.port_id)
            if not port.port_id:
                issues.append(self._issue(
                    "error",
                    "empty_port_id",
                    f"Subcircuit {subdef_name} has a port with empty port_id.",
                    subdef_name,
                ))
            if not port.port_name.strip():
                issues.append(self._issue(
                    "error",
                    "empty_port_name",
                    f"Subcircuit {subdef_name} has a port with empty name.",
                    subdef_name,
                ))
            if port.port_name in seen_ports:
                duplicate_ports.add(port.port_name)
            seen_ports.add(port.port_name)
        for port_id in sorted(duplicate_port_ids):
            issues.append(self._issue(
                "error",
                "duplicate_port_id",
                f"Subcircuit {subdef_name} has duplicate port id: {port_id}",
                subdef_name,
            ))
        for port_name in sorted(duplicate_ports):
            issues.append(self._issue(
                "error",
                "duplicate_port_name",
                f"Subcircuit {subdef_name} has duplicate port name: {port_name}",
                subdef_name,
            ))

        for port in subdef.ports:
            comp = subdef.components.get(port.internal_comp_id)
            location = f"{subdef_name}.{port.port_name}"
            if comp is None:
                issues.append(self._issue(
                    "error",
                    "port_missing_component",
                    f"Port {port.port_name} references missing component {port.internal_comp_id}.",
                    location,
                ))
                continue
            if comp.comp_type != ComponentType.SUBCIRCUIT_PORT:
                issues.append(self._issue(
                    "error",
                    "port_component_wrong_type",
                    f"Port {port.port_name} references non-port component {port.internal_comp_id}.",
                    location,
                ))
            comp_port_id = comp.params.get("port_id")
            if comp_port_id and comp_port_id != port.port_id:
                issues.append(self._issue(
                    "error",
                    "port_component_id_mismatch",
                    f"Port {port.port_name} id {port.port_id} does not match {comp.comp_id} port_id {comp_port_id}.",
                    location,
                ))
            if port.internal_pin_name not in self._pin_names(comp):
                issues.append(self._issue(
                    "error",
                    "port_missing_pin",
                    f"Port {port.port_name} references missing pin {port.internal_pin_name}.",
                    location,
                ))
            if comp.comp_type == ComponentType.SUBCIRCUIT_PORT:
                connected = any(
                    wire.from_comp == comp.comp_id or wire.to_comp == comp.comp_id
                    for wire in subdef.wires.values()
                )
                if not connected:
                    issues.append(self._issue(
                        "warning",
                        "floating_internal_port",
                        f"Port {port.port_name} internal port {comp.comp_id} is not wired.",
                        location,
                    ))
            if port.default_side not in {"left", "right", "top", "bottom"}:
                issues.append(self._issue(
                    "error",
                    "invalid_port_side",
                    f"Port {port.port_name} has invalid side {port.default_side}.",
                    location,
                ))
            if port.default_offset is not None and not 0.0 <= float(port.default_offset) <= 1.0:
                issues.append(self._issue(
                    "error",
                    "invalid_port_offset",
                    f"Port {port.port_name} has invalid offset {port.default_offset}.",
                    location,
                ))

        for wire in subdef.wires.values():
            from_comp = subdef.components.get(wire.from_comp)
            to_comp = subdef.components.get(wire.to_comp)
            location = f"{subdef_name}.{wire.wire_id}"
            if from_comp is None:
                issues.append(self._issue(
                    "error",
                    "wire_missing_component",
                    f"Wire {wire.wire_id} references missing component {wire.from_comp}.",
                    location,
                ))
            elif wire.from_pin not in self._pin_names(from_comp):
                issues.append(self._issue(
                    "error",
                    "wire_missing_pin",
                    f"Wire {wire.wire_id} references missing pin {wire.from_comp}.{wire.from_pin}.",
                    location,
                ))
            if to_comp is None:
                issues.append(self._issue(
                    "error",
                    "wire_missing_component",
                    f"Wire {wire.wire_id} references missing component {wire.to_comp}.",
                    location,
                ))
            elif wire.to_pin not in self._pin_names(to_comp):
                issues.append(self._issue(
                    "error",
                    "wire_missing_pin",
                    f"Wire {wire.wire_id} references missing pin {wire.to_comp}.{wire.to_pin}.",
                    location,
                ))

        return ValidationResult(issues)

    def iter_subcircuit_instances(self, subdef_name: Optional[str] = None):
        for comp in self.components.values():
            if comp.comp_type == ComponentType.SUBCIRCUIT:
                if subdef_name is None or comp.params.get("subcircuit_name") == subdef_name:
                    yield self.components, self.wires, comp

        for parent_subdef in self.subcircuit_defs.values():
            for comp in parent_subdef.components.values():
                if comp.comp_type == ComponentType.SUBCIRCUIT:
                    if subdef_name is None or comp.params.get("subcircuit_name") == subdef_name:
                        yield parent_subdef.components, parent_subdef.wires, comp

    def _find_subcircuit_instance_or_raise(self, instance_comp_id: str) -> ComponentInstance:
        for _components, _wires, instance in self.iter_subcircuit_instances():
            if instance.comp_id == instance_comp_id:
                return instance

        for comp in self.iter_all_components():
            if comp.comp_id == instance_comp_id:
                raise ValueError(f"Component is not subcircuit: {instance_comp_id}")
        raise ValueError(f"Component not found: {instance_comp_id}")

    def find_external_wires_using_port(
        self,
        subdef_name: str,
        port_id: str,
    ) -> List[Wire]:
        result: List[Wire] = []
        for _components, wires, instance in self.iter_subcircuit_instances(subdef_name):
            for wire in wires.values():
                if (
                    wire.from_comp == instance.comp_id and wire.from_pin == port_id
                ) or (
                    wire.to_comp == instance.comp_id and wire.to_pin == port_id
                ):
                    result.append(wire)
        return result

    def validate_subcircuit_instances(self) -> ValidationResult:
        issues: List[ValidationIssue] = []
        for _components, wires, instance in self.iter_subcircuit_instances():
            sub_name = instance.params.get("subcircuit_name", "")
            location = instance.comp_id
            if not sub_name:
                issues.append(self._issue(
                    "error",
                    "instance_missing_subcircuit_name",
                    f"Subcircuit instance {instance.comp_id} has no subcircuit_name.",
                    location,
                ))
                continue
            subdef = self.subcircuit_defs.get(sub_name)
            if subdef is None:
                issues.append(self._issue(
                    "error",
                    "instance_missing_definition",
                    f"Subcircuit instance {instance.comp_id} references missing definition {sub_name}.",
                    location,
                ))
                continue

            expected = [pin["name"] for pin in subdef.get_port_pins()]
            actual = [pin.name for pin in instance.pins]
            if set(expected) != set(actual):
                issues.append(self._issue(
                    "error",
                    "instance_ports_mismatch",
                    f"{instance.comp_id} ports do not match definition {sub_name}.",
                    location,
                ))
            elif expected != actual:
                issues.append(self._issue(
                    "warning",
                    "instance_ports_order_mismatch",
                    f"{instance.comp_id} port order differs from definition {sub_name}.",
                    location,
                ))

            pin_names = {pin.name for pin in instance.pins}
            for wire in wires.values():
                if wire.from_comp == instance.comp_id and wire.from_pin not in pin_names:
                    issues.append(self._issue(
                        "error",
                        "wire_missing_instance_port",
                        f"Wire {wire.wire_id} references missing port {instance.comp_id}.{wire.from_pin}.",
                        f"{location}.{wire.wire_id}",
                    ))
                if wire.to_comp == instance.comp_id and wire.to_pin not in pin_names:
                    issues.append(self._issue(
                        "error",
                        "wire_missing_instance_port",
                        f"Wire {wire.wire_id} references missing port {instance.comp_id}.{wire.to_pin}.",
                        f"{location}.{wire.wire_id}",
                    ))
        return ValidationResult(issues)

    def validate_subcircuit_cycles(self) -> ValidationResult:
        issues: List[ValidationIssue] = []
        reported = set()

        def visit(name: str, stack: List[str]):
            if name in stack:
                cycle = stack[stack.index(name):] + [name]
                cycle_text = " -> ".join(cycle)
                if cycle_text not in reported:
                    reported.add(cycle_text)
                    issues.append(self._issue(
                        "error",
                        "subcircuit_cycle",
                        f"Detected circular subcircuit reference: {cycle_text}",
                        name,
                    ))
                return
            subdef = self.subcircuit_defs.get(name)
            if subdef is None:
                return
            next_stack = stack + [name]
            for comp in subdef.components.values():
                if comp.comp_type == ComponentType.SUBCIRCUIT:
                    child_name = comp.params.get("subcircuit_name", "")
                    if child_name:
                        visit(child_name, next_stack)

        for name in self.subcircuit_defs:
            visit(name, [])
        return ValidationResult(issues)

    def validate_all_subcircuits(self) -> ValidationResult:
        issues: List[ValidationIssue] = []
        for name in self.subcircuit_defs:
            issues.extend(self.validate_subcircuit_definition(name).issues)
        issues.extend(self.validate_subcircuit_instances().issues)
        issues.extend(self.validate_subcircuit_cycles().issues)
        return ValidationResult(issues)

    def _subcircuit_def_or_raise(self, subdef_name: str) -> SubcircuitDefinition:
        subdef = self.subcircuit_defs.get(subdef_name)
        if subdef is None:
            raise ValueError(f"Subcircuit definition not found: {subdef_name}")
        return subdef

    def _find_subcircuit_port(self, subdef_name: str, port_identity: str) -> SubcircuitPort:
        subdef = self._subcircuit_def_or_raise(subdef_name)
        port = subdef.find_port(port_identity)
        if port is None:
            raise ValueError(f"Subcircuit port not found: {subdef_name}.{port_identity}")
        return port

    def sync_subcircuit_instance_pins(self, subdef_name: str) -> None:
        subdef = self._subcircuit_def_or_raise(subdef_name)
        for _components, _wires, instance in self.iter_subcircuit_instances(subdef_name):
            pin_template = subdef.get_port_pins(instance)
            old_node_ids = {pin.name: pin.node_id for pin in instance.pins}
            instance.pins = [
                Pin(
                    name=pin["name"],
                    local_x=pin["local_x"],
                    local_y=pin["local_y"],
                    node_id=old_node_ids.get(pin["name"]),
                    display_name=pin.get("display_name"),
                )
                for pin in pin_template
            ]

    def add_port_to_subcircuit(
        self,
        subdef_name: str,
        port_name: str,
        x: float = 0.0,
        y: float = 0.0,
        side: str = "left",
        offset: Optional[float] = 0.5,
        kind: str = "electrical",
    ) -> SubcircuitPort:
        valid_sides = {"left", "right", "top", "bottom"}
        port_name = (port_name or "").strip()
        if not port_name:
            raise ValueError("Subcircuit port name cannot be empty")
        if side not in valid_sides:
            raise ValueError(f"Invalid subcircuit port side: {side}")
        subdef = self._subcircuit_def_or_raise(subdef_name)
        if subdef.get_port_by_name(port_name) is not None:
            raise ValueError(f"Subcircuit port already exists: {port_name}")

        self._save_undo_state()
        port_id = subdef.next_port_id()
        comp_id = f"PORT_{port_id}"
        suffix = 1
        while comp_id in subdef.components:
            suffix += 1
            comp_id = f"PORT_{port_id}_{suffix}"
        port_comp = ComponentInstance(
            comp_id=comp_id,
            comp_type=ComponentType.SUBCIRCUIT_PORT,
            name=port_name,
            x=int(x),
            y=int(y),
            params={
                "port_id": port_id,
                "port_name": port_name,
                "kind": kind,
            },
            pins=[Pin("node", 0, 0)],
        )
        subdef.components[port_comp.comp_id] = port_comp
        port = SubcircuitPort(
            port_name=port_name,
            internal_comp_id=port_comp.comp_id,
            internal_pin_name="node",
            side=side,
            order=len(subdef.ports),
            port_id=port_id,
            kind=kind,
            default_side=side,
            default_offset=max(0.0, min(1.0, float(offset))) if offset is not None else None,
            default_order=len(subdef.ports),
            visible=True,
        )
        subdef.ports.append(port)
        self.sync_subcircuit_instance_pins(subdef_name)
        self._notify("subcircuit_ports_updated")
        return port

    def rename_subcircuit_port(self, subdef_name: str, port_identity: str, new_name: str) -> None:
        new_name = new_name.strip()
        if not new_name:
            raise ValueError("Subcircuit port name cannot be empty")
        subdef = self._subcircuit_def_or_raise(subdef_name)
        port = self._find_subcircuit_port(subdef_name, port_identity)
        if any(other.port_name == new_name and other.port_id != port.port_id for other in subdef.ports):
            raise ValueError(f"Subcircuit port already exists: {new_name}")

        self._save_undo_state()
        port.port_name = new_name
        port_comp = subdef.components.get(port.internal_comp_id)
        if port_comp is not None and port_comp.comp_type == ComponentType.SUBCIRCUIT_PORT:
            port_comp.name = new_name
            port_comp.params["port_name"] = new_name

        self.sync_subcircuit_instance_pins(subdef_name)
        self._notify("subcircuit_ports_updated")

    def remove_port_from_subcircuit(
        self,
        subdef_name: str,
        port_identity: str,
        remove_external_wires: bool = True,
    ) -> None:
        subdef = self._subcircuit_def_or_raise(subdef_name)
        port = self._find_subcircuit_port(subdef_name, port_identity)
        self._save_undo_state()

        for wire_id in [
            wid for wid, wire in subdef.wires.items()
            if wire.from_comp == port.internal_comp_id or wire.to_comp == port.internal_comp_id
        ]:
            del subdef.wires[wire_id]
        subdef.components.pop(port.internal_comp_id, None)
        subdef.ports = [p for p in subdef.ports if p.port_id != port.port_id]

        if remove_external_wires:
            for _components, wires, instance in self.iter_subcircuit_instances(subdef_name):
                for wire_id in [
                    wid for wid, wire in wires.items()
                    if (
                        wire.from_comp == instance.comp_id and wire.from_pin == port.port_id
                    ) or (
                        wire.to_comp == instance.comp_id and wire.to_pin == port.port_id
                    )
                ]:
                    del wires[wire_id]
                overrides = instance.params.get("port_layout_overrides", {}) or {}
                overrides.pop(port.port_id, None)
                instance.params["port_layout_overrides"] = overrides

        self.sync_subcircuit_instance_pins(subdef_name)
        self._notify("subcircuit_ports_updated")

    def update_subcircuit_default_port_layout(
        self,
        subdef_name: str,
        port_identity: str,
        side: Optional[str] = None,
        offset: Optional[float] = None,
        order: Optional[int] = None,
    ) -> None:
        valid_sides = {"left", "right", "top", "bottom"}
        port = self._find_subcircuit_port(subdef_name, port_identity)
        self._save_undo_state()
        if side is not None:
            if side not in valid_sides:
                raise ValueError(f"Invalid subcircuit port side: {side}")
            port.side = side
            port.default_side = side
        if offset is not None:
            port.default_offset = max(0.0, min(1.0, float(offset)))
        if order is not None:
            port.order = int(order)
            port.default_order = int(order)
        self.sync_subcircuit_instance_pins(subdef_name)
        self._notify("subcircuit_ports_updated")

    def update_subcircuit_port_side(self, subdef_name: str, port_identity: str, side: str) -> None:
        self.update_subcircuit_default_port_layout(subdef_name, port_identity, side=side)

    def update_subcircuit_port_order(self, subdef_name: str, port_identity: str, order: int) -> None:
        self.update_subcircuit_default_port_layout(subdef_name, port_identity, order=order)

    def update_instance_port_layout(
        self,
        instance_comp_id: str,
        port_id: str,
        side: Optional[str] = None,
        offset: Optional[float] = None,
        order: Optional[int] = None,
    ) -> None:
        valid_sides = {"left", "right", "top", "bottom"}
        comp = self._find_subcircuit_instance_or_raise(instance_comp_id)
        sub_name = comp.params.get("subcircuit_name", "")
        subdef = self._subcircuit_def_or_raise(sub_name)
        if subdef.get_port(port_id) is None:
            raise ValueError(f"Port not found: {port_id}")

        self._save_undo_state()
        overrides = comp.params.setdefault("port_layout_overrides", {})
        layout = overrides.setdefault(port_id, {})
        if side is not None:
            if side not in valid_sides:
                raise ValueError(f"Invalid subcircuit port side: {side}")
            layout["side"] = side
        if offset is not None:
            layout["offset"] = max(0.0, min(1.0, float(offset)))
        if order is not None:
            layout["order"] = int(order)

        self.sync_subcircuit_instance_pins(sub_name)
        self._notify("subcircuit_ports_updated")

    def reset_instance_port_layout(
        self,
        instance_comp_id: str,
        port_id: Optional[str] = None,
    ) -> None:
        comp = self._find_subcircuit_instance_or_raise(instance_comp_id)
        self._save_undo_state()
        if port_id is None:
            comp.params["port_layout_overrides"] = {}
        else:
            overrides = comp.params.get("port_layout_overrides", {}) or {}
            overrides.pop(port_id, None)
            comp.params["port_layout_overrides"] = overrides
        sub_name = comp.params.get("subcircuit_name", "")
        self.sync_subcircuit_instance_pins(sub_name)
        self._notify("subcircuit_ports_updated")

    def update_subcircuit_port_description(
        self,
        subdef_name: str,
        port_identity: str,
        description: str,
    ) -> None:
        port = self._find_subcircuit_port(subdef_name, port_identity)
        self._save_undo_state()
        port.description = description
        self._notify("subcircuit_ports_updated")

    # ---- 子电路操作 ----

    def add_subcircuit_def(self, subdef: SubcircuitDefinition) -> None:
        """添加子电路定义"""
        self.subcircuit_defs[subdef.name] = subdef
        self._migrate_subcircuit_ports_to_stable_ids()
        self._notify("subcircuit_def_added")

    def remove_subcircuit_def(self, name: str) -> None:
        """移除子电路定义"""
        if name in self.subcircuit_defs:
            del self.subcircuit_defs[name]
            self._notify("subcircuit_def_removed")

    def create_subcircuit_from_selection(
        self,
        selected_comp_ids: List[str],
        name: str,
        overwrite: bool = False,
    ) -> Optional[Tuple['ComponentInstance', 'SubcircuitDefinition']]:
        """
        从选中的元件创建子电路。

        1. 提取选中元件和它们之间的内部连线
        2. 识别连到外部的引脚 → 生成端口
        3. 创建 SubcircuitDefinition
        4. 从画布移除原元件和连线，添加子电路实例

        返回: (子电路实例, 子电路定义) 或 None（如果失败）
        """
        return self.create_subcircuit_from_design_selection(
            components=self.components,
            wires=self.wires,
            comp_ids=selected_comp_ids,
            name=name,
            overwrite=overwrite,
        )

    def create_subcircuit_from_design_selection(
        self,
        components: Dict[str, ComponentInstance],
        wires: Dict[str, Wire],
        comp_ids: List[str],
        name: str,
        overwrite: bool = False,
    ) -> Optional[Tuple['ComponentInstance', 'SubcircuitDefinition']]:
        """Create a subcircuit from a supplied design container."""
        name = (name or "").strip()
        if not name:
            raise ValueError("Subcircuit name cannot be empty")
        if name in self.subcircuit_defs and not overwrite:
            raise ValueError(f"Subcircuit already exists: {name}")
        if len(comp_ids) < 2:
            return None

        selected_set = set(comp_ids)
        internal_comps = {
            cid: components[cid]
            for cid in comp_ids
            if cid in components
        }

        node_model = CircuitModel()
        node_model.components = components
        node_model.wires = wires
        node_model.subcircuit_defs = self.subcircuit_defs
        node_map = node_model.assign_node_ids()

        internal_wires = {}
        boundary_groups: Dict[tuple, Dict[str, Any]] = {}

        for wid, wire in list(wires.items()):
            from_in = wire.from_comp in selected_set
            to_in = wire.to_comp in selected_set
            if from_in and to_in:
                internal_wires[wid] = wire
            elif from_in and not to_in:
                key = ("node", node_map.get((wire.from_comp, wire.from_pin)))
                group = boundary_groups.setdefault(
                    key,
                    {"internal_pins": set(), "connections": []},
                )
                group["internal_pins"].add((wire.from_comp, wire.from_pin))
                group["connections"].append(
                    (wid, wire.from_comp, wire.from_pin, wire.to_comp, wire.to_pin, True)
                )
            elif not from_in and to_in:
                key = ("node", node_map.get((wire.to_comp, wire.to_pin)))
                group = boundary_groups.setdefault(
                    key,
                    {"internal_pins": set(), "connections": []},
                )
                group["internal_pins"].add((wire.to_comp, wire.to_pin))
                group["connections"].append(
                    (wid, wire.to_comp, wire.to_pin, wire.from_comp, wire.from_pin, False)
                )

        for key, group in boundary_groups.items():
            node_id = key[1]
            for comp_id in comp_ids:
                comp = components.get(comp_id)
                if comp is None:
                    continue
                for pin in comp.pins:
                    if node_map.get((comp_id, pin.name)) == node_id:
                        group["internal_pins"].add((comp_id, pin.name))

        def pin_position(comp_id: str, pin_name: str) -> Tuple[float, float]:
            comp = components.get(comp_id)
            if comp is None:
                return 0.0, 0.0
            pin = comp.get_pin(pin_name)
            if pin is None:
                return float(comp.x), float(comp.y)
            return float(comp.x + pin.local_x), float(comp.y + pin.local_y)

        def centroid(points: List[Tuple[float, float]]) -> Tuple[float, float]:
            if not points:
                return 0.0, 0.0
            return (
                sum(point[0] for point in points) / len(points),
                sum(point[1] for point in points) / len(points),
            )

        side_order = {"left": 0, "right": 1, "top": 2, "bottom": 3}
        prepared_groups = []
        for group in boundary_groups.values():
            if not group["internal_pins"]:
                continue
            internal_center = centroid([
                pin_position(comp_id, pin_name)
                for comp_id, pin_name in group["internal_pins"]
            ])
            external_points = [
                pin_position(ext_comp, ext_pin)
                for _wid, _int_comp, _int_pin, ext_comp, ext_pin, _was_from
                in group["connections"]
            ]
            external_center = centroid(external_points) if external_points else internal_center
            dx = external_center[0] - internal_center[0]
            dy = external_center[1] - internal_center[1]
            if abs(dx) >= abs(dy):
                side = "right" if dx > 0 else "left"
            else:
                side = "bottom" if dy > 0 else "top"
            group["side"] = side
            group["sort_coord"] = internal_center[1] if side in ("left", "right") else internal_center[0]
            prepared_groups.append(group)

        prepared_groups.sort(
            key=lambda group: (
                side_order.get(group["side"], 99),
                group["sort_coord"],
                sorted(group["internal_pins"]),
            )
        )

        ports = []
        port_pins = []
        for i, group in enumerate(prepared_groups):
            int_comp, _int_pin = sorted(group["internal_pins"])[0]
            int_c = components[int_comp]
            side = group["side"]
            port_name = f"P{i + 1}"
            port_id = f"P_{i + 1:03d}"
            port_comp_id = f"PORT_{port_id}"
            offset_x, offset_y = {
                "left": (-70, 0),
                "right": (70, 0),
                "top": (0, -60),
                "bottom": (0, 60),
            }[side]
            port_comp = ComponentInstance(
                comp_id=port_comp_id,
                comp_type=ComponentType.SUBCIRCUIT_PORT,
                name=port_name,
                x=int(int_c.x + offset_x),
                y=int(int_c.y + offset_y),
                rotation=0,
                params={
                    "port_id": port_id,
                    "port_name": port_name,
                    "kind": "electrical",
                },
                pins=[Pin("node", 0, 0)],
            )
            internal_comps[port_comp_id] = port_comp
            ports.append(SubcircuitPort(
                port_name=port_name,
                internal_comp_id=port_comp_id,
                internal_pin_name="node",
                side=side,
                order=i,
                port_id=port_id,
                kind="electrical",
                default_side=side,
                default_offset=None,
                default_order=i,
            ))
            for j, (pin_comp, pin_name) in enumerate(sorted(group["internal_pins"]), start=1):
                wire_id = f"W_{port_comp_id}_{j:03d}"
                internal_wires[wire_id] = Wire(
                    wire_id=wire_id,
                    from_comp=port_comp_id,
                    from_pin="node",
                    to_comp=pin_comp,
                    to_pin=pin_name,
                )
            for wid, _int_comp, _int_pin, ext_comp, ext_pin, internal_was_from in group["connections"]:
                port_pins.append((wid, port_id, ext_comp, ext_pin, internal_was_from))

        if not ports:
            return None

        subdef = SubcircuitDefinition(
            name=name,
            components=internal_comps,
            wires=internal_wires,
            ports=ports,
        )

        self._save_undo_state()

        for wid, _port_name, _ext_comp, _ext_pin, _was_from in port_pins:
            if wid in wires:
                del wires[wid]
        for wid in internal_wires:
            if wid in wires:
                del wires[wid]
        for cid in comp_ids:
            if cid in components:
                del components[cid]

        pin_defs = subdef.get_port_pins()
        pins = [
            Pin(
                name=p['name'],
                local_x=p['local_x'],
                local_y=p['local_y'],
                display_name=p.get('display_name'),
            )
            for p in pin_defs
        ]

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

        self.subcircuit_defs[subdef.name] = subdef
        components[sub_comp.comp_id] = sub_comp
        seen_external_connections = set()

        for _wid, port_name, ext_comp, ext_pin, internal_was_from in port_pins:
            if internal_was_from:
                from_comp, from_pin = sub_comp.comp_id, port_name
                to_comp, to_pin = ext_comp, ext_pin
            else:
                from_comp, from_pin = ext_comp, ext_pin
                to_comp, to_pin = sub_comp.comp_id, port_name
            key = (from_comp, from_pin, to_comp, to_pin)
            reverse_key = (to_comp, to_pin, from_comp, from_pin)
            if key in seen_external_connections or reverse_key in seen_external_connections:
                continue
            seen_external_connections.add(key)
            new_wire = Wire(
                wire_id=f"W_{uuid.uuid4().hex[:8]}",
                from_comp=from_comp,
                from_pin=from_pin,
                to_comp=to_comp,
                to_pin=to_pin,
            )
            wires[new_wire.wire_id] = new_wire

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
        self.subcircuit_defs.clear()
        self._selected_ids.clear()
        self._id_counters.clear()
        self._next_node_id = 1
        self._notify("cleared")

    # ---- 序列化 ----

    def _migrate_subcircuit_ports_to_stable_ids(self):
        for subdef in self.subcircuit_defs.values():
            used_ids = set()
            for index, port in enumerate(subdef.ports):
                if not port.port_id or port.port_id in used_ids:
                    port.port_id = f"P_{index + 1:03d}"
                used_ids.add(port.port_id)
                if not port.default_side:
                    port.default_side = port.side
                if port.default_order is None:
                    port.default_order = port.order
                comp = subdef.components.get(port.internal_comp_id)
                if comp is not None and comp.comp_type == ComponentType.SUBCIRCUIT_PORT:
                    comp.name = port.port_name
                    comp.params["port_id"] = port.port_id
                    comp.params["port_name"] = port.port_name
                    comp.params.setdefault("kind", port.kind)

        for sub_name, subdef in self.subcircuit_defs.items():
            name_to_id = {
                port.port_name: port.port_id
                for port in subdef.ports
                if port.port_name != port.port_id
            }
            if not name_to_id:
                continue
            for _components, wires, instance in self.iter_subcircuit_instances(sub_name):
                for pin in instance.pins:
                    if pin.name in name_to_id:
                        port = subdef.get_port(name_to_id[pin.name])
                        pin.name = name_to_id[pin.name]
                        if port is not None:
                            pin.display_name = port.port_name
                for wire in wires.values():
                    if wire.from_comp == instance.comp_id and wire.from_pin in name_to_id:
                        wire.from_pin = name_to_id[wire.from_pin]
                    if wire.to_comp == instance.comp_id and wire.to_pin in name_to_id:
                        wire.to_pin = name_to_id[wire.to_pin]
            self.sync_subcircuit_instance_pins(sub_name)

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

        model._migrate_subcircuit_ports_to_stable_ids()
        model._normalize_compact_symbol_pins()
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
