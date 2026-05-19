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

Папка агента теперь разделена:
- agents\\ServerAgent (серверный агент метрик/Hyper-V)
- agents\\PrintAgent (клиент печати)
- agents\\ServerPrinterAgent (синхронизация принтеров)

Проверь config.ini или config.ini (где он лежит в твоей сборке), чтобы ApiUrl был вида http://<server>:8000/api/ и Token валиден.
Запуск:
cd C:\Users\mkv\Documents\Projects\TechTracker\agents\ServerAgent
python agent_server.py

Синхронизация принтеров (отдельный агент):
cd C:\Users\mkv\Documents\Projects\TechTracker\agents\ServerPrinterAgent
python printer_agent.py
Installer:
- Папка: agents\\ServerPrinterAgent\\installer
- Файл: server_printer_agent_installer.iss
Если хочешь, могу сделать скрипты run-backend.ps1 и run-frontend.ps1, чтобы запуск был одной командой.

Новые параметры агента:
- RetentionDays (по умолчанию 365) — срок хранения сырых метрик
- VmSyncInterval — частота обновления статуса Hyper-V ВМ
- StorcliPath — путь до storcli64.exe или папки (например C:\Soft\storcli\Windows)

Очистка сырых метрик (сервер):
python manage.py purge_raw_metrics --default-days 365

Вычисление метрик уровня 2:
python manage.py compute_derived_metrics

Планировщик (Windows, раз в час):
1) install-compute-metrics-task.ps1
2) при необходимости удалить: uninstall-compute-metrics-task.ps1

ServerAgent installer:
- Папка: agents\\ServerAgent\\installer
- Скрипт удаления на ПК: {app}\\remove_agent.ps1 (удаляет задачу автозапуска и папку)

Встроенный auto-job для сетевого probe (без внешнего планировщика):
- Запускается автоматически внутри backend-процесса Django.
- Использует PostgreSQL advisory lock, чтобы не было дублей проверки при нескольких процессах.
- Уважает interval_sec каждого NetworkPath.
- Настройки через переменные окружения:
  - NETWORK_PROBE_AUTOSTART=1
  - NETWORK_PROBE_AUTO_INTERVAL_SEC=60
  - NETWORK_PROBE_LOCK_KEY=4829137

4) Рекомендованные библиотеки для прогноза (актуально)

Для локального preprocessing + SARIMA baseline в backend добавлены:
- numpy==2.3.4 — численные операции и массивы.
- pandas==2.3.3 — временные ряды, ресемплинг и подготовка данных.
- statsmodels==0.14.5 — SARIMA/STL и доверительные интервалы прогноза.

Установка/обновление:
pip install -r requirements.txt

5) Интеграция удаленного LSTM API (через backend)

Переменные окружения backend:
- LSTM_REMOTE_API_BASE_URL (пример: http://100.88.10.24:8099)
- LSTM_REMOTE_API_TOKEN (тот же токен, что на LSTM сервисе)
- LSTM_REMOTE_TIMEOUT_SEC (по умолчанию 20)
- LSTM_REMOTE_VERIFY_SSL (0/false для HTTP внутри VPN, 1/true для HTTPS)

Дополнительно backend теперь умеет задавать дефолты модели для remote LSTM без правки кода:
- LSTM_REMOTE_DEFAULT_EPOCHS (default 60)
- LSTM_REMOTE_DEFAULT_LOOKBACK (default 336, но backend автоматически ограничивает его доступной историей)
- LSTM_REMOTE_DEFAULT_HIDDEN_SIZE (default 96)
- LSTM_REMOTE_DEFAULT_LR (default 0.001)
- LSTM_REMOTE_DEFAULT_DROPOUT (default 0.15)
- LSTM_REMOTE_DEFAULT_WEIGHT_DECAY (default 1e-5)
- LSTM_REMOTE_DEFAULT_BATCH_SIZE (default 64)
- LSTM_REMOTE_DEFAULT_USE_CALENDAR (default true)
- LSTM_REMOTE_DEFAULT_USE_SEASONAL_RESIDUAL (default true)
- LSTM_REMOTE_DEFAULT_SEASONALITY_MODE (default rolling_profile)
- LSTM_REMOTE_DEFAULT_SEASONALITY_WINDOW_DAYS (default 14)
- LSTM_REMOTE_DEFAULT_LOSS_KIND (default quantile)
- LSTM_REMOTE_DEFAULT_OUTPUT_MODE (default direct_multi_horizon)
- LSTM_REMOTE_DEFAULT_TRAIN_MODE (default fit_on_request)

Смысл обновлённой модели:
- backend передаёт в LSTM не только `alpha`, а полный профиль модели;
- удалённый сервис считает локальную сезонность по недавнему окну, а не по всей истории;
- LSTM строит всю траекторию горизонта сразу, а не раскатывает прогноз шаг за шагом от собственного же прогноза;
- интервалы `p10/p50/p90` можно обучать напрямую в quantile-режиме.

Пример (PowerShell):
$env:LSTM_REMOTE_API_BASE_URL='http://100.88.10.24:8099'
$env:LSTM_REMOTE_API_TOKEN='your-token'
$env:LSTM_REMOTE_TIMEOUT_SEC='20'
$env:LSTM_REMOTE_VERIFY_SSL='0'

Проверка с backend:
python manage.py run_forecast_lstm_remote --serial HOST-001 --no-wait --max-retries 5
python manage.py poll_forecast_lstm_remote --run-id 123 --limit 20 --poll-interval-sec 10

Оркестр SARIMA + LSTM:
- Запускается из экрана прогнозов в едином блоке "Запуск прогнозирования" (режим "Полный прогноз").
- Backend сначала считает локальный SARIMA baseline, затем ставит удаленный LSTM в очередь.
- После завершения LSTM backend собирает итоговый `ensemble` и сохраняет его как отдельный ForecastRun/ForecastPoint/StateEstimate.
- В UI используется realtime NDJSON stream (`GET /api/forecast-runs/workflow_stream/`): пошаговый статус этапов и итоговая сводка без ручного curl.
- Для ручного API-вызова используются:
  - POST /api/forecast-runs/run_orchestrated/
  - POST /api/forecast-runs/poll_orchestrated/
  - GET /api/forecast-runs/orchestrator_defaults/

Калибровка оркестра (без правки кода):
- В `run_orchestrated` можно передать `ensemble_beta`, `ensemble_sarima_weight`, `ensemble_lstm_weight`.
- Дефолты можно задавать через env:
  - FORECAST_ENSEMBLE_BETA (default 0.5)
  - FORECAST_ENSEMBLE_DEFAULT_SARIMA_WEIGHT (default 0.5)
  - FORECAST_ENSEMBLE_DEFAULT_LSTM_WEIGHT (default 0.5)

6) Оценка риска отказа (новая вкладка Мониторинг -> Оценка риска)

Что реализовано в backend:
- Вейбулл применяется только к изнашиваемым метрикам (wear/TBW каналы).
- Для остальных метрик считается риск превышения порога (по p90 из прогноза).
- Поверх этого считается Марковская динамика состояний S0/S1/S2 (S2 поглощающее).
- Итоговый риск комбинирует риск метрик и прогнозную вероятность S2.

API:
- GET `/api/risk-assessment/defaults/` (admin)
- POST `/api/risk-assessment/evaluate/` (admin)

Пример запроса:
```json
{
  "serial": "HOST-001",
  "horizons": ["24h", "7d", "30d"],
  "preferred_model_kind": "auto",
  "personalized_thresholds": true,
  "threshold_lookback_days": 60,
  "markov_lookback_days": 120,
  "markov_smoothing": 1.0,
  "type_blend": 0.35,
  "overall_weight_markov": 0.65,
  "history_limit": 12
}
```

Новые элементы UI на странице "Оценка риска":
- timeline риска за последние N запусков (`overall` и `p_s2`);
- heatmap матрицы переходов Маркова;
- режим таблицы "Только критичные";
- раскрытие строки метрики с формулой и входными значениями.

6.1) Диссертационный evaluation-пакет (глава 7)

Команда:
```bash
python manage.py run_dissertation_evaluation \
  --days-back 120 \
  --horizons 24h,7d,30d \
  --model-kinds sarima,lstm,ensemble \
  --baseline-action-code no_action \
  --strict-intersection 1 \
  --enable-stat-tests 1 \
  --bootstrap-samples 300 \
  --bootstrap-block-size 0 \
  --output-dir research/evaluation
```

Где `--bootstrap-block-size 0` означает автоматический выбор `L` (moving block bootstrap), а `>0` — фиксированный размер блока.

Что считает:
- технические метрики качества прогноза: RMSE, MAE, MAPE, sMAPE, MASE, RMSSE;
- вероятностные/интервальные метрики: Pinball(q10/q50/q90), PICP80, ACE80, MIW, Winkler80;
- статистическую значимость: DM-test + moving block bootstrap CI95;
- экономический эффект: `ΔR = R(без системы) - R(с системой)` по decision-runs.

Артефакты формируются в `research/evaluation/run_YYYYMMDD_HHMMSS/`:
- CSV по ошибкам прогноза и агрегатам;
- CSV по ΔR (по запускам и по горизонтам);
- markdown-отчет и `manifest.json`.

6.2) UI-вкладка в системе: "Мониторинг -> Верификация диссертации"

Backend API для вкладки:
- POST `/api/dissertation-evaluation/run/` — запустить расчет evaluation и создать новый `run_*` каталог.
- GET `/api/dissertation-evaluation/history/?limit=30` — история запусков с summary.
- GET `/api/dissertation-evaluation/detail/?run_id=run_...` — manifest + текст markdown-отчета.
- GET `/api/dissertation-evaluation/download/?run_id=run_...&artifact=<artifact_key>` — скачать CSV/MD.

Что видно во вкладке:
- запуск evaluation по выбранному устройству/периоду/наборам горизонтов и моделей;
- включение strict intersection (научно-корректное сравнение на общих точках);
- включение DM/Bootstrap и настройка числа bootstrap-итераций/длины блока L;
- история запусков;
- summary-карточки (coverage, ΔR, доля ΔR>0, вероятностные метрики);
- блок статистической значимости (таблицы DM-test и Bootstrap CI95);
- блок "Ключевые выводы" (лучшая модель/горизонт и покрытие фактом);
- графики RMSE/MAE, Pinball, калибровки интервалов и ΔR по горизонтам;
- таблица артефактов и скачивание результатов через backend.

Автогенерация отчетов:
- после каждого запуска evaluation автоматически формируются:
  - PNG-графики;
  - `dissertation_evaluation_report.pdf` (собран из summary + графиков);
  - CSV/MD артефакты как и раньше.

7) СППР: Формирование рекомендаций (новая вкладка Мониторинг -> Рекомендации СППР)

Что реализовано:
- Сущности СППР в БД: альтернативы действий, критерии, политики, матрица потерь, AHP-парные сравнения.
- Запуск рекомендаций:
  - Bayes MVP (`recommend`)
  - Bayes + AHP (`recommend_advanced`)
- Сохранение результата запуска (ранжирование альтернатив, выбранное действие, объяснение).
- Обратная связь по фактическому исходу (`feedback`) для последующей калибровки.

Backend API:
- GET/POST `/api/decision-actions/` (admin)
- GET/POST `/api/decision-criteria/` (admin)
- GET/POST `/api/decision-policies/` (admin)
- GET/POST `/api/decision-policy-losses/` (admin)
- POST `/api/decision-policies/bootstrap_defaults/` (admin)
- GET/POST `/api/decision-policies/{id}/ahp_matrix/` (admin)
- POST `/api/decision-policies/{id}/ahp_validate/` (admin)
- GET `/api/decision-runs/` (admin)
- GET `/api/decision-runs/latest/` (admin)
- POST `/api/decision-runs/recommend/` (admin)
- POST `/api/decision-runs/recommend_advanced/` (admin)
- POST `/api/decision-runs/{id}/feedback/` (admin)

UI вкладка "Рекомендации СППР":
- выбор устройства/горизонта/режима/политики;
- запуск расчета рекомендации;
- таблица ранжирования альтернатив;
- блок объяснения формул;
- вывод активных риск-метрик, по которым принято решение;
- настраиваемые пороги отбора риск-метрик (`min_risk`, `min_contribution`) для фильтрации действий;
- форма feedback по фактическому исходу.

UI вкладка "Настройки СППР":
- полный CRUD по справочникам и параметрам СППР;
- действия, критерии, политики, строки матрицы потерь;
- редактирование AHP-матрицы критериев;
- подсказки и краткие описания по каждому блоку.

Связь СППР с прогнозами отказов:
- В расчете рекомендации автоматически выбираются активные риск-метрики из результата Forecast/Risk.
- В ranking остаются только те действия, которые совпали с текущим риск-контекстом:
  - по `metric_codes`,
  - или по `metric_groups`,
  - и (опционально) по `source_models`.
- Если у действия нет привязки к метрикам (`metric_codes`/`metric_groups`), оно исключается из ranking при наличии активных риск-метрик.
- Настраивается в `constraints_json` действия (теперь через понятные поля на экране настроек).
- Защита истории: при удалении действия/критерия, если они уже использовались в расчетах, backend архивирует их (`is_active=false`) вместо физического удаления.

Стартовый профиль СППР по умолчанию:
- 16 преднастроенных действий (диск/CPU/RAM/сеть/температура/аварийные сценарии);
- 7 критериев (надежность, SLA, скорость восстановления, стоимость, трудозатраты, обратимость, автоматизируемость);
- детализированная матрица потерь для горизонтов `24h/7d/30d`.
