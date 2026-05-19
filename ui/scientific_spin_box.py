import re

from PySide6.QtGui import QValidator
from PySide6.QtWidgets import QDoubleSpinBox


class ScientificSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox with compact scientific notation formatting."""

    _ACCEPTABLE_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
    _INTERMEDIATE_RE = re.compile(r"^[+-]?(?:(?:\d+(?:\.\d*)?|\.\d*)?(?:[eE][+-]?\d*)?)?$")
    _NUMBER_WITH_UNIT_RE = re.compile(
        r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
        r"\s*(?:\[([^\]]+)\]|([A-Za-zΩΩμµ]+))?\s*$"
    )
    _NUMBER_WITH_PARTIAL_UNIT_RE = re.compile(
        r"^\s*[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
        r"\s*(?:\[?[A-Za-zΩΩμµ]*)?$"
    )
    _PREFIX_FACTORS = {
        "": 1.0,
        "f": 1e-15,
        "p": 1e-12,
        "n": 1e-9,
        "u": 1e-6,
        "m": 1e-3,
        "c": 1e-2,
        "k": 1e3,
        "K": 1e3,
        "M": 1e6,
        "G": 1e9,
        "T": 1e12,
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(1e-15, 1e6)
        self.setDecimals(18)
        self.setMinimumWidth(130)
        self.setKeyboardTracking(False)
        self._base_unit = ""

    def set_base_unit(self, unit: str):
        self._base_unit = self._normalize_unit(unit or "")

    def textFromValue(self, val: float) -> str:
        if val == 0:
            return "0"
        if abs(val) < 1e-3 or abs(val) >= 1e6:
            return f"{val:.6e}"
        return f"{val:.6g}"

    def valueFromText(self, text: str) -> float:
        try:
            return self._parse_value(text)
        except ValueError:
            return self.value()

    @classmethod
    def _normalize_unit(cls, unit: str) -> str:
        normalized = (unit or "").strip().replace(" ", "")
        normalized = normalized.replace("μ", "u").replace("µ", "u").replace("Ω", "Ω")
        if normalized.lower().endswith("ohm"):
            normalized = f"{normalized[:-3]}Ω"
        return normalized

    def _unit_multiplier(self, unit: str) -> float:
        normalized = self._normalize_unit(unit)
        if not normalized:
            return 1.0
        if not self._base_unit:
            raise ValueError("Unit suffix is not supported for this field")
        if normalized == self._base_unit:
            return 1.0
        if not normalized.endswith(self._base_unit):
            raise ValueError(f"Unit {unit!r} does not match base unit {self._base_unit!r}")

        prefix = normalized[:-len(self._base_unit)]
        if prefix not in self._PREFIX_FACTORS:
            raise ValueError(f"Unsupported SI prefix: {prefix}")
        return self._PREFIX_FACTORS[prefix]

    def _parse_value(self, text: str) -> float:
        candidate = text.strip().replace(",", "")
        match = self._NUMBER_WITH_UNIT_RE.fullmatch(candidate)
        if not match:
            raise ValueError(text)
        unit = match.group(2) or match.group(3) or ""
        return float(match.group(1)) * self._unit_multiplier(unit)

    def validate(self, text: str, pos: int):
        candidate = text.strip().replace(",", "")
        try:
            value = self._parse_value(candidate)
            if self.minimum() <= value <= self.maximum():
                return (QValidator.State.Acceptable, text, pos)
            return (QValidator.State.Intermediate, text, pos)
        except ValueError:
            pass

        if self._INTERMEDIATE_RE.fullmatch(candidate):
            return (QValidator.State.Intermediate, text, pos)
        if self._NUMBER_WITH_PARTIAL_UNIT_RE.fullmatch(candidate):
            return (QValidator.State.Intermediate, text, pos)
        return (QValidator.State.Invalid, text, pos)
