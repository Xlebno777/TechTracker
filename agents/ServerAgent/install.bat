@echo off
echo Installing TechTracker Agent...

:: 1. Настройка путей
set INSTALL_DIR="C:\Program Files\TechTracker\ServerAgent"
set EXE_SOURCE="TechTrackerAgent.exe"
set CONFIG_SOURCE="config.ini"
set EXE_DEST="%INSTALL_DIR%\TechTrackerAgent.exe"

:: 2. Проверка прав администратора
net session >nul 2>&1
if %errorLevel% == 0 (
    echo Admin rights confirmed.
) else (
    echo Please run as Administrator!
    pause
    exit
)

:: 3. Создание папки
if not exist %INSTALL_DIR% mkdir %INSTALL_DIR%

:: 4. Копирование файлов
copy /Y %EXE_SOURCE% %INSTALL_DIR%
copy /Y %CONFIG_SOURCE% %INSTALL_DIR%

:: 5. Создание задачи в планировщике (Запуск при старте системы, скрыто, от имени SYSTEM)
schtasks /create /tn "TechTracker Server Agent" /tr "'%INSTALL_DIR%\TechTrackerAgent.exe'" /sc onstart /ru System /f

:: 6. Запуск задачи прямо сейчас
schtasks /run /tn "TechTracker Server Agent"

echo.
echo Installation Complete! Agent is running.
echo Logs are located at: %INSTALL_DIR%\agent.log
pause
