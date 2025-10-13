@echo off
set NAME=ASCII-Animator-BW
py -m venv .venv || goto :err
.\.venv\Scripts\pip.exe install --no-cache-dir -r requirements.txt || goto :err
.\.venv\Scripts\pip.exe install --no-cache-dir pyinstaller || goto :err
.\.venv\Scripts\python.exe -m PyInstaller --onefile --windowed --name "%NAME%" --icon app.ico ascii_wave_animator.py || goto :err
echo Portable EXE ready: dist\%NAME%.exe
exit /b 0
:err
echo Build failed.
pause
