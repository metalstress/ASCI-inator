param([string]$Python = "py")
Set-ExecutionPolicy -Scope Process Bypass -Force
& $Python -m venv .venv
$venvPy = ".\.venv\Scripts\python.exe"
$venvPip = ".\.venv\Scripts\pip.exe"
& $venvPip install --no-cache-dir -r requirements.txt
& $venvPy ascii_wave_animator.py
