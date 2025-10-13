param([string]$Python = "py", [string]$Name = "ASCII-Animator-BW")
Set-ExecutionPolicy -Scope Process Bypass -Force
& $Python -m venv .venv
$venvPy = ".\.venv\Scripts\python.exe"
$venvPip = ".\.venv\Scripts\pip.exe"
& $venvPip install --no-cache-dir -r requirements.txt
& $venvPip install --no-cache-dir pyinstaller
& $venvPy -m PyInstaller --onefile --windowed --name $Name --icon app.ico ascii_wave_animator.py
Write-Host "Portable EXE ready: dist\$Name.exe"
