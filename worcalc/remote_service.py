"""Start and stop the private worCalc web service on Windows."""

from __future__ import annotations

import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen


HOST = "127.0.0.1"
PORT = 8000
LOCAL_URL = f"http://{HOST}:{PORT}/"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = Path(tempfile.gettempdir()) / "worcalc-web.log"
TAILSCALE_EXE = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tailscale" / "tailscale.exe"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class RemoteServiceError(RuntimeError):
    """Raised when the remote service cannot be changed safely."""


def server_is_ready(timeout: float = 0.75) -> bool:
    try:
        with urlopen(LOCAL_URL, timeout=timeout) as response:
            return b"worCalc Mobile" in response.read(64_000)
    except OSError:
        return False


def _port_is_open(timeout: float = 0.25) -> bool:
    with socket.socket() as connection:
        connection.settimeout(timeout)
        return connection.connect_ex((HOST, PORT)) == 0


def _pythonw_executable() -> Path:
    executable = Path(sys.executable)
    pythonw = executable.with_name("pythonw.exe")
    return pythonw if pythonw.exists() else executable


def start_server() -> bool:
    """Start the local web server, returning False when it was already running."""
    if server_is_ready():
        return False
    if _port_is_open():
        raise RemoteServiceError(f"Port {PORT} is being used by another application.")

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as log:
        subprocess.Popen(
            [
                str(_pythonw_executable()),
                "-m",
                "worcalc.web",
                "--host",
                HOST,
                "--port",
                str(PORT),
            ],
            cwd=REPOSITORY_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=NO_WINDOW,
        )

    for _ in range(24):
        if server_is_ready(timeout=0.25):
            return True
        time.sleep(0.25)
    raise RemoteServiceError(f"worCalc did not start. Check {LOG_PATH} for details.")


def _elevated_tailscale(arguments: list[str]) -> None:
    if not TAILSCALE_EXE.exists():
        raise RemoteServiceError(f"Tailscale was not found at {TAILSCALE_EXE}.")
    argument_list = ",".join("'" + value.replace("'", "''") + "'" for value in arguments)
    command = (
        f"$process = Start-Process -FilePath '{TAILSCALE_EXE}' "
        f"-ArgumentList {argument_list} -Verb RunAs -WindowStyle Hidden -Wait -PassThru; "
        "exit $process.ExitCode"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        creationflags=NO_WINDOW,
        check=False,
    )
    if result.returncode:
        raise RemoteServiceError("Tailscale did not accept the requested change.")


def tailscale_url() -> str | None:
    if not TAILSCALE_EXE.exists():
        return None
    result = subprocess.run(
        [str(TAILSCALE_EXE), "serve", "status"],
        capture_output=True,
        text=True,
        creationflags=NO_WINDOW,
        check=False,
    )
    match = re.search(r"https://[^\s|]+", result.stdout)
    return match.group(0).rstrip("/") if match else None


def start_remote_service() -> str | None:
    start_server()
    _elevated_tailscale(["serve", "--bg", str(PORT)])
    return tailscale_url()


def _stop_server() -> bool:
    command = (
        f"$listeners = Get-NetTCPConnection -LocalPort {PORT} -State Listen -ErrorAction SilentlyContinue; "
        "$found = $false; $failed = $false; foreach ($listener in $listeners) { "
        "$process = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $listener.OwningProcess) "
        "-ErrorAction SilentlyContinue; if ($null -ne $process -and "
        "$process.CommandLine -match '(?i)-m\\s+worcalc\\.web(?:\\s|$)') { $found = $true; "
        "try { Stop-Process -Id $listener.OwningProcess -Force -ErrorAction Stop } "
        "catch { $failed = $true } } }; if ($failed) { exit 1 }; if ($found) { exit 0 }; exit 2"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        creationflags=NO_WINDOW,
        check=False,
    )
    if result.returncode == 1:
        raise RemoteServiceError("The worCalc server could not be stopped.")
    return result.returncode == 0


def stop_remote_service() -> bool:
    tailscale_error: RemoteServiceError | None = None
    try:
        _elevated_tailscale(["serve", "--bg", str(PORT), "off"])
    except RemoteServiceError as error:
        tailscale_error = error

    stopped = _stop_server()
    if tailscale_error is not None:
        raise RemoteServiceError(f"The server was stopped, but {tailscale_error}")
    return stopped
