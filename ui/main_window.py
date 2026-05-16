"""
EMTP 电路仿真 GUI - 主窗口
包含菜单栏、工具栏、元件面板、属性编辑器、仿真配置、代码预览、波形显示、控制台
"""

import re

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QDockWidget, QStatusBar, QMenuBar, QToolBar,
    QMessageBox, QFileDialog, QLabel, QPushButton, QDialog,
    QTabWidget, QComboBox, QSpinBox, QDoubleSpinBox,
    QGroupBox, QFormLayout, QLineEdit, QPlainTextEdit,
    QCheckBox, QTextEdit, QSplitter, QSizePolicy,
    QProgressDialog, QScrollArea,
)
from PySide6.QtCore import Qt, QSize, QPointF, Signal, QRegularExpression
from PySide6.QtGui import (
    QAction, QKeySequence, QCloseEvent,
    QFont, QTextCharFormat, QColor, QSyntaxHighlighter,
    QTextDocument, QValidator,
)

from models.circuit_model import (
    CircuitModel, ComponentType, ComponentInstance, Pin, Wire,
)
from models.component_lib import (
    COMPONENT_REGISTRY, get_default_params, create_component_pins,
)
from core.code_generator import generate_code
from core.file_io import save_project, load_project, export_python_code
from core.sim_runner import SimulationRunner
from ui.circuit_canvas import CircuitCanvas, CanvasMode, ComponentGraphicsItem


# ---------------------------------------------------------------------------
#  Python 语法高亮
# ---------------------------------------------------------------------------

class PythonHighlighter(QSyntaxHighlighter):
    """Python 语法高亮器（暗色主题）"""

    def __init__(self, document: QTextDocument):
        super().__init__(document)
        self._formats = self._build_formats()
        self._rules = self._build_rules()

    # ---- 颜色/格式 ----

    @staticmethod
    def _build_formats():
        _f = PythonHighlighter._fmt
        return {
            'keyword':      _f('#c586c0', bold=True),
            'builtin':      _f('#dcdcaa'),
            'string':       _f('#ce9178'),
            'number':       _f('#b5cea8'),
            'comment':      _f('#6a9955', italic=True),
            'decorator':    _f('#dcdcaa'),
            'classname':    _f('#4ec9b0'),
            'function':     _f('#dcdcaa'),
        }

    @staticmethod
    def _fmt(color: str, bold=False, italic=False) -> QTextCharFormat:
        f = QTextCharFormat()
        f.setForeground(QColor(color))
        if bold:
            f.setFontWeight(QFont.Bold)
        if italic:
            f.setFontItalic(True)
        return f

    # ---- 规则 ----

    def _build_rules(self):
        fmts = self._formats
        rules = []

        # 关键字
        kw = r'\b(?:import|from|def|class|return|if|elif|else|for|while|' \
             r'break|continue|with|as|try|except|finally|raise|yield|' \
             r'lambda|and|or|not|in|is|pass|del|global|nonlocal|assert|' \
             r'True|False|None)\b'
        rules.append((QRegularExpression(kw), 'keyword'))

        # 内建函数
        bi = r'\b(?:print|range|len|int|float|str|list|dict|set|tuple|' \
             r'type|isinstance|abs|max|min|sum|sorted|reversed|enumerate|' \
             r'zip|map|filter|open|super|property|staticmethod)\b'
        rules.append((QRegularExpression(bi), 'builtin'))

        # 字符串（三引号 & 单双引号）
        rules.append((QRegularExpression(r'"""[\s\S]*?"""'), 'string'))
        rules.append((QRegularExpression(r"'''[\s\S]*?'''"), 'string'))
        rules.append((QRegularExpression(r'"[^"\\]*(?:\\.[^"\\]*)*"'), 'string'))
        rules.append((QRegularExpression(r"'[^'\\]*(?:\\.[^'\\]*)*'"), 'string'))

        # 数字
        rules.append((QRegularExpression(
            r'\b(?:0[box])?[0-9](?:_?[0-9])*(?:\.[0-9](?:_?[0-9])*)?'
            r'(?:[eE][+-]?[0-9]+)?\b'), 'number'))

        # 注释
        rules.append((QRegularExpression(r'#[^\n]*'), 'comment'))

        # 装饰器
        rules.append((QRegularExpression(r'@\w+'), 'decorator'))

        return rules

    def highlightBlock(self, text: str):
        for regex, fmt_name in self._rules:
            it = regex.globalMatch(text)
            while it.hasNext():
                match = it.next()
                self.setFormat(match.capturedStart(), match.capturedLength(),
                               self._formats[fmt_name])


# ---------------------------------------------------------------------------
#  科学计数法 QDoubleSpinBox 辅助
# ---------------------------------------------------------------------------

class ScientificSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox that accepts compact scientific notation while typing."""

    _ACCEPTABLE_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
    _INTERMEDIATE_RE = re.compile(r"^[+-]?(?:(?:\d+(?:\.\d*)?|\.\d*)?(?:[eE][+-]?\d*)?)?$")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(1e-15, 1e6)
        self.setDecimals(12)
        self.setMinimumWidth(130)
        self.setKeyboardTracking(False)

    def textFromValue(self, val: float) -> str:
        if val == 0:
            return "0"
        if abs(val) < 1e-3 or abs(val) >= 1e6:
            return f"{val:.6e}"
        return f"{val:.6g}"

    def valueFromText(self, text: str) -> float:
        try:
            return float(text.replace(',', ''))
        except ValueError:
            return self.value()

    def validate(self, text: str, pos: int):
        candidate = text.strip().replace(',', '')
        if self._ACCEPTABLE_RE.fullmatch(candidate):
            value = float(candidate)
            if self.minimum() <= value <= self.maximum():
                return (QValidator.State.Acceptable, text, pos)
            return (QValidator.State.Intermediate, text, pos)
        if self._INTERMEDIATE_RE.fullmatch(candidate):
            return (QValidator.State.Intermediate, text, pos)
        return (QValidator.State.Invalid, text, pos)


# ---------------------------------------------------------------------------
#  SourceFuncEditor — 电源函数编辑器（DC / AC / Lightning / Custom）
# ---------------------------------------------------------------------------

class SourceFuncEditor(QGroupBox):
    """编辑电压源/电流源的激励函数"""

    dataChanged = Signal()  # 参数变化信号

    def __init__(self, parent=None):
        super().__init__("激励函数", parent)
        self._func_data: dict = {}
        self._func_param_key = None  # 绑定的参数名
        self._build_ui()

    def _build_ui(self):
        layout = QFormLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 模式选择
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["DC 直流", "AC 交流", "Lightning 雷电", "Custom 自定义"])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        layout.addRow("模式:", self.mode_combo)

        # --- DC ---
        self.dc_value = ScientificSpinBox()
        self.dc_value.setValue(100.0)
        self.dc_value.valueChanged.connect(self._emit_data_changed)
        self.dc_widget = QWidget()
        fl = QFormLayout(self.dc_widget)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.addRow("电压/电流值:", self.dc_value)
        layout.addRow(self.dc_widget)

        # --- AC ---
        self.ac_widget = QWidget()
        ac_fl = QFormLayout(self.ac_widget)
        ac_fl.setContentsMargins(0, 0, 0, 0)
        self.ac_amplitude = ScientificSpinBox()
        self.ac_amplitude.setValue(100.0)
        self.ac_amplitude.valueChanged.connect(self._emit_data_changed)
        self.ac_frequency = QDoubleSpinBox()
        self.ac_frequency.setRange(0.001, 1e9)
        self.ac_frequency.setValue(50.0)
        self.ac_frequency.setSuffix(" Hz")
        self.ac_frequency.valueChanged.connect(self._emit_data_changed)
        self.ac_phase = ScientificSpinBox()
        self.ac_phase.setValue(0.0)
        self.ac_phase.setSuffix(" rad")
        self.ac_phase.valueChanged.connect(self._emit_data_changed)
        ac_fl.addRow("幅值:", self.ac_amplitude)
        ac_fl.addRow("频率:", self.ac_frequency)
        ac_fl.addRow("初相:", self.ac_phase)
        layout.addRow(self.ac_widget)

        # --- Lightning ---
        self.ln_widget = QWidget()
        ln_fl = QFormLayout(self.ln_widget)
        ln_fl.setContentsMargins(0, 0, 0, 0)

        # 雷电模型选择
        self.ln_model = QComboBox()
        self.ln_model.addItems([
            "标准双指数波形",
            "自定义双指数 (T1/T2)",
            "双指数直接参数 (τ1/τ2)",
            "双指数 ATP参数 (A/B)",
            "Heidler (T1/T2/n)",
            "Heidler 直接参数 (Tf/τ)",
        ])
        self.ln_model.setCurrentIndex(0)
        self.ln_model.currentIndexChanged.connect(self._on_ln_model_changed)
        ln_fl.addRow("雷电模型:", self.ln_model)

        # 通用参数：峰值 & 起始时间
        self.ln_peak = ScientificSpinBox()
        self.ln_peak.setRange(0, 1e9)
        self.ln_peak.setValue(10000.0)
        self.ln_peak.setSuffix(" A")
        self.ln_peak.valueChanged.connect(self._emit_data_changed)
        ln_fl.addRow("峰值:", self.ln_peak)

        self.ln_tstart = ScientificSpinBox()
        self.ln_tstart.setRange(0, 1e6)
        self.ln_tstart.setValue(0.0)
        self.ln_tstart.setSuffix(" s")
        self.ln_tstart.valueChanged.connect(self._emit_data_changed)
        ln_fl.addRow("起始时间:", self.ln_tstart)

        # ---- 子面板: 标准双指数波形 ----
        self.ln_std_widget = QWidget()
        std_fl = QFormLayout(self.ln_std_widget)
        std_fl.setContentsMargins(0, 0, 0, 0)
        self.ln_waveform = QComboBox()
        self.ln_waveform.addItems([
            "1.2/50 μs  (标准雷电电压冲击)",
            "2/20 μs   (后续雷击电流)",
            "8/20 μs   (标准雷电流冲击)",
            "4/10 μs   (快速雷电流冲击)",
            "10/350 μs (首次雷击电流)",
            "0.25/100 μs (后续雷击电流)",
            "10/700 μs (通信线路雷电冲击)",
            "30/80 μs  (操作电流冲击)",
            "250/2500 μs (长波头电压冲击)",
            "1/200 μs  (后续雷击电流)",
        ])
        self.ln_waveform.setCurrentIndex(2)  # 8/20 为默认
        self.ln_waveform.currentIndexChanged.connect(self._emit_data_changed)
        self.ln_perc = QComboBox()
        self.ln_perc.addItems(["30", "0", "10", "50"])
        self.ln_perc.setCurrentIndex(0)  # PERC=30 默认
        self.ln_perc.currentIndexChanged.connect(self._emit_data_changed)
        std_fl.addRow("波形:", self.ln_waveform)
        std_fl.addRow("PERC:", self.ln_perc)
        ln_fl.addRow(self.ln_std_widget)

        # ---- 子面板: 自定义双指数 (T1/T2) ----
        self.ln_twoexpf_custom_widget = QWidget()
        t2c_fl = QFormLayout(self.ln_twoexpf_custom_widget)
        t2c_fl.setContentsMargins(0, 0, 0, 0)
        self.ln_t1 = ScientificSpinBox()
        self.ln_t1.setRange(1e-12, 1)
        self.ln_t1.setValue(8e-6)
        self.ln_t1.setSuffix(" s")
        self.ln_t1.valueChanged.connect(self._emit_data_changed)
        self.ln_t2 = ScientificSpinBox()
        self.ln_t2.setRange(1e-12, 1)
        self.ln_t2.setValue(20e-6)
        self.ln_t2.setSuffix(" s")
        self.ln_t2.valueChanged.connect(self._emit_data_changed)
        self.ln_twoexpf_perc = QComboBox()
        self.ln_twoexpf_perc.addItems(["30", "0", "10", "50"])
        self.ln_twoexpf_perc.currentIndexChanged.connect(self._emit_data_changed)
        t2c_fl.addRow("T1 (波头):", self.ln_t1)
        t2c_fl.addRow("T2 (波尾):", self.ln_t2)
        t2c_fl.addRow("PERC:", self.ln_twoexpf_perc)
        ln_fl.addRow(self.ln_twoexpf_custom_widget)

        # ---- 子面板: 双指数直接 τ1/τ2 ----
        self.ln_twoexpf_tau_widget = QWidget()
        t2t_fl = QFormLayout(self.ln_twoexpf_tau_widget)
        t2t_fl.setContentsMargins(0, 0, 0, 0)
        self.ln_tau1 = ScientificSpinBox()
        self.ln_tau1.setRange(1e-15, 1)
        self.ln_tau1.setValue(20.37e-6)
        self.ln_tau1.setSuffix(" s")
        self.ln_tau1.valueChanged.connect(self._emit_data_changed)
        self.ln_tau2 = ScientificSpinBox()
        self.ln_tau2.setRange(1e-15, 1)
        self.ln_tau2.setValue(3.91e-6)
        self.ln_tau2.setSuffix(" s")
        self.ln_tau2.valueChanged.connect(self._emit_data_changed)
        # T1/T2 仍需要（用于记录和校验）
        self.ln_tau_t1 = ScientificSpinBox()
        self.ln_tau_t1.setRange(1e-12, 1)
        self.ln_tau_t1.setValue(8e-6)
        self.ln_tau_t1.setSuffix(" s")
        self.ln_tau_t1.valueChanged.connect(self._emit_data_changed)
        self.ln_tau_t2_val = ScientificSpinBox()
        self.ln_tau_t2_val.setRange(1e-12, 1)
        self.ln_tau_t2_val.setValue(20e-6)
        self.ln_tau_t2_val.setSuffix(" s")
        self.ln_tau_t2_val.valueChanged.connect(self._emit_data_changed)
        t2t_fl.addRow("τ1:", self.ln_tau1)
        t2t_fl.addRow("τ2:", self.ln_tau2)
        t2t_fl.addRow("T1 (记录用):", self.ln_tau_t1)
        t2t_fl.addRow("T2 (记录用):", self.ln_tau_t2_val)
        ln_fl.addRow(self.ln_twoexpf_tau_widget)

        # ---- 子面板: 双指数 ATP A/B ----
        self.ln_twoexpf_ab_widget = QWidget()
        t2a_fl = QFormLayout(self.ln_twoexpf_ab_widget)
        t2a_fl.setContentsMargins(0, 0, 0, 0)
        self.ln_a = ScientificSpinBox()
        self.ln_a.setRange(-1e12, 0)
        self.ln_a.setValue(-1.0 / 20.37e-6)
        self.ln_a.valueChanged.connect(self._emit_data_changed)
        self.ln_b = ScientificSpinBox()
        self.ln_b.setRange(-1e12, 0)
        self.ln_b.setValue(-1.0 / 3.91e-6)
        self.ln_b.valueChanged.connect(self._emit_data_changed)
        self.ln_ab_t1 = ScientificSpinBox()
        self.ln_ab_t1.setRange(1e-12, 1)
        self.ln_ab_t1.setValue(8e-6)
        self.ln_ab_t1.setSuffix(" s")
        self.ln_ab_t1.valueChanged.connect(self._emit_data_changed)
        self.ln_ab_t2_val = ScientificSpinBox()
        self.ln_ab_t2_val.setRange(1e-12, 1)
        self.ln_ab_t2_val.setValue(20e-6)
        self.ln_ab_t2_val.setSuffix(" s")
        self.ln_ab_t2_val.valueChanged.connect(self._emit_data_changed)
        t2a_fl.addRow("A:", self.ln_a)
        t2a_fl.addRow("B:", self.ln_b)
        t2a_fl.addRow("T1 (记录用):", self.ln_ab_t1)
        t2a_fl.addRow("T2 (记录用):", self.ln_ab_t2_val)
        ln_fl.addRow(self.ln_twoexpf_ab_widget)

        # ---- 子面板: Heidler (T1/T2/n) ----
        self.ln_heidler_custom_widget = QWidget()
        hc_fl = QFormLayout(self.ln_heidler_custom_widget)
        hc_fl.setContentsMargins(0, 0, 0, 0)
        self.ln_h_t1 = ScientificSpinBox()
        self.ln_h_t1.setRange(1e-12, 1)
        self.ln_h_t1.setValue(10e-6)
        self.ln_h_t1.setSuffix(" s")
        self.ln_h_t1.valueChanged.connect(self._emit_data_changed)
        self.ln_h_t2 = ScientificSpinBox()
        self.ln_h_t2.setRange(1e-12, 1)
        self.ln_h_t2.setValue(350e-6)
        self.ln_h_t2.setSuffix(" s")
        self.ln_h_t2.valueChanged.connect(self._emit_data_changed)
        self.ln_h_n = QSpinBox()
        self.ln_h_n.setRange(1, 100)
        self.ln_h_n.setValue(10)
        self.ln_h_n.valueChanged.connect(self._emit_data_changed)
        self.ln_h_perc = QComboBox()
        self.ln_h_perc.addItems(["30", "0", "10", "50"])
        self.ln_h_perc.currentIndexChanged.connect(self._emit_data_changed)
        hc_fl.addRow("T1 (波头):", self.ln_h_t1)
        hc_fl.addRow("T2 (波尾):", self.ln_h_t2)
        hc_fl.addRow("n (陡度):", self.ln_h_n)
        hc_fl.addRow("PERC:", self.ln_h_perc)
        ln_fl.addRow(self.ln_heidler_custom_widget)

        # ---- 子面板: Heidler 直接参数 (Tf/τ) ----
        self.ln_heidler_direct_widget = QWidget()
        hd_fl = QFormLayout(self.ln_heidler_direct_widget)
        hd_fl.setContentsMargins(0, 0, 0, 0)
        self.ln_hd_t1 = ScientificSpinBox()
        self.ln_hd_t1.setRange(1e-12, 1)
        self.ln_hd_t1.setValue(10e-6)
        self.ln_hd_t1.setSuffix(" s")
        self.ln_hd_t1.valueChanged.connect(self._emit_data_changed)
        self.ln_hd_t2 = ScientificSpinBox()
        self.ln_hd_t2.setRange(1e-12, 1)
        self.ln_hd_t2.setValue(350e-6)
        self.ln_hd_t2.setSuffix(" s")
        self.ln_hd_t2.valueChanged.connect(self._emit_data_changed)
        self.ln_hd_n = QSpinBox()
        self.ln_hd_n.setRange(1, 100)
        self.ln_hd_n.setValue(10)
        self.ln_hd_n.valueChanged.connect(self._emit_data_changed)
        self.ln_hd_tf = ScientificSpinBox()
        self.ln_hd_tf.setRange(1e-15, 1)
        self.ln_hd_tf.setValue(2.5e-6)
        self.ln_hd_tf.setSuffix(" s")
        self.ln_hd_tf.valueChanged.connect(self._emit_data_changed)
        self.ln_hd_tau = ScientificSpinBox()
        self.ln_hd_tau.setRange(1e-15, 1)
        self.ln_hd_tau.setValue(350e-6)
        self.ln_hd_tau.setSuffix(" s")
        self.ln_hd_tau.valueChanged.connect(self._emit_data_changed)
        hd_fl.addRow("T1 (波头):", self.ln_hd_t1)
        hd_fl.addRow("T2 (波尾):", self.ln_hd_t2)
        hd_fl.addRow("n (陡度):", self.ln_hd_n)
        hd_fl.addRow("Tf:", self.ln_hd_tf)
        hd_fl.addRow("τ:", self.ln_hd_tau)
        ln_fl.addRow(self.ln_heidler_direct_widget)

        # 初始只显示标准波形
        self._on_ln_model_changed(0)
        layout.addRow(self.ln_widget)

        # --- Custom ---
        self.custom_widget = QWidget()
        cu_fl = QVBoxLayout(self.custom_widget)
        cu_fl.setContentsMargins(0, 0, 0, 0)
        cu_fl.addWidget(QLabel("lambda 表达式 (变量 t):"))
        self.custom_edit = QLineEdit("lambda t: 0.0")
        self.custom_edit.setFont(QFont("Consolas", 10))
        self.custom_edit.textChanged.connect(self._emit_data_changed)
        cu_fl.addWidget(self.custom_edit)
        layout.addRow(self.custom_widget)

        # 初始显示
        self._on_mode_changed(0)

    def _on_mode_changed(self, idx: int):
        self.dc_widget.setVisible(idx == 0)
        self.ac_widget.setVisible(idx == 1)
        self.ln_widget.setVisible(idx == 2)
        self.custom_widget.setVisible(idx == 3)
        self._emit_data_changed()

    def _on_ln_model_changed(self, idx: int):
        """雷电模型子面板切换"""
        self.ln_std_widget.setVisible(idx == 0)
        self.ln_twoexpf_custom_widget.setVisible(idx == 1)
        self.ln_twoexpf_tau_widget.setVisible(idx == 2)
        self.ln_twoexpf_ab_widget.setVisible(idx == 3)
        self.ln_heidler_custom_widget.setVisible(idx == 4)
        self.ln_heidler_direct_widget.setVisible(idx == 5)
        self._emit_data_changed()

    def _emit_data_changed(self):
        """发射 dataChanged 信号"""
        self.dataChanged.emit()

    # 标准波形名 → ComboBox index
    _STD_WAVEFORM_MAP = {
        '1.2/50': 0, '2/20': 1, '8/20': 2, '4/10': 3,
        '10/350': 4, '0.25/100': 5, '10/700': 6,
        '30/80': 7, '250/2500': 8, '1/200': 9,
    }
    _STD_WAVEFORM_LIST = [
        '1.2/50', '2/20', '8/20', '4/10',
        '10/350', '0.25/100', '10/700',
        '30/80', '250/2500', '1/200',
    ]
    _PERC_MAP = {'30': 0, '0': 1, '10': 2, '50': 3}
    _PERC_LIST = ['30', '0', '10', '50']

    # 雷电子模型 → ln_model index
    _LN_MODEL_MAP = {
        'twoexpf_standard': 0, 'twoexpf_custom': 1,
        'twoexpf_tau': 2, 'twoexpf_ab': 3,
        'heidler_custom': 4, 'heidler_direct': 5,
    }
    _LN_MODEL_LIST = [
        'twoexpf_standard', 'twoexpf_custom',
        'twoexpf_tau', 'twoexpf_ab',
        'heidler_custom', 'heidler_direct',
    ]

    def set_func_data(self, data: dict):
        """设置函数数据并同步 UI"""
        self._func_data = data.copy() if data else {}
        mode = self._func_data.get('mode', 'dc')
        mode_map = {'dc': 0, 'ac': 1, 'lightning': 2, 'custom': 3}
        idx = mode_map.get(mode, 0)
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentIndex(idx)
        self.mode_combo.blockSignals(False)

        if mode == 'dc':
            self.dc_value.setValue(self._func_data.get('value', 100.0))
        elif mode == 'ac':
            self.ac_amplitude.setValue(self._func_data.get('amplitude', 100.0))
            self.ac_frequency.setValue(self._func_data.get('frequency', 50.0))
            self.ac_phase.setValue(self._func_data.get('phase', 0.0))
        elif mode == 'lightning':
            # 通用参数
            self.ln_peak.setValue(self._func_data.get('peak', 10000.0))
            self.ln_tstart.setValue(self._func_data.get('t_start', 0.0))
            # 子模型
            ln_model = self._func_data.get('lightning_model', 'twoexpf_standard')
            # 向后兼容：旧数据没有 lightning_model 字段
            if 'lightning_model' not in self._func_data and 'waveform_type' in self._func_data:
                ln_model = 'twoexpf_standard'
            ln_idx = self._LN_MODEL_MAP.get(ln_model, 0)
            self.ln_model.blockSignals(True)
            self.ln_model.setCurrentIndex(ln_idx)
            self.ln_model.blockSignals(False)

            if ln_model == 'twoexpf_standard':
                wt = self._func_data.get('waveform_type', '8/20')
                self.ln_waveform.setCurrentIndex(self._STD_WAVEFORM_MAP.get(wt, 2))
                perc_val = str(int(self._func_data.get('PERC', 30)))
                self.ln_perc.setCurrentIndex(self._PERC_MAP.get(perc_val, 0))
            elif ln_model == 'twoexpf_custom':
                self.ln_t1.setValue(self._func_data.get('T1', 8e-6))
                self.ln_t2.setValue(self._func_data.get('T2', 20e-6))
                perc_val = str(int(self._func_data.get('PERC', 30)))
                self.ln_twoexpf_perc.setCurrentIndex(self._PERC_MAP.get(perc_val, 0))
            elif ln_model == 'twoexpf_tau':
                self.ln_tau1.setValue(self._func_data.get('tau1', 20.37e-6))
                self.ln_tau2.setValue(self._func_data.get('tau2', 3.91e-6))
                self.ln_tau_t1.setValue(self._func_data.get('T1', 8e-6))
                self.ln_tau_t2_val.setValue(self._func_data.get('T2', 20e-6))
            elif ln_model == 'twoexpf_ab':
                self.ln_a.setValue(self._func_data.get('A', -1.0 / 20.37e-6))
                self.ln_b.setValue(self._func_data.get('B', -1.0 / 3.91e-6))
                self.ln_ab_t1.setValue(self._func_data.get('T1', 8e-6))
                self.ln_ab_t2_val.setValue(self._func_data.get('T2', 20e-6))
            elif ln_model == 'heidler_custom':
                self.ln_h_t1.setValue(self._func_data.get('T1', 10e-6))
                self.ln_h_t2.setValue(self._func_data.get('T2', 350e-6))
                self.ln_h_n.setValue(int(self._func_data.get('n', 10)))
                perc_val = str(int(self._func_data.get('PERC', 30)))
                self.ln_h_perc.setCurrentIndex(self._PERC_MAP.get(perc_val, 0))
            elif ln_model == 'heidler_direct':
                self.ln_hd_t1.setValue(self._func_data.get('T1', 10e-6))
                self.ln_hd_t2.setValue(self._func_data.get('T2', 350e-6))
                self.ln_hd_n.setValue(int(self._func_data.get('n', 10)))
                self.ln_hd_tf.setValue(self._func_data.get('Tf', 2.5e-6))
                self.ln_hd_tau.setValue(self._func_data.get('tau', 350e-6))

            self._on_ln_model_changed(ln_idx)
        elif mode == 'custom':
            self.custom_edit.setText(self._func_data.get('expression', 'lambda t: 0.0'))

        self._on_mode_changed(idx)

    def get_func_data(self) -> dict:
        """从 UI 读取当前函数数据"""
        idx = self.mode_combo.currentIndex()
        if idx == 0:
            return {'mode': 'dc', 'value': self.dc_value.value()}
        elif idx == 1:
            return {
                'mode': 'ac',
                'amplitude': self.ac_amplitude.value(),
                'frequency': self.ac_frequency.value(),
                'phase': self.ac_phase.value(),
            }
        elif idx == 2:
            ln_model_idx = self.ln_model.currentIndex()
            ln_model = self._LN_MODEL_LIST[ln_model_idx]
            base = {
                'mode': 'lightning',
                'lightning_model': ln_model,
                'peak': self.ln_peak.value(),
                't_start': self.ln_tstart.value(),
            }
            if ln_model == 'twoexpf_standard':
                base['waveform_type'] = self._STD_WAVEFORM_LIST[self.ln_waveform.currentIndex()]
                base['PERC'] = int(self._PERC_LIST[self.ln_perc.currentIndex()])
            elif ln_model == 'twoexpf_custom':
                base['T1'] = self.ln_t1.value()
                base['T2'] = self.ln_t2.value()
                base['PERC'] = int(self._PERC_LIST[self.ln_twoexpf_perc.currentIndex()])
            elif ln_model == 'twoexpf_tau':
                base['tau1'] = self.ln_tau1.value()
                base['tau2'] = self.ln_tau2.value()
                base['T1'] = self.ln_tau_t1.value()
                base['T2'] = self.ln_tau_t2_val.value()
            elif ln_model == 'twoexpf_ab':
                base['A'] = self.ln_a.value()
                base['B'] = self.ln_b.value()
                base['T1'] = self.ln_ab_t1.value()
                base['T2'] = self.ln_ab_t2_val.value()
            elif ln_model == 'heidler_custom':
                base['T1'] = self.ln_h_t1.value()
                base['T2'] = self.ln_h_t2.value()
                base['n'] = self.ln_h_n.value()
                base['PERC'] = int(self._PERC_LIST[self.ln_h_perc.currentIndex()])
            elif ln_model == 'heidler_direct':
                base['T1'] = self.ln_hd_t1.value()
                base['T2'] = self.ln_hd_t2.value()
                base['n'] = self.ln_hd_n.value()
                base['Tf'] = self.ln_hd_tf.value()
                base['tau'] = self.ln_hd_tau.value()
            return base
        elif idx == 3:
            return {
                'mode': 'custom',
                'expression': self.custom_edit.text().strip(),
            }
        return {'mode': 'dc', 'value': 0.0}


# ---------------------------------------------------------------------------
#  ComponentPalette — 左侧元件面板
# ---------------------------------------------------------------------------

class ComponentPalette(QWidget):
    """元件选择面板"""

    comp_type_selected = Signal(object)  # 通知主窗口切换按钮状态

    def __init__(self, model: CircuitModel, canvas: CircuitCanvas):
        super().__init__()
        self.model = model
        self.canvas = canvas
        self._setup_ui()

    def _setup_ui(self):
        # 内容容器
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # 基础元件
        layout.addWidget(self._section_label("基础元件"))
        self._add_comp_button(layout, "电阻 (R)", ComponentType.RESISTOR, "#ef4444")
        self._add_comp_button(layout, "电感 (L)", ComponentType.INDUCTOR, "#3b82f6")
        self._add_comp_button(layout, "电容 (C)", ComponentType.CAPACITOR, "#22c55e")
        self._add_comp_button(layout, "串联RL (SRL)", ComponentType.SERIES_RL, "#8b5cf6")
        self._add_comp_button(layout, "开关 (SW)", ComponentType.SWITCH, "#f59e0b")

        # 电源
        layout.addWidget(self._section_label("电源"))
        self._add_comp_button(layout, "电压源 (VS)", ComponentType.VOLTAGE_SOURCE, "#dc2626")
        self._add_comp_button(layout, "电流源 (IS)", ComponentType.CURRENT_SOURCE, "#2563eb")

        # 非线性
        layout.addWidget(self._section_label("非线性元件"))
        self._add_comp_button(layout, "MOA避雷器", ComponentType.MOA, "#7c3aed")
        self._add_comp_button(layout, "LPM绝缘子", ComponentType.LPM, "#f97316")

        # 传输线
        layout.addWidget(self._section_label("传输线"))
        self._add_comp_button(layout, "Bergeron", ComponentType.BERGERON, "#0891b2")
        self._add_comp_button(layout, "ULM", ComponentType.ULM, "#0891b2")
        self._add_comp_button(layout, "LCP架空线", ComponentType.LCP_OHL, "#0d9488")
        self._add_comp_button(layout, "LCP单芯电缆", ComponentType.LCP_SINGLE_CABLE, "#0d9488")
        self._add_comp_button(layout, "LCP三芯电缆", ComponentType.LCP_THREE_CABLE, "#0d9488")

        # 变压器
        layout.addWidget(self._section_label("变压器"))
        self._add_comp_button(layout, "UMEC变压器", ComponentType.UMEC_TRANSFORMER, "#6366f1")

        # 接地
        layout.addWidget(self._section_label("接地"))
        self._add_comp_button(layout, "接地 (GND)", ComponentType.GROUND, "#1e2a3a")

        # 测量
        layout.addWidget(self._section_label("测量"))
        self._add_comp_button(
            layout,
            "对地电压探针",
            ComponentType.PROBE,
            "#eab308",
            {"probe_type": "voltage_ground", "unit": "kV"},
        )
        self._add_comp_button(
            layout,
            "两节点电压探针",
            ComponentType.PROBE,
            "#f59e0b",
            {"probe_type": "voltage_between", "unit": "kV"},
        )
        self._add_comp_button(
            layout,
            "电流探针",
            ComponentType.PROBE,
            "#06b6d4",
            {"probe_type": "branch_current", "unit": "A"},
        )

        layout.addStretch()

        # 包进 ScrollArea
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #64748b; font-size: 11px; margin-top: 8px; margin-bottom: 2px;")
        return lbl

    def _add_comp_button(
        self,
        layout,
        text: str,
        comp_type: ComponentType,
        color: str,
        default_params=None,
    ):
        btn = QPushButton(text)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color}15;
                color: {color};
                border: 1px solid {color}40;
                border-radius: 4px;
                padding: 6px 8px;
                text-align: left;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {color}30;
                border-color: {color};
            }}
        """)
        btn.clicked.connect(
            lambda _, ct=comp_type, params=default_params: self._on_select_comp_type(ct, params)
        )
        layout.addWidget(btn)

    def _on_select_comp_type(self, comp_type: ComponentType, default_params=None):
        self.canvas.set_placing_type(comp_type, default_params)
        self.canvas._placing_type = comp_type
        self.comp_type_selected.emit(comp_type)


# ---------------------------------------------------------------------------
#  PropertyPanel — 右侧属性编辑面板（含 SourceFuncEditor）
# ---------------------------------------------------------------------------

class PropertyPanel(QWidget):
    """属性编辑面板"""

    def __init__(self, model: CircuitModel, canvas: CircuitCanvas):
        super().__init__()
        self.model = model
        self.canvas = canvas
        self._current_comp_id = None
        self._source_editor: SourceFuncEditor = None
        self._param_spin_widgets = []  # (param_name, widget) 列表
        self._setup_ui()

        canvas.canvas_changed.connect(self._on_selection_changed)

    def _setup_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(8, 8, 8, 8)

        self.info_label = QLabel("选择元件查看属性")
        self.info_label.setStyleSheet("color: #64748b; font-style: italic;")
        self.layout.addWidget(self.info_label)

        # SourceFuncEditor 占位（动态显示/隐藏）
        self._source_editor = SourceFuncEditor()
        self._source_editor.setVisible(False)
        self._source_connected = False  # 跟踪 dataChanged 是否已连接
        self.layout.addWidget(self._source_editor)

        # 参数表单容器
        self._params_container = QWidget()
        self._params_layout = QVBoxLayout(self._params_container)
        self._params_layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self._params_container)

        self.layout.addStretch()

    def _on_selection_changed(self):
        selected = [
            item for item in self.canvas.scene.selectedItems()
            if isinstance(item, ComponentGraphicsItem)
        ]
        if selected:
            comp = selected[0].component
            # 如果当前正在编辑同一元件，跳过重建，避免输入焦点丢失
            if self._current_comp_id == comp.comp_id:
                return
            self._show_component(comp)
        else:
            self._clear()

    def _show_component(self, comp: ComponentInstance):
        self._clear()
        self._current_comp_id = comp.comp_id

        registry = COMPONENT_REGISTRY.get(comp.comp_type, {})

        # 标题
        display = registry.get('display_name', comp.comp_type.value)
        self.info_label.setText(f"{display}: {comp.name}")
        self.info_label.setStyleSheet("font-weight: bold; color: #1e2a3a;")

        # 名称
        name_form = QFormLayout()
        name_edit = QLineEdit(comp.name)
        name_edit.textChanged.connect(lambda t: self._on_param_changed('name', t))
        name_form.addRow("名称:", name_edit)
        self._params_layout.addLayout(name_form)

        # 如果是电源，显示 SourceFuncEditor
        if comp.comp_type == ComponentType.VOLTAGE_SOURCE:
            param_key = 'voltage_func'
            func_data = comp.params.get(param_key, {})
            self._source_editor.setTitle("电压函数")
            self._source_editor.set_func_data(func_data)
            self._source_editor._func_param_key = param_key
            self._source_editor.setVisible(True)
            self._source_editor.dataChanged.connect(
                lambda: self._on_source_changed(param_key)
            )
            self._source_connected = True
        elif comp.comp_type == ComponentType.CURRENT_SOURCE:
            param_key = 'current_func'
            func_data = comp.params.get(param_key, {})
            self._source_editor.setTitle("电流函数")
            self._source_editor.set_func_data(func_data)
            self._source_editor._func_param_key = param_key
            self._source_editor.setVisible(True)
            self._source_editor.dataChanged.connect(
                lambda: self._on_source_changed(param_key)
            )
            self._source_connected = True

        # 普通参数
        params_template = registry.get('params_template', {})
        for param_name, param_spec in params_template.items():
            if param_spec.get('type') == 'source_func':
                continue  # 已由 SourceFuncEditor 处理
            self._add_param_widget(param_name, param_spec, comp)

        # LCP 元件添加配置按钮和截面预览按钮
        if comp.comp_type in (ComponentType.LCP_OHL, ComponentType.LCP_SINGLE_CABLE,
                              ComponentType.LCP_THREE_CABLE):
            # LCP 参数配置按钮
            config_btn = QPushButton("⚙ LCP 参数配置")
            config_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2563eb15; color: #2563eb; border: 1px solid #2563eb40;
                    border-radius: 4px; padding: 6px 12px; font-weight: bold;
                }
                QPushButton:hover { background-color: #2563eb30; border-color: #2563eb; }
            """)
            config_btn.clicked.connect(lambda: self._open_lcp_config(comp))
            self._params_layout.addWidget(config_btn)

            preview_btn = QPushButton("🔍 预览截面")
            preview_btn.setStyleSheet("""
                QPushButton {
                    background-color: #0d948815; color: #0d9488; border: 1px solid #0d948840;
                    border-radius: 4px; padding: 6px 12px; font-weight: bold;
                }
                QPushButton:hover { background-color: #0d948830; border-color: #0d9488; }
            """)
            preview_btn.clicked.connect(lambda: self._show_lcp_preview(comp))
            self._params_layout.addWidget(preview_btn)

        # UMEC 变压器添加配置按钮
        if comp.comp_type == ComponentType.UMEC_TRANSFORMER:
            config_btn = QPushButton("⚙ UMEC 参数配置")
            config_btn.setStyleSheet("""
                QPushButton {
                    background-color: #6366f115; color: #6366f1; border: 1px solid #6366f140;
                    border-radius: 4px; padding: 6px 12px; font-weight: bold;
                }
                QPushButton:hover { background-color: #6366f130; border-color: #6366f1; }
            """)
            config_btn.clicked.connect(lambda: self._open_umec_config(comp))
            self._params_layout.addWidget(config_btn)

        self.layout.addStretch()

    def _add_param_widget(self, param_name: str, param_spec: dict, comp: ComponentInstance):
        label_text = param_spec.get('label', param_name)
        current_val = comp.params.get(param_name, param_spec.get('default'))

        if param_spec.get('type') == 'float' or param_spec.get('scientific'):
            spin = ScientificSpinBox()
            spin.setRange(param_spec.get('min', -1e30), param_spec.get('max', 1e30))
            if current_val is not None:
                spin.setValue(float(current_val))
            spin.valueChanged.connect(
                lambda v, p=param_name: self._on_param_changed(p, v)
            )
            form = QFormLayout()
            form.addRow(f"{label_text}:", spin)
            self._params_layout.addLayout(form)
            self._param_spin_widgets.append((param_name, spin))
        elif param_spec.get('type') == 'int':
            spin = QSpinBox()
            spin.setRange(param_spec.get('min', 0), param_spec.get('max', 999999))
            if current_val is not None:
                spin.setValue(int(current_val))
            spin.valueChanged.connect(
                lambda v, p=param_name: self._on_param_changed(p, v)
            )
            form = QFormLayout()
            form.addRow(f"{label_text}:", spin)
            self._params_layout.addLayout(form)
            self._param_spin_widgets.append((param_name, spin))
        elif param_spec.get('type') == 'bool':
            check = QCheckBox()
            check.setChecked(bool(current_val) if current_val is not None else param_spec.get('default', False))
            check.toggled.connect(
                lambda v, p=param_name: self._on_param_changed(p, v)
            )
            form = QFormLayout()
            form.addRow(f"{label_text}:", check)
            self._params_layout.addLayout(form)
            self._param_spin_widgets.append((param_name, check))
        elif param_spec.get('type') == 'file':
            edit = QLineEdit(str(current_val) if current_val else '')
            browse_btn = QPushButton("浏览...")
            browse_btn.setFixedWidth(60)
            row = QHBoxLayout()
            row.addWidget(edit)
            row.addWidget(browse_btn)
            form = QFormLayout()
            form.addRow(f"{label_text}:", row)
            self._params_layout.addLayout(form)
            edit.textChanged.connect(
                lambda t, p=param_name: self._on_param_changed(p, t)
            )
            browse_btn.clicked.connect(
                lambda _, e=edit: self._browse_file(e)
            )
            self._param_spin_widgets.append((param_name, edit))
        elif param_spec.get('type') == 'breakpoints_table':
            # 简化处理：显示为文本提示
            from PySide6.QtWidgets import QTableWidget, QTableWidgetItem
            table = QTableWidget(5, 2)
            table.setHorizontalHeaderLabels(["V", "I"])
            table.setMaximumHeight(150)
            breakpoints = current_val if current_val else []
            for i, (v, i_val) in enumerate(breakpoints[:5]):
                table.setItem(i, 0, QTableWidgetItem(str(v)))
                table.setItem(i, 1, QTableWidgetItem(str(i_val)))
            form = QFormLayout()
            form.addRow(f"{label_text}:", table)
            self._params_layout.addLayout(form)
            self._param_spin_widgets.append((param_name, table))
        elif param_spec.get('type') == 'choice':
            combo = QComboBox()
            choices = param_spec.get('choices', [])
            combo.addItems(choices)
            if current_val and current_val in choices:
                combo.setCurrentText(str(current_val))
            combo.currentTextChanged.connect(
                lambda t, p=param_name: self._on_param_changed(p, t)
            )
            form = QFormLayout()
            form.addRow(f"{label_text}:", combo)
            self._params_layout.addLayout(form)
            self._param_spin_widgets.append((param_name, combo))

        # LCP 元件添加截面预览按钮
        if comp.comp_type in (ComponentType.LCP_OHL, ComponentType.LCP_SINGLE_CABLE,
                              ComponentType.LCP_THREE_CABLE):
            if param_name == list(param_spec.keys())[-1] if hasattr(param_spec, 'keys') else False:
                pass  # 会在 _show_component 末尾统一添加

    def _browse_file(self, line_edit: QLineEdit):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择文件", "", "All Files (*)"
        )
        if path:
            line_edit.setText(path)

    def _on_param_changed(self, param_name: str, value):
        if self._current_comp_id and self._current_comp_id in self.model.components:
            if param_name == 'name':
                self.model._save_undo_state()
                self.model.components[self._current_comp_id].name = value
                self.model._notify("params_updated")
            elif param_name in ('probe_type', 'wtype1', 'wtype2'):
                comp = self.model.components[self._current_comp_id]
                self.model._save_undo_state()
                comp.params[param_name] = value
                self._rebuild_component_pins(comp)
                self.model._notify("params_updated")
            elif param_name == 'n_phases':
                # ULM / LCP_OHL 改相数时必须重建引脚列表
                comp = self.model.components[self._current_comp_id]
                self.model._save_undo_state()
                comp.params['n_phases'] = value
                comp.pins = create_component_pins(comp.comp_type, value)
                valid_pins = {pin.name for pin in comp.pins}
                wires_to_remove = [
                    wire_id for wire_id, wire in self.model.wires.items()
                    if (
                        wire.from_comp == comp.comp_id and wire.from_pin not in valid_pins
                    ) or (
                        wire.to_comp == comp.comp_id and wire.to_pin not in valid_pins
                    )
                ]
                for wire_id in wires_to_remove:
                    del self.model.wires[wire_id]
                self.model._notify("params_updated")
            elif param_name == 'n_cables':
                # LCP_SINGLE_CABLE 改电缆数时重建引脚
                comp = self.model.components[self._current_comp_id]
                self.model._save_undo_state()
                comp.params['n_cables'] = value
                comp.pins = create_component_pins(comp.comp_type, value)
                valid_pins = {pin.name for pin in comp.pins}
                wires_to_remove = [
                    wire_id for wire_id, wire in self.model.wires.items()
                    if (
                        wire.from_comp == comp.comp_id and wire.from_pin not in valid_pins
                    ) or (
                        wire.to_comp == comp.comp_id and wire.to_pin not in valid_pins
                    )
                ]
                for wire_id in wires_to_remove:
                    del self.model.wires[wire_id]
                self.model._notify("params_updated")
            else:
                self.model.update_params(self._current_comp_id, {param_name: value})

    def _remove_wires_with_invalid_pins(self, comp: ComponentInstance) -> int:
        valid_pins = {pin.name for pin in comp.pins}
        wires_to_remove = [
            wire_id for wire_id, wire in self.model.wires.items()
            if (
                wire.from_comp == comp.comp_id and wire.from_pin not in valid_pins
            ) or (
                wire.to_comp == comp.comp_id and wire.to_pin not in valid_pins
            )
        ]
        for wire_id in wires_to_remove:
            del self.model.wires[wire_id]
        return len(wires_to_remove)

    def _rebuild_component_pins(self, comp: ComponentInstance) -> int:
        probe_type = comp.params.get('probe_type') if comp.comp_type == ComponentType.PROBE else None
        pin_count = comp.params.get('n_phases', 3)
        if comp.comp_type == ComponentType.LCP_SINGLE_CABLE:
            pin_count = comp.params.get('n_cables', 1)
        elif comp.comp_type == ComponentType.LCP_OHL:
            from core.lcp_config import get_lcp_ohl_conductor_count
            pin_count = get_lcp_ohl_conductor_count(comp.params)
        comp.pins = create_component_pins(
            comp.comp_type,
            int(pin_count or 1),
            probe_type=probe_type,
            params=comp.params,
        )
        return self._remove_wires_with_invalid_pins(comp)

    def _on_source_changed(self, param_key: str):
        if self._current_comp_id:
            data = self._source_editor.get_func_data()
            self.model.update_params(self._current_comp_id, {param_key: data})

    def _clear(self):
        # 断开 SourceFuncEditor 信号，防止重复连接
        if self._source_connected:
            try:
                self._source_editor.dataChanged.disconnect()
                self._source_connected = False
            except RuntimeError:
                pass

        # 清除参数控件
        while self._params_layout.count():
            child = self._params_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                self._clear_layout(child.layout())

        # 清除底部 stretch
        while self.layout.count() > 3:
            child = self.layout.takeAt(self.layout.count() - 1)
            if child.widget():
                child.widget().deleteLater()

        self._current_comp_id = None
        self._param_spin_widgets.clear()
        self._source_editor.setVisible(False)
        self.info_label.setText("选择元件查看属性")
        self.info_label.setStyleSheet("color: #64748b; font-style: italic;")

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                PropertyPanel._clear_layout(child.layout())  # BUG-2 修复: 加 ()

    def _open_lcp_config(self, comp: ComponentInstance):
        """打开 LCP 参数配置对话框"""
        from ui.lcp_param_dialog import LCPOHLDialog, LCPSingleCableDialog, LCPThreeCoreCableDialog

        if comp.comp_type == ComponentType.LCP_OHL:
            dialog = LCPOHLDialog(comp.params, self)
        elif comp.comp_type == ComponentType.LCP_SINGLE_CABLE:
            dialog = LCPSingleCableDialog(comp.params, self)
        elif comp.comp_type == ComponentType.LCP_THREE_CABLE:
            dialog = LCPThreeCoreCableDialog(comp.params, self)
        else:
            return

        if dialog.exec() == QDialog.DialogCode.Accepted:
            config = dialog.get_config()
            # 将 config 合并到元件参数中
            self.model._save_undo_state()
            comp.params.update(config)
            # 更新引脚（相数/电缆数可能变化）
            if comp.comp_type == ComponentType.LCP_OHL:
                n_phases = config.get('n_phases', 2) + config.get('n_gw', 2)
                comp.params['n_phases'] = n_phases
                comp.pins = create_component_pins(comp.comp_type, n_phases)
            elif comp.comp_type == ComponentType.LCP_SINGLE_CABLE:
                n_cables = config.get('n_cables', 1)
                comp.params['n_cables'] = n_cables
                comp.pins = create_component_pins(comp.comp_type, n_cables)
            self.model._notify("params_updated")

    def _show_lcp_preview(self, comp: ComponentInstance):
        """显示 LCP 元件截面预览（使用增强的预览窗口）"""
        from ui.lcp_preview_widgets import LCPPreviewWindow

        dialog = LCPPreviewWindow(
            comp_name=comp.name,
            comp_type=comp.comp_type,
            config=comp.params,
            parent=self,
        )
        dialog.exec()

    def _open_umec_config(self, comp: ComponentInstance):
        """打开 UMEC 变压器参数配置对话框"""
        from ui.umec_param_dialog import UMECTransformerDialog

        dialog = UMECTransformerDialog(comp.params, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            config = dialog.get_config()
            self.model._save_undo_state()
            comp.params.update(config)
            self._rebuild_component_pins(comp)
            self.model._notify("params_updated")


# ---------------------------------------------------------------------------
#  SimulationConfigPanel — 仿真配置面板
# ---------------------------------------------------------------------------

class SimulationConfigPanel(QWidget):
    """仿真配置面板"""

    def __init__(self, model: CircuitModel):
        super().__init__()
        self.model = model
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        form = QFormLayout()
        form.setSpacing(6)

        # dt
        self.dt_spin = ScientificSpinBox()
        self.dt_spin.setRange(1e-15, 1)
        self.dt_spin.setValue(self.model.settings.dt)
        self.dt_spin.valueChanged.connect(self._on_dt_changed)
        form.addRow("dt (s):", self.dt_spin)

        # finish_time
        self.finish_spin = ScientificSpinBox()
        self.finish_spin.setRange(1e-12, 1000)
        self.finish_spin.setValue(self.model.settings.finish_time)
        self.finish_spin.valueChanged.connect(self._on_finish_changed)
        form.addRow("T_end (s):", self.finish_spin)

        layout.addLayout(form)

        # Verbose
        self.verbose_check = QCheckBox("详细输出 (verbose)")
        self.verbose_check.setChecked(self.model.settings.verbose)
        self.verbose_check.toggled.connect(self._on_verbose_changed)
        layout.addWidget(self.verbose_check)

        self.auto_vprobe_check = QCheckBox("自动为所有非地节点添加电压探针")
        self.auto_vprobe_check.setToolTip(
            "勾选后，仿真将自动为所有非接地节点记录电压波形。\n"
            "不勾选时，仅记录画布上放置的探针和自定义探针。"
        )
        self.auto_vprobe_check.setChecked(self.model.settings.auto_voltage_probes)
        self.auto_vprobe_check.toggled.connect(
            lambda checked: self.model.update_settings(auto_voltage_probes=checked)
        )
        layout.addWidget(self.auto_vprobe_check)

        # 高级设置（折叠面板）
        advanced_group = QGroupBox("高级设置")
        advanced_group.setCheckable(True)
        advanced_group.setChecked(False)  # 默认收起
        adv_form = QFormLayout(advanced_group)
        adv_form.setSpacing(4)

        self.result_mode_combo = QComboBox()
        self.result_mode_combo.addItems(["probes_only", "full"])
        idx = self.result_mode_combo.findText(self.model.settings.result_mode)
        if idx >= 0:
            self.result_mode_combo.setCurrentIndex(idx)
        self.result_mode_combo.currentTextChanged.connect(
            lambda t: self.model.update_settings(result_mode=t)
        )
        adv_form.addRow("结果模式:", self.result_mode_combo)

        self.ulm_batch_combo = QComboBox()
        self.ulm_batch_combo.addItems(["auto", "parallel", "serial", "off"])
        idx = self.ulm_batch_combo.findText(self.model.settings.ulm_batch_mode)
        if idx >= 0:
            self.ulm_batch_combo.setCurrentIndex(idx)
        self.ulm_batch_combo.currentTextChanged.connect(
            lambda t: self.model.update_settings(ulm_batch_mode=t)
        )
        adv_form.addRow("ULM batch:", self.ulm_batch_combo)

        self.record_node_check = QCheckBox("记录节点电压历史")
        self.record_node_check.setChecked(self.model.settings.record_node_history)
        self.record_node_check.toggled.connect(
            lambda c: self.model.update_settings(record_node_history=c)
        )
        adv_form.addRow(self.record_node_check)

        self.record_branch_check = QCheckBox("记录支路电流历史")
        self.record_branch_check.setChecked(self.model.settings.record_branch_history)
        self.record_branch_check.toggled.connect(
            lambda c: self.model.update_settings(record_branch_history=c)
        )
        adv_form.addRow(self.record_branch_check)

        self.record_line_check = QCheckBox("记录线路历史")
        self.record_line_check.setChecked(self.model.settings.record_line_history)
        self.record_line_check.toggled.connect(
            lambda c: self.model.update_settings(record_line_history=c)
        )
        adv_form.addRow(self.record_line_check)

        self.record_source_check = QCheckBox("记录电源历史")
        self.record_source_check.setChecked(self.model.settings.record_source_history)
        self.record_source_check.toggled.connect(
            lambda c: self.model.update_settings(record_source_history=c)
        )
        adv_form.addRow(self.record_source_check)

        layout.addWidget(advanced_group)

        layout.addStretch()

    def _on_dt_changed(self, value: float):
        self.model.update_settings(dt=value)

    def _on_finish_changed(self, value: float):
        self.model.update_settings(finish_time=value)

    def _on_verbose_changed(self, checked: bool):
        self.model.update_settings(verbose=checked)

    def sync_from_model(self):
        """从 model.settings 同步 UI 控件"""
        self.dt_spin.blockSignals(True)
        self.dt_spin.setValue(self.model.settings.dt)
        self.dt_spin.blockSignals(False)

        self.finish_spin.blockSignals(True)
        self.finish_spin.setValue(self.model.settings.finish_time)
        self.finish_spin.blockSignals(False)

        self.verbose_check.blockSignals(True)
        self.verbose_check.setChecked(self.model.settings.verbose)
        self.verbose_check.blockSignals(False)

        self.auto_vprobe_check.blockSignals(True)
        self.auto_vprobe_check.setChecked(self.model.settings.auto_voltage_probes)
        self.auto_vprobe_check.blockSignals(False)

        # 高级设置同步
        self.result_mode_combo.blockSignals(True)
        idx = self.result_mode_combo.findText(self.model.settings.result_mode)
        if idx >= 0:
            self.result_mode_combo.setCurrentIndex(idx)
        self.result_mode_combo.blockSignals(False)

        self.ulm_batch_combo.blockSignals(True)
        idx = self.ulm_batch_combo.findText(self.model.settings.ulm_batch_mode)
        if idx >= 0:
            self.ulm_batch_combo.setCurrentIndex(idx)
        self.ulm_batch_combo.blockSignals(False)

        self.record_node_check.blockSignals(True)
        self.record_node_check.setChecked(self.model.settings.record_node_history)
        self.record_node_check.blockSignals(False)

        self.record_branch_check.blockSignals(True)
        self.record_branch_check.setChecked(self.model.settings.record_branch_history)
        self.record_branch_check.blockSignals(False)

        self.record_line_check.blockSignals(True)
        self.record_line_check.setChecked(self.model.settings.record_line_history)
        self.record_line_check.blockSignals(False)

        self.record_source_check.blockSignals(True)
        self.record_source_check.setChecked(self.model.settings.record_source_history)
        self.record_source_check.blockSignals(False)


# ---------------------------------------------------------------------------
#  CodePreviewPanel — 代码预览（含 Python 语法高亮）
# ---------------------------------------------------------------------------

class CodePreviewPanel(QWidget):
    """代码预览面板"""

    def __init__(self, model: CircuitModel):
        super().__init__()
        self.model = model
        self._setup_ui()
        self.update_code()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.code_edit = QPlainTextEdit()
        self.code_edit.setReadOnly(True)
        self.code_edit.setFont(QFont("Consolas", 11))
        self.code_edit.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 12px;
                border: none;
            }
            QScrollBar:vertical {
                background-color: #1e1e1e;
                width: 12px;
            }
            QScrollBar::handle:vertical {
                background-color: #424242;
                border-radius: 6px;
                min-height: 30px;
            }
        """)

        # 语法高亮
        self.highlighter = PythonHighlighter(self.code_edit.document())

        layout.addWidget(self.code_edit)

    def update_code(self):
        code = generate_code(self.model)
        self.code_edit.setPlainText(code)

    def setPlainText(self, text: str):
        self.code_edit.setPlainText(text)


# ---------------------------------------------------------------------------
#  PlotPanel — 波形显示面板（matplotlib）
# ---------------------------------------------------------------------------

class PlotPanel(QWidget):
    """波形显示面板"""

    def __init__(self, model: CircuitModel = None):
        super().__init__()
        self.model = model
        self._last_solver = None  # 保存最近一次 solver 用于导出
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as MplCanvas
        from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as MplToolbar
        from matplotlib.figure import Figure

        self.figure = Figure(figsize=(8, 4), dpi=100, facecolor='#f8fafc')
        self.mpl_canvas = MplCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)

        toolbar = MplToolbar(self.mpl_canvas, self)

        # 控制栏：时间单位切换 + 探针选择 + 导出按钮
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setSpacing(4)

        # 时间单位
        ctrl_layout.addWidget(QLabel("时间:"))
        self.time_unit_combo = QComboBox()
        self.time_unit_combo.addItems(["μs", "ms", "s", "ns"])
        self.time_unit_combo.setCurrentText("μs")
        self.time_unit_combo.setFixedWidth(60)
        self.time_unit_combo.currentTextChanged.connect(self._replot)
        ctrl_layout.addWidget(self.time_unit_combo)

        # 探针选择
        ctrl_layout.addWidget(QLabel("探针:"))
        self.probe_combo = QComboBox()
        self.probe_combo.addItems(["全部"])
        self.probe_combo.setFixedWidth(120)
        self.probe_combo.currentTextChanged.connect(self._replot)
        ctrl_layout.addWidget(self.probe_combo)

        ctrl_layout.addWidget(toolbar)

        # 导出按钮
        self.export_csv_btn = QPushButton("📄 CSV")
        self.export_csv_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9; border: 1px solid #cbd5e1;
                border-radius: 3px; padding: 4px 10px; font-size: 11px;
            }
            QPushButton:hover { background-color: #e2e8f0; }
        """)
        self.export_csv_btn.clicked.connect(self._export_csv)

        self.export_png_btn = QPushButton("🖼 PNG")
        self.export_png_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9; border: 1px solid #cbd5e1;
                border-radius: 3px; padding: 4px 10px; font-size: 11px;
            }
            QPushButton:hover { background-color: #e2e8f0; }
        """)
        self.export_png_btn.clicked.connect(self._export_png)

        ctrl_layout.addWidget(self.export_csv_btn)
        ctrl_layout.addWidget(self.export_png_btn)
        ctrl_layout.addStretch()

        layout.addLayout(ctrl_layout)
        layout.addWidget(self.mpl_canvas)

        # 内部数据缓存
        self._time_data = None       # 时间数组
        self._probe_data = {}        # {probe_name: (numpy_array, label, linestyle)}

        # 初始提示
        self.ax.text(0.5, 0.5, '仿真结果将在此显示',
                     ha='center', va='center', transform=self.ax.transAxes,
                     color='#64748b', fontsize=14)
        self.ax.set_axis_off()
        self.mpl_canvas.draw()

    def set_model(self, model: CircuitModel):
        """更新 model 引用"""
        self.model = model

    def _export_csv(self):
        """导出波形数据为 CSV"""
        if self._last_solver is None:
            QMessageBox.warning(self, "导出失败", "没有仿真数据可导出")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出 CSV", "", "CSV Files (*.csv)"
        )
        if not file_path:
            return
        if not file_path.endswith('.csv'):
            file_path += '.csv'

        try:
            solver = self._last_solver
            t = solver.get_time('us')

            # 收集所有列数据: [(列名, numpy数组), ...]
            series = [('time_us', t)]

            try:
                probes = solver.list_probes()
            except AttributeError:
                probes = None

            if probes:
                for name in probes.get('voltage', []):
                    try:
                        V = solver.get_probe(name, unit='kV')
                        series.append((name.replace(' ', '_'), V))
                    except Exception:
                        pass
                for name in probes.get('branch_current', []):
                    try:
                        I = solver.get_probe(name, unit='A')
                        series.append((name.replace(' ', '_'), I))
                    except Exception:
                        pass
            else:
                # 回退：节点电压
                unique_nodes = set()
                if self.model:
                    for comp in self.model.components.values():
                        for pin in comp.pins:
                            if pin.node_id is not None and pin.node_id > 0:
                                unique_nodes.add(pin.node_id)
                for node in sorted(unique_nodes):
                    try:
                        V = solver.get_node_voltage(node, 'kV')
                        series.append((f'Node_{node}_kV', V))
                    except Exception:
                        pass

            import csv
            n_rows = len(t)
            with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([col_name for col_name, _ in series])
                for i in range(n_rows):
                    row = []
                    for _, arr in series:
                        if i < len(arr):
                            row.append(f'{arr[i]:.6e}')
                        else:
                            row.append('')
                    writer.writerow(row)

            QMessageBox.information(self, "导出成功", f"CSV 已导出到:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出 CSV 出错:\n{str(e)}")

    def _export_png(self):
        """导出波形图为 PNG"""
        if self._last_solver is None:
            QMessageBox.warning(self, "导出失败", "没有仿真图表可导出")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出 PNG", "", "PNG Files (*.png)"
        )
        if not file_path:
            return
        if not file_path.endswith('.png'):
            file_path += '.png'

        try:
            self.figure.savefig(file_path, dpi=150, bbox_inches='tight',
                                facecolor=self.figure.get_facecolor())
            QMessageBox.information(self, "导出成功", f"PNG 已导出到:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出 PNG 出错:\n{str(e)}")

    def display_results(self, solver):
        """显示仿真结果 - 使用探针系统，缓存数据支持重绘"""
        self._last_solver = solver  # 保存用于导出
        self._probe_data = {}

        try:
            self._time_data = solver.get_time('s')  # 原始秒

            # 尝试使用探针 API
            has_data = False
            try:
                probes = solver.list_probes()
            except AttributeError:
                probes = None

            if probes:
                # 电压探针
                for name in probes.get('voltage', []):
                    try:
                        V = solver.get_probe(name, unit='kV')
                        self._probe_data[name] = (V, f'{name} (kV)', '-')
                        has_data = True
                    except Exception:
                        pass

                # 支路电流探针
                for name in probes.get('branch_current', []):
                    try:
                        I = solver.get_probe(name, unit='A')
                        self._probe_data[name] = (I, f'{name} (A)', '--')
                        has_data = True
                    except Exception:
                        pass

                # 线路电流探针
                for name in probes.get('line_current', []):
                    try:
                        I = solver.get_probe(name, unit='A')
                        self._probe_data[name] = (I, f'{name} (A)', ':')
                        has_data = True
                    except Exception:
                        pass
            else:
                # 回退：使用旧版 get_node_voltage
                unique_nodes = set()
                if self.model:
                    for comp in self.model.components.values():
                        for pin in comp.pins:
                            if pin.node_id is not None and pin.node_id > 0:
                                unique_nodes.add(pin.node_id)

                for node in sorted(unique_nodes):
                    try:
                        V = solver.get_node_voltage(node, 'kV')
                        self._probe_data[f'Node_{node}'] = (V, f'Node {node} (kV)', '-')
                        has_data = True
                    except Exception:
                        pass

            # 更新探针选择下拉框
            self.probe_combo.blockSignals(True)
            self.probe_combo.clear()
            self.probe_combo.addItems(["全部"] + list(self._probe_data.keys()))
            self.probe_combo.blockSignals(False)

            if not has_data:
                self.ax.clear()
                self.ax.text(0.5, 0.5, '未注册探针，无数据',
                             ha='center', va='center',
                             transform=self.ax.transAxes, color='#64748b', fontsize=12)
                self.ax.set_axis_off()
            else:
                self._replot()

        except Exception as e:
            self.ax.clear()
            self.ax.text(0.5, 0.5, f'显示结果出错:\n{str(e)}',
                         ha='center', va='center', transform=self.ax.transAxes,
                         color='#ef4444', fontsize=12)

        self.mpl_canvas.draw()

    def _replot(self):
        """根据当前时间单位和探针选择重绘"""
        if self._time_data is None:
            return

        self.ax.clear()

        # 时间缩放
        unit = self.time_unit_combo.currentText()
        scale_map = {"s": 1.0, "ms": 1e3, "μs": 1e6, "ns": 1e9}
        scale = scale_map.get(unit, 1e6)
        t = self._time_data * scale

        # 选择要显示的探针
        selected = self.probe_combo.currentText()
        if selected == "全部":
            probes_to_show = self._probe_data
        else:
            probes_to_show = {k: v for k, v in self._probe_data.items() if k == selected}

        for name, (data, label, ls) in probes_to_show.items():
            self.ax.plot(t, data, label=label, linestyle=ls)

        self.ax.set_xlabel(f'Time ({unit})')
        self.ax.set_ylabel('Voltage (kV) / Current (A)')
        self.ax.legend(fontsize=8, loc='best')
        self.ax.grid(True, alpha=0.3)
        self.mpl_canvas.draw()


# ---------------------------------------------------------------------------
#  ConsolePanel — 控制台输出面板
# ---------------------------------------------------------------------------

class ConsolePanel(QWidget):
    """控制台输出面板"""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("Consolas", 10))
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #1a1a2e;
                color: #e0e0e0;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 11px;
                border: none;
            }
        """)
        layout.addWidget(self.text_edit)

    def append_text(self, text: str):
        self.text_edit.append(text)

    def clear(self):
        self.text_edit.clear()


# ---------------------------------------------------------------------------
#  MainWindow — 主窗口
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    """EMTP 电路仿真 GUI 主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("EMTP Circuit Designer")
        self.resize(1400, 900)

        # 数据模型
        self.model = CircuitModel()
        self.current_file = None
        self._last_sim_results = None

        # 初始化 UI
        self._setup_ui()

        # 监听模型变化
        self.model.add_observer(self._on_model_changed)

        # 画布右键菜单接地信号
        self.canvas.add_ground_requested.connect(self._on_add_ground_at_pos)

        # 元件放置完成，自动切回选择模式
        self.canvas.placement_completed.connect(self._on_placement_completed)

        # 元件面板选择元件时，更新工具栏按钮状态
        self.component_palette.comp_type_selected.connect(self._on_comp_type_selected_from_palette)

    # ================================================================
    #  UI 搭建
    # ================================================================

    def _setup_ui(self):
        self._setup_menu_bar()
        self._setup_tool_bar()
        self._setup_central_widget()
        self._setup_dock_widgets()
        self._setup_status_bar()

    # ---- 菜单栏 ----

    def _setup_menu_bar(self):
        menubar = self.menuBar()

        # 文件
        file_menu = menubar.addMenu("文件(&F)")

        for text, shortcut, slot in [
            ("新建",           "Ctrl+N",       self._on_new),
            ("打开...",        "Ctrl+O",       self._on_open),
            ("保存",           "Ctrl+S",       self._on_save),
            ("另存为...",      "Ctrl+Shift+S", self._on_save_as),
        ]:
            act = QAction(text, self)
            act.setShortcut(shortcut)
            act.triggered.connect(slot)
            file_menu.addAction(act)

        file_menu.addSeparator()

        export_action = QAction("导出Python代码...", self)
        export_action.triggered.connect(self._on_export_code)
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        exit_action = QAction("退出", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 编辑
        edit_menu = menubar.addMenu("编辑(&E)")

        undo_action = QAction("撤销", self)
        undo_action.setShortcut("Ctrl+Z")
        undo_action.triggered.connect(lambda: self.model.undo())
        edit_menu.addAction(undo_action)

        redo_action = QAction("重做", self)
        redo_action.setShortcut("Ctrl+Y")
        redo_action.triggered.connect(lambda: self.model.redo())
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()

        delete_action = QAction("删除", self)
        delete_action.setShortcut(QKeySequence.Delete)
        delete_action.triggered.connect(self._on_delete)
        edit_menu.addAction(delete_action)

        clear_action = QAction("清空电路", self)
        clear_action.triggered.connect(self._on_clear)
        edit_menu.addAction(clear_action)

        edit_menu.addSeparator()

        wire_action = QAction("连线模式", self)
        wire_action.setShortcut("Ctrl+W")
        wire_action.triggered.connect(self._on_toggle_wire_mode)
        edit_menu.addAction(wire_action)

        ground_action = QAction("添加接地", self)
        ground_action.setShortcut("Ctrl+G")
        ground_action.triggered.connect(self._on_add_ground)
        edit_menu.addAction(ground_action)

        # 视图
        view_menu = menubar.addMenu("视图(&V)")

        zoom_in_action = QAction("放大", self)
        zoom_in_action.setShortcut(QKeySequence.ZoomIn)
        # FIX #4: use scale_view() instead of canvas.scale()
        zoom_in_action.triggered.connect(lambda: self.canvas.scale_view(1.2))
        view_menu.addAction(zoom_in_action)

        zoom_out_action = QAction("缩小", self)
        zoom_out_action.setShortcut(QKeySequence.ZoomOut)
        zoom_out_action.triggered.connect(lambda: self.canvas.scale_view(0.8))
        view_menu.addAction(zoom_out_action)

        reset_zoom_action = QAction("重置缩放", self)
        reset_zoom_action.setShortcut("Ctrl+0")
        reset_zoom_action.triggered.connect(self._on_reset_zoom)
        view_menu.addAction(reset_zoom_action)

        view_menu.addSeparator()

        grid_action = QAction("显示/隐藏网格", self)
        grid_action.triggered.connect(self._on_toggle_grid)
        view_menu.addAction(grid_action)

        # 仿真
        sim_menu = menubar.addMenu("仿真(&S)")

        validate_action = QAction("验证电路", self)
        validate_action.setShortcut("F4")
        validate_action.triggered.connect(self._on_validate)
        sim_menu.addAction(validate_action)

        sim_menu.addSeparator()

        self.run_action = QAction("运行仿真", self)
        self.run_action.setShortcut("F5")
        self.run_action.triggered.connect(self._on_run_simulation)
        sim_menu.addAction(self.run_action)

        settings_action = QAction("仿真设置", self)
        settings_action.triggered.connect(self._on_sim_settings)
        sim_menu.addAction(settings_action)

        # 帮助
        help_menu = menubar.addMenu("帮助(&H)")
        about_action = QAction("关于", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    # ---- 工具栏 ----

    def _setup_tool_bar(self):
        toolbar = QToolBar("主工具栏")
        toolbar.setIconSize(QSize(24, 24))
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        toolbar.addWidget(self._tool_button("新建 (Ctrl+N)", "新建", self._on_new))
        toolbar.addWidget(self._tool_button("打开 (Ctrl+O)", "打开", self._on_open))
        toolbar.addWidget(self._tool_button("保存 (Ctrl+S)", "保存", self._on_save))

        toolbar.addSeparator()

        # 运行
        self.run_btn = QPushButton("▶ 运行")
        self.run_btn.setToolTip("运行仿真 (F5)")
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #059669; color: white; border: none;
                border-radius: 4px; padding: 6px 14px; font-weight: bold;
            }
            QPushButton:hover { background-color: #047857; }
            QPushButton:disabled { background-color: #94a3b8; }
        """)
        self.run_btn.clicked.connect(self._on_run_simulation)
        toolbar.addWidget(self.run_btn)

        toolbar.addSeparator()

        # 选择模式（默认激活）
        self.select_btn = QPushButton("↖ 选择")
        self.select_btn.setToolTip("选择模式 (V)")
        self.select_btn.setCheckable(True)
        self.select_btn.setChecked(True)
        self.select_btn.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6; color: white; border: 1px solid #2563eb;
                border-radius: 4px; padding: 6px 12px;
            }
            QPushButton:checked { background-color: #3b82f6; color: white; border-color: #2563eb; }
            QPushButton:hover { background-color: #2563eb; }
        """)
        self.select_btn.clicked.connect(self._on_select_mode)
        toolbar.addWidget(self.select_btn)

        # 连线
        self.wire_btn = QPushButton("🔗 连线")
        self.wire_btn.setToolTip("连线模式 (Ctrl+W)")
        self.wire_btn.setCheckable(True)
        self.wire_btn.setStyleSheet("""
            QPushButton {
                background-color: #f8fafc; border: 1px solid #e2e8f0;
                border-radius: 4px; padding: 6px 12px;
            }
            QPushButton:checked { background-color: #3b82f6; color: white; border-color: #2563eb; }
            QPushButton:hover { background-color: #e2e8f0; }
            QPushButton:checked:hover { background-color: #2563eb; }
        """)
        self.wire_btn.clicked.connect(self._on_toggle_wire_mode)
        toolbar.addWidget(self.wire_btn)

    # FIX #3: _tool_button returns QPushButton, not QLabel
    @staticmethod
    def _tool_button(tooltip: str, text: str, slot) -> QPushButton:
        btn = QPushButton(text)
        btn.setToolTip(tooltip)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #f8fafc; border: 1px solid #e2e8f0;
                border-radius: 4px; padding: 6px 12px;
            }
            QPushButton:hover { background-color: #e2e8f0; border-color: #94a3b8; }
        """)
        btn.clicked.connect(slot)
        return btn

    # ---- 中央部件 ----

    def _setup_central_widget(self):
        self.canvas = CircuitCanvas(self.model)

    # ---- Dock widgets ----

    def _setup_dock_widgets(self):
        # 主工作区：左侧元件库 + 中间画布 + 右侧属性/配置
        self.component_palette = ComponentPalette(self.model, self.canvas)

        self.right_tabs = QTabWidget()
        self.property_panel = PropertyPanel(self.model, self.canvas)
        self.simulation_config = SimulationConfigPanel(self.model)
        self.right_tabs.addTab(self.property_panel, "🔧 属性编辑")
        self.right_tabs.addTab(self.simulation_config, "⚙️ 仿真配置")
        self.right_dock = self.right_tabs

        # 底部输出区独占整行，可用垂直 splitter 上下拖动调整高度
        self.output_tabs = QTabWidget()
        self.code_preview = CodePreviewPanel(self.model)
        self.plot_panel = PlotPanel(self.model)
        self.console_panel = ConsolePanel()
        self.output_tabs.addTab(self.code_preview, "📝 代码预览")
        self.output_tabs.addTab(self.plot_panel, "📊 波形")
        self.output_tabs.addTab(self.console_panel, "🖥 控制台")

        self.work_splitter = QSplitter(Qt.Horizontal)
        self.work_splitter.addWidget(self.component_palette)
        self.work_splitter.addWidget(self.canvas)
        self.work_splitter.addWidget(self.right_tabs)
        self.work_splitter.setStretchFactor(0, 0)
        self.work_splitter.setStretchFactor(1, 1)
        self.work_splitter.setStretchFactor(2, 0)
        self.work_splitter.setSizes([220, 900, 320])

        self.main_splitter = QSplitter(Qt.Vertical)
        self.main_splitter.addWidget(self.work_splitter)
        self.main_splitter.addWidget(self.output_tabs)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 0)
        self.main_splitter.setSizes([620, 240])
        self.setCentralWidget(self.main_splitter)

    # ---- 状态栏 ----

    def _setup_status_bar(self):
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("padding: 2px 8px;")
        self.statusBar().addPermanentWidget(self.status_label)

    # ================================================================
    #  模型观察者回调
    # ================================================================

    def _on_model_changed(self, event: str = "changed"):
        if event in ("component_added", "component_removed", "params_updated",
                      "settings_updated", "cleared", "undone", "redone",
                      "wire_added", "wire_removed"):
            self.code_preview.update_code()
            n = len(self.model.components)
            self.status_label.setText(f"电路已更新 - {n} 个元件, {len(self.model.wires)} 条连线")

    # ================================================================
    #  文件操作
    # ================================================================

    def _on_new(self):
        self.model.clear()
        self.canvas.clear_canvas()
        self.current_file = None
        self.setWindowTitle("EMTP Circuit Designer - 新建")
        self.status_label.setText("新建电路")

    def _on_open(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "打开电路", "",
            "EMTP Circuit Files (*.emtp);;JSON Files (*.json)",
        )
        if file_path:
            self._load_from_file(file_path)

    def _load_from_file(self, file_path: str):
        try:
            # 保存旧模型引用并移除观察者（BUG-10 修复）
            old_model = self.model
            try:
                old_model.remove_observer(self._on_model_changed)
                old_model.remove_observer(self.canvas._on_model_changed)
            except (ValueError, AttributeError):
                pass

            # 创建新模型
            self.model = load_project(file_path)

            # 重新注册观察者到新 model
            self.model.add_observer(self._on_model_changed)

            # 更新 canvas 的 model 引用
            self.canvas.model = self.model
            self.model.add_observer(self.canvas._on_model_changed)

            # 刷新各面板
            self.canvas._refresh_view()
            # BUG-4 修复: 先更新 model 引用再同步
            self.simulation_config.model = self.model
            self.simulation_config.sync_from_model()
            # FIX #2: 同步 PlotPanel 的 model 引用
            self.plot_panel.set_model(self.model)
            self.code_preview.model = self.model
            self.code_preview.update_code()
            # 同步 PropertyPanel 和 ComponentPalette 的 model 引用
            self.property_panel.model = self.model
            self.component_palette.model = self.model

            self.current_file = file_path
            self.setWindowTitle(f"EMTP Circuit Designer - {file_path}")
            self.status_label.setText(f"已加载: {file_path}")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法打开文件:\n{str(e)}")

    def _on_save(self):
        if self.current_file:
            self._save_to_file(self.current_file)
        else:
            self._on_save_as()

    def _on_save_as(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存电路", "", "EMTP Circuit Files (*.emtp)"
        )
        if file_path:
            if not file_path.endswith('.emtp'):
                file_path += '.emtp'
            self._save_to_file(file_path)

    def _save_to_file(self, file_path: str):
        try:
            save_project(self.model, file_path)
            self.current_file = file_path
            self.setWindowTitle(f"EMTP Circuit Designer - {file_path}")
            self.status_label.setText(f"已保存: {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法保存文件:\n{str(e)}")

    def _on_export_code(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出Python代码", "", "Python Files (*.py)"
        )
        if file_path:
            if not file_path.endswith('.py'):
                file_path += '.py'
            try:
                code = generate_code(self.model)
                export_python_code(code, file_path)
                self.status_label.setText(f"已导出: {file_path}")
                QMessageBox.information(self, "成功", f"代码已导出到:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导出失败:\n{str(e)}")

    # ================================================================
    #  编辑操作
    # ================================================================

    def _on_delete(self):
        self.canvas._delete_selected()

    def _on_clear(self):
        reply = QMessageBox.question(
            self, "确认清空", "确定要清空当前电路吗？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.model.clear()
            self.canvas.clear_canvas()
            self.status_label.setText("电路已清空")

    def _on_select_mode(self):
        """切换到选择模式"""
        self.canvas.set_mode(CanvasMode.SELECT)
        self.canvas._placing_type = None
        self.wire_btn.setChecked(False)
        self.status_label.setText("就绪")

    def _on_placement_completed(self):
        """元件放置完成，恢复选择模式按钮状态"""
        self.select_btn.setChecked(True)
        self.wire_btn.setChecked(False)

    def _on_comp_type_selected_from_palette(self, comp_type):
        """元件面板选择元件时，更新工具栏按钮状态"""
        self.select_btn.setChecked(False)
        self.wire_btn.setChecked(False)

    def _on_toggle_wire_mode(self):
        if self.canvas.mode == CanvasMode.WIRE:
            self.canvas.set_mode(CanvasMode.SELECT)
            self.wire_btn.setChecked(False)
            self.select_btn.setChecked(True)
            self.status_label.setText("就绪")
        else:
            self.canvas.set_mode(CanvasMode.WIRE)
            self.canvas._placing_type = None
            self.wire_btn.setChecked(True)
            self.select_btn.setChecked(False)
            self.status_label.setText("连线模式: 从引脚拖拽到引脚 (按Esc退出)")

    def _on_add_ground(self):
        """添加接地（到画布中心）"""
        center = self.canvas.mapToScene(
            self.canvas.viewport().width() // 2,
            self.canvas.viewport().height() // 2,
        )
        self._on_add_ground_at_pos(center)

    def _on_add_ground_at_pos(self, pos: QPointF):
        """在指定位置添加接地"""
        pos = self.canvas.snap_to_grid(pos)
        ground = ComponentInstance(
            comp_id=self.model.generate_component_id(ComponentType.GROUND),
            comp_type=ComponentType.GROUND,
            name="GND",
            x=int(pos.x()),
            y=int(pos.y()),
            rotation=0,
            params={},
            pins=create_component_pins(ComponentType.GROUND),
        )
        self.model.add_component(ground)
        self.status_label.setText("已添加接地")

    def _on_rotate(self):
        self.canvas._rotate_selected()

    # ================================================================
    #  视图操作
    # ================================================================

    def _on_reset_zoom(self):
        self.canvas.resetTransform()

    def _on_toggle_grid(self):
        self.canvas.show_grid = not self.canvas.show_grid
        self.canvas._refresh_view()

    # ================================================================
    #  仿真操作
    # ================================================================

    def _set_running_ui(self, running: bool):
        """统一切换仿真运行期间的按钮状态。"""
        enabled = not running
        if hasattr(self, "run_action"):
            self.run_action.setEnabled(enabled)
        if hasattr(self, "run_btn"):
            self.run_btn.setEnabled(enabled)
        if hasattr(self, "status_label"):
            self.status_label.setText("正在运行仿真..." if running else "就绪")

    def _on_validate(self):
        """验证电路 - 检查常见错误"""
        from core.validator import validate_circuit, ValidationSeverity

        errors = validate_circuit(self.model)
        if not errors:
            QMessageBox.information(self, "验证通过", "✅ 电路验证通过，未发现问题。")
            return

        # 按严重程度分组
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        warning_list = [e for e in errors if e.severity == ValidationSeverity.WARNING]

        # 构建结果文本
        lines = []
        if error_list:
            lines.append(f"❌ 错误 ({len(error_list)}):")
            for e in error_list:
                lines.append(f"  • {e.message}")
                if e.fix:
                    lines.append(f"    → {e.fix}")
        if warning_list:
            lines.append(f"\n⚠️ 警告 ({len(warning_list)}):")
            for e in warning_list:
                lines.append(f"  • {e.message}")
                if e.fix:
                    lines.append(f"    → {e.fix}")

        text = "\n".join(lines)
        if error_list:
            QMessageBox.warning(self, f"验证失败 ({len(error_list)} 错误, {len(warning_list)} 警告)", text)
        else:
            QMessageBox.information(self, f"验证完成 ({len(warning_list)} 警告)", text)

        # 同时输出到控制台
        self.console_panel.append_text(f">>> 验证结果: {len(error_list)} 错误, {len(warning_list)} 警告")
        for line in lines:
            self.console_panel.append_text(line)

    def _on_run_simulation(self):
        """使用 SolverBuilder 直接构建并在后台线程执行仿真"""
        self.console_panel.clear()
        self.console_panel.append_text(">>> 正在构建电路...")

        # 同时更新代码预览（仅用于展示）
        code = generate_code(self.model)
        self.code_preview.setPlainText(code)

        # 创建进度对话框
        self._progress_dialog = QProgressDialog("正在运行仿真...", "取消", 0, 100, self)
        self._progress_dialog.setWindowTitle("仿真进度")
        self._progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress_dialog.setMinimumDuration(500)  # 500ms 后才显示
        self._progress_dialog.setAutoClose(False)
        self._progress_dialog.setAutoReset(False)
        self._progress_dialog.canceled.connect(self._on_sim_cancel)

        # 使用 SolverBuilder 直接构建（不再用 exec）
        self._sim_runner = SimulationRunner(self.model, parent=self)
        self._sim_runner.progress.connect(self._on_sim_progress)
        self._sim_runner.progress_pct.connect(self._on_sim_progress_pct)
        self._sim_runner.log_received.connect(self._on_sim_log)
        self._sim_runner.results_ready.connect(self._on_sim_results)
        self._sim_runner.finished_ok.connect(self._on_sim_finished)
        self._sim_runner.error.connect(self._on_sim_error)
        self._set_running_ui(True)

        self._sim_runner.start()

    def _on_sim_cancel(self):
        """用户点击取消仿真"""
        if hasattr(self, '_sim_runner') and self._sim_runner.isRunning():
            self._sim_runner.request_cancel()
            self.console_panel.append_text(">>> 正在取消仿真...")
            self.status_label.setText("正在取消仿真...")

    def _on_sim_progress(self, msg: str):
        """仿真进度回调（在主线程中调用）"""
        if msg:
            self.console_panel.append_text(msg)

    def _on_sim_progress_pct(self, pct: int):
        """仿真进度百分比回调"""
        if hasattr(self, '_progress_dialog') and self._progress_dialog:
            self._progress_dialog.setValue(pct)

    def _on_sim_finished(self, solver):
        """仿真完成回调（在主线程中调用）"""
        # 关闭进度对话框
        if hasattr(self, '_progress_dialog') and self._progress_dialog:
            self._progress_dialog.close()
            self._progress_dialog = None

        self._set_running_ui(False)

        try:
            self.plot_panel.display_results(solver)
            self.status_label.setText("仿真完成")
            self.console_panel.append_text(">>> 仿真完成！")
            QMessageBox.information(self, "仿真完成", "仿真已成功完成！")
        except Exception as e:
            import traceback
            error_msg = f"显示结果出错:\n{str(e)}\n\n{traceback.format_exc()}"
            self.console_panel.append_text(f">>> {error_msg}")
            self.status_label.setText("结果显示出错")

    def _on_sim_error(self, error_msg: str):
        """仿真错误回调（在主线程中调用）"""
        # 关闭进度对话框
        if hasattr(self, '_progress_dialog') and self._progress_dialog:
            self._progress_dialog.close()
            self._progress_dialog = None

        self._set_running_ui(False)

        self.console_panel.append_text(f">>> 仿真出错:\n{error_msg}")
        QMessageBox.critical(self, "仿真错误", f"仿真出错:\n{error_msg[:200]}...")
        self.status_label.setText("仿真出错")

    def _on_sim_log(self, msg: str):
        """浠跨湡鏃ュ織鍥炶皟锛堝湪涓荤嚎绋嬩腑璋冪敤锛?"""
        if msg:
            self.console_panel.append_text(msg)

    def _on_sim_results(self, results: dict):
        """缂撳瓨浠跨湡搴忓垪鍖栫粨鏋滐紝渚涘鍑烘垨鍚庣画鏌ョ湅銆?"""
        self._last_sim_results = results
        n_probes = len(results.get("probes", {}))
        self.console_panel.append_text(f">>> received serialized data for {n_probes} probes")
        if results.get("timing"):
            self.console_panel.append_text(">>> timing stats cached")

    def _on_sim_settings(self):
        """聚焦到仿真配置面板"""
        if hasattr(self, "right_tabs"):
            self.right_tabs.setCurrentWidget(self.simulation_config)
            self.right_tabs.setVisible(True)

    # ================================================================
    #  关于 / 关闭
    # ================================================================

    def _on_about(self):
        QMessageBox.about(
            self, "关于",
            "EMTP Circuit Designer\n\n"
            "电磁暂态仿真图形化前处理工具\n"
            "版本 1.0\n\n"
            "基于 PySide6 + QGraphicsView 构建",
        )

    def closeEvent(self, event: QCloseEvent):
        if self.current_file or self.model.components:
            reply = QMessageBox.question(
                self, "确认退出", "是否保存当前电路？",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            )
            if reply == QMessageBox.Save:
                self._on_save()
                event.accept()
            elif reply == QMessageBox.Discard:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
