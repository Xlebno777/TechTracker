# План автоматизации установки TechTracker на Windows Server

Цель: привести установку TechTracker к максимально «однокнопочному» сценарию, где администратор запускает один PowerShell-скрипт от имени администратора, отвечает на минимальный набор вопросов, а система сама ставит зависимости, настраивает БД, получает код проекта, создает `.env.local`, собирает frontend/backend и регистрирует WinSW-сервисы.

Важно: на основной Windows Server не устанавливается удаленный LSTM-сервис. На этом сервере устанавливается только основной контур TechTracker: backend, frontend и worker опроса удаленных LSTM-задач. Сам LSTM-сервис остается отдельным компонентом для другого компьютера. В будущем GUI должен уметь формировать отдельные установочные пакеты для разных устройств: основной сервер, LSTM-ПК, агенты сбора метрик и другие сервисы.

## 1. Целевой пользовательский сценарий

Итоговая команда на чистом Windows Server:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deployment\windows\bootstrap_techtracker.ps1
```

Скрипт должен:

1. Проверить права администратора.
2. Проверить версию Windows Server и PowerShell.
3. Установить зависимости:
   - Git;
   - Python 3.11/3.12;
   - Node.js LTS;
   - PostgreSQL;
   - WinSW.
4. Скачать или обновить проект из GitHub.
5. Спросить базовые параметры:
   - путь установки;
   - IP/домен сервера;
   - порт frontend;
   - порт backend;
   - имя администратора системы;
   - email администратора системы;
   - пароль администратора системы;
   - имя пользователя PostgreSQL;
   - пароль PostgreSQL;
   - включать ли обновления из UI.
6. Создать `.env.local`.
7. Создать БД и пользователя PostgreSQL.
8. Создать Python virtualenv.
9. Установить backend-зависимости.
10. Установить frontend-зависимости и собрать Vue.
11. Выполнить миграции Django.
12. Создать администратора Django по данным, введенным пользователем.
13. Установить WinSW-сервисы:
    - `TechTrackerBackend`;
    - `TechTrackerFrontend`;
    - `TechTrackerLSTMWorker`.
14. Запустить сервисы.
15. Проверить health:
    - backend `/api/`;
    - frontend `http://server:8080`;
    - подключение к удаленному LSTM `/health`, если задан URL.
16. Вывести итоговую сводку:
    - URL интерфейса;
    - путь установки;
    - имена сервисов;
    - где лежат логи;
    - как обновлять систему.

## 2. Структура будущих скриптов

Добавить папку:

```text
deployment/windows/installer/
```

Файлы:

```text
bootstrap_techtracker.ps1
install_prerequisites.ps1
install_postgresql.ps1
configure_env.ps1
configure_database.ps1
install_project.ps1
install_services.ps1
healthcheck.ps1
lib/common.ps1
```

Назначение:

- `bootstrap_techtracker.ps1` — главный однокнопочный сценарий.
- `install_prerequisites.ps1` — установка Git, Python, Node.js, PostgreSQL.
- `install_postgresql.ps1` — отдельная логика PostgreSQL, если пакетный менеджер не справился.
- `configure_env.ps1` — интерактивная генерация `.env.local`.
- `configure_database.ps1` — создание пользователя и БД.
- `install_project.ps1` — clone/pull проекта, venv, pip, npm, build, migrate.
- `install_services.ps1` — вызов уже существующего `winsw_services.ps1`.
- `healthcheck.ps1` — проверка итогового запуска.
- `lib/common.ps1` — общие функции логирования, проверки прав, скачивания, генерации секретов.

Отдельно в будущем:

```text
deployment/windows/package_generators/
```

Назначение:

- генератор установщика основного сервера;
- генератор установщика LSTM-ПК;
- генератор установщика агента сбора метрик;
- генератор установщика дополнительных сервисов.

Эти пакеты должны формироваться из GUI, чтобы пользователь выбирал тип устройства и получал готовый архив/инсталлятор с нужной конфигурацией.

## 3. Установка зависимостей

### 3.1 Основной способ

Использовать `winget`, если доступен:

```powershell
winget install --id Git.Git -e
winget install --id Python.Python.3.12 -e
winget install --id OpenJS.NodeJS.LTS -e
winget install --id PostgreSQL.PostgreSQL -e
```

### 3.2 Fallback

Если `winget` недоступен:

1. Предложить установить `winget`.
2. Либо скачать MSI/EXE напрямую:
   - Git for Windows;
   - Python;
   - Node.js LTS;
   - PostgreSQL installer.

На первом этапе лучше реализовать только `winget` + понятную ошибку, потому что прямые silent-installers PostgreSQL требуют больше тестирования.

### 3.3 Проверки после установки

Команды:

```powershell
git --version
python --version
node --version
npm --version
psql --version
```

Если команда не найдена, обновить `PATH` текущей PowerShell-сессии или попросить перезапустить терминал.

## 4. Доступ к репозиторию

Поддержать два режима.

### 4.1 Public HTTPS

Так как текущий репозиторий публичный:

```powershell
git clone https://github.com/Xlebno777/TechTracker.git C:\TechTracker
```

Это самый простой режим для первой установки.

### 4.2 SSH или PAT для приватного режима

На будущее:

- SSH key:
  - сгенерировать ключ;
  - показать публичный ключ;
  - пользователь добавляет его в GitHub;
  - скрипт проверяет `ssh -T git@github.com`.
- GitHub PAT:
  - пользователь вводит token;
  - скрипт использует HTTPS clone;
  - token не сохраняется в `.env.local`.

Для первой реализации использовать public HTTPS.

## 5. Настройки при установке

Скрипт должен спрашивать:

```text
Путь установки: C:\TechTracker
GitHub repo URL: https://github.com/Xlebno777/TechTracker.git
Git ref/tag: main или v0.1.0
Server host/IP для ALLOWED_HOSTS: localhost,127.0.0.1,<server-ip>
Backend host: 0.0.0.0
Backend port: 8000
Frontend port: 8080
PostgreSQL DB name: techtracker_db
PostgreSQL user: techtracker_admin
PostgreSQL password: ввод скрытым вводом
TechTracker admin username: ввод пользователя
TechTracker admin email: ввод пользователя
TechTracker admin password: ввод скрытым вводом
LSTM API URL и token не запрашиваются при первой установке. Они настраиваются позже в GUI: `Настройки -> Интеграции`.
Включить обновления из UI: yes/no
```

Секреты:

- `DJANGO_SECRET_KEY` генерировать автоматически.
- `DB_USER` спрашивать у пользователя с дефолтом `techtracker_admin`.
- `DB_PASSWORD` всегда спрашивать скрытым вводом.
- `TECHTRACKER_ADMIN_USERNAME` спрашивать у пользователя.
- `TECHTRACKER_ADMIN_EMAIL` спрашивать у пользователя.
- `TECHTRACKER_ADMIN_PASSWORD` всегда спрашивать скрытым вводом.
- `LSTM_REMOTE_API_TOKEN` не спрашивать на установке; token генерируется в GUI на странице интеграций.
- Если token генерируется при установке основного сервера, скрипт должен вывести его один раз и явно подписать: «этот token нужно вставить в конфигурацию LSTM-ПК».

## 6. Генерация `.env.local`

Итоговый `.env.local` создается из `deployment/windows/.env.windows.example`, но без ручного редактирования.

Минимальные значения:

```env
DJANGO_SECRET_KEY=<generated>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,<server-ip>

DB_NAME=techtracker_db
DB_USER=<db-user>
DB_PASSWORD=<secret>
DB_HOST=localhost
DB_PORT=5432

LSTM_REMOTE_API_BASE_URL=http://<lstm-ip>:8099
LSTM_REMOTE_API_TOKEN=
LSTM_REMOTE_TIMEOUT_SEC=60
LSTM_REMOTE_VERIFY_SSL=0

APP_VERSION=<VERSION>
APP_RELEASE_CHANNEL=single
APP_RELEASE_MANIFEST_URL=C:\TechTracker\deployment\windows\release_manifest.json
APP_UPDATE_ENABLED=0
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
```

Администратор TechTracker не обязан храниться в `.env.local`. Данные администратора используются только в момент установки для создания пользователя в БД. Пароль администратора не должен сохраняться в открытом виде в установочных логах.

## 7. PostgreSQL

### 7.1 Если PostgreSQL уже установлен

Скрипт спрашивает:

- host;
- port;
- superuser;
- superuser password.

Затем выполняет:

```sql
CREATE USER techtracker_admin WITH PASSWORD '<password>';
CREATE DATABASE techtracker_db OWNER techtracker_admin;
GRANT ALL PRIVILEGES ON DATABASE techtracker_db TO techtracker_admin;
```

### 7.2 Если PostgreSQL устанавливается впервые

На первом этапе:

- установить PostgreSQL через `winget`;
- попросить пользователя задать пароль суперпользователя при установке;
- после установки выполнить создание БД через `psql`.

На втором этапе:

- добавить полностью silent install PostgreSQL;
- хранить временный superuser password только в памяти процесса.

## 8. Установка проекта

Логика:

```powershell
git clone <repo> <AppRoot>
cd <AppRoot>
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate --noinput
.\.venv\Scripts\python.exe manage.py collectstatic --noinput
cd techtracker_vue
npm ci
npm run build
```

После этого:

```powershell
.\deployment\windows\winsw_services.ps1 -Action Install -AppRoot C:\TechTracker -StartAfterInstall
```

## 9. Создание администратора системы

Варианты:

Скрипт всегда спрашивает:

- username;
- email;
- password.

Затем вызывает отдельную management command:

```powershell
python manage.py ensure_admin_user --username admin --email admin@example.local
```

Пароль передавать через stdin или безопасную временную env-переменную.

Если пользователь с таким username уже существует:

- обновить email, если пользователь подтвердил;
- предложить сбросить пароль;
- не удалять существующего пользователя автоматически.

## 10. Проверка первого запуска

Проверки:

```powershell
Get-Service TechTrackerBackend
Get-Service TechTrackerFrontend
Get-Service TechTrackerLSTMWorker
Invoke-WebRequest http://127.0.0.1:8000/api/
Invoke-WebRequest http://127.0.0.1:8080/
```

Если LSTM URL задан:

```powershell
Invoke-WebRequest http://<lstm-ip>:8099/health -Headers @{"X-API-Key"="<token>"}
```

## 11. Обновления после установки

Цель: обновления должны устанавливаться из web-интерфейса настроек по одному клику.

После первого успешного запуска:

1. `APP_UPDATE_ENABLED` по умолчанию можно оставить `0` для первой версии установщика.
2. В интерфейсе показать, что обновления выключены, и объяснить, что нужно проверить update-скрипт.
3. После проверки пользователь включает:

```env
APP_UPDATE_ENABLED=1
```

4. После включения обновления выполняются через GUI:
   - пользователь открывает `Настройки -> Интеграции`;
   - нажимает «Проверить обновления»;
   - видит новую версию, список изменений и статус готовности сервера;
   - нажимает «Запустить обновление»;
   - backend создает update-job;
   - backend запускает `update_techtracker.ps1`;
   - скрипт делает backup, обновляет код, зависимости, миграции, frontend build и перезапускает WinSW-сервисы;
   - UI показывает статус задания и итоговый лог.

5. В будущем добавить кнопку в UI:
   - «Проверить готовность обновлений»;
   - она проверяет:
     - доступ к git;
     - наличие WinSW services;
     - наличие прав на запись в папку проекта;
     - наличие `.env.local`;
     - возможность остановить/запустить сервисы.

## 12. Безопасность

Обязательные правила:

1. `.env.local` никогда не коммитить.
2. В release zip не включать `.env.local`.
3. GitHub token/PAT не хранить в `.env.local`.
4. `DJANGO_SECRET_KEY`, `DB_PASSWORD`, `LSTM_REMOTE_API_TOKEN` генерировать/спрашивать на установке.
5. Перед каждым обновлением сохранять:
   - текущий git commit;
   - `.env.local`;
   - при возможности dump БД.
6. Не включать `APP_UPDATE_ENABLED=1` автоматически без явного подтверждения пользователя.

## 13. Логирование

Все установочные шаги писать в:

```text
C:\TechTracker\logs\install_YYYYMMDD_HHMMSS.log
```

WinSW логи:

```text
C:\TechTracker\logs\winsw
```

Обновления:

```text
C:\TechTracker\logs\update_*.log
```

## 14. Будущая генерация установщиков из GUI

В будущем в web-интерфейсе должен появиться раздел:

```text
Настройки -> Установочные пакеты
```

Пользователь выбирает тип пакета:

- основной сервер TechTracker;
- LSTM-ПК;
- агент сбора метрик;
- агент печати;
- другой вспомогательный сервис.

GUI должен:

1. Спросить параметры выбранного устройства.
2. Сгенерировать token/секреты, если нужно.
3. Сформировать `.env`/config только для выбранного сервиса.
4. Собрать zip-пакет или инсталлятор.
5. Показать инструкцию: куда перенести и какую команду запустить.

Для LSTM-ПК это означает отдельный пакет, который содержит:

- `lstm_remote_service`;
- `.env` с `LSTM_API_TOKEN`;
- настройки GPU/CPU;
- скрипт установки зависимостей;
- скрипт запуска сервиса;
- опционально WinSW/systemd-инструкцию, в зависимости от ОС LSTM-ПК.

Основной Windows Server не должен устанавливать LSTM-сервис автоматически.

## 15. Этапы реализации

### Этап 1. План и безопасный bootstrap

Сделать:

- `deployment/windows/installer/bootstrap_techtracker.ps1`;
- проверку администратора;
- интерактивный сбор параметров;
- генерацию `.env.local`;
- вызов текущего `install_windows_server.ps1`.
- создание администратора Django по введенным данным.

Не делать пока silent install PostgreSQL.

### Этап 2. Автоустановка Git/Python/Node через winget

Сделать:

- проверку `winget`;
- установку Git;
- установку Python;
- установку Node.js;
- проверку команд после установки.

### Этап 3. PostgreSQL semi-auto

Сделать:

- проверку наличия `psql`;
- если PostgreSQL есть — создать БД и пользователя;
- если PostgreSQL нет — установить через `winget` и попросить пользователя завершить wizard, затем продолжить.

### Этап 4. Репозиторий и обновления

Сделать:

- clone/pull проекта;
- режим `RepoUrl`;
- режим `GitRef`;
- запись `APP_RELEASE_MANIFEST_URL`;
- проверку `git fetch`.

### Этап 5. Полная сборка и WinSW

Сделать:

- venv;
- pip;
- npm ci;
- npm run build;
- migrate;
- collectstatic;
- установка WinSW services;
- старт сервисов.

### Этап 6. Healthcheck и итоговый отчет

Сделать:

- backend check;
- frontend check;
- LSTM check;
- итоговый отчет в консоль и файл.

### Этап 7. Обновление из GUI одним кликом

Сделать:

- расширить экран настроек обновлений;
- показывать готовность сервера к обновлению;
- запускать update-job;
- показывать live/polling статус;
- показывать последние строки лога;
- после обновления предлагать открыть страницу заново.

### Этап 8. Генератор установщиков из GUI

Сделать:

- backend endpoint генерации пакета;
- UI выбора типа пакета;
- шаблоны `.env` под основной сервер, LSTM-ПК и агенты;
- скачивание готового zip.

### Этап 9. Release package v0.1.1

После реализации:

- обновить `VERSION`;
- собрать `TechTracker-v0.1.1-windows-server.zip`;
- приложить к GitHub Release;
- обновить `release_manifest.json`.

## 16. Критерий готовности

Сценарий считается готовым, если на чистом Windows Server после одной команды:

1. Установлены Git/Python/Node/PostgreSQL или выдана понятная инструкция по недостающему компоненту.
2. Проект скачан в `C:\TechTracker`.
3. `.env.local` создан без ручного редактирования.
4. БД создана.
5. Администратор TechTracker создан по данным пользователя.
6. Backend зависимости установлены.
7. Frontend собран.
8. Миграции применены.
9. WinSW services установлены.
10. Сервисы запущены.
11. UI открывается по `http://server:8080`.
12. Backend отвечает.
13. В UI видно состояние версии и обновлений.
14. Обновление можно запустить из web-интерфейса настроек одним кликом после включения `APP_UPDATE_ENABLED=1`.
15. LSTM-сервис не установлен на основной сервер, но подключение к удаленному LSTM можно проверить через healthcheck.
