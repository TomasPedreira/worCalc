"""Compatibility facade; use :mod:`worcalc.app` in new code."""

from worcalc.app import MainWindow, discover_maps, fit_window_to_screen, run
from worcalc.ui.main_window import CalibrationDialog, CalibrationEditor

__all__ = [
    "CalibrationDialog",
    "CalibrationEditor",
    "MainWindow",
    "discover_maps",
    "fit_window_to_screen",
    "run",
]
