@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Creating the Python environment...
  python -m venv .venv
  if errorlevel 1 goto failed
)
echo Installing or checking the app packages...
".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
if errorlevel 1 goto failed
echo.
echo SEATIQ is starting. Open http://127.0.0.1:8000 in your browser.
".venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir backend --reload
goto done
:failed
echo.
echo Startup failed. Confirm Python 3.10+ is installed and internet is available for first-time setup.
pause
:done
endlocal

