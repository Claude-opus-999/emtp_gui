"""
EMTP 电路仿真 GUI - 后台仿真执行器
在 QThread 中通过 SolverBuilder 直接构建并运行求解器，避免 GUI 卡死。
不再使用 exec() 执行代码字符串，消除了安全风险。
支持进度回调、中途取消、结果序列化、timing 统计提取。

当内核不支持 step_callback 时，将 solver.run() 放入内部 daemon 线程，
QThread 用轮询循环监控取消标志，实现「真正可取消」。
"""

from PySide6.QtCore import QThread, Signal
import inspect
import threading
import traceback


def solver_supports_step_callback(solver) -> bool:
    """Return whether solver.run accepts a step_callback keyword."""
    try:
        return "step_callback" in inspect.signature(solver.run).parameters
    except (TypeError, ValueError, AttributeError):
        return False


def extract_timing_report(solver) -> dict:
    """从 solver 提取 timing 报告（如果内核支持）"""
    try:
        report = solver.get_timing_report()
        if isinstance(report, dict):
            return report
    except (AttributeError, TypeError):
        pass
    return {}


def extract_probe_results(solver) -> dict:
    """从 solver 提取所有探针数据（用于序列化导出）"""
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
        for name in probe_list.get('voltage', []):
            try:
                data = solver.get_probe(name, unit='kV')
                result['probes'][name] = {
                    'data': data, 'unit': 'kV', 'type': 'voltage'
                }
            except Exception:
                pass

        for name in probe_list.get('branch_current', []):
            try:
                data = solver.get_probe(name, unit='A')
                result['probes'][name] = {
                    'data': data, 'unit': 'A', 'type': 'branch_current'
                }
            except Exception:
                pass

        for name in probe_list.get('line_current', []):
            try:
                data = solver.get_probe(name, unit='A')
                result['probes'][name] = {
                    'data': data, 'unit': 'A', 'type': 'line_current'
                }
            except Exception:
                pass

    return result


_POLL_INTERVAL = 0.25  # 轮询间隔（秒）


class SimulationRunner(QThread):
    """后台仿真线程 - 使用 SolverBuilder 直接构建

    progress_pct 特殊值:
        -1  → 告知 UI 切换到「不确定」脉冲模式（无法计算百分比）
        0~100 → 正常百分比
    """

    progress = Signal(str)       # 进度消息
    progress_pct = Signal(int)   # 进度百分比 (0-100)，-1 表示不确定模式
    log_received = Signal(str)   # 日志行
    finished_ok = Signal(object) # 仿真完成，传回 solver 对象
    error = Signal(str)          # 错误消息
    results_ready = Signal(dict) # 序列化结果（探针数据 + timing）

    def __init__(self, model, parent=None):
        super().__init__(parent)
        # 不能用 copy.deepcopy(model)！
        # model._observers 包含绑定到 PySide6 QWidget 的回调方法，
        # deepcopy 会尝试复制 QWidget → TypeError 崩溃。
        # 改用 to_dict/from_dict 序列化，既安全又避免复制 undo 栈。
        from models.circuit_model import CircuitModel as CM
        self.model = CM.from_dict(model.to_dict())
        self._cancel_requested = False

    def request_cancel(self):
        """请求取消仿真"""
        self._cancel_requested = True

    # ------------------------------------------------------------------
    #  主入口
    # ------------------------------------------------------------------

    def run(self):
        self._cancel_requested = False
        try:
            # 1. 检查 emtp 内核
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

            # 2. 构建求解器
            self.progress.emit("正在构建电路...")
            self.log_received.emit("[构建] 正在构建电路...")
            self.progress_pct.emit(5)

            if self._cancel_requested:
                self._emit_cancelled()
                return

            builder = SolverBuilder()
            solver, node_map = builder.build(self.model)

            if self._cancel_requested:
                self._emit_cancelled()
                return

            # 3. 运行仿真
            self.progress.emit("正在运行仿真...")
            self.log_received.emit("[仿真] 开始运行...")
            self.progress_pct.emit(10)

            cancelled = self._run_solver(solver)
            if cancelled:
                self._emit_cancelled()
                return

            # 4. 完成
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

            self.finished_ok.emit(solver)

        except Exception as e:
            if self._cancel_requested:
                self._emit_cancelled()
            else:
                error_msg = f"{type(e).__name__}: {str(e)}\n\n{traceback.format_exc()}"
                self.error.emit(error_msg)

    # ------------------------------------------------------------------
    #  solver.run 的两种执行策略
    # ------------------------------------------------------------------

    def _run_solver(self, solver) -> bool:
        """执行 solver.run()，返回 True 表示已取消。

        策略 A：内核支持 step_callback → 直接在当前线程运行，回调中检查取消。
        策略 B：内核不支持 step_callback → 在 daemon 线程中运行 solver.run()，
                QThread 用轮询循环监控取消标志，可随时中断等待。
        """
        if solver_supports_step_callback(solver):
            return self._run_with_callback(solver)
        else:
            return self._run_with_polling(solver)

    def _run_with_callback(self, solver) -> bool:
        """策略 A：内核支持 step_callback"""
        self.log_received.emit("[仿真] 内核支持 step_callback，进度实时上报")

        def on_step(step, total_steps):
            if self._cancel_requested:
                return False
            pct = 10 + int(85 * step / max(total_steps, 1))
            self.progress_pct.emit(min(pct, 95))
            if step % max(1, total_steps // 10) == 0:
                self.progress.emit(f"仿真进行中: {step}/{total_steps} 步")
                self.log_received.emit(f"[仿真] 步骤 {step}/{total_steps}")
            return True

        solver.run(step_callback=on_step)
        return self._cancel_requested

    def _run_with_polling(self, solver) -> bool:
        """策略 B：内核不支持 step_callback。

        将 solver.run() 放入 daemon 线程，QThread 轮询取消标志。
        取消时 daemon 线程可能仍在后台运行（受限于 C 扩展无法中断），
        但 QThread 会立即返回，UI 不再卡死。
        """
        self.log_received.emit(
            "[仿真] 内核不支持 step_callback，使用轮询模式"
        )
        # 告诉 UI 切换到「不确定」脉冲进度条
        self.progress_pct.emit(-1)

        # 用于捕获 solver.run() 可能抛出的异常
        solver_error = [None]

        def _solver_target():
            try:
                solver.run()
            except Exception as exc:
                solver_error[0] = exc

        worker = threading.Thread(target=_solver_target, daemon=True)
        worker.start()

        # 轮询等待：每 250ms 检查一次取消标志和线程存活状态
        elapsed = 0.0
        while worker.is_alive():
            worker.join(timeout=_POLL_INTERVAL)
            elapsed += _POLL_INTERVAL

            if self._cancel_requested:
                self.log_received.emit(
                    f"[仿真] 收到取消请求，正在终止（已运行 {elapsed:.1f}s）"
                )
                # daemon 线程会在进程退出时自动清理，
                # 这里直接返回，不再等待 solver 完成。
                return True

            # 每 2 秒报告一次仍在运行（让用户知道没有假死）
            if elapsed > 0 and int(elapsed / 2.0) != int((elapsed - _POLL_INTERVAL) / 2.0):
                self.progress.emit(f"仿真运行中… 已用时 {elapsed:.0f}s")

        # solver.run() 已结束
        if solver_error[0] is not None:
            raise solver_error[0]

        return self._cancel_requested

    # ------------------------------------------------------------------

    def _emit_cancelled(self):
        self.progress.emit("仿真已取消")
        self.progress_pct.emit(0)
        self.log_received.emit("[仿真] 仿真已取消")
