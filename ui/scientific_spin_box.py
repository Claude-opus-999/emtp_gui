from PySide6.QtWidgets import QDoubleSpinBox


class ScientificSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox with compact scientific notation formatting."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(1e-15, 1e6)
        self.setDecimals(12)
        self.setMinimumWidth(130)

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
