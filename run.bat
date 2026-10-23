@echo off
setlocal
cd /d "%~dp0"
python -c "import media_studio.gui" >nul 2>nul
if errorlevel 1 (
 echo Activate your existing Python or Conda environment with the project dependencies. See README.md.
 exit /b 1
)
if "%~1"=="--check" (
 echo Existing environment imports and desktop dependencies are ready.
 exit /b 0
)
python -m media_studio
