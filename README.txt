Ниже короткая инструкция (PowerShell, Windows). У тебя settings.py теперь требует переменные окружения, поэтому их нужно задать перед запуском.

1) Backend (Django)

# из корня проекта
cd C:\Users\mkv\Documents\Projects\TechTracker

# активировать venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\TechTracker_env\Scripts\Activate.ps1

# переменные окружения (подставь свои значения)
$env:DJANGO_SECRET_KEY='dev-local-key'
$env:DJANGO_DEBUG='True'
$env:DJANGO_ALLOWED_HOSTS='localhost,127.0.0.1'
$env:DB_NAME='techtracker_db'
$env:DB_USER='zulixo'
$env:DB_PASSWORD='q2w1e4r3'
$env:DB_HOST='localhost'
$env:DB_PORT='5432'

# если зависимости ещё не ставил
pip install -r requirements.txt

# миграции
python manage.py migrate

# (опционально) админ
python manage.py createsuperuser

# запуск
python manage.py runserver 0.0.0.0:8000
2) Frontend (Vue)

# новый терминал
cd C:\Users\mkv\Documents\Projects\TechTracker\techtracker_vue

# если зависимости ещё не ставил
npm install

# запуск dev-сервера
npm run serve
3) Агент (опционально)

Проверь config.ini или config.ini (где он лежит в твоей сборке), чтобы ApiUrl был вида http://<server>:8000/api/ и Token валиден.
Запуск:
cd C:\Users\mkv\Documents\Projects\TechTracker\agents
python agent_server.py
Если хочешь, могу сделать скрипты run-backend.ps1 и run-frontend.ps1, чтобы запуск был одной командой.

Новые параметры агента:
- RetentionDays (по умолчанию 365) — срок хранения сырых метрик
- VmSyncInterval — частота обновления статуса Hyper-V ВМ
- SmartctlPath — путь до smartctl.exe (если нужен SMART)

SMART (Windows):
1) Установи smartmontools
2) Добавь путь к smartctl.exe в PATH или пропиши SmartctlPath в config.ini

Очистка сырых метрик (сервер):
python manage.py purge_raw_metrics --default-days 365
