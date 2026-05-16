import re

from PySide6.QtGui import QValidator
from PySide6.QtWidgets import QDoubleSpinBox


class ScientificSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox with compact scientific notation formatting."""

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
            return float(text.replace(",", ""))
        except ValueError:
            return self.value()

    def validate(self, text: str, pos: int):
        candidate = text.strip().replace(",", "")
        if self._ACCEPTABLE_RE.fullmatch(candidate):
            value = float(candidate)
            if self.minimum() <= value <= self.maximum():
                return (QValidator.State.Acceptable, text, pos)
            return (QValidator.State.Intermediate, text, pos)
        if self._INTERMEDIATE_RE.fullmatch(candidate):
            return (QValidator.State.Intermediate, text, pos)
        return (QValidator.State.Invalid, text, pos)
