# TechTracker на Windows Server

Документ описывает практическую схему установки и обновления TechTracker на Windows Server без разделения на dev/prod ветки.

## Рекомендуемая схема

- Backend: Django + PostgreSQL, запущен как Windows service.
- Frontend: собранный Vue build, отдается встроенным Node static-server через Windows service.
- LSTM: остается на отдельном ПК и подключается по VPN/Tailscale через backend.
- LSTM worker: отдельный Windows service на основном сервере, который опрашивает очередь удаленных LSTM-задач.
- Обновления: пользователь нажимает кнопку в UI, backend создает задание обновления, затем запускает `deployment/windows/update_techtracker.ps1`.

## Сервисы WinSW

Добавлены три сервиса:

- `TechTrackerBackend` — Django API через Waitress, порт по умолчанию `8000`.
- `TechTrackerFrontend` — Vue `dist` + proxy `/api/` на backend, порт по умолчанию `8080`.
- `TechTrackerLSTMWorker` — постоянный worker для polling удаленного LSTM API.

Установка одной командой от имени администратора:

```powershell
cd C:\TechTracker
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deployment\windows\install_winsw_services.ps1 -AppRoot C:\TechTracker -Start
```

Перезапуск всех сервисов одной командой:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deployment\windows\restart_winsw_services.ps1 -AppRoot C:\TechTracker
```

Статус:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deployment\windows\winsw_services.ps1 -Action Status -AppRoot C:\TechTracker
```

Удаление сервисов:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deployment\windows\uninstall_winsw_services.ps1 -AppRoot C:\TechTracker
```

Скрипт сам скачивает `WinSW-x64.exe` в `deployment\windows\bin`, копирует его под каждый сервис и создает XML-конфиги в `deployment\windows\services`.
Команды установки/удаления сервисов запускайте из PowerShell от имени администратора. Если сервер без доступа в интернет, скачайте `WinSW-x64.exe` заранее и положите его в `deployment\windows\bin\WinSW-x64.exe`.

## Переменные окружения для обновлений

Добавьте в `.env.local` на сервере:

```env
APP_VERSION=0.1.0
APP_RELEASE_CHANNEL=single
APP_RELEASE_MANIFEST_URL=https://api.github.com/repos/Xlebno777/TechTracker/releases/latest
APP_UPDATE_ENABLED=1
APP_UPDATE_SCRIPT=C:\TechTracker\deployment\windows\update_techtracker.ps1
APP_UPDATE_WORKDIR=C:\TechTracker
APP_UPDATE_TIMEOUT_SEC=3600
TECHTRACKER_BACKEND_SERVICE=TechTrackerBackend
TECHTRACKER_FRONTEND_SERVICE=TechTrackerFrontend
TECHTRACKER_LSTM_WORKER_SERVICE=TechTrackerLSTMWorker

TECHTRACKER_BACKEND_HOST=0.0.0.0
TECHTRACKER_BACKEND_PORT=8000
TECHTRACKER_FRONTEND_PORT=8080
TECHTRACKER_BACKEND_URL=http://127.0.0.1:8000
TECHTRACKER_LSTM_WORKER_LIMIT=20
TECHTRACKER_LSTM_WORKER_POLL_INTERVAL_SEC=10
TECHTRACKER_LSTM_WORKER_IDLE_SLEEP_SEC=15
```

`APP_UPDATE_ENABLED=1` включайте только после того, как вручную проверите скрипт обновления на сервере.

## Manifest релиза

Минимальный manifest:

```json
{
  "version": "0.1.1",
  "channel": "single",
  "release_date": "2026-05-19",
  "git_ref": "v0.1.1",
  "notes": [
    "Краткое описание изменения."
  ]
}
```

`git_ref` может быть тегом, веткой или commit hash. Так как проект ведется одним пользователем без dev/prod веток, самый безопасный вариант — выпускать git tag на каждую рабочую версию.

## Ручная проверка скрипта

Перед включением кнопки в интерфейсе выполните на Windows Server:

```powershell
cd C:\TechTracker
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deployment\windows\update_techtracker.ps1 -AppRoot C:\TechTracker -GitRef v0.1.1 -TargetVersion 0.1.1
```

Если команда проходит без ошибок, можно включать `APP_UPDATE_ENABLED=1`.

## Как выпускать новую версию

1. Обновить `VERSION`.
2. Сделать commit.
3. Создать tag, например `v0.1.1`.
4. Обновить release manifest на сервере или в доступном URL.
5. На странице `Настройки -> Интеграции` нажать `Проверить обновления`.
6. Если версия найдена, нажать `Запустить обновление`.

## Что делает скрипт обновления

- Создает папку `backups/before_update_*`.
- Сохраняет `.env.local` и текущий git commit.
- Останавливает сервисы, если заданы `TECHTRACKER_BACKEND_SERVICE` и `TECHTRACKER_FRONTEND_SERVICE`.
- Останавливает `TechTrackerBackend`, `TechTrackerFrontend`, `TechTrackerLSTMWorker`.
- Выполняет `git fetch`.
- Переключается на `git_ref` из manifest или делает `git pull --ff-only`.
- Обновляет Python-зависимости.
- Выполняет `python manage.py migrate --noinput`.
- Выполняет `npm ci` и `npm run build` для Vue.
- Запускает сервисы обратно.

## Полная первая установка

Рекомендуемый новый сценарий:

```powershell
cd C:\TechTracker
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deployment\windows\bootstrap_techtracker.ps1 -AppRoot C:\TechTracker
```

Bootstrap-установщик интерактивно спросит и перед каждым блоком объяснит, что именно задаётся:

- параметры сервера и портов;
- пользователя и пароль PostgreSQL;
- администратора TechTracker;
- параметры LSTM не запрашиваются при установке и задаются позже в `Настройки -> Интеграции`;
- включать ли обновления из web-интерфейса.

Старый низкоуровневый сценарий, если `.env.local` уже создан вручную:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deployment\windows\install_windows_server.ps1 -AppRoot C:\TechTracker -InstallServices -StartServices
```

Bootstrap-установщик сам проверяет и устанавливает зависимости. На Windows Server `winget` часто отсутствует; в этом случае установщик скачивает official silent-инсталляторы напрямую и ставит Git for Windows, Python 3.12, Node.js LTS и PostgreSQL 17 без Chocolatey. Пароли PostgreSQL и администратора TechTracker запрашиваются во время установки.

## Ограничения MVP

- Rollback автоматизирован частично: сохраняется commit до обновления, но откат лучше запускать вручную.
- Для production-уровня желательно добавить подпись manifest и проверку checksum артефактов.
- Если frontend отдается через IIS/nginx, убедитесь, что его директория указывает на актуальный `techtracker_vue/dist`.

## Настройка LSTM после установки

Установщик не спрашивает LSTM token и не генерирует его. После первого входа откройте `Настройки -> Интеграции`, задайте IP/порт LSTM-ПК, нажмите `Сгенерировать токен`, скопируйте его в `LSTM_API_TOKEN` на LSTM-ПК и сохраните настройки.
