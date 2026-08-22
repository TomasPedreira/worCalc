@echo off
setlocal
cd /d "%~dp0"

set "PYTHONW_EXE=%~dp0.venv\Scripts\pythonw.exe"
set "TAILSCALE_EXE=%ProgramFiles%\Tailscale\tailscale.exe"
set "WORCALC_URL=http://127.0.0.1:8000/"
set "WORCALC_LOG=%TEMP%\worcalc-web.log"

if not exist "%PYTHONW_EXE%" goto missing_python
if not exist "%TAILSCALE_EXE%" goto missing_tailscale

call :server_ready
if not errorlevel 1 goto server_running

rem Do not start worCalc over an unrelated service already using port 8000.
powershell.exe -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if not errorlevel 1 goto port_conflict

echo Starting the worCalc web server...
start "" /b "%PYTHONW_EXE%" -m worcalc.web --host 127.0.0.1 --port 8000 > "%WORCALC_LOG%" 2>&1
call :wait_for_server
if errorlevel 1 goto server_failed
goto configure_tailscale

:server_running
echo The worCalc web server is already running.

:configure_tailscale
echo Configuring private Tailscale access...
powershell.exe -NoProfile -Command "$process = Start-Process -FilePath '%TAILSCALE_EXE%' -ArgumentList 'serve','--bg','8000' -Verb RunAs -WindowStyle Hidden -Wait -PassThru; exit $process.ExitCode"
if errorlevel 1 goto tailscale_failed

echo.
echo worCalc is ready. Open the HTTPS address shown below on a device in your tailnet:
"%TAILSCALE_EXE%" serve status
echo.
echo The server is running in the background. Closing this launcher is safe.
pause
exit /b 0

:missing_python
echo ERROR: The project environment was not found at:
echo   %PYTHONW_EXE%
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
echo Check the Python log for the error:
echo   %WORCALC_LOG%
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
