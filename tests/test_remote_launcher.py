from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = REPOSITORY_ROOT / "START_REMOTE_WORCALC.bat"
SHUTDOWN = REPOSITORY_ROOT / "END_REMOTE_WORCALC.bat"


class RemoteLauncherTests(unittest.TestCase):
    def test_launcher_starts_local_web_app_and_private_tailscale_serve(self) -> None:
        launcher = LAUNCHER.read_text(encoding="utf-8")

        self.assertIn(r".venv\Scripts\pythonw.exe", launcher)
        self.assertIn("-m worcalc.web --host 127.0.0.1 --port 8000", launcher)
        self.assertIn('start "" /b', launcher)
        self.assertIn(r"%ProgramFiles%\Tailscale\tailscale.exe", launcher)
        self.assertIn("-ArgumentList 'serve','--bg','8000'", launcher)
        self.assertNotIn("funnel", launcher.lower())

    def test_launcher_only_elevates_tailscale_and_checks_the_server_identity(self) -> None:
        launcher = LAUNCHER.read_text(encoding="utf-8")

        self.assertIn("-Verb RunAs", launcher)
        self.assertIn("-WindowStyle Hidden", launcher)
        self.assertIn("Start-Process -FilePath '%TAILSCALE_EXE%'", launcher)
        self.assertNotIn("Start-Process -FilePath '%~f0'", launcher)
        self.assertIn("worCalc Mobile", launcher)
        self.assertIn("Get-NetTCPConnection -LocalPort 8000", launcher)

    def test_shutdown_disables_the_matching_tailscale_serve_endpoint(self) -> None:
        shutdown = SHUTDOWN.read_text(encoding="utf-8")

        self.assertIn(r"%ProgramFiles%\Tailscale\tailscale.exe", shutdown)
        self.assertIn("serve --bg 8000 off", shutdown)
        self.assertNotIn("serve reset", shutdown)
        self.assertNotIn("tailscale down", shutdown.lower())

    def test_shutdown_self_elevates_and_only_stops_the_worcalc_server(self) -> None:
        shutdown = SHUTDOWN.read_text(encoding="utf-8")

        self.assertIn("-Verb RunAs", shutdown)
        self.assertIn("Get-NetTCPConnection -LocalPort 8000", shutdown)
        self.assertIn(r"-m\s+worcalc\.web", shutdown)
        self.assertIn("Stop-Process -Id $listener.OwningProcess", shutdown)


if __name__ == "__main__":
    unittest.main()
