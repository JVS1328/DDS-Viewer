@echo off
REM Build a standalone DDSViewer.exe into dist\ . Run from this folder.
cd /d "%~dp0"
py -3.13 -m PyInstaller --noconsole --onefile --name DDSViewer ^
    --collect-submodules PyQt6 run_viewer.pyw
echo.
echo Done. Executable: "%~dp0dist\DDSViewer.exe"
pause
