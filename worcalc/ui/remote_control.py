"""Minimal desktop controller for worCalc remote access."""

from __future__ import annotations

import sys
import webbrowser
from collections.abc import Callable

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from worcalc.remote_service import (
    LOCAL_URL,
    LOG_PATH,
    server_is_ready,
    start_remote_service,
    stop_remote_service,
    tailscale_url,
)


class ActionWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, action: Callable[[], object]) -> None:
        super().__init__()
        self.action = action

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(self.action())
        except Exception as error:
            self.failed.emit(str(error))


class RemoteControlWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._thread: QThread | None = None
        self._worker: ActionWorker | None = None
        self._remote_url: str | None = None
        self._action_failed = False
        self.setWindowTitle("worCalc Remote")
        self.setFixedSize(390, 205)

        title = QLabel("worCalc Remote")
        title.setFont(QFont(title.font().family(), 16, QFont.Weight.DemiBold))

        self.status = QLabel()
        self.status.setFont(QFont(self.status.font().family(), 11, QFont.Weight.DemiBold))
        self.detail = QLabel(f"Log: {LOG_PATH}")
        self.detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail.setWordWrap(True)

        self.start_button = QPushButton("Start")
        self.stop_button = QPushButton("Stop")
        self.open_button = QPushButton("Open")
        self.start_button.clicked.connect(self._start)
        self.stop_button.clicked.connect(self._stop)
        self.open_button.clicked.connect(self._open)

        buttons = QHBoxLayout()
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)
        buttons.addWidget(self.open_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.addWidget(title)
        layout.addWidget(self.status)
        layout.addWidget(self.detail, 1)
        layout.addLayout(buttons)

        self._timer = QTimer(self)
        self._timer.setInterval(2_000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    @Slot()
    def refresh(self) -> None:
        if self._thread is not None:
            return
        running = server_is_ready(timeout=0.2)
        self.status.setText("● Running" if running else "● Stopped")
        self.status.setStyleSheet("color: #238636" if running else "color: #8c959f")
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.open_button.setEnabled(running)
        if running:
            self._remote_url = tailscale_url()
            self.detail.setText(self._remote_url or LOCAL_URL)
        else:
            self._remote_url = None
            self.detail.setText(f"Log: {LOG_PATH}")

    def _run(self, action: Callable[[], object], message: str) -> None:
        self._action_failed = False
        self.status.setText(message)
        self.status.setStyleSheet("color: #1f6feb")
        for button in (self.start_button, self.stop_button, self.open_button):
            button.setEnabled(False)

        self._thread = QThread(self)
        self._worker = ActionWorker(action)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._complete)
        self._worker.failed.connect(self._failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup)
        self._thread.start()

    @Slot()
    def _start(self) -> None:
        self._run(start_remote_service, "Starting… approve the UAC prompt")

    @Slot()
    def _stop(self) -> None:
        self._run(stop_remote_service, "Stopping… approve the UAC prompt")

    @Slot(object)
    def _complete(self, result: object) -> None:
        if isinstance(result, str):
            self._remote_url = result

    @Slot(str)
    def _failed(self, message: str) -> None:
        self._action_failed = True
        self.status.setText("● Action failed")
        self.status.setStyleSheet("color: #cf222e")
        self.detail.setText(message)

    @Slot()
    def _cleanup(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()
        self._worker = None
        self._thread = None
        if self._action_failed:
            running = server_is_ready(timeout=0.2)
            self.start_button.setEnabled(not running)
            self.stop_button.setEnabled(running)
            self.open_button.setEnabled(running)
        else:
            QTimer.singleShot(150, self.refresh)

    @Slot()
    def _open(self) -> None:
        webbrowser.open(self._remote_url or LOCAL_URL)


def main() -> int:
    app = QApplication(sys.argv)
    window = RemoteControlWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
