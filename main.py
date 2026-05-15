"""
EMTP 电路仿真 GUI - 主入口
"""

import sys
import os
from PySide6.QtWidgets import QApplication

# ============================================================
#  注册 emtp 内核包
#  内核目录名可能不是标准包名，需要手动加载并注册为 "emtp"
# ============================================================
_EMTP_KERNEL_DIR = os.environ.get(
    'EMTP_KERNEL_DIR',
    r'D:\pythonproject\emtp_0508_back',
)

_emtp_available = False

def _try_import_emtp():
    """尝试导入 emtp 内核，支持多种路径策略"""
    global _emtp_available

    # 策略 1: 直接 import（如果 pip install -e 或目录名就是 emtp）
    try:
        import emtp
        _emtp_available = True
        return
    except ModuleNotFoundError:
        pass

    # 策略 2: 将内核目录手动加载为 emtp 包
    kernel_dir = _EMTP_KERNEL_DIR
    init_file = os.path.join(kernel_dir, '__init__.py')
    if os.path.isfile(init_file):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'emtp', init_file,
            submodule_search_locations=[kernel_dir],
        )
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys.modules['emtp'] = mod
            spec.loader.exec_module(mod)
            _emtp_available = True
            return

    # 策略 3: 将父目录加入 sys.path，期望子目录名为 emtp
    parent_dir = os.path.dirname(kernel_dir)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    try:
        import emtp
        _emtp_available = True
    except ModuleNotFoundError:
        print(f"[EMTP GUI] 警告: 无法加载 emtp 内核 (尝试路径: {kernel_dir})")
        print("[EMTP GUI] 仿真功能将不可用，请设置 EMTP_KERNEL_DIR 环境变量或 pip install -e 安装内核")

_try_import_emtp()

# 将 emtp_gui 包目录加入 sys.path，确保子模块可直接 import
_pkg_dir = os.path.dirname(os.path.abspath(__file__))
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)

from ui.mpl_config import configure_matplotlib_fonts

configure_matplotlib_fonts()

from ui.main_window import MainWindow


def main():
    """主函数"""
    app = QApplication(sys.argv)
    app.setApplicationName("EMTP Circuit Simulator")
    app.setOrganizationName("EMTP")

    # 设置样式
    app.setStyleSheet("""
        QMainWindow {
            background-color: #f8fafc;
        }
        QMenuBar {
            background-color: #ffffff;
            border-bottom: 1px solid #e2e8f0;
        }
        QMenuBar::item:selected {
            background-color: #2563eb;
            color: white;
        }
        QMenu {
            background-color: #ffffff;
            border: 1px solid #e2e8f0;
        }
        QMenu::item:selected {
            background-color: #2563eb;
            color: white;
        }
        QToolBar {
            background-color: #ffffff;
            border-bottom: 1px solid #e2e8f0;
            spacing: 4px;
            padding: 4px;
        }
        QStatusBar {
            background-color: #ffffff;
            border-top: 1px solid #e2e8f0;
            color: #64748b;
        }
        QDockWidget {
            background-color: #ffffff;
            titlebar-close-icon: url(close.png);
        }
        QDockWidget::title {
            background-color: #f8fafc;
            border-bottom: 1px solid #e2e8f0;
            padding: 6px;
        }
    """)

    window = MainWindow()
    window.resize(1400, 900)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
