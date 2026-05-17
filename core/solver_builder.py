"""
EMTP 电路仿真 GUI - 直接构建器
将 CircuitModel 直接翻译为 EMTPSolver 对象调用，无需生成中间脚本字符串。
消除了 exec() 的安全风险，也支持进度回调、中途取消、结果复用。
"""

import numpy as np
from typing import Dict, List, Optional

from models.circuit_model import (
    CircuitModel, ComponentType, ComponentInstance, ProbeConfig,
    SubcircuitDefinition, Wire,
)
from core.lcp_config import (
    build_lcp_ohl_config,
    build_lcp_single_cable_config,
    build_lcp_three_core_cable_config,
    get_lcp_ohl_conductor_count,
)


class SolverBuilder:
    """直接从 CircuitModel 构建 EMTPSolver 实例"""

    def __init__(self):
        self._node_map: Dict[tuple, int] = {}

    def build(self, model: CircuitModel):
        """
        从 CircuitModel 构建 EMTPSolver 实例。
        展平子电路后再添加元件。
        返回: (solver, node_map)
        """
        from emtp import EMTPSolver
        import copy

        s = model.settings

        validation = model.validate_all_subcircuits()
        if validation.has_errors:
            raise ValueError(model.format_validation_errors(validation))

        # 展平子电路：生成一个不含子电路的展平模型副本
        flat_model = self._flatten_subcircuits(model)

        self._node_map = flat_model.assign_node_ids()

        solver = EMTPSolver(
            dt=s.dt,
            finish_time=s.finish_time,
            verbose=s.verbose,
            result_mode=s.result_mode,
            record_node_history=s.record_node_history,
            record_branch_history=s.record_branch_history,
            record_line_history=s.record_line_history,
            record_source_history=s.record_source_history,
            ulm_batch_mode=s.ulm_batch_mode,
        )

        self._add_components(solver, flat_model)
        self._add_probes(solver, flat_model)
        return solver, self._node_map

    # ================================================================
    #  子电路展平
    # ================================================================

    def _prefixed_id(self, prefix: str, comp_id: str) -> str:
        return f"{prefix}{comp_id}" if prefix else comp_id

    def _rewrite_probe_params_after_prefix(
        self,
        probe_comp: ComponentInstance,
        source_components: Dict[str, ComponentInstance],
        prefix: str,
    ) -> None:
        """Keep flattened probe references aligned with prefixed component names."""
        if probe_comp.comp_type != ComponentType.PROBE:
            return

        params = dict(probe_comp.params or {})
        probe_type = params.get("probe_type")

        if probe_type == "branch_current":
            target_id = params.get("target_comp_id")
            if target_id and target_id in source_components:
                target_comp = source_components[target_id]
                old_name = target_comp.name or target_id
                params["target_comp_id"] = self._prefixed_id(prefix, target_id)
                params["branch_name"] = self._prefixed_id(prefix, old_name)
            elif params.get("branch_name"):
                params["branch_name"] = self._prefixed_id(prefix, params["branch_name"])

        elif probe_type == "line_current":
            target_id = params.get("target_comp_id")
            if target_id and target_id in source_components:
                target_comp = source_components[target_id]
                old_name = target_comp.name or target_id
                params["target_comp_id"] = self._prefixed_id(prefix, target_id)
                params["line_name"] = self._prefixed_id(prefix, old_name)
            elif params.get("line_name"):
                params["line_name"] = self._prefixed_id(prefix, params["line_name"])

        probe_comp.params = params

    def _build_local_param_overrides(
        self,
        subdef: SubcircuitDefinition,
        instance: ComponentInstance,
    ) -> Dict[str, object]:
        result = {}
        result.update(instance.params.get("_raw_param_overrides", {}) or {})

        instance_overrides = instance.params.get("param_overrides", {}) or {}
        exposed_params = getattr(subdef, "exposed_params", {}) or {}

        for key, value in instance_overrides.items():
            if "." in key:
                result[key] = value

        for internal_path, exposed_name in exposed_params.items():
            if exposed_name in instance_overrides:
                result[internal_path] = instance_overrides[exposed_name]

        return result

    def _apply_direct_param_overrides(
        self,
        comp: ComponentInstance,
        local_overrides: Dict[str, object],
    ) -> None:
        prefix = f"{comp.comp_id}."
        for path, value in local_overrides.items():
            if not path.startswith(prefix):
                continue
            rest = path[len(prefix):]
            if "." in rest:
                continue
            comp.params[rest] = value

    def _extract_child_param_overrides(
        self,
        child_comp_id: str,
        local_overrides: Dict[str, object],
    ) -> tuple[Dict[str, object], Dict[str, object]]:
        child_exposed_overrides = {}
        child_raw_overrides = {}
        prefix = f"{child_comp_id}."

        for path, value in local_overrides.items():
            if not path.startswith(prefix):
                continue
            child_path = path[len(prefix):]
            if "." in child_path:
                child_raw_overrides[child_path] = value
            else:
                child_exposed_overrides[child_path] = value

        return child_exposed_overrides, child_raw_overrides

    def _remap_legacy_numeric_probes_after_flatten(
        self,
        original_model: CircuitModel,
        flat_model: CircuitModel,
        top_pin_map: Dict[tuple, tuple],
    ) -> None:
        if not flat_model.probes:
            return

        import copy

        original_snapshot = CircuitModel()
        original_snapshot.components = copy.deepcopy(original_model.components)
        original_snapshot.wires = copy.deepcopy(original_model.wires)
        original_snapshot.subcircuit_defs = original_model.subcircuit_defs
        original_node_map = original_snapshot.assign_node_ids()
        flat_node_map = flat_model.assign_node_ids()

        node_remap = {0: 0}
        for original_pin, original_node in original_node_map.items():
            flat_pin = top_pin_map.get(original_pin)
            if flat_pin is None:
                continue
            flat_node = flat_node_map.get(flat_pin)
            if flat_node is None:
                continue
            node_remap.setdefault(original_node, flat_node)

        for probe in flat_model.probes:
            if probe.probe_type != "voltage":
                continue
            if probe.node_pos is not None:
                probe.node_pos = node_remap.get(probe.node_pos, probe.node_pos)
            if probe.node_neg is not None:
                probe.node_neg = node_remap.get(probe.node_neg, probe.node_neg)

    def _flatten_subcircuits(self, model: CircuitModel) -> CircuitModel:
        """
        将模型中的子电路展平为普通元件。
        递归展开：子电路内部元件用前缀重命名，端口引脚映射到外部节点。
        返回一个不含 SUBCIRCUIT 元件的新模型副本。
        """

        # 如果没有子电路实例，直接返回原模型
        has_subcircuit = any(
            c.comp_type == ComponentType.SUBCIRCUIT
            for c in model.components.values()
        )
        if not has_subcircuit:
            return model

        return self._flatten_subcircuits_by_nodes(model)

    def _flatten_subcircuits_by_nodes(self, model: CircuitModel) -> CircuitModel:
        """Flatten subcircuits recursively and preserve topology by node groups."""
        import copy

        flat = CircuitModel()
        flat.settings = copy.deepcopy(model.settings)
        flat.probes = copy.deepcopy(model.probes)
        flat.subcircuit_defs = copy.deepcopy(model.subcircuit_defs)
        wire_counter = 0

        def add_flat_wire(a, b, prefix):
            nonlocal wire_counter
            if a == b:
                return
            wire_counter += 1
            wire_id = f"_flat_{prefix}_{wire_counter:06d}"
            flat.wires[wire_id] = Wire(
                wire_id=wire_id,
                from_comp=a[0],
                from_pin=a[1],
                to_comp=b[0],
                to_pin=b[1],
            )

        def node_groups_for(components, wires):
            temp = CircuitModel()
            temp.components = copy.deepcopy(components)
            temp.wires = copy.deepcopy(wires)
            temp.subcircuit_defs = model.subcircuit_defs
            node_map = temp.assign_node_ids()
            groups = {}
            for comp in temp.components.values():
                for pin in comp.pins:
                    key = (comp.comp_id, pin.name)
                    groups.setdefault(node_map[key], []).append(key)
            return groups

        def connect_node_groups(groups, pin_map, prefix):
            for pins in groups.values():
                flat_pins = []
                seen = set()
                for pin_key in pins:
                    flat_pin = pin_map.get(pin_key)
                    if flat_pin is None or flat_pin in seen:
                        continue
                    seen.add(flat_pin)
                    flat_pins.append(flat_pin)
                for a, b in zip(flat_pins, flat_pins[1:]):
                    add_flat_wire(a, b, prefix)

        def subcircuit_def_for(instance):
            sub_name = instance.params.get("subcircuit_name", "")
            subdef = model.subcircuit_defs.get(sub_name)
            if subdef is None:
                raise ValueError(
                    f"Subcircuit instance {instance.comp_id} references missing "
                    f"definition: {sub_name}"
                )
            return sub_name, subdef

        def instantiate_subcircuit(instance, subdef, prefix, stack):
            sub_name = instance.params.get("subcircuit_name", subdef.name)
            if sub_name in stack:
                cycle = stack[stack.index(sub_name):] + [sub_name]
                raise ValueError(
                    "Detected circular subcircuit reference: "
                    + " -> ".join(cycle)
                )
            stack = stack + [sub_name]
            pin_map = {}
            port_map = {}
            local_overrides = self._build_local_param_overrides(subdef, instance)

            for inner_comp in subdef.components.values():
                if inner_comp.comp_type == ComponentType.SUBCIRCUIT:
                    nested_instance = copy.deepcopy(inner_comp)
                    child_exposed, child_raw = self._extract_child_param_overrides(
                        nested_instance.comp_id,
                        local_overrides,
                    )
                    existing_overrides = nested_instance.params.get("param_overrides", {}) or {}
                    merged_overrides = {**existing_overrides, **child_exposed}
                    nested_instance.params["param_overrides"] = merged_overrides
                    nested_instance.params["_raw_param_overrides"] = child_raw

                    _nested_name, nested_def = subcircuit_def_for(nested_instance)
                    nested_prefix = f"{prefix}{inner_comp.comp_id}__"
                    nested_ports = instantiate_subcircuit(
                        nested_instance,
                        nested_def,
                        nested_prefix,
                        stack,
                    )
                    for pin in inner_comp.pins:
                        mapped = nested_ports.get(pin.name)
                        if mapped is not None:
                            pin_map[(inner_comp.comp_id, pin.name)] = mapped
                    continue

                new_comp = copy.deepcopy(inner_comp)
                self._apply_direct_param_overrides(new_comp, local_overrides)
                new_comp.comp_id = prefix + inner_comp.comp_id
                new_comp.name = prefix + inner_comp.name
                self._rewrite_probe_params_after_prefix(
                    new_comp,
                    subdef.components,
                    prefix,
                )
                flat.components[new_comp.comp_id] = new_comp
                for pin in new_comp.pins:
                    pin_map[(inner_comp.comp_id, pin.name)] = (new_comp.comp_id, pin.name)

            connect_node_groups(
                node_groups_for(subdef.components, subdef.wires),
                pin_map,
                prefix.rstrip("_"),
            )

            for port in subdef.ports:
                mapped = pin_map.get((port.internal_comp_id, port.internal_pin_name))
                if mapped is not None:
                    port_map[port.port_id] = mapped
                    port_map.setdefault(port.port_name, mapped)
            return port_map

        top_pin_map = {}
        for comp in model.components.values():
            if comp.comp_type == ComponentType.SUBCIRCUIT:
                _sub_name, subdef = subcircuit_def_for(comp)
                port_map = instantiate_subcircuit(comp, subdef, f"{comp.comp_id}__", [])
                for pin in comp.pins:
                    mapped = port_map.get(pin.name)
                    if mapped is not None:
                        top_pin_map[(comp.comp_id, pin.name)] = mapped
                continue

            new_comp = copy.deepcopy(comp)
            flat.components[new_comp.comp_id] = new_comp
            for pin in new_comp.pins:
                top_pin_map[(comp.comp_id, pin.name)] = (new_comp.comp_id, pin.name)

        connect_node_groups(
            node_groups_for(model.components, model.wires),
            top_pin_map,
            "top",
        )

        self._remap_legacy_numeric_probes_after_flatten(model, flat, top_pin_map)
        flat._rebuild_id_counters()
        return flat

    # ================================================================
    #  元件添加
    # ================================================================

    def _add_components(self, solver, model: CircuitModel):
        """按类型顺序添加所有元件（探针不添加到求解器，由 _add_probes 处理）"""
        # 顺序：电源 → 传输线 → R/L/C/SRL/SW → 非线性 → 变压器
        order = [
            ComponentType.VOLTAGE_SOURCE,
            ComponentType.CURRENT_SOURCE,
            ComponentType.BERGERON,
            ComponentType.ULM,
            ComponentType.LCP_OHL,
            ComponentType.LCP_SINGLE_CABLE,
            ComponentType.LCP_THREE_CABLE,
            ComponentType.RESISTOR,
            ComponentType.INDUCTOR,
            ComponentType.CAPACITOR,
            ComponentType.SERIES_RL,
            ComponentType.SWITCH,
            ComponentType.MOA,
            ComponentType.LPM,
            ComponentType.UMEC_TRANSFORMER,
            # PROBE 不添加到求解器
        ]

        for comp_type in order:
            for comp in model.components.values():
                if comp.comp_type == comp_type:
                    self._add_one(solver, comp)

    def _add_one(self, solver, comp: ComponentInstance):
        """添加单个元件到 solver"""
        ct = comp.comp_type
        p = comp.params

        if ct == ComponentType.RESISTOR:
            nf, nt = self._nodes_2pin(comp)
            solver.add_R(comp.name, nf, nt, p.get('R', 100.0))

        elif ct == ComponentType.INDUCTOR:
            nf, nt = self._nodes_2pin(comp)
            kwargs = {}
            if p.get('Rp') is not None:
                kwargs['Rp'] = p['Rp']
            solver.add_L(comp.name, nf, nt, p.get('L', 1e-3), **kwargs)

        elif ct == ComponentType.CAPACITOR:
            nf, nt = self._nodes_2pin(comp)
            kwargs = {}
            if p.get('Rp') is not None:
                kwargs['Rp'] = p['Rp']
            solver.add_C(comp.name, nf, nt, p.get('C', 1e-6), **kwargs)

        elif ct == ComponentType.SERIES_RL:
            nf, nt = self._nodes_2pin(comp)
            solver.add_series_RL(
                comp.name, nf, nt,
                R=p.get('R', 10.0),
                L=p.get('L', 1e-3),
            )

        elif ct == ComponentType.SWITCH:
            nf, nt = self._nodes_2pin(comp)
            solver.add_SW(
                comp.name, nf, nt,
                t_close=p.get('t_close', 0.0),
                t_open=p.get('t_open', 1e30),
                R_closed=p.get('R_closed', 1e-6),
                R_open=p.get('R_open', 1e8),
            )

        elif ct == ComponentType.VOLTAGE_SOURCE:
            np_ = self._node(comp, 'node_pos')
            nn_ = self._node(comp, 'node_neg')
            func = self._build_source_func(p.get('voltage_func', {}))
            # EMTP 求解器要求电压源正端 node > 0（MNA 矩阵约束）
            # 如果正端接地（node_pos=0），自动交换正负端并取反电压函数
            if np_ == 0 and nn_ > 0:
                np_, nn_ = nn_, np_
                func = self._negate_source_func(func)
            elif np_ == 0 and nn_ == 0:
                raise ValueError(
                    f"电压源 {comp.name} 两端都接地（node 0），电路无意义"
                )
            solver.add_VS(comp.name, np_, nn_, func)

        elif ct == ComponentType.CURRENT_SOURCE:
            nf, nt = self._nodes_2pin(comp)
            func = self._build_source_func(p.get('current_func', {}))
            solver.add_IS(comp.name, nf, nt, func)

        elif ct == ComponentType.BERGERON:
            nk = self._node(comp, 'nk')
            nm = self._node(comp, 'nm')
            solver.add_bergeron_line(
                comp.name,
                node_k=nk,
                node_m=nm,
                Zc=p.get('Zc', 300.0),
                length=p.get('length', 15000.0),
            )

        elif ct == ComponentType.ULM:
            nk_list, nm_list = self._nodes_multipin(comp, 'nk', 'nm')
            solver.add_ulm_line(
                comp.name,
                nodes_k=nk_list,
                nodes_m=nm_list,
                fitulm_file=p.get('fitulm_file', ''),
                length=p.get('length', 20000.0),
            )

        elif ct == ComponentType.MOA:
            nf, nt = self._nodes_2pin(comp)
            vi_file = p.get('vi_file', '')
            if vi_file:
                solver.add_MOA_from_file(
                    comp.name, nf, nt,
                    file_path=vi_file,
                    rated_voltage=p.get('rated_voltage', 1.0),
                    voltage_is_pu=p.get('voltage_is_pu', True),
                )
            else:
                breakpoints = p.get('breakpoints', [])
                if breakpoints:
                    from emtp.models.moa import SegmentedMOAResistor
                    moa = SegmentedMOAResistor.from_breakpoints(
                        comp.name,
                        breakpoints=[tuple(b) for b in breakpoints],
                        rated_voltage=p.get('rated_voltage', 1.0),
                        voltage_is_pu=p.get('voltage_is_pu', True),
                    )
                    # 注册 MOA 设备
                    solver.add_MOA_device(comp.name, nf, nt, moa)
                else:
                    # 回退：用 Vref/I0/alpha 生成断点（旧格式兼容）
                    Vref = p.get('rated_voltage', p.get('_legacy_Vref', 1e3))
                    I0 = p.get('_legacy_I0', 1e-3)
                    alpha = p.get('_legacy_alpha', 25.0)
                    n_seg = p.get('_legacy_n_segments', 50)
                    breakpoints = self._generate_moa_breakpoints(Vref, I0, alpha, n_seg)
                    from emtp.models.moa import SegmentedMOAResistor
                    moa = SegmentedMOAResistor.from_breakpoints(
                        comp.name, breakpoints,
                        rated_voltage=Vref,
                        voltage_is_pu=p.get('voltage_is_pu', True),
                    )
                    solver.add_MOA_device(comp.name, nf, nt, moa)

        elif ct == ComponentType.LPM:
            nf, nt = self._nodes_2pin(comp)
            solver.add_insulator_LPM(
                comp.name,
                node_from=nf,
                node_to=nt,
                gap_length=p.get('gap_length', 2.5),
                k=p.get('k', 1e-6),
                E0=p.get('E0', 600.0),
                R_arc=p.get('R_arc', 1.0),
                altitude_m=p.get('altitude_m', 0.0),
                allow_extinction=p.get('allow_extinction', True),
                extinction_current=p.get('extinction_current', 0.1),
            )

        elif ct == ComponentType.LCP_OHL:
            conductor_count = get_lcp_ohl_conductor_count(p)
            nk_list, nm_list = self._nodes_multipin(
                comp, 'nk', 'nm', conductor_count)
            config = build_lcp_ohl_config(p)

            solver.add_lcp_ohl_line(
                comp.name,
                nodes_k=nk_list,
                nodes_m=nm_list,
                length=p.get('length', 900.0),
                force_rebuild=p.get('force_rebuild', True),
                config=config,
            )

        elif ct == ComponentType.LCP_SINGLE_CABLE:
            nk_list, nm_list = self._nodes_cable(comp, 'nk', 'nm')
            solver.add_lcp_single_core_cable_line(
                comp.name,
                nodes_k=nk_list,
                nodes_m=nm_list,
                length=p.get('length', 1000.0),
                force_rebuild=p.get('force_rebuild', True),
                config=build_lcp_single_cable_config(p),
            )

        elif ct == ComponentType.LCP_THREE_CABLE:
            nk_list, nm_list = self._nodes_cable(comp, 'nk', 'nm')
            solver.add_lcp_three_core_cable_line(
                comp.name,
                nodes_k=nk_list,
                nodes_m=nm_list,
                length=p.get('length', 1000.0),
                force_rebuild=p.get('force_rebuild', True),
                config=build_lcp_three_core_cable_config(p),
            )

        elif ct == ComponentType.UMEC_TRANSFORMER:
            from emtp.models.transformer import create_umec_transformer_3ph_bank

            # 构建 nodes[phase][winding] = (from_node, to_node)
            nodes = []
            wtype1 = p.get('wtype1', 'Y_gnd')
            wtype2 = p.get('wtype2', 'Delta')
            for phase in ['A', 'B', 'C']:
                phase_nodes = []
                # 高压侧 #1
                h_from = self._node(comp, f'H_{phase}')
                if wtype1 == 'Y_gnd':
                    h_to = 0
                elif wtype1 == 'Y':
                    h_to = self._node(comp, 'H_N')
                else:  # Delta
                    next_phase = {'A': 'B', 'B': 'C', 'C': 'A'}[phase]
                    h_to = self._node(comp, f'H_{next_phase}')
                phase_nodes.append((h_from, h_to))
                # 低压侧 #2
                x_from = self._node(comp, f'X_{phase}')
                if wtype2 == 'Y_gnd':
                    x_to = 0
                elif wtype2 == 'Y':
                    x_to = self._node(comp, 'X_N')
                else:  # Delta
                    next_phase = {'A': 'B', 'B': 'C', 'C': 'A'}[phase]
                    x_to = self._node(comp, f'X_{next_phase}')
                phase_nodes.append((x_from, x_to))
                nodes.append(phase_nodes)

            data = create_umec_transformer_3ph_bank(
                name=comp.name,
                S_mva=p.get('S_mva', 100.0),
                V1_kV=p.get('V1_kV', 220.0),
                V2_kV=p.get('V2_kV', 110.0),
                wtype1=wtype1,
                wtype2=wtype2,
                X_leak_pu=p.get('X_leak_pu', 0.08),
                Im_percent=p.get('Im_percent', 1.0),
                freq=p.get('freq', 50.0),
                NLL_pu=p.get('NLL_pu', 0.0),
                CL_pu=p.get('CL_pu', 0.0),
                nodes=nodes,
            )
            solver.add_UMEC_transformer(comp.name, data)

    # ================================================================
    #  探针添加
    # ================================================================

    def _add_probes(self, solver, model: CircuitModel):
        """添加探针到 solver

        包含：
        - 画布上 PROBE 元件对应的探针（voltage / branch_current / line_current）
        - probes_only 模式下自动补充的非接地节点电压探针
        - 用户自定义探针列表
        """
        auto_probes = model.get_auto_voltage_probes()
        for probe in auto_probes:
            if probe.probe_type == "voltage":
                solver.add_voltage_probe(probe.probe_id, probe.node_pos, probe.node_neg)
            elif probe.probe_type == "branch_current":
                if probe.branch_name:
                    solver.add_branch_current_probe(probe.probe_id, probe.branch_name)
            elif probe.probe_type == "line_current":
                kwargs = {}
                if probe.line_name:
                    kwargs['line_name'] = probe.line_name
                if probe.end:
                    kwargs['end'] = probe.end
                if probe.phase is not None:
                    kwargs['phase'] = probe.phase
                solver.add_line_current_probe(probe.probe_id, **kwargs)

        # 用户自定义探针
        for probe in model.probes:
            if probe.probe_type == "voltage":
                solver.add_voltage_probe(
                    probe.probe_id,
                    probe.node_pos or 0,
                    probe.node_neg or 0,
                )
            elif probe.probe_type == "branch_current":
                if probe.branch_name:
                    solver.add_branch_current_probe(probe.probe_id, probe.branch_name)
            elif probe.probe_type == "line_current":
                kwargs = {}
                if probe.line_name:
                    kwargs['line_name'] = probe.line_name
                if probe.end:
                    kwargs['end'] = probe.end
                if probe.phase is not None:
                    kwargs['phase'] = probe.phase
                solver.add_line_current_probe(probe.probe_id, **kwargs)

    # ================================================================
    #  节点获取辅助方法
    # ================================================================

    def _node(self, comp: ComponentInstance, pin_name: str) -> int:
        """获取引脚的节点ID"""
        key = (comp.comp_id, pin_name)
        return self._node_map.get(key, 0)

    def _nodes_2pin(self, comp: ComponentInstance):
        """获取双端口元件的两个节点ID"""
        nf = self._node(comp, 'nf')
        nt = self._node(comp, 'nt')
        return nf, nt

    def _nodes_multipin(
        self,
        comp: ComponentInstance,
        prefix_k: str,
        prefix_m: str,
        n_phases: int = None,
    ):
        """获取多相元件的节点列表（如 ULM 的 nk_0, nm_0, nk_1, nm_1...）"""
        if n_phases is None:
            n_phases = comp.params.get('n_phases', 3)
        nk_list = []
        nm_list = []
        for i in range(n_phases):
            # 尝试 nk_i 格式
            nk_key = f'{prefix_k}_{i}'
            nm_key = f'{prefix_m}_{i}'
            # 单相兼容：也尝试 nk / nm
            if n_phases == 1 and i == 0:
                nk_val = self._node_map.get((comp.comp_id, nk_key),
                           self._node_map.get((comp.comp_id, prefix_k), 0))
                nm_val = self._node_map.get((comp.comp_id, nm_key),
                           self._node_map.get((comp.comp_id, prefix_m), 0))
            else:
                nk_val = self._node_map.get((comp.comp_id, nk_key), 0)
                nm_val = self._node_map.get((comp.comp_id, nm_key), 0)
            nk_list.append(nk_val)
            nm_list.append(nm_val)
        return nk_list, nm_list

    def _nodes_cable(self, comp: ComponentInstance, prefix_k: str, prefix_m: str):
        """获取电缆元件的节点列表（动态引脚名）"""
        nk_list = []
        nm_list = []
        for pin in comp.pins:
            if pin.name.startswith(prefix_k):
                nk_list.append(self._node_map.get((comp.comp_id, pin.name), 0))
            elif pin.name.startswith(prefix_m):
                nm_list.append(self._node_map.get((comp.comp_id, pin.name), 0))
        return nk_list, nm_list

    # ================================================================
    #  电源函数构建
    # ================================================================

    def _negate_source_func(self, func):
        """取反电源函数（用于电压源正端接地时自动交换极性）"""
        if func is None:
            return 0.0
        if isinstance(func, (int, float)):
            return -func
        if callable(func):
            return lambda t, _f=func: -_f(t)
        return func  # 无法取反的类型，原样返回

    def _build_source_func(self, func_def: Dict):
        """从参数字典构建电源函数"""
        if not func_def:
            return 0.0

        mode = func_def.get('mode', 'dc')

        if mode == 'dc':
            return func_def.get('value', 0.0)

        elif mode == 'ac':
            A = func_def.get('amplitude', 1.0)
            f = func_def.get('frequency', 50.0)
            ph = func_def.get('phase', 0.0)
            return lambda t, _A=A, _f=f, _ph=ph: (
                _A * np.sin(2 * np.pi * _f * t + _ph)
            )

        elif mode == 'lightning':
            ln_model = func_def.get('lightning_model', 'twoexpf_standard')
            # 向后兼容：旧数据没有 lightning_model 字段
            if 'lightning_model' not in func_def and 'waveform_type' in func_def:
                ln_model = 'twoexpf_standard'

            if ln_model == 'twoexpf_standard':
                from emtp.models.lightning import create_standard_twoexpf_current_source
                return create_standard_twoexpf_current_source(
                    waveform_type=func_def.get('waveform_type', '8/20'),
                    peak=func_def.get('peak', 10000.0),
                    PERC=int(func_def.get('PERC', 30)),
                    Tstart=func_def.get('t_start', 0.0),
                )
            elif ln_model == 'twoexpf_custom':
                from emtp.models.lightning import create_twoexpf_current_source
                return create_twoexpf_current_source(
                    peak=func_def.get('peak', 10000.0),
                    T1=func_def.get('T1', 8e-6),
                    T2=func_def.get('T2', 20e-6),
                    PERC=int(func_def.get('PERC', 30)),
                    Tstart=func_def.get('t_start', 0.0),
                )
            elif ln_model == 'twoexpf_tau':
                from emtp.models.lightning import create_twoexpf_current_source
                return create_twoexpf_current_source(
                    peak=func_def.get('peak', 10000.0),
                    T1=func_def.get('T1', 8e-6),
                    T2=func_def.get('T2', 20e-6),
                    tau1=func_def.get('tau1', 20.37e-6),
                    tau2=func_def.get('tau2', 3.91e-6),
                    Tstart=func_def.get('t_start', 0.0),
                )
            elif ln_model == 'twoexpf_ab':
                from emtp.models.lightning import create_twoexpf_current_source
                return create_twoexpf_current_source(
                    peak=func_def.get('peak', 10000.0),
                    T1=func_def.get('T1', 8e-6),
                    T2=func_def.get('T2', 20e-6),
                    A=func_def.get('A', -1.0 / 20.37e-6),
                    B=func_def.get('B', -1.0 / 3.91e-6),
                    Tstart=func_def.get('t_start', 0.0),
                )
            elif ln_model == 'heidler_custom':
                from emtp.models.lightning import create_heidlerf_current_source
                return create_heidlerf_current_source(
                    peak=func_def.get('peak', 10000.0),
                    T1=func_def.get('T1', 10e-6),
                    T2=func_def.get('T2', 350e-6),
                    n=int(func_def.get('n', 10)),
                    PERC=int(func_def.get('PERC', 30)),
                    Tstart=func_def.get('t_start', 0.0),
                )
            elif ln_model == 'heidler_direct':
                from emtp.models.lightning import create_heidlerf_current_source
                return create_heidlerf_current_source(
                    peak=func_def.get('peak', 10000.0),
                    T1=func_def.get('T1', 10e-6),
                    T2=func_def.get('T2', 350e-6),
                    n=int(func_def.get('n', 10)),
                    Tf=func_def.get('Tf', 2.5e-6),
                    tau=func_def.get('tau', 350e-6),
                    Tstart=func_def.get('t_start', 0.0),
                )
            else:
                # 回退到标准双指数
                from emtp.models.lightning import create_standard_twoexpf_current_source
                return create_standard_twoexpf_current_source(
                    waveform_type=func_def.get('waveform_type', '8/20'),
                    peak=func_def.get('peak', 10000.0),
                    PERC=30,
                    Tstart=func_def.get('t_start', 0.0),
                )

        elif mode == 'custom':
            expr = func_def.get('expression', 'lambda t: 0.0')
            return self._safe_eval_source_expr(expr)

        return 0.0

    @staticmethod
    def _safe_eval_source_expr(expr: str):
        """Safely evaluate a custom source expression in lambda form."""
        import re

        expr = expr.strip()
        blacklist = re.compile(
            r'(__\w+__|import|exec|eval|open|compile|globals|locals'
            r'|getattr|setattr|delattr|vars|dir|type|super'
            r'|breakpoint|exit|quit|os\.|sys\.|subprocess)',
            re.IGNORECASE,
        )
        if blacklist.search(expr):
            raise ValueError(
                f"Source expression contains disallowed content: {expr!r}. "
                "Use only 'lambda t: <math expression>'."
            )
        if not re.match(r'^lambda\s+\w+\s*:', expr):
            raise ValueError(
                f"Invalid source expression format: {expr!r}. "
                "Use 'lambda t: <math expression>'."
            )

        safe_ns = {
            "np": np,
            "numpy": np,
            "sin": np.sin,
            "cos": np.cos,
            "exp": np.exp,
            "sqrt": np.sqrt,
            "log": np.log,
            "log10": np.log10,
            "pi": np.pi,
            "abs": abs,
            "__builtins__": {},
        }
        return eval(expr, safe_ns)

    # ================================================================
    #  MOA 断点生成（旧格式兼容）
    # ================================================================

    @staticmethod
    def _generate_moa_breakpoints(Vref: float, I0: float, alpha: float, n_segments: int):
        """从 Vref/I0/alpha 生成 V-I 断点列表（旧格式兼容）"""
        breakpoints = [(0.0, 0.0)]
        for i in range(1, n_segments + 1):
            frac = i / n_segments
            V = Vref * frac
            I = I0 * (V / Vref) ** alpha if Vref > 0 else 0.0
            breakpoints.append((V, I))
        return breakpoints
