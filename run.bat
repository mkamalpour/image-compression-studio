@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Preparing a local Python 3.11 environment...
    py -3.11 -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        py -3.11 -m venv .venv
    ) else (
        python -c "import sys; sys.exit(0 if sys.version_info[:2] == (3,11) else 1)" >nul 2>&1
        if errorlevel 1 goto missing_python
        python -m venv .venv
    )
    if not exist ".venv\Scripts\python.exe" goto setup_failed
)
".venv\Scripts\python.exe" -c "import numpy, PIL; assert numpy.__version__ == '2.4.4' and PIL.__version__ == '12.2.0'" >nul 2>&1
if errorlevel 1 (
    echo Installing required libraries. Internet access is needed for first setup.
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto setup_failed
)
if "%~1"=="--check" goto check_setup
".venv\Scripts\python.exe" -m media_studio
if errorlevel 1 goto launch_failed
exit /b 0
:check_setup
".venv\Scripts\python.exe" -c "import media_studio, numpy, PIL, tkinter; print('Setup ready. Open run.bat to launch Media Compression Studio.')"
exit /b %errorlevel%
:missing_python
echo Install Python 3.11 from python.org with PATH enabled, then open run.bat again.
pause
exit /b 2
:setup_failed
echo Setup failed. Check Python and your internet connection, then try again.
pause
exit /b 2
:launch_failed
echo The app could not open. See the error above and the README setup steps.
pause
exit /b 2
