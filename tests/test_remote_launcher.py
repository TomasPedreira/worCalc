from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = REPOSITORY_ROOT / "START_REMOTE_WORCALC.bat"


class RemoteLauncherTests(unittest.TestCase):
    def test_launcher_starts_local_web_app_and_private_tailscale_serve(self) -> None:
        launcher = LAUNCHER.read_text(encoding="utf-8")

        self.assertIn(r".venv\Scripts\python.exe", launcher)
        self.assertIn("-m worcalc.web --host 127.0.0.1 --port 8000", launcher)
        self.assertIn(r"%ProgramFiles%\Tailscale\tailscale.exe", launcher)
        self.assertIn("serve --bg 8000", launcher)
        self.assertNotIn("funnel", launcher.lower())

    def test_launcher_self_elevates_and_checks_the_server_identity(self) -> None:
        launcher = LAUNCHER.read_text(encoding="utf-8")

        self.assertIn("-Verb RunAs", launcher)
        self.assertIn("worCalc Mobile", launcher)
        self.assertIn("Get-NetTCPConnection -LocalPort 8000", launcher)


if __name__ == "__main__":
    unittest.main()
