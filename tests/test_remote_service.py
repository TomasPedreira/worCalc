from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch
import unittest

from worcalc import remote_service


class RemoteServiceTests(unittest.TestCase):
    @patch.object(remote_service, "server_is_ready", side_effect=[False, True])
    @patch.object(remote_service, "_port_is_open", return_value=False)
    @patch.object(remote_service.subprocess, "Popen")
    def test_start_server_uses_background_pythonw(
        self, popen: MagicMock, _port_open: MagicMock, _ready: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with (
                patch.object(remote_service, "_pythonw_executable", return_value=Path("pythonw.exe")),
                patch.object(remote_service, "LOG_PATH", Path(temporary_directory) / "server.log"),
            ):
                self.assertTrue(remote_service.start_server())

        command = popen.call_args.args[0]
        self.assertEqual(command[0], "pythonw.exe")
        self.assertIn("worcalc.web", command)
        self.assertEqual(popen.call_args.kwargs["creationflags"], remote_service.NO_WINDOW)

    @patch.object(remote_service, "_port_is_open", return_value=True)
    @patch.object(remote_service, "server_is_ready", return_value=False)
    def test_start_server_refuses_an_unrelated_port_listener(
        self, _ready: MagicMock, _port_open: MagicMock
    ) -> None:
        with self.assertRaisesRegex(remote_service.RemoteServiceError, "another application"):
            remote_service.start_server()

    @patch.object(remote_service, "_stop_server", return_value=True)
    @patch.object(remote_service, "_elevated_tailscale")
    def test_stop_disables_tailscale_then_stops_server(
        self, elevated_tailscale: MagicMock, stop_server: MagicMock
    ) -> None:
        self.assertTrue(remote_service.stop_remote_service())

        elevated_tailscale.assert_called_once_with(["serve", "--bg", "8000", "off"])
        stop_server.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
