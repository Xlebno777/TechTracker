@echo off
echo Uninstalling TechTracker Agent...

:: 1. Проверка прав
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Please run as Administrator!
    pause
    exit
)

:: 2. Остановка и удаление задачи
schtasks /end /tn "TechTrackerAgent" >nul 2>&1
schtasks /delete /tn "TechTrackerAgent" /f

:: 3. Остановка процесса (на всякий случай)
taskkill /F /IM TechTrackerAgent.exe >nul 2>&1

:: 4. Удаление файлов (ждем секунду, чтобы процесс точно умер)
timeout /t 2 /nobreak >nul
rmdir /s /q "C:\Program Files\TechTrackerAgent"

echo.
echo Uninstallation Complete.
pause