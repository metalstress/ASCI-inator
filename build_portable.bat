@echo off
echo === Building ASCI-inator portable version ===
echo.

REM Проверяем наличие Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [Ошибка] Python не найден. Установи Python 3.10+ и добавь его в PATH.
    pause
    exit /b
)

REM Создаём виртуальное окружение, если нет
if not exist .venv (
    echo Создаю виртуальное окружение...
    python -m venv .venv
)

REM Активируем окружение
call .venv\Scripts\activate

REM Устанавливаем зависимости
echo Устанавливаю зависимости...
if exist requirements.txt (
    pip install -r requirements.txt
) else (
    echo [Предупреждение] requirements.txt не найден, ставлю основные пакеты.
    pip install PySide6 Pillow sounddevice numpy
)

REM Устанавливаем PyInstaller (если не установлен)
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo Устанавливаю PyInstaller...
    pip install pyinstaller
)

REM Собираем exe через spec-файл
echo Собираю exe...
pyinstaller ASCII-Animator-BW.spec

REM Проверяем результат
if exist dist\ASCII-Animator-BW\ASCII-Animator-BW.exe (
    echo.
    echo ✅ Сборка успешно завершена!
    echo Файл: dist\ASCII-Animator-BW\ASCII-Animator-BW.exe
) else (
    echo.
    echo ⚠️ Ошибка: exe не найден. Проверь вывод PyInstaller.
)

pause
