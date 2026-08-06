@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
set "TAILSCALE_EXE=%ProgramFiles%\Tailscale\tailscale.exe"
set "WORCALC_URL=http://127.0.0.1:8000/"

if not exist "%PYTHON_EXE%" goto missing_python
if not exist "%TAILSCALE_EXE%" goto missing_tailscale

rem Tailscale Serve on Windows requires an Administrator console.
powershell.exe -NoProfile -Command "if (([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { exit 0 } else { exit 1 }"
if errorlevel 1 goto elevate

call :server_ready
if not errorlevel 1 goto server_running

rem Do not start worCalc over an unrelated service already using port 8000.
powershell.exe -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if not errorlevel 1 goto port_conflict

echo Starting the worCalc web server...
start "worCalc web server" /min "%PYTHON_EXE%" -m worcalc.web --host 127.0.0.1 --port 8000
call :wait_for_server
if errorlevel 1 goto server_failed
goto configure_tailscale

:server_running
echo The worCalc web server is already running.

:configure_tailscale
echo Configuring private Tailscale access...
"%TAILSCALE_EXE%" serve --bg 8000
if errorlevel 1 goto tailscale_failed

echo.
echo worCalc is ready. Open the HTTPS address shown below on a device in your tailnet:
"%TAILSCALE_EXE%" serve status
echo.
echo The server is running in a minimized window. Closing this launcher is safe.
pause
exit /b 0

:elevate
echo Requesting Administrator permission for Tailscale Serve...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -WorkingDirectory '%~dp0' -Verb RunAs"
exit /b

:missing_python
echo ERROR: The project environment was not found at:
echo   %PYTHON_EXE%
echo Run setup_windows.bat first.
pause
exit /b 1

:missing_tailscale
echo ERROR: Tailscale was not found at:
echo   %TAILSCALE_EXE%
echo Install Tailscale and sign in before using this launcher.
pause
exit /b 1

:port_conflict
echo ERROR: Port 8000 is already being used by something other than worCalc.
echo Stop that application, then run this launcher again.
pause
exit /b 1

:server_failed
echo ERROR: worCalc did not become ready on %WORCALC_URL%.
echo Check the minimized "worCalc web server" window for the Python error.
pause
exit /b 1

:tailscale_failed
echo ERROR: Tailscale Serve could not be configured.
echo Confirm Tailscale is connected, then run this launcher again.
pause
exit /b 1

:server_ready
powershell.exe -NoProfile -Command "try { $response = Invoke-WebRequest -UseBasicParsing -Uri '%WORCALC_URL%' -TimeoutSec 2; if ($response.Content -match 'worCalc Mobile') { exit 0 } } catch {}; exit 1"
exit /b %ERRORLEVEL%

:wait_for_server
powershell.exe -NoProfile -Command "$ready = $false; for ($attempt = 0; $attempt -lt 20; $attempt++) { try { $response = Invoke-WebRequest -UseBasicParsing -Uri '%WORCALC_URL%' -TimeoutSec 1; if ($response.Content -match 'worCalc Mobile') { $ready = $true; break } } catch {}; Start-Sleep -Milliseconds 250 }; if ($ready) { exit 0 } else { exit 1 }"
exit /b %ERRORLEVEL%
