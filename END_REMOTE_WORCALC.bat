@echo off
setlocal
cd /d "%~dp0"

set "TAILSCALE_EXE=%ProgramFiles%\Tailscale\tailscale.exe"
set "TAILSCALE_FAILED=0"
set "SERVER_FAILED=0"

rem Tailscale Serve on Windows requires an Administrator console.
powershell.exe -NoProfile -Command "if (([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { exit 0 } else { exit 1 }"
if errorlevel 1 goto elevate

if not exist "%TAILSCALE_EXE%" goto missing_tailscale

echo Disabling private Tailscale access to worCalc...
"%TAILSCALE_EXE%" serve --bg 8000 off
if errorlevel 1 goto tailscale_failed
goto stop_worcalc

:stop_worcalc
echo Stopping the worCalc web server...
call :stop_server
if errorlevel 2 goto server_not_running
if errorlevel 1 goto server_failed
echo The worCalc web server has stopped.
goto finished

:server_not_running
echo No worCalc web server was listening on port 8000.
goto finished

:server_failed
echo ERROR: The worCalc web server could not be stopped.
set "SERVER_FAILED=1"
goto finished

:finished
if "%TAILSCALE_FAILED%"=="1" goto partial_failure
if "%SERVER_FAILED%"=="1" goto partial_failure
echo.
echo worCalc and its Tailscale Serve endpoint have stopped.
pause
exit /b 0

:partial_failure
echo.
echo Shutdown finished with the error shown above.
pause
exit /b 1

:elevate
echo Requesting Administrator permission to stop Tailscale Serve and worCalc...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -WorkingDirectory '%~dp0' -Verb RunAs"
exit /b

:missing_tailscale
echo WARNING: Tailscale was not found at:
echo   %TAILSCALE_EXE%
echo The script will still try to stop the worCalc web server.
set "TAILSCALE_FAILED=1"
goto stop_worcalc

:tailscale_failed
echo WARNING: The worCalc Tailscale Serve endpoint could not be disabled.
echo The script will still try to stop the worCalc web server.
set "TAILSCALE_FAILED=1"
goto stop_worcalc

:stop_server
powershell.exe -NoProfile -Command "$listeners = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue; $found = $false; $failed = $false; foreach ($listener in $listeners) { $process = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $listener.OwningProcess) -ErrorAction SilentlyContinue; if ($null -ne $process -and $process.CommandLine -match '(?i)-m\s+worcalc\.web(?:\s|$)') { $found = $true; try { Stop-Process -Id $listener.OwningProcess -Force -ErrorAction Stop } catch { $failed = $true } } }; if ($failed) { exit 1 }; if ($found) { exit 0 }; exit 2"
exit /b %ERRORLEVEL%
