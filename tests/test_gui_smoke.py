import os
import tempfile
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

    def test_lcp_cable_dialogs_expose_vf_fitting_page_and_config(self):
        get_app()
        from ui.lcp_param_dialog import LCPSingleCableDialog, LCPThreeCoreCableDialog

        fitting_params = {
            "Yc_poles_min": 5,
            "Yc_poles_max": 17,
            "Yc_target_error": 0.004,
            "H_poles_min": 7,
            "H_poles_max": 19,
            "H_target_error": 0.006,
            "freq_min": 0.25,
            "freq_max": 250000.0,
            "n_freq_increments": 321,
        }

        for dialog_cls in (LCPSingleCableDialog, LCPThreeCoreCableDialog):
            dialog = dialog_cls(fitting_params)
            try:
                tab_names = [
                    dialog.tabs.tabText(index)
                    for index in range(dialog.tabs.count())
                ]
                self.assertIn("拟合配置", tab_names)
                self.assertTrue(hasattr(dialog, "yc_poles_min_spin"))
                self.assertTrue(hasattr(dialog, "h_poles_max_spin"))
                self.assertTrue(hasattr(dialog, "freq_n_spin"))

                config = dialog.get_config()
                for key, value in fitting_params.items():
                    self.assertEqual(config[key], value)
            finally:
                dialog.close()

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

    def test_main_window_load_file_runs_subcircuit_validation_without_name_error(self):
        get_app()
        import ui.main_window as main_window_module
        from core.file_io import save_project
        from ui.main_window import MainWindow

        window = MainWindow()
        critical_calls = []
        warning_calls = []
        original_message_box = main_window_module.QMessageBox

        class FakeMessageBox:
            Save = 1
            Discard = 2
            Cancel = 4

            @staticmethod
            def critical(*args, **kwargs):
                critical_calls.append(args)

            @staticmethod
            def warning(*args, **kwargs):
                warning_calls.append(args)

            @staticmethod
            def question(*args, **kwargs):
                return FakeMessageBox.Discard

        main_window_module.QMessageBox = FakeMessageBox
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                file_path = os.path.join(temp_dir, "empty_project.emtp")
                save_project(window.model, file_path)

                window._load_from_file(file_path)

                self.assertEqual(critical_calls, [])
                self.assertEqual(window.current_file, file_path)
        finally:
            window.close()
            main_window_module.QMessageBox = original_message_box

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

    def test_plot_panel_uses_compact_legend_thin_lines_and_max_markers(self):
        get_app()
        import numpy as np
        from ui.main_window import PlotPanel

        class FakeSolver:
            def get_time(self, unit):
                self.assertEqual(unit, "s")
                return np.array([0.0, 1e-6, 2e-6])

            def list_probes(self):
                return {
                    "voltage": ["V1"],
                    "branch_current": ["I1"],
                    "line_current": [],
                }

            def get_probe(self, name, unit):
                data = {
                    "V1": np.array([0.0, 3.0, 2.0]),
                    "I1": np.array([1.0, 0.5, 4.0]),
                }
                return data[name]

        panel = PlotPanel()
        try:
            solver = FakeSolver()
            solver.assertEqual = self.assertEqual
            panel.display_results(solver)

            data_lines = [
                line for line in panel.ax.lines
                if not line.get_label().startswith("_")
            ]
            self.assertGreaterEqual(len(data_lines), 2)
            self.assertTrue(all(line.get_linewidth() <= 1.1 for line in data_lines))

            legend = panel.ax.get_legend()
            self.assertIsNotNone(legend)
            self.assertEqual(legend._loc, 1)
            self.assertTrue(all(text.get_fontsize() <= 7 for text in legend.get_texts()))

            annotation_text = "\n".join(text.get_text() for text in panel.ax.texts)
            self.assertIn("max=", annotation_text)
            self.assertIn("t=", annotation_text)
            self.assertGreaterEqual(len(panel.ax.collections), 2)
        finally:
            panel.close()


if __name__ == "__main__":
    unittest.main()
