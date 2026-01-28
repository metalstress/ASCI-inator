@echo off
setlocal
pushd %~dp0
if not exist .venv (
  python -m venv .venv
)
call .venv\Scripts\activate.bat
python -u ascii_wave_animator.py 1>debug_out.txt 2>debug_err.txt
set EC=%errorlevel%
echo Exit code: %EC%>> debug_out.txt
echo Exit code: %EC%>> debug_err.txt
start notepad debug_err.txt
popd
endlocal
