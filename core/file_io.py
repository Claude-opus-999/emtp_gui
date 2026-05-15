"""
EMTP 电路仿真 GUI - 项目文件读写
处理 .emtp JSON 格式的保存和加载
"""

import json
from typing import Optional
from models.circuit_model import CircuitModel


def save_project(model: CircuitModel, file_path: str) -> None:
    """保存项目到 .emtp 文件"""
    data = model.to_dict()
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_project(file_path: str) -> CircuitModel:
    """从 .emtp 文件加载项目"""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return CircuitModel.from_dict(data)


def export_python_code(code: str, file_path: str) -> None:
    """导出 Python 脚本"""
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(code)
