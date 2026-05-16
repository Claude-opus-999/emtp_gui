"""
EMTP 电路仿真 GUI - 后台仿真执行器
在 QThread 中通过 SolverBuilder 直接构建并运行求解器，避免 GUI 卡死。
不再使用 exec() 执行代码字符串，消除了安全风险。
支持进度回调、中途取消、结果序列化、timing 统计提取。
"""

from PySide6.QtCore import QThread, Signal
import copy
import inspect
import traceback


def solver_supports_step_callback(solver) -> bool:
    """Return whether solver.run accepts a step_callback keyword."""
    try:
        return "step_callback" in inspect.signature(solver.run).parameters
    except (TypeError, ValueError, AttributeError):
        return False


def extract_timing_report(solver) -> dict:
    """从 solver 提取 timing 报告（如果内核支持）

    Returns:
        dict: timing 数据，可能为空
    """
    try:
        report = solver.get_timing_report()
        if isinstance(report, dict):
            return report
    except (AttributeError, TypeError):
        pass
    return {}


def extract_probe_results(solver) -> dict:
    """从 solver 提取所有探针数据（用于序列化导出）

    Returns:
        dict: {
            'time': numpy_array,
            'probes': {name: {'data': numpy_array, 'unit': str, 'type': str}},
            'timing': dict,
        }
    """
    result = {
        'time': None,
        'probes': {},
        'timing': extract_timing_report(solver),
    }

    try:
        result['time'] = solver.get_time('s')
    except (AttributeError, TypeError):
        pass

    try:
        probe_list = solver.list_probes()
    except (AttributeError, TypeError):
        probe_list = None

    if probe_list:
        # 电压探针
        for name in probe_list.get('voltage', []):
            try:
                data = solver.get_probe(name, unit='kV')
                result['probes'][name] = {
                    'data': data, 'unit': 'kV', 'type': 'voltage'
                }
            except Exception:
                pass

        # 支路电流探针
        for name in probe_list.get('branch_current', []):
            try:
                data = solver.get_probe(name, unit='A')
                result['probes'][name] = {
                    'data': data, 'unit': 'A', 'type': 'branch_current'
                }
            except Exception:
                pass

        # 线路电流探针
        for name in probe_list.get('line_current', []):
            try:
                data = solver.get_probe(name, unit='A')
                result['probes'][name] = {
                    'data': data, 'unit': 'A', 'type': 'line_current'
                }
            except Exception:
                pass

    return result


class SimulationRunner(QThread):
    """后台仿真线程 - 使用 SolverBuilder 直接构建"""

    progress = Signal(str)       # 进度消息
    progress_pct = Signal(int)   # 进度百分比 (0-100)
    log_received = Signal(str)   # 日志行（用于实时流式输出）
    finished_ok = Signal(object) # 仿真完成，传回 solver 对象
    error = Signal(str)          # 错误消息
    results_ready = Signal(dict) # 序列化结果（探针数据 + timing）

    def __init__(self, model, parent=None):
        """
        初始化仿真执行器。

        Args:
            model: CircuitModel 实例
        """
        super().__init__(parent)
        self.model = copy.deepcopy(model)
        self._cancel_requested = False

    def request_cancel(self):
        """请求取消仿真"""
        self._cancel_requested = True

    def run(self):
        self._cancel_requested = False
        try:
            # 检查 emtp 内核是否可用
            try:
                from emtp import EMTPSolver
            except ModuleNotFoundError:
                self.error.emit(
                    "无法导入 emtp 内核！\n\n"
                    "请确认内核已安装或路径正确：\n"
                    "  1. pip install -e D:/pythonproject/emtp_0508_back\n"
                    "  2. 或设置环境变量 EMTP_KERNEL_DIR 指向内核目录\n\n"
                    "当前搜索路径中的 emtp 包未找到。"
                )
                return

            from core.solver_builder import SolverBuilder

            self.progress.emit("正在构建电路...")
            self.log_received.emit("[构建] 正在构建电路...")
            self.progress_pct.emit(5)

            if self._cancel_requested:
                self.progress.emit("仿真已取消")
                return

            builder = SolverBuilder()
            solver, node_map = builder.build(self.model)
            supports_step_callback = solver_supports_step_callback(solver)

            self.progress.emit("正在运行仿真...")
            self.log_received.emit("[仿真] 开始运行...")
            self.progress_pct.emit(10)

            # 设置进度回调
            def on_step(step, total_steps):
                if self._cancel_requested:
                    return False  # 通知 solver 停止
                pct = 10 + int(85 * step / max(total_steps, 1))
                self.progress_pct.emit(min(pct, 95))
                if step % max(1, total_steps // 10) == 0:
                    self.progress.emit(f"仿真进行中: {step}/{total_steps} 步")
                    self.log_received.emit(f"[仿真] 步骤 {step}/{total_steps}")
                return True  # 继续

            # 尝试使用带回调的 run
            if supports_step_callback:
                solver.run(step_callback=on_step)
            else:
                self.log_received.emit(
                    "[仿真] 当前内核不支持 step_callback，取消将在本次求解返回后生效。"
                )
                solver.run()

            if self._cancel_requested:
                self.progress.emit("仿真已取消")
                self.progress_pct.emit(0)
                return

            self.progress.emit("仿真完成")
            self.progress_pct.emit(100)
            self.log_received.emit("[仿真] 仿真完成")

            # 提取序列化结果
            try:
                serialized = extract_probe_results(solver)
                self.results_ready.emit(serialized)
                self.log_received.emit(
                    f"[结果] 已提取 {len(serialized['probes'])} 个探针数据"
                )
                if serialized['timing']:
                    self.log_received.emit("[结果] timing 统计已提取")
            except Exception as e:
                self.log_received.emit(f"[结果] 提取序列化结果时出错: {e}")

            # 发射 solver 对象（供 PlotPanel 直接使用）
            self.finished_ok.emit(solver)

        except Exception as e:
            if self._cancel_requested:
                self.progress.emit("仿真已取消")
                self.progress_pct.emit(0)
            else:
                error_msg = f"{type(e).__name__}: {str(e)}\n\n{traceback.format_exc()}"
                self.error.emit(error_msg)
