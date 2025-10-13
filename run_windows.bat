@echo off
setlocal
set VENV=.venv
where py >nul 2>nul || (echo Python launcher 'py' not found.& pause & exit /b 1)
if not exist %VENV% ( py -m venv %VENV% || goto :err )
set VENV_PY=%VENV%\Scripts\python.exe
set VENV_PIP=%VENV%\Scripts\pip.exe
%VENV_PIP% install --no-cache-dir -r requirements.txt || goto :err
%VENV_PY% ascii_wave_animator.py
exit /b 0
:err
echo Ошибка установки. Если папка в OneDrive — поставь синхронизацию на паузу или перенеси проект.
pause
