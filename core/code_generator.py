"""
EMTP 电路仿真 GUI - Python 代码生成器
将 CircuitModel 翻译为可执行的 Python 脚本。

注意：此模块仅用于代码预览和导出，实际仿真执行使用 SolverBuilder。
"""

from models.circuit_model import CircuitModel, ComponentType, ComponentInstance
from core.lcp_config import (
    build_lcp_ohl_config,
    build_lcp_single_cable_config,
    build_lcp_three_core_cable_config,
    get_lcp_ohl_conductor_count,
)
from typing import Dict, List
import numpy as np


class CodeGenerator:
    """代码生成器 - 对齐新内核 emtp API"""

    def __init__(self):
        self.indent = "    "

    def generate(self, model: CircuitModel) -> str:
        """生成完整的 Python 代码"""
        lines = []
        node_map = model.assign_node_ids()

        # 导入语句
        lines.append(self._gen_imports(model))
        lines.append("")

        # 仿真参数
        lines.append(self._gen_params(model))
        lines.append("")

        # 创建求解器
        lines.append(self._gen_solver(model))
        lines.append("")

        # 按类型分组添加元件
        lines.append(self._gen_components(model, node_map))
        lines.append("")

        # 探针
        lines.append(self._gen_probes(model, node_map))
        lines.append("")

        # 运行仿真
        lines.append(self._gen_run(model))
        lines.append("")

        # 结果提取与绘图
        lines.append(self._gen_results(model, node_map))

        return "\n".join(lines)

    def _gen_imports(self, model: CircuitModel) -> str:
        """生成导入语句 - 对齐新内核"""
        types_used = {c.comp_type for c in model.components.values()}

        imports = ["import numpy as np", "from emtp import EMTPSolver"]

        # 雷电流源
        has_lightning = any(
            c.params.get('current_func', {}).get('mode') == 'lightning'
            for c in model.components.values()
            if c.comp_type == ComponentType.CURRENT_SOURCE
        )
        if has_lightning:
            lightning_imports = set()
            for c in model.components.values():
                if c.comp_type == ComponentType.CURRENT_SOURCE:
                    fd = c.params.get('current_func', {})
                    if fd.get('mode') != 'lightning':
                        continue
                    ln_model = fd.get('lightning_model', 'twoexpf_standard')
                    if 'lightning_model' not in fd and 'waveform_type' in fd:
                        ln_model = 'twoexpf_standard'
                    if ln_model == 'twoexpf_standard':
                        lightning_imports.add('create_standard_twoexpf_current_source')
                    elif ln_model in ('twoexpf_custom', 'twoexpf_tau', 'twoexpf_ab'):
                        lightning_imports.add('create_twoexpf_current_source')
                    elif ln_model in ('heidler_custom', 'heidler_direct'):
                        lightning_imports.add('create_heidlerf_current_source')
            if lightning_imports:
                imports.append(
                    "from emtp.models.lightning import " +
                    ", ".join(sorted(lightning_imports))
                )

        # MOA 断点模式
        has_moa_breakpoints = any(
            c.params.get('breakpoints')
            for c in model.components.values()
            if c.comp_type == ComponentType.MOA
        )
        if has_moa_breakpoints:
            imports.append(
                "from emtp.models.moa import SegmentedMOAResistor"
            )

        return "\n".join(imports)

    def _gen_params(self, model: CircuitModel) -> str:
        """生成参数常量"""
        s = model.settings
        lines = [
            "# " + "=" * 60,
            "# 仿真参数",
            "# " + "=" * 60,
            f"DT = {self._format_num(s.dt)}",
            f"T_END = {self._format_num(s.finish_time)}",
        ]
        return "\n".join(lines)

    def _gen_solver(self, model: CircuitModel) -> str:
        """生成求解器创建代码 - 对齐新内核 API"""
        s = model.settings
        lines = [
            "# " + "=" * 60,
            "# 创建求解器",
            "# " + "=" * 60,
            f'solver = EMTPSolver(',
            f'    dt=DT,',
            f'    finish_time=T_END,',
            f'    verbose={s.verbose},',
            f'    result_mode="{s.result_mode}",',
            f'    record_node_history={s.record_node_history},',
            f'    record_branch_history={s.record_branch_history},',
            f'    record_line_history={s.record_line_history},',
            f'    record_source_history={s.record_source_history},',
            f'    ulm_batch_mode="{s.ulm_batch_mode}",',
            f')',
        ]
        return "\n".join(lines)

    def _gen_components(self, model: CircuitModel, node_map: Dict) -> str:
        """生成元件添加代码"""
        lines = [
            "# " + "=" * 60,
            "# 搭建电路",
            "# " + "=" * 60,
        ]

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
        ]

        type_labels = {
            ComponentType.VOLTAGE_SOURCE: '电压源 VS',
            ComponentType.CURRENT_SOURCE: '电流源 IS',
            ComponentType.BERGERON: 'Bergeron传输线',
            ComponentType.ULM: 'ULM传输线',
            ComponentType.LCP_OHL: 'LCP架空线',
            ComponentType.LCP_SINGLE_CABLE: 'LCP单芯电缆',
            ComponentType.LCP_THREE_CABLE: 'LCP三芯电缆',
            ComponentType.LCP_SINGLE_CABLE: 'LCP单芯电缆',
            ComponentType.LCP_THREE_CABLE: 'LCP三芯电缆',
            ComponentType.RESISTOR: '电阻 R',
            ComponentType.INDUCTOR: '电感 L',
            ComponentType.CAPACITOR: '电容 C',
            ComponentType.SERIES_RL: '串联RL',
            ComponentType.SWITCH: '开关 SW',
            ComponentType.MOA: 'MOA避雷器',
            ComponentType.LPM: 'LPM绝缘子',
            ComponentType.UMEC_TRANSFORMER: 'UMEC变压器',
        }

        for comp_type in order:
            group = sorted(
                (c for c in model.components.values() if c.comp_type == comp_type),
                key=lambda comp: (comp.comp_id, comp.name),
            )
            if not group:
                continue

            label = type_labels.get(comp_type, str(comp_type.value))
            lines.append(f"\n# --- {label} ---")

            for comp in group:
                code = self._gen_add_call(comp, node_map)
                if code:
                    lines.append(code)

        return "\n".join(lines)

    def _gen_add_call(self, comp: ComponentInstance, node_map: Dict) -> str:
        """生成单个 add_xxx() 调用 - 对齐新内核 API"""
        ct = comp.comp_type
        p = comp.params

        if ct == ComponentType.RESISTOR:
            nf = self._get_node_id(comp, 'nf', node_map)
            nt = self._get_node_id(comp, 'nt', node_map)
            R = p.get('R', 100.0)
            return f'solver.add_R("{comp.name}", {nf}, {nt}, {self._format_num(R)})'

        elif ct == ComponentType.INDUCTOR:
            nf = self._get_node_id(comp, 'nf', node_map)
            nt = self._get_node_id(comp, 'nt', node_map)
            L = p.get('L', 1e-3)
            Rp = p.get('Rp')
            if Rp is not None:
                return f'solver.add_L("{comp.name}", {nf}, {nt}, {self._format_num(L)}, Rp={self._format_num(Rp)})'
            else:
                return f'solver.add_L("{comp.name}", {nf}, {nt}, {self._format_num(L)})'

        elif ct == ComponentType.CAPACITOR:
            nf = self._get_node_id(comp, 'nf', node_map)
            nt = self._get_node_id(comp, 'nt', node_map)
            C = p.get('C', 1e-6)
            Rp = p.get('Rp')
            if Rp is not None:
                return f'solver.add_C("{comp.name}", {nf}, {nt}, {self._format_num(C)}, Rp={self._format_num(Rp)})'
            else:
                return f'solver.add_C("{comp.name}", {nf}, {nt}, {self._format_num(C)})'

        elif ct == ComponentType.SERIES_RL:
            nf = self._get_node_id(comp, 'nf', node_map)
            nt = self._get_node_id(comp, 'nt', node_map)
            R = p.get('R', 10.0)
            L = p.get('L', 1e-3)
            return f'solver.add_series_RL("{comp.name}", {nf}, {nt}, R={self._format_num(R)}, L={self._format_num(L)})'

        elif ct == ComponentType.SWITCH:
            nf = self._get_node_id(comp, 'nf', node_map)
            nt = self._get_node_id(comp, 'nt', node_map)
            return (f'solver.add_SW("{comp.name}", {nf}, {nt}, '
                    f't_close={self._format_num(p.get("t_close", 0.0))}, '
                    f't_open={self._format_num(p.get("t_open", 1e30))}, '
                    f'R_closed={self._format_num(p.get("R_closed", 1e-6))}, '
                    f'R_open={self._format_num(p.get("R_open", 1e8))})')

        elif ct == ComponentType.VOLTAGE_SOURCE:
            np_ = self._get_node_id(comp, 'node_pos', node_map)
            nn_ = self._get_node_id(comp, 'node_neg', node_map)
            vfunc = self._gen_source_func(p.get('voltage_func', {}))
            return f'solver.add_VS("{comp.name}", {np_}, {nn_}, {vfunc})'

        elif ct == ComponentType.CURRENT_SOURCE:
            nf = self._get_node_id(comp, 'nf', node_map)
            nt = self._get_node_id(comp, 'nt', node_map)
            ifunc = self._gen_source_func(p.get('current_func', {}))
            return f'solver.add_IS("{comp.name}", {nf}, {nt}, {ifunc})'

        elif ct == ComponentType.BERGERON:
            nk = self._get_node_id(comp, 'nk', node_map)
            nm = self._get_node_id(comp, 'nm', node_map)
            Zc = p.get('Zc', 300.0)
            length = p.get('length', 15000.0)
            return (f'solver.add_bergeron_line("{comp.name}", '
                    f'node_k={nk}, node_m={nm}, '
                    f'Zc={self._format_num(Zc)}, length={self._format_num(length)})')

        elif ct == ComponentType.ULM:
            nk_list = []
            nm_list = []
            n_phases = p.get('n_phases', 3)
            for i in range(n_phases):
                nk = self._get_first_node_id(
                    comp, self._ulm_pin_candidates('nk', i, n_phases), node_map)
                nm = self._get_first_node_id(
                    comp, self._ulm_pin_candidates('nm', i, n_phases), node_map)
                nk_list.append(str(nk))
                nm_list.append(str(nm))
            return (f'solver.add_ulm_line("{comp.name}", '
                    f'[{", ".join(nk_list)}], [{", ".join(nm_list)}], '
                    f'"{p.get("fitulm_file", "")}", {self._format_num(p.get("length", 20000.0))})')

        elif ct == ComponentType.MOA:
            nf = self._get_node_id(comp, 'nf', node_map)
            nt = self._get_node_id(comp, 'nt', node_map)
            vi_file = p.get('vi_file', '')
            if vi_file:
                return (f'solver.add_MOA_from_file("{comp.name}", {nf}, {nt}, '
                        f'file_path="{vi_file}", '
                        f'rated_voltage={self._format_num(p.get("rated_voltage", 1.0))}, '
                        f'voltage_is_pu={p.get("voltage_is_pu", True)})')
            breakpoints = p.get('breakpoints', [])
            if breakpoints:
                bp_str = repr([tuple(b) for b in breakpoints])
                return (
                    f'_moa = SegmentedMOAResistor.from_breakpoints("{comp.name}", {bp_str})\n'
                    f'solver.add_MOA_device("{comp.name}", {nf}, {nt}, _moa)'
                )
            # 回退旧格式
            return f'# MOA "{comp.name}" - 需要配置V-I数据文件或断点'

        elif ct == ComponentType.LPM:
            nf = self._get_node_id(comp, 'nf', node_map)
            nt = self._get_node_id(comp, 'nt', node_map)
            return (f'solver.add_insulator_LPM("{comp.name}", '
                    f'node_from={nf}, node_to={nt}, '
                    f'gap_length={self._format_num(p.get("gap_length", 2.5))}, '
                    f'k={self._format_num(p.get("k", 1e-6))}, '
                    f'E0={self._format_num(p.get("E0", 600.0))}, '
                    f'R_arc={self._format_num(p.get("R_arc", 1.0))}, '
                    f'altitude_m={self._format_num(p.get("altitude_m", 0.0))}, '
                    f'allow_extinction={p.get("allow_extinction", True)}, '
                    f'extinction_current={self._format_num(p.get("extinction_current", 0.1))})')

        elif ct == ComponentType.LCP_OHL:
            conductor_count = get_lcp_ohl_conductor_count(p)
            nk_list, nm_list = self._gen_multipin_nodes(
                comp, 'nk', 'nm', node_map, conductor_count)
            config = build_lcp_ohl_config(p)
            var_name = f"_config_{self._safe_var_name(comp.name)}"
            return (
                f"{var_name} = {self._format_literal(config)}\n"
                f'solver.add_lcp_ohl_line("{comp.name}", '
                f'nodes_k=[{", ".join(nk_list)}], '
                f'nodes_m=[{", ".join(nm_list)}], '
                f'length={self._format_num(p.get("length", 900.0))}, '
                f'force_rebuild={p.get("force_rebuild", True)}, '
                f'config={var_name})'
            )

        elif ct == ComponentType.LCP_SINGLE_CABLE:
            nk_list, nm_list = self._gen_cable_nodes(comp, 'nk', 'nm', node_map)
            var_name = f"_config_{self._safe_var_name(comp.name)}"
            config = build_lcp_single_cable_config(p)
            return (
                f"{var_name} = {self._format_literal(config)}\n"
                f'solver.add_lcp_single_core_cable_line("{comp.name}", '
                f'nodes_k=[{", ".join(nk_list)}], '
                f'nodes_m=[{", ".join(nm_list)}], '
                f'length={self._format_num(p.get("length", 1000.0))}, '
                f'force_rebuild={p.get("force_rebuild", True)}, '
                f'config={var_name})'
            )

        elif ct == ComponentType.LCP_THREE_CABLE:
            nk_list, nm_list = self._gen_cable_nodes(comp, 'nk', 'nm', node_map)
            var_name = f"_config_{self._safe_var_name(comp.name)}"
            config = build_lcp_three_core_cable_config(p)
            return (
                f"{var_name} = {self._format_literal(config)}\n"
                f'solver.add_lcp_three_core_cable_line("{comp.name}", '
                f'nodes_k=[{", ".join(nk_list)}], '
                f'nodes_m=[{", ".join(nm_list)}], '
                f'length={self._format_num(p.get("length", 1000.0))}, '
                f'force_rebuild={p.get("force_rebuild", True)}, '
                f'config={var_name})'
            )

        elif ct == ComponentType.UMEC_TRANSFORMER:
            # 构建 nodes 列表
            wtype1 = p.get('wtype1', 'Y_gnd')
            wtype2 = p.get('wtype2', 'Delta')
            nodes_lines = []
            for phase in ['A', 'B', 'C']:
                h = self._get_node_id(comp, f'H_{phase}', node_map)
                x = self._get_node_id(comp, f'X_{phase}', node_map)
                if wtype1 == 'Y_gnd':
                    h_to = 0
                elif wtype1 == 'Y':
                    h_to = self._get_node_id(comp, 'H_N', node_map)
                else:
                    next_p = {'A': 'B', 'B': 'C', 'C': 'A'}[phase]
                    h_to = self._get_node_id(comp, f'H_{next_p}', node_map)
                if wtype2 == 'Y_gnd':
                    x_to = 0
                elif wtype2 == 'Y':
                    x_to = self._get_node_id(comp, 'X_N', node_map)
                else:
                    next_p = {'A': 'B', 'B': 'C', 'C': 'A'}[phase]
                    x_to = self._get_node_id(comp, f'X_{next_p}', node_map)
                nodes_lines.append(f'    [({h}, {h_to}), ({x}, {x_to})],')
            nodes_str = '\n'.join(nodes_lines)

            return (
                f'from emtp.models.transformer import create_umec_transformer_3ph_bank\n'
                f'_data = create_umec_transformer_3ph_bank(\n'
                f'    name="{comp.name}",\n'
                f'    S_mva={self._format_num(p.get("S_mva", 100.0))},\n'
                f'    V1_kV={self._format_num(p.get("V1_kV", 220.0))},\n'
                f'    V2_kV={self._format_num(p.get("V2_kV", 110.0))},\n'
                f'    wtype1="{wtype1}",\n'
                f'    wtype2="{wtype2}",\n'
                f'    X_leak_pu={self._format_num(p.get("X_leak_pu", 0.08))},\n'
                f'    Im_percent={self._format_num(p.get("Im_percent", 1.0))},\n'
                f'    freq={self._format_num(p.get("freq", 50.0))},\n'
                f'    NLL_pu={self._format_num(p.get("NLL_pu", 0.0))},\n'
                f'    CL_pu={self._format_num(p.get("CL_pu", 0.0))},\n'
                f'    nodes=[\n'
                f'{nodes_str}\n'
                f'    ],\n'
                f')\n'
                f'solver.add_UMEC_transformer("{comp.name}", _data)'
            )

        elif ct == ComponentType.GROUND:
            return None

        return None

    def _gen_probes(self, model: CircuitModel, node_map: Dict) -> str:
        """生成探针注册代码 - 支持 voltage / branch_current / line_current"""
        lines = [
            "# " + "=" * 60,
            "# 探针注册",
            "# " + "=" * 60,
        ]

        # 自动探针（含用户放置的 PROBE 元件 + probes_only 自动补充）
        auto_probes = model.get_auto_voltage_probes()
        for probe in auto_probes:
            if probe.probe_type == "voltage":
                lines.append(
                    f'solver.add_voltage_probe("{probe.probe_id}", '
                    f'{probe.node_pos}, {probe.node_neg})'
                )
            elif probe.probe_type == "branch_current":
                lines.append(
                    f'solver.add_branch_current_probe("{probe.probe_id}", '
                    f'"{probe.branch_name}")'
                )
            elif probe.probe_type == "line_current":
                lines.append(
                    f'solver.add_line_current_probe("{probe.probe_id}", '
                    f'line_name="{probe.line_name}", '
                    f'end="{probe.end}", phase={probe.phase})'
                )

        # 用户自定义探针
        for probe in model.probes:
            if probe.probe_type == "voltage":
                lines.append(
                    f'solver.add_voltage_probe("{probe.probe_id}", '
                    f'{probe.node_pos}, {probe.node_neg})'
                )
            elif probe.probe_type == "branch_current":
                lines.append(
                    f'solver.add_branch_current_probe("{probe.probe_id}", '
                    f'"{probe.branch_name}")'
                )
            elif probe.probe_type == "line_current":
                lines.append(
                    f'solver.add_line_current_probe("{probe.probe_id}", '
                    f'line_name="{probe.line_name}", '
                    f'end="{probe.end}", phase={probe.phase})'
                )

        if len(lines) <= 3:
            lines.append("# （未放置探针，probes_only 模式下将无输出数据）")

        return "\n".join(lines)

    def _gen_run(self, model: CircuitModel) -> str:
        """生成运行代码"""
        lines = [
            "# " + "=" * 60,
            "# 运行仿真",
            "# " + "=" * 60,
            "solver.run()",
        ]
        return "\n".join(lines)

    def _gen_results(self, model: CircuitModel, node_map: Dict) -> str:
        """生成结果提取和绘图代码 - 使用探针（适配 probes_only 模式）"""
        lines = [
            "# " + "=" * 60,
            "# 结果提取与绘图",
            "# " + "=" * 60,
            "import matplotlib.pyplot as plt",
            "",
            "t = solver.get_time('us')",
        ]

        # 收集所有探针
        auto_probes = model.get_auto_voltage_probes()
        all_probes = auto_probes + [p for p in model.probes]

        # 生成每个探针的数据提取代码
        for probe in all_probes:
            unit = getattr(probe, 'unit', 'kV') or 'kV'
            lines.append(
                f'{probe.probe_id} = solver.get_probe("{probe.probe_id}", unit="{unit}")'
            )

        if all_probes:
            lines.append("")
            lines.append("# 绘图")
            lines.append("fig, ax = plt.subplots(figsize=(10, 5))")
            for probe in all_probes:
                if probe.probe_type == "branch_current" or probe.probe_type == "line_current":
                    ls = "--"
                else:
                    ls = "-"
                lines.append(f'ax.plot(t, {probe.probe_id}, label="{probe.probe_id}", linestyle="{ls}")')
            lines.extend([
                "ax.set_xlabel('Time (μs)')",
                "ax.set_ylabel('Voltage (kV) / Current (A)')",
                "ax.legend()",
                "ax.grid(True, alpha=0.3)",
                "plt.tight_layout()",
                "plt.show()",
            ])
        else:
            lines.append("")
            lines.append("# 未注册探针，无法提取结果")
            lines.append("print('警告：未注册任何探针，probes_only 模式下无输出数据')")

        return "\n".join(lines)

    # ================================================================
    #  辅助方法
    # ================================================================

    def _get_node_id(self, comp: ComponentInstance, pin_name: str, node_map: Dict) -> int:
        """获取引脚的节点ID"""
        key = (comp.comp_id, pin_name)
        return node_map.get(key, 0)

    def _get_first_node_id(self, comp: ComponentInstance, pin_names: List[str], node_map: Dict) -> int:
        """按候选顺序获取第一个存在的引脚节点ID"""
        for pin_name in pin_names:
            key = (comp.comp_id, pin_name)
            if key in node_map:
                return node_map[key]
        return 0

    @staticmethod
    def _ulm_pin_candidates(prefix: str, index: int, n_phases: int) -> List[str]:
        """兼容旧版单相 ULM 的 nk/nm 命名和新版 nk_0/nm_0 命名"""
        candidates = [f'{prefix}_{index}']
        if n_phases == 1 and index == 0:
            candidates.append(prefix)
        return candidates

    def _gen_multipin_nodes(
        self,
        comp: ComponentInstance,
        prefix_k: str,
        prefix_m: str,
        node_map: Dict,
        n_phases: int = None,
    ):
        """生成多相元件的节点列表字符串"""
        if n_phases is None:
            n_phases = comp.params.get('n_phases', 3)
        nk_list = []
        nm_list = []
        for i in range(n_phases):
            nk_candidates = self._ulm_pin_candidates(prefix_k, i, n_phases)
            nm_candidates = self._ulm_pin_candidates(prefix_m, i, n_phases)
            nk_list.append(str(self._get_first_node_id(comp, nk_candidates, node_map)))
            nm_list.append(str(self._get_first_node_id(comp, nm_candidates, node_map)))
        return nk_list, nm_list

    def _gen_cable_nodes(self, comp: ComponentInstance, prefix_k: str, prefix_m: str, node_map: Dict):
        """生成电缆元件的节点列表字符串（动态引脚名）"""
        nk_list = []
        nm_list = []
        for pin in comp.pins:
            if pin.name.startswith(prefix_k):
                nk_list.append(str(node_map.get((comp.comp_id, pin.name), 0)))
            elif pin.name.startswith(prefix_m):
                nm_list.append(str(node_map.get((comp.comp_id, pin.name), 0)))
        return nk_list, nm_list

    def _gen_source_func(self, func_def: Dict) -> str:
        """生成电源函数表达式 - 对齐新内核 API，支持完整雷电模型"""
        if not func_def:
            return "lambda t: 0.0"

        mode = func_def.get('mode', 'dc')

        if mode == 'dc':
            value = func_def.get('value', 0.0)
            return str(self._format_num(value))

        elif mode == 'ac':
            amplitude = func_def.get('amplitude', 1.0)
            frequency = func_def.get('frequency', 50.0)
            phase = func_def.get('phase', 0.0)
            return f"lambda t: {self._format_num(amplitude)} * np.sin(2 * np.pi * {self._format_num(frequency)} * t + {self._format_num(phase)})"

        elif mode == 'lightning':
            ln_model = func_def.get('lightning_model', 'twoexpf_standard')
            # 向后兼容
            if 'lightning_model' not in func_def and 'waveform_type' in func_def:
                ln_model = 'twoexpf_standard'

            peak = self._format_num(func_def.get('peak', 10000.0))
            t_start = self._format_num(func_def.get('t_start', 0.0))

            if ln_model == 'twoexpf_standard':
                wt = func_def.get('waveform_type', '8/20')
                perc = int(func_def.get('PERC', 30))
                return (
                    f'create_standard_twoexpf_current_source('
                    f'waveform_type="{wt}", '
                    f'peak={peak}, '
                    f'PERC={perc}, '
                    f'Tstart={t_start})'
                )
            elif ln_model == 'twoexpf_custom':
                t1 = self._format_num(func_def.get('T1', 8e-6))
                t2 = self._format_num(func_def.get('T2', 20e-6))
                perc = int(func_def.get('PERC', 30))
                return (
                    f'create_twoexpf_current_source('
                    f'peak={peak}, '
                    f'T1={t1}, T2={t2}, '
                    f'PERC={perc}, '
                    f'Tstart={t_start})'
                )
            elif ln_model == 'twoexpf_tau':
                t1 = self._format_num(func_def.get('T1', 8e-6))
                t2 = self._format_num(func_def.get('T2', 20e-6))
                tau1 = self._format_num(func_def.get('tau1', 20.37e-6))
                tau2 = self._format_num(func_def.get('tau2', 3.91e-6))
                return (
                    f'create_twoexpf_current_source('
                    f'peak={peak}, '
                    f'T1={t1}, T2={t2}, '
                    f'tau1={tau1}, tau2={tau2}, '
                    f'Tstart={t_start})'
                )
            elif ln_model == 'twoexpf_ab':
                t1 = self._format_num(func_def.get('T1', 8e-6))
                t2 = self._format_num(func_def.get('T2', 20e-6))
                a = self._format_num(func_def.get('A', -1.0 / 20.37e-6))
                b = self._format_num(func_def.get('B', -1.0 / 3.91e-6))
                return (
                    f'create_twoexpf_current_source('
                    f'peak={peak}, '
                    f'T1={t1}, T2={t2}, '
                    f'A={a}, B={b}, '
                    f'Tstart={t_start})'
                )
            elif ln_model == 'heidler_custom':
                t1 = self._format_num(func_def.get('T1', 10e-6))
                t2 = self._format_num(func_def.get('T2', 350e-6))
                n = int(func_def.get('n', 10))
                perc = int(func_def.get('PERC', 30))
                return (
                    f'create_heidlerf_current_source('
                    f'peak={peak}, '
                    f'T1={t1}, T2={t2}, n={n}, '
                    f'PERC={perc}, '
                    f'Tstart={t_start})'
                )
            elif ln_model == 'heidler_direct':
                t1 = self._format_num(func_def.get('T1', 10e-6))
                t2 = self._format_num(func_def.get('T2', 350e-6))
                n = int(func_def.get('n', 10))
                tf = self._format_num(func_def.get('Tf', 2.5e-6))
                tau = self._format_num(func_def.get('tau', 350e-6))
                return (
                    f'create_heidlerf_current_source('
                    f'peak={peak}, '
                    f'T1={t1}, T2={t2}, n={n}, '
                    f'Tf={tf}, tau={tau}, '
                    f'Tstart={t_start})'
                )
            else:
                # 回退
                wt = func_def.get('waveform_type', '8/20')
                return (
                    f'create_standard_twoexpf_current_source('
                    f'waveform_type="{wt}", '
                    f'peak={peak}, '
                    f'PERC=30, '
                    f'Tstart={t_start})'
                )

        elif mode == 'custom':
            expr = func_def.get('expression', 'lambda t: 0.0')
            return expr

        return "lambda t: 0.0"

    def _format_num(self, value: float) -> str:
        """格式化数字为可读字符串"""
        if value is None:
            return "None"

        if isinstance(value, str):
            return value

        if value == 0:
            return "0"

        if abs(value) < 1e-6 or abs(value) >= 1e6:
            return f"{value:.6e}"
        elif abs(value) < 1:
            return f"{value:.6f}"
        else:
            return f"{value:g}"

    def _format_literal(self, value):
        """Format nested Python literals for generated scripts."""
        if isinstance(value, float):
            return repr(value)
        if isinstance(value, list):
            return "[" + ", ".join(self._format_literal(v) for v in value) + "]"
        if isinstance(value, tuple):
            return "(" + ", ".join(self._format_literal(v) for v in value) + ")"
        if isinstance(value, dict):
            items = [
                f"{key!r}: {self._format_literal(val)}"
                for key, val in value.items()
            ]
            return "{" + ", ".join(items) + "}"
        return repr(value)

    def _safe_var_name(self, name: str) -> str:
        """Return a valid Python identifier suffix from a component name."""
        return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name)


# 快捷函数
def generate_code(model: CircuitModel) -> str:
    """生成电路的 Python 代码"""
    generator = CodeGenerator()
    return generator.generate(model)
