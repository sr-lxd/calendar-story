@echo off
setlocal
cd /d "%~dp0"

set "HOST=127.0.0.1"
set "PORT=5091"
set "THREADS=8"

set "LISTEN_PID="
for /f "tokens=5" %%P in ('netstat -ano -p tcp ^| findstr /R /C:":%PORT% .*LISTENING"') do (
  set "LISTEN_PID=%%P"
)
if defined LISTEN_PID (
  echo [ERROR] Port %PORT% is already in use by PID %LISTEN_PID%.
  echo Please stop that process first, then run this script again.
  echo Hint: open an Administrator terminal and run:
  echo   taskkill /PID %LISTEN_PID% /F
  pause
  exit /b 1
)

python -c "import waitress" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] waitress is not installed.
  echo Run: python -m pip install waitress
  pause
  exit /b 1
)

echo Starting Calendar Story on %HOST%:%PORT% ...
python -m waitress --host=%HOST% --port=%PORT% --threads=%THREADS% app:app
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo [ERROR] waitress exited with code %EXIT_CODE%.
  pause
)
exit /b %EXIT_CODE%
