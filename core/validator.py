"""
EMTP GUI - 电路验证引擎

在运行仿真前检测常见错误：
- 浮空节点（无对地路径）
- 接地缺失
- 电压源冲突
- 参数越界
- 探针引用完整性
- 连线连通性
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Set

from models.circuit_model import (
    CircuitModel, ComponentType, ComponentInstance, Wire,
)


class ValidationSeverity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationError:
    severity: ValidationSeverity
    component_id: Optional[str]
    field: str
    message: str
    fix: Optional[str] = None


class CircuitValidator:
    """电路验证器 - 在仿真运行前检查常见问题"""

    def validate(self, model: CircuitModel) -> List[ValidationError]:
        """执行完整验证，返回错误/警告列表"""
        errors = []
        errors.extend(self._check_empty_circuit(model))
        errors.extend(self._check_floating_nodes(model))
        errors.extend(self._check_ground_connection(model))
        errors.extend(self._check_voltage_source_conflict(model))
        errors.extend(self._check_parameter_ranges(model))
        errors.extend(self._check_probe_references(model))
        errors.extend(self._check_wire_connectivity(model))
        errors.extend(self._check_simulation_settings(model))
        return errors

    def _check_empty_circuit(self, model: CircuitModel) -> List[ValidationError]:
        """检查电路是否为空"""
        errors = []
        if not model.components:
            errors.append(ValidationError(
                severity=ValidationSeverity.ERROR,
                component_id=None,
                field="circuit",
                message="电路为空，没有添加任何元件",
                fix="请添加元件并连接后再运行仿真",
            ))
        return errors

    def _check_floating_nodes(self, model: CircuitModel) -> List[ValidationError]:
        """检测浮空节点（无对地路径的节点）"""
        errors = []
        if not model.components:
            return errors

        node_map = model.assign_node_ids()
        if not node_map:
            return errors

        # 统计每个节点有多少引脚连接
        pin_counts: Dict[int, int] = {}
        node_comps: Dict[int, List[str]] = {}  # node_id -> [comp_ids]
        for (comp_id, pin_name), node_id in node_map.items():
            if node_id != 0:  # 排除地
                pin_counts[node_id] = pin_counts.get(node_id, 0) + 1
                if node_id not in node_comps:
                    node_comps[node_id] = []
                node_comps[node_id].append(comp_id)

        # 单引脚节点可能是浮空的
        for node_id, count in pin_counts.items():
            if count == 1:
                comp_id = node_comps[node_id][0]
                comp = model.components.get(comp_id)
                if comp and comp.comp_type not in (
                    ComponentType.VOLTAGE_SOURCE,
                    ComponentType.PROBE,
                    ComponentType.GROUND,
                ):
                    errors.append(ValidationError(
                        severity=ValidationSeverity.WARNING,
                        component_id=comp_id,
                        field="pins",
                        message=f"节点 {node_id} 只有单个连接（元件 {comp.name}），可能浮空",
                        fix="添加接地电阻或确认连接完整",
                    ))

        return errors

    def _check_ground_connection(self, model: CircuitModel) -> List[ValidationError]:
        """检查是否有接地"""
        errors = []
        has_ground = any(
            c.comp_type == ComponentType.GROUND
            for c in model.components.values()
        )
        if not has_ground and model.components:
            errors.append(ValidationError(
                severity=ValidationSeverity.ERROR,
                component_id=None,
                field="circuit",
                message="电路中没有接地（GND）元件",
                fix="请添加接地元件并连接到电路的参考节点",
            ))
        return errors

    def _check_voltage_source_conflict(self, model: CircuitModel) -> List[ValidationError]:
        """检查电压源是否形成环路（两个电压源并联在同一对节点上）"""
        errors = []
        if not model.components:
            return errors

        node_map = model.assign_node_ids()

        # 收集所有电压源的有序节点对
        vs_nodes: Dict[tuple, List[tuple]] = {}
        for comp in model.components.values():
            if comp.comp_type == ComponentType.VOLTAGE_SOURCE:
                pos = node_map.get((comp.comp_id, 'node_pos'), 0)
                neg = node_map.get((comp.comp_id, 'node_neg'), 0)
                key = (min(pos, neg), max(pos, neg))
                vs_nodes.setdefault(key, []).append((comp.name, pos, neg))

        for key, sources in vs_nodes.items():
            if len(sources) > 1:
                names = [name for name, _, _ in sources]
                polarities = {(pos, neg) for _, pos, neg in sources}
                severity = (
                    ValidationSeverity.ERROR
                    if len(polarities) == 1
                    else ValidationSeverity.WARNING
                )
                errors.append(ValidationError(
                    severity=severity,
                    component_id=None,
                    field="circuit",
                    message=f"电压源 {', '.join(names)} 并联在同一对节点上，可能冲突",
                    fix="检查电压源连接，避免理想电压源直接并联",
                ))

        return errors

    def _check_parameter_ranges(self, model: CircuitModel) -> List[ValidationError]:
        """检查参数范围"""
        from models.component_lib import PARAM_TEMPLATES
        errors = []
        for comp in model.components.values():
            if comp.comp_type == ComponentType.GROUND:
                continue
            template = PARAM_TEMPLATES.get(comp.comp_type, {})
            for param_name, param_def in template.items():
                value = comp.params.get(param_name)
                if value is None:
                    continue
                if not isinstance(value, (int, float)):
                    continue
                if 'min' in param_def and value < param_def['min']:
                    errors.append(ValidationError(
                        severity=ValidationSeverity.ERROR,
                        component_id=comp.comp_id,
                        field=f"params.{param_name}",
                        message=f"{comp.name}: {param_def.get('label', param_name)} = {value} 低于最小值 {param_def['min']}",
                    ))
                if 'max' in param_def and value > param_def['max']:
                    errors.append(ValidationError(
                        severity=ValidationSeverity.ERROR,
                        component_id=comp.comp_id,
                        field=f"params.{param_name}",
                        message=f"{comp.name}: {param_def.get('label', param_name)} = {value} 超过最大值 {param_def['max']}",
                    ))
        return errors

    def _check_probe_references(self, model: CircuitModel) -> List[ValidationError]:
        """检查探针引用的元件是否存在"""
        errors = []
        comp_names = {c.name for c in model.components.values()}
        line_names = {c.name for c in model.components.values()
                      if c.comp_type in (ComponentType.ULM, ComponentType.BERGERON,
                                          ComponentType.LCP_OHL, ComponentType.LCP_SINGLE_CABLE,
                                          ComponentType.LCP_THREE_CABLE)}

        for probe in model.probes:
            if probe.probe_type == "branch_current" and probe.branch_name:
                if probe.branch_name not in comp_names:
                    errors.append(ValidationError(
                        severity=ValidationSeverity.ERROR,
                        component_id=probe.probe_id,
                        field="branch_name",
                        message=f"探针 {probe.probe_id} 引用的支路 '{probe.branch_name}' 不存在",
                        fix=f"可用元件: {', '.join(sorted(comp_names)[:10])}",
                    ))
            elif probe.probe_type == "line_current" and probe.line_name:
                if probe.line_name not in line_names:
                    errors.append(ValidationError(
                        severity=ValidationSeverity.ERROR,
                        component_id=probe.probe_id,
                        field="line_name",
                        message=f"探针 {probe.probe_id} 引用的线路 '{probe.line_name}' 不存在",
                        fix=f"可用线路: {', '.join(sorted(line_names)[:10])}",
                    ))

        return errors

    def _check_wire_connectivity(self, model: CircuitModel) -> List[ValidationError]:
        """检查连线是否两端都连接到有效元件"""
        errors = []
        comp_ids = set(model.components.keys())
        for wire in model.wires.values():
            if wire.from_comp not in comp_ids:
                errors.append(ValidationError(
                    severity=ValidationSeverity.ERROR,
                    component_id=wire.from_comp,
                    field="wire",
                    message=f"连线 {wire.wire_id} 的起始元件 {wire.from_comp} 不存在",
                ))
            if wire.to_comp not in comp_ids:
                errors.append(ValidationError(
                    severity=ValidationSeverity.ERROR,
                    component_id=wire.to_comp,
                    field="wire",
                    message=f"连线 {wire.wire_id} 的目标元件 {wire.to_comp} 不存在",
                ))
        return errors

    def _check_simulation_settings(self, model: CircuitModel) -> List[ValidationError]:
        """检查仿真参数设置"""
        errors = []
        s = model.settings

        if s.dt <= 0:
            errors.append(ValidationError(
                severity=ValidationSeverity.ERROR,
                component_id=None,
                field="settings.dt",
                message=f"时间步长 dt={s.dt} 必须为正数",
            ))

        if s.finish_time <= 0:
            errors.append(ValidationError(
                severity=ValidationSeverity.ERROR,
                component_id=None,
                field="settings.finish_time",
                message=f"仿真结束时间 T_end={s.finish_time} 必须为正数",
            ))

        if s.dt > s.finish_time:
            errors.append(ValidationError(
                severity=ValidationSeverity.WARNING,
                component_id=None,
                field="settings",
                message=f"时间步长 dt={s.dt} 大于仿真结束时间 T_end={s.finish_time}",
                fix="减小 dt 或增大 T_end",
            ))

        # 检查 ULM 元件是否有 fitulm_file
        for comp in model.components.values():
            if comp.comp_type == ComponentType.ULM:
                fitulm = comp.params.get('fitulm_file', '')
                if not fitulm:
                    errors.append(ValidationError(
                        severity=ValidationSeverity.ERROR,
                        component_id=comp.comp_id,
                        field="params.fitulm_file",
                        message=f"ULM 线路 {comp.name} 缺少 fitULM 文件路径",
                        fix="请指定 .fitULM 文件路径",
                    ))

        return errors


def validate_circuit(model: CircuitModel) -> List[ValidationError]:
    """快捷函数：验证电路"""
    validator = CircuitValidator()
    return validator.validate(model)
