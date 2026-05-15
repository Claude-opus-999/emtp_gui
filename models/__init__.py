"""
EMTP 电路仿真 GUI - 数据模型
"""

from .circuit_model import (
    ComponentType,
    Pin,
    ComponentInstance,
    Wire,
    SimSettings,
    CircuitModel,
)

from .component_lib import COMPONENT_REGISTRY, get_component_info

__all__ = [
    'ComponentType',
    'Pin',
    'ComponentInstance',
    'Wire',
    'SimSettings',
    'CircuitModel',
    'COMPONENT_REGISTRY',
    'get_component_info',
]