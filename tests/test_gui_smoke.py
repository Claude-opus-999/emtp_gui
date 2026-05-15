import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton, QSplitter


def get_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class GuiSmokeTests(unittest.TestCase):
    def test_parameter_dialog_imports(self):
        from ui.moa_param_dialog import MOAParamDialog
        from ui.lpm_param_dialog import LPMParamDialog
        from ui.lcp_param_dialog import (
            LCPOHLDialog,
            LCPSingleCableDialog,
            LCPThreeCoreCableDialog,
        )
        from ui.umec_param_dialog import UMECTransformerDialog

        self.assertIsNotNone(MOAParamDialog)
        self.assertIsNotNone(LPMParamDialog)
        self.assertIsNotNone(LCPOHLDialog)
        self.assertIsNotNone(LCPSingleCableDialog)
        self.assertIsNotNone(LCPThreeCoreCableDialog)
        self.assertIsNotNone(UMECTransformerDialog)

    def test_main_window_exposes_run_and_right_tab_controls(self):
        get_app()
        from ui.main_window import MainWindow

        window = MainWindow()
        try:
            self.assertTrue(hasattr(window, "run_action"))
            self.assertTrue(hasattr(window, "run_btn"))
            self.assertTrue(hasattr(window, "right_tabs"))
            self.assertTrue(hasattr(window, "right_dock"))
        finally:
            window.close()

    def test_sim_settings_selects_simulation_config_tab(self):
        get_app()
        from ui.main_window import MainWindow

        window = MainWindow()
        try:
            window.right_tabs.setCurrentWidget(window.property_panel)
            window._on_sim_settings()
            self.assertIs(window.right_tabs.currentWidget(), window.simulation_config)
        finally:
            window.close()

    def test_set_running_ui_toggles_run_controls(self):
        get_app()
        from ui.main_window import MainWindow

        window = MainWindow()
        try:
            window._set_running_ui(True)
            self.assertFalse(window.run_action.isEnabled())
            self.assertFalse(window.run_btn.isEnabled())

            window._set_running_ui(False)
            self.assertTrue(window.run_action.isEnabled())
            self.assertTrue(window.run_btn.isEnabled())
        finally:
            window.close()

    def test_output_area_uses_vertical_splitter_and_probe_panel_is_removed(self):
        get_app()
        from ui.main_window import MainWindow

        window = MainWindow()
        try:
            self.assertTrue(hasattr(window, "main_splitter"))
            self.assertIsInstance(window.main_splitter, QSplitter)
            self.assertEqual(window.main_splitter.orientation(), Qt.Vertical)
            self.assertIs(window.centralWidget(), window.main_splitter)
            self.assertEqual(window.main_splitter.count(), 2)
            self.assertTrue(hasattr(window, "work_splitter"))
            self.assertIs(window.main_splitter.widget(0), window.work_splitter)
            self.assertIs(window.main_splitter.widget(1), window.output_tabs)
            self.assertIsInstance(window.work_splitter, QSplitter)
            self.assertEqual(window.work_splitter.orientation(), Qt.Horizontal)
            self.assertEqual(window.work_splitter.count(), 3)
            self.assertIs(window.work_splitter.widget(0), window.component_palette)
            self.assertIs(window.work_splitter.widget(1), window.canvas)
            self.assertIs(window.work_splitter.widget(2), window.right_tabs)
            self.assertTrue(hasattr(window, "output_tabs"))
            self.assertFalse(hasattr(window, "probe_panel"))
        finally:
            window.close()

    def test_palette_has_pscad_style_probe_buttons(self):
        get_app()
        from models.circuit_model import ComponentType
        from ui.main_window import MainWindow

        window = MainWindow()
        try:
            buttons = {
                button.text(): button
                for button in window.component_palette.findChildren(QPushButton)
            }

            self.assertIn("对地电压探针", buttons)
            self.assertIn("两节点电压探针", buttons)
            self.assertIn("电流探针", buttons)

            buttons["对地电压探针"].click()
            self.assertEqual(window.canvas._placing_type, ComponentType.PROBE)
            self.assertEqual(window.canvas._placing_params["probe_type"], "voltage_ground")

            buttons["两节点电压探针"].click()
            self.assertEqual(window.canvas._placing_type, ComponentType.PROBE)
            self.assertEqual(window.canvas._placing_params["probe_type"], "voltage_between")

            buttons["电流探针"].click()
            self.assertEqual(window.canvas._placing_type, ComponentType.PROBE)
            self.assertEqual(window.canvas._placing_params["probe_type"], "branch_current")
        finally:
            window.close()

    def test_shared_matplotlib_font_config_sets_expected_rcparams(self):
        from ui.mpl_config import configure_matplotlib_fonts
        import matplotlib

        configure_matplotlib_fonts()

        self.assertEqual(matplotlib.rcParams["font.family"], ["sans-serif"])
        self.assertIn("Microsoft YaHei", matplotlib.rcParams["font.sans-serif"])
        self.assertFalse(matplotlib.rcParams["axes.unicode_minus"])


if __name__ == "__main__":
    unittest.main()
