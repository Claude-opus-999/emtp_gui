"""
EMTP 电路仿真 GUI - 元件注册表
定义10种元件的图形符号、参数模板、引脚定义、API映射
"""

from .circuit_model import ComponentType
from typing import Dict, Any, List


# 元件引脚定义
PINS = {
    'two_port': [  # 双端口元件: R, L, C, SW, IS
        {'name': 'nf', 'local_x': -30, 'local_y': 0},
        {'name': 'nt', 'local_x': 30, 'local_y': 0},
    ],
    'voltage_source': [  # 电压源
        {'name': 'node_pos', 'local_x': -30, 'local_y': 0},
        {'name': 'node_neg', 'local_x': 30, 'local_y': 0},
    ],
    'bergeron': [  # Bergeron传输线
        {'name': 'nk', 'local_x': -30, 'local_y': 0},
        {'name': 'nm', 'local_x': 30, 'local_y': 0},
    ],
    'ulm_single': [  # ULM单相
        {'name': 'nk', 'local_x': -30, 'local_y': 0},
        {'name': 'nm', 'local_x': 30, 'local_y': 0},
    ],
    'ulm_multi': [  # ULM多相 (动态)
        {'name': 'nk_0', 'local_x': -30, 'local_y': -15},
        {'name': 'nm_0', 'local_x': 30, 'local_y': -15},
        {'name': 'nk_1', 'local_x': -30, 'local_y': 0},
        {'name': 'nm_1', 'local_x': 30, 'local_y': 0},
        {'name': 'nk_2', 'local_x': -30, 'local_y': 15},
        {'name': 'nm_2', 'local_x': 30, 'local_y': 15},
    ],
    'ground': [  # 接地
        {'name': 'gnd', 'local_x': 0, 'local_y': 0},
    ],
    'moa': [  # MOA避雷器
        {'name': 'nf', 'local_x': -30, 'local_y': 0},
        {'name': 'nt', 'local_x': 30, 'local_y': 0},
    ],
    'lpm': [  # LPM绝缘子
        {'name': 'nf', 'local_x': -30, 'local_y': 0},
        {'name': 'nt', 'local_x': 30, 'local_y': 0},
    ],
    'umec': [  # UMEC变压器（两绕组三相组）
        {'name': 'H_A', 'local_x': -30, 'local_y': -15},
        {'name': 'H_B', 'local_x': -30, 'local_y': 0},
        {'name': 'H_C', 'local_x': -30, 'local_y': 15},
        {'name': 'H_N', 'local_x': -30, 'local_y': 30},
        {'name': 'X_A', 'local_x': 30, 'local_y': -15},
        {'name': 'X_B', 'local_x': 30, 'local_y': 0},
        {'name': 'X_C', 'local_x': 30, 'local_y': 15},
        {'name': 'X_N', 'local_x': 30, 'local_y': 30},
    ],
    'probe': [  # 探针（单引脚，连接到目标节点）
        {'name': 'sense', 'local_x': 0, 'local_y': -15},
    ],
    'probe_between': [  # 两节点电压探针（sense 为正端，ref 为负端）
        {'name': 'sense', 'local_x': -12, 'local_y': -15},
        {'name': 'ref', 'local_x': 12, 'local_y': -15},
    ],
}


def get_umec_pins(params: Dict[str, Any] = None) -> List[Dict]:
    """Generate UMEC transformer pins from winding type parameters."""
    params = params or {}
    wtype1 = params.get('wtype1', 'Y_gnd')
    wtype2 = params.get('wtype2', 'Delta')

    pins = [
        {'name': 'H_A', 'local_x': -60, 'local_y': -30},
        {'name': 'H_B', 'local_x': -60, 'local_y': 0},
        {'name': 'H_C', 'local_x': -60, 'local_y': 30},
    ]
    if wtype1 in ('Y', 'Y_gnd'):
        pins.append({'name': 'H_N', 'local_x': -30, 'local_y': 58})

    pins.extend([
        {'name': 'X_A', 'local_x': 60, 'local_y': -30},
        {'name': 'X_B', 'local_x': 60, 'local_y': 0},
        {'name': 'X_C', 'local_x': 60, 'local_y': 30},
    ])
    if wtype2 in ('Y', 'Y_gnd'):
        pins.append({'name': 'X_N', 'local_x': 30, 'local_y': 58})

    return pins


def get_pins(
    comp_type: ComponentType,
    n_phases: int = 1,
    probe_type: str = None,
    params: Dict[str, Any] = None,
) -> List[Dict]:
    """获取指定类型的引脚定义"""
    if comp_type == ComponentType.GROUND:
        return PINS['ground']
    elif comp_type == ComponentType.VOLTAGE_SOURCE:
        return PINS['voltage_source']
    elif comp_type == ComponentType.BERGERON:
        return PINS['bergeron']
    elif comp_type == ComponentType.ULM:
        if n_phases == 1:
            return PINS['ulm_single']
        else:
            # 动态生成任意相数的引脚
            spacing = 15
            start_y = -(n_phases - 1) * spacing / 2
            pins = []
            for i in range(n_phases):
                y = start_y + i * spacing
                pins.append({'name': f'nk_{i}', 'local_x': -30, 'local_y': y})
                pins.append({'name': f'nm_{i}', 'local_x': 30, 'local_y': y})
            return pins
    elif comp_type == ComponentType.LCP_OHL:
        n_lines = max(1, n_phases)
        spacing = 15
        start_y = -(n_lines - 1) * spacing / 2
        pins = []
        for i in range(n_lines):
            y = start_y + i * spacing
            pins.append({'name': f'nk_{i}', 'local_x': -72, 'local_y': y})
            pins.append({'name': f'nm_{i}', 'local_x': 72, 'local_y': y})
        return pins
    elif comp_type == ComponentType.LCP_SINGLE_CABLE:
        # 每根电缆 3 导体 (core/sheath/armor) × 电缆数
        n_cables = max(1, n_phases)
        spacing = 15
        start_y = -(n_cables * 3 - 1) * spacing / 2
        pins = []
        for i in range(n_cables):
            for j, conductor in enumerate(['core', 'sheath', 'armor']):
                y = start_y + (i * 3 + j) * spacing
                pins.append({'name': f'nk_{i}_{conductor}', 'local_x': -72, 'local_y': y})
                pins.append({'name': f'nm_{i}_{conductor}', 'local_x': 72, 'local_y': y})
        return pins
    elif comp_type == ComponentType.LCP_THREE_CABLE:
        # 7 导体 (3 core + 3 sheath + pipe)
        spacing = 12
        conductor_names = ['core_a', 'core_b', 'core_c', 'sheath_a', 'sheath_b', 'sheath_c', 'pipe']
        start_y = -(len(conductor_names) - 1) * spacing / 2
        pins = []
        for j, cn in enumerate(conductor_names):
            y = start_y + j * spacing
            pins.append({'name': f'nk_{cn}', 'local_x': -72, 'local_y': y})
            pins.append({'name': f'nm_{cn}', 'local_x': 72, 'local_y': y})
        return pins
    elif comp_type == ComponentType.MOA:
        return PINS['moa']
    elif comp_type == ComponentType.LPM:
        return PINS['lpm']
    elif comp_type == ComponentType.UMEC_TRANSFORMER:
        return get_umec_pins(params)
    elif comp_type == ComponentType.PROBE:
        if probe_type == 'voltage_between':
            return PINS['probe_between']
        return PINS['probe']
    elif comp_type == ComponentType.SUBCIRCUIT:
        # 子电路引脚动态生成，默认返回空
        return []
    else:
        return PINS['two_port']


# 元件参数模板
PARAM_TEMPLATES = {
    ComponentType.RESISTOR: {
        'R': {
            'label': '电阻值',
            'unit': 'Ω',
            'default': 100.0,
            'min': 1e-6,
            'max': 1e12,
            'type': 'float',
            'scientific': True,
        },
    },

    ComponentType.INDUCTOR: {
        'L': {
            'label': '电感值',
            'unit': 'H',
            'default': 1e-3,
            'min': 1e-12,
            'max': 1e6,
            'type': 'float',
            'scientific': True,
        },
        'Rp': {
            'label': '并联电阻',
            'unit': 'Ω',
            'default': None,
            'min': 0,
            'max': 1e12,
            'type': 'float',
            'optional': True,
            'scientific': True,
        },
    },

    ComponentType.CAPACITOR: {
        'C': {
            'label': '电容值',
            'unit': 'F',
            'default': 1e-6,
            'min': 1e-15,
            'max': 1e3,
            'type': 'float',
            'scientific': True,
        },
        'Rp': {
            'label': '并联电阻',
            'unit': 'Ω',
            'default': None,
            'min': 0,
            'max': 1e12,
            'type': 'float',
            'optional': True,
            'scientific': True,
        },
    },

    ComponentType.SWITCH: {
        't_close': {
            'label': '闭合时间',
            'unit': 's',
            'default': 0.0,
            'type': 'float',
            'scientific': True,
        },
        't_open': {
            'label': '断开时间',
            'unit': 's',
            'default': 1e30,
            'type': 'float',
            'scientific': True,
        },
        'R_closed': {
            'label': '闭合电阻',
            'unit': 'Ω',
            'default': 1e-6,
            'min': 0,
            'max': 1e12,
            'type': 'float',
            'scientific': True,
        },
        'R_open': {
            'label': '断开电阻',
            'unit': 'Ω',
            'default': 1e8,
            'min': 0,
            'max': 1e12,
            'type': 'float',
            'scientific': True,
        },
    },

    ComponentType.VOLTAGE_SOURCE: {
        'voltage_func': {
            'label': '电压函数',
            'type': 'source_func',
            'default': {'mode': 'dc', 'value': 100.0},
            'supports_lightning': False,
        },
    },

    ComponentType.CURRENT_SOURCE: {
        'current_func': {
            'label': '电流函数',
            'type': 'source_func',
            'default': {'mode': 'dc', 'value': 1.0},
            'supports_lightning': True,
        },
    },

    ComponentType.MOA: {
        'vi_file': {
            'label': 'V-I 数据文件',
            'type': 'file',
            'default': '',
            'optional': True,
        },
        'rated_voltage': {
            'label': '额定电压',
            'unit': 'V',
            'default': 1.0,
            'min': 0,
            'max': 1e8,
            'type': 'float',
            'scientific': True,
        },
        'voltage_is_pu': {
            'label': '电压为标幺值',
            'type': 'bool',
            'default': True,
        },
        'breakpoints': {
            'label': 'V-I 断点',
            'type': 'breakpoints_table',
            'default': [],
            'optional': True,
        },
    },

    ComponentType.BERGERON: {
        'Zc': {
            'label': '波阻抗',
            'unit': 'Ω',
            'default': 300.0,
            'min': 0.01,
            'max': 1e4,
            'type': 'float',
            'scientific': True,
        },
        'length': {
            'label': '线路长度',
            'unit': 'm',
            'default': 15000.0,
            'min': 1,
            'max': 1e6,
            'type': 'float',
        },
    },

    ComponentType.ULM: {
        'fitulm_file': {
            'label': 'fitULM参数文件',
            'type': 'file',
            'default': '',
        },
        'length': {
            'label': '线路长度',
            'unit': 'm',
            'default': 20000.0,
            'min': 1,
            'max': 1e6,
            'type': 'float',
        },
        'n_phases': {
            'label': '相数',
            'unit': '',
            'default': 3,
            'min': 1,
            'max': 7,
            'type': 'int',
        },
    },

    ComponentType.GROUND: {},

    ComponentType.SERIES_RL: {
        'R': {
            'label': '电阻',
            'unit': 'Ω',
            'default': 10.0,
            'min': 1e-9,
            'max': 1e12,
            'type': 'float',
            'scientific': True,
        },
        'L': {
            'label': '电感',
            'unit': 'H',
            'default': 1e-3,
            'min': 1e-15,
            'max': 1e6,
            'type': 'float',
            'scientific': True,
        },
    },

    ComponentType.LPM: {
        'gap_length': {
            'label': '间隙长度',
            'unit': 'm',
            'default': 2.5,
            'min': 0.01,
            'max': 100,
            'type': 'float',
        },
        'k': {
            'label': '速度系数',
            'unit': '',
            'default': 1e-6,
            'min': 1e-15,
            'max': 1,
            'type': 'float',
            'scientific': True,
        },
        'E0': {
            'label': '临界场强',
            'unit': 'kV/m',
            'default': 600.0,
            'min': 1,
            'max': 1e5,
            'type': 'float',
        },
        'R_arc': {
            'label': '电弧电阻',
            'unit': 'Ω',
            'default': 1.0,
            'min': 1e-6,
            'max': 1e6,
            'type': 'float',
        },
        'altitude_m': {
            'label': '海拔',
            'unit': 'm',
            'default': 0.0,
            'min': 0,
            'max': 5000,
            'type': 'float',
        },
        'allow_extinction': {
            'label': '允许熄弧',
            'type': 'bool',
            'default': True,
        },
        'extinction_current': {
            'label': '熄弧电流',
            'unit': 'A',
            'default': 0.1,
            'min': 0,
            'max': 1e6,
            'type': 'float',
        },
    },

    ComponentType.LCP_OHL: {
        'length': {
            'label': '线路长度',
            'unit': 'm',
            'default': 900.0,
            'min': 1,
            'max': 1e6,
            'type': 'float',
        },
        'n_phases': {
            'label': '相数',
            'unit': '',
            'default': 2,
            'min': 1,
            'max': 7,
            'type': 'int',
        },
        'n_gw': {
            'label': '地线数',
            'unit': '',
            'default': 2,
            'min': 0,
            'max': 4,
            'type': 'int',
        },
        'ground_resistivity': {
            'label': '土壤电阻率',
            'unit': 'Ω·m',
            'default': 1000.0,
            'min': 1,
            'max': 1e5,
            'type': 'float',
        },
        'force_rebuild': {
            'label': '强制重建',
            'type': 'bool',
            'default': True,
        },
    },

    ComponentType.LCP_SINGLE_CABLE: {
        'length': {
            'label': '线路长度',
            'unit': 'm',
            'default': 1000.0,
            'min': 1,
            'max': 1e6,
            'type': 'float',
        },
        'n_cables': {
            'label': '电缆数',
            'unit': '',
            'default': 1,
            'min': 1,
            'max': 7,
            'type': 'int',
        },
        'force_rebuild': {
            'label': '强制重建',
            'type': 'bool',
            'default': True,
        },
    },

    ComponentType.LCP_THREE_CABLE: {
        'length': {
            'label': '线路长度',
            'unit': 'm',
            'default': 1000.0,
            'min': 1,
            'max': 1e6,
            'type': 'float',
        },
        'force_rebuild': {
            'label': '强制重建',
            'type': 'bool',
            'default': True,
        },
    },

    ComponentType.UMEC_TRANSFORMER: {
        'S_mva': {
            'label': '额定容量',
            'unit': 'MVA',
            'default': 100.0,
            'type': 'float',
            'scientific': True,
        },
        'freq': {
            'label': '额定频率',
            'unit': 'Hz',
            'default': 50.0,
            'type': 'float',
        },
        'V1_kV': {
            'label': '#1侧线电压',
            'unit': 'kV',
            'default': 220.0,
            'type': 'float',
        },
        'V2_kV': {
            'label': '#2侧线电压',
            'unit': 'kV',
            'default': 110.0,
            'type': 'float',
        },
        'wtype1': {
            'label': '#1侧接法',
            'type': 'choice',
            'choices': ['Y', 'Y_gnd', 'Delta'],
            'default': 'Y_gnd',
        },
        'wtype2': {
            'label': '#2侧接法',
            'type': 'choice',
            'choices': ['Y', 'Y_gnd', 'Delta'],
            'default': 'Delta',
        },
        'X_leak_pu': {
            'label': '漏抗',
            'unit': 'pu',
            'default': 0.08,
            'min': 0.001,
            'max': 0.5,
            'type': 'float',
        },
        'Im_percent': {
            'label': '励磁电流',
            'unit': '%',
            'default': 1.0,
            'min': 0.01,
            'max': 50.0,
            'type': 'float',
        },
        'NLL_pu': {
            'label': '空载损耗',
            'unit': 'pu',
            'default': 0.0,
            'min': 0,
            'max': 0.1,
            'type': 'float',
        },
        'CL_pu': {
            'label': '铜损',
            'unit': 'pu',
            'default': 0.0,
            'min': 0,
            'max': 0.1,
            'type': 'float',
        },
    },

    ComponentType.PROBE: {
        'probe_type': {
            'label': '探针类型',
            'type': 'choice',
            'choices': ['voltage_ground', 'voltage_between', 'branch_current'],
            'default': 'voltage_ground',
        },
        'unit': {
            'label': '显示单位',
            'type': 'choice',
            'choices': ['kV', 'V', 'A', 'kA', 'mA', 'mV'],
            'default': 'kV',
        },
        'line_name': {
            'label': '线路名称',
            'type': 'str',
            'default': '',
        },
        'line_end': {
            'label': '采样端',
            'type': 'choice',
            'choices': ['k', 'm'],
            'default': 'm',
        },
        'line_phase': {
            'label': '相序(0-based)',
            'type': 'int',
            'default': 0,
            'min': 0,
            'max': 99,
        },
    },

    ComponentType.SUBCIRCUIT: {
        'subcircuit_name': {
            'label': '子电路名称',
            'type': 'str',
            'default': '',
        },
    },
}


# 元件注册表
COMPONENT_REGISTRY = {
    ComponentType.RESISTOR: {
        'display_name': '电阻 R',
        'short_name': 'R',
        'pins': PINS['two_port'],
        'params_template': PARAM_TEMPLATES[ComponentType.RESISTOR],
        'api_method': 'add_R',
        'symbol_color': '#ef4444',
    },

    ComponentType.INDUCTOR: {
        'display_name': '电感 L',
        'short_name': 'L',
        'pins': PINS['two_port'],
        'params_template': PARAM_TEMPLATES[ComponentType.INDUCTOR],
        'api_method': 'add_L',
        'symbol_color': '#3b82f6',
    },

    ComponentType.CAPACITOR: {
        'display_name': '电容 C',
        'short_name': 'C',
        'pins': PINS['two_port'],
        'params_template': PARAM_TEMPLATES[ComponentType.CAPACITOR],
        'api_method': 'add_C',
        'symbol_color': '#22c55e',
    },

    ComponentType.SWITCH: {
        'display_name': '开关 SW',
        'short_name': 'SW',
        'pins': PINS['two_port'],
        'params_template': PARAM_TEMPLATES[ComponentType.SWITCH],
        'api_method': 'add_SW',
        'symbol_color': '#f59e0b',
    },

    ComponentType.VOLTAGE_SOURCE: {
        'display_name': '电压源 VS',
        'short_name': 'VS',
        'pins': PINS['voltage_source'],
        'params_template': PARAM_TEMPLATES[ComponentType.VOLTAGE_SOURCE],
        'api_method': 'add_VS',
        'symbol_color': '#dc2626',
    },

    ComponentType.CURRENT_SOURCE: {
        'display_name': '电流源 IS',
        'short_name': 'IS',
        'pins': PINS['two_port'],
        'params_template': PARAM_TEMPLATES[ComponentType.CURRENT_SOURCE],
        'api_method': 'add_IS',
        'symbol_color': '#2563eb',
    },

    ComponentType.MOA: {
        'display_name': 'MOA避雷器',
        'short_name': 'MOA',
        'pins': PINS['moa'],
        'params_template': PARAM_TEMPLATES[ComponentType.MOA],
        'api_method': 'add_MOA',
        'symbol_color': '#7c3aed',
    },

    ComponentType.BERGERON: {
        'display_name': 'Bergeron传输线',
        'short_name': 'Berg',
        'pins': PINS['bergeron'],
        'params_template': PARAM_TEMPLATES[ComponentType.BERGERON],
        'api_method': 'add_bergeron_line',
        'symbol_color': '#0891b2',
    },

    ComponentType.ULM: {
        'display_name': 'ULM传输线',
        'short_name': 'ULM',
        'pins': lambda n_phases=1: get_pins(ComponentType.ULM, n_phases),
        'params_template': PARAM_TEMPLATES[ComponentType.ULM],
        'api_method': 'add_ulm_line',
        'symbol_color': '#0891b2',
        'dynamic_pins': True,  # 引脚数量根据 n_phases 参数变化
    },

    ComponentType.GROUND: {
        'display_name': '接地',
        'short_name': 'GND',
        'pins': PINS['ground'],
        'params_template': PARAM_TEMPLATES[ComponentType.GROUND],
        'api_method': None,
        'symbol_color': '#1e2a3a',
    },

    ComponentType.SERIES_RL: {
        'display_name': '串联RL',
        'short_name': 'SRL',
        'pins': PINS['two_port'],
        'params_template': PARAM_TEMPLATES[ComponentType.SERIES_RL],
        'api_method': 'add_series_RL',
        'symbol_color': '#8b5cf6',
    },

    ComponentType.LPM: {
        'display_name': 'LPM绝缘子',
        'short_name': 'LPM',
        'pins': PINS['lpm'],
        'params_template': PARAM_TEMPLATES[ComponentType.LPM],
        'api_method': 'add_insulator_LPM',
        'symbol_color': '#f97316',
    },

    ComponentType.LCP_OHL: {
        'display_name': 'LCP架空线',
        'short_name': 'LCP-OHL',
        'pins': lambda n_phases=1: get_pins(ComponentType.LCP_OHL, n_phases),
        'params_template': PARAM_TEMPLATES[ComponentType.LCP_OHL],
        'api_method': 'add_lcp_ohl_line',
        'symbol_color': '#0d9488',
        'dynamic_pins': True,
    },

    ComponentType.LCP_SINGLE_CABLE: {
        'display_name': 'LCP单芯电缆',
        'short_name': 'LCP-SC',
        'pins': lambda n_phases=1: get_pins(ComponentType.LCP_SINGLE_CABLE, n_phases),
        'params_template': PARAM_TEMPLATES[ComponentType.LCP_SINGLE_CABLE],
        'api_method': 'add_lcp_single_core_cable_line',
        'symbol_color': '#0d9488',
        'dynamic_pins': True,
    },

    ComponentType.LCP_THREE_CABLE: {
        'display_name': 'LCP三芯电缆',
        'short_name': 'LCP-3C',
        'pins': lambda n_phases=1: get_pins(ComponentType.LCP_THREE_CABLE, n_phases),
        'params_template': PARAM_TEMPLATES[ComponentType.LCP_THREE_CABLE],
        'api_method': 'add_lcp_three_core_cable_line',
        'symbol_color': '#0d9488',
        'dynamic_pins': True,
    },

    ComponentType.UMEC_TRANSFORMER: {
        'display_name': 'UMEC变压器',
        'short_name': 'UMEC',
        'pins': lambda params=None: get_umec_pins(params),
        'params_template': PARAM_TEMPLATES[ComponentType.UMEC_TRANSFORMER],
        'api_method': 'add_UMEC_transformer',
        'symbol_color': '#6366f1',
        'dynamic_pins': True,
    },

    ComponentType.PROBE: {
        'display_name': '探针',
        'short_name': 'PRB',
        'pins': PINS['probe'],
        'params_template': PARAM_TEMPLATES[ComponentType.PROBE],
        'api_method': None,  # 探针不直接映射到 solver API，由 SolverBuilder 处理
        'symbol_color': '#eab308',
    },

    ComponentType.SUBCIRCUIT: {
        'display_name': '子电路',
        'short_name': 'SUB',
        'pins': [],  # 引脚动态生成
        'params_template': PARAM_TEMPLATES[ComponentType.SUBCIRCUIT],
        'api_method': None,  # 子电路由 SolverBuilder 展平处理
        'symbol_color': '#0369a1',
    },
}


def get_component_info(comp_type: ComponentType) -> Dict:
    """获取元件信息"""
    return COMPONENT_REGISTRY.get(comp_type, {})


def get_default_params(comp_type: ComponentType) -> Dict[str, Any]:
    """获取元件默认参数"""
    template = PARAM_TEMPLATES.get(comp_type, {})
    defaults = {}
    for name, spec in template.items():
        if spec.get('type') == 'source_func':
            defaults[name] = spec['default'].copy()
        elif spec.get('type') == 'bool':
            defaults[name] = spec.get('default', False)
        elif spec.get('type') in ('breakpoints_table', 'position_table'):
            defaults[name] = spec.get('default', [])
        elif spec.get('type') == 'choice':
            defaults[name] = spec.get('default', spec.get('choices', [''])[0])
        else:
            defaults[name] = spec.get('default')
    return defaults


def create_component_pins(
    comp_type: ComponentType,
    n_phases: int = 3,
    probe_type: str = None,
    params: Dict[str, Any] = None,
) -> List:
    """从模板创建元件引脚"""
    from .circuit_model import Pin
    pin_defs = get_pins(comp_type, n_phases, probe_type=probe_type, params=params)
    return [Pin(name=p['name'], local_x=p['local_x'], local_y=p['local_y']) for p in pin_defs]

def create_component(comp_type: ComponentType, n_phases: int = 1):
    """创建元件参数字典（含引脚）"""
    return {
        'pins': get_pins(comp_type, n_phases),
    }
