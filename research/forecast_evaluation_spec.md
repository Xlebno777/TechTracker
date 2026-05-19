# Спецификация диссертационного модуля «Оценка прогноза»

Версия: 1.0  
Контекст: модуль строится поверх текущей страницы `MonitoringEvaluation` и backend `dissertation-evaluation/*`.

## 1. Цель и научные требования

Цель модуля: формально и воспроизводимо оценивать качество прогнозов `SARIMA`, `LSTM`, `Оркестр` и их практическую пользу для СППР.

Научные требования:
1. Разделять точечную точность, интервальную калибровку и экономический эффект.
2. Исключать утечку будущего: оценивать только «созревшие» прогнозные точки.
3. Сравнивать модели на одинаковых срезах данных и одинаковых горизонтах.
4. Подкреплять выводы статистической проверкой значимости.
5. Формировать артефакты (CSV/PNG/PDF), пригодные для главы диссертации.

## 2. Что уже есть в системе (база для расширения)

Текущие источники:
1. `ForecastPoint` с `y_hat`, `p10`, `p90`, `target_ts`, `model_kind`, `horizon`, `labels`.
2. `RawMetric` как фактические значения для сопоставления.
3. `DecisionRun` и `DecisionRunScore` для экономической части (`ΔR`).

Текущие метрики:
1. `MAE`, `RMSE`, `MAPE`.
2. `ΔR` по горизонтам и доля `ΔR > 0`.
3. Сравнение режимов SARIMA по `RMSE/MAE/MAPE`.

Текущие артефакты:
1. `forecast_point_errors.csv`.
2. `forecast_metrics_by_model_horizon.csv`.
3. `forecast_metrics_by_variant_horizon.csv`.
4. `decision_delta_r_*.csv`.
5. `dissertation_evaluation_report.md`, `dissertation_evaluation_report.pdf`.

## 3. Диссертационный протокол оценки

Протокол:
1. Фильтр прогнозов: только `run.status=success`, выбранные `model_kinds`, `horizons`.
2. Созревание точки: `target_ts <= now`.
3. Подбор факта: ближайшая точка `RawMetric` в окне допуска `±tolerance`.
4. Сравнение только на пересечении фактов по одинаковым `(device, metric, horizon, target_ts)`.
5. Отчёт строится отдельно по каждому горизонту `24h/7d/30d` и по агрегату.

Расширение протокола:
1. Добавить режим `strict_intersection=true` в `run`-параметры.
2. Добавить rolling-origin backtest (серия срезов времени), не только единичный retrospective-срез.
3. Фиксировать конфигурацию запуска в manifest для полной воспроизводимости.

## 4. Метрики качества (формулы для диссертации)

Обозначения:
1. `y_t` — факт.
2. `ŷ_t` — прогноз медианы/точки.
3. `q_τ(t)` — τ-квантиль прогноза (`τ in {0.1, 0.5, 0.9}`).
4. `N` — число валидных сопоставлений.

Точечные:
1. `MAE = (1/N) * Σ |ŷ_t - y_t|`.
2. `RMSE = sqrt((1/N) * Σ (ŷ_t - y_t)^2)`.
3. `sMAPE = (100/N) * Σ [2|ŷ_t-y_t|/(|y_t|+|ŷ_t|+eps)]`.
4. `MASE = MAE / MAE_naive_seasonal`.
5. `RMSSE = RMSE / RMSE_naive_seasonal`.

Вероятностные и интервальные:
1. `Pinball(τ) = (1/N) * Σ ρ_τ(y_t - q_τ(t))`, где  
`ρ_τ(u) = τu, u>=0; (τ-1)u, u<0`.
2. `PICP(80%) = (1/N) * Σ I[p10_t <= y_t <= p90_t]`.
3. `ACE(80%) = |PICP - 0.80|`.
4. `MIW = (1/N) * Σ (p90_t - p10_t)`.
5. `Winkler(80%)` для штрафа узкого/некалиброванного интервала.
6. `CRPS_approx` через дискретные квантили `0.1/0.5/0.9`.

Экономические:
1. `ΔR = R_baseline - R_recommended`.
2. `E[ΔR]`, медиана `ΔR`, `P(ΔR>0)` по горизонту.
3. Опционально: cost-weighted error по risk-критичным метрикам.

## 5. Статистическая значимость

Обязательные тесты:
1. `Diebold-Mariano` для пар:
   `SARIMA vs LSTM`, `Оркестр vs SARIMA`, `Оркестр vs LSTM`.
2. Блочный bootstrap 95% CI для `RMSE`, `MASE`, `Pinball(0.9)`, `Winkler`.

Правила интерпретации:
1. Если `p < 0.05`, различие статистически значимо.
2. Если доверительные интервалы пересекаются существенно, вывод «преимущество не доказано».

## 6. Контракт backend (расширение поверх существующего)

Текущие endpoint’ы сохраняются:
1. `POST /api/dissertation-evaluation/run/`
2. `GET /api/dissertation-evaluation/history/`
3. `GET /api/dissertation-evaluation/detail/`
4. `GET /api/dissertation-evaluation/download/`

Новые входные параметры `run`:
1. `strict_intersection: bool = true`
2. `enable_stat_tests: bool = true`
3. `bootstrap_samples: int = 300`
4. `bootstrap_block_size: int = 0` (0 = auto для moving block bootstrap)
5. `backtest_folds: int = 0` (0 = текущий режим, >0 = rolling-origin)
6. `seasonal_period_hint: int | null`

Новые выходные блоки в `manifest.summary`:
1. `probabilistic_metrics_by_model_horizon`
2. `interval_calibration_by_model_horizon`
3. `stat_tests_dm`
4. `bootstrap_ci`

Новые CSV-артефакты:
1. `forecast_prob_metrics_by_model_horizon.csv`
2. `forecast_interval_calibration.csv`
3. `forecast_dm_tests.csv`
4. `forecast_bootstrap_ci.csv`

## 7. Контракт UI (страница «Оценка прогноза»)

Страница должна показывать 4 слоя:
1. Точность: `MAE/RMSE/sMAPE/MASE/RMSSE`.
2. Неопределённость: `Pinball`, `PICP`, `ACE`, `Winkler`, `MIW`.
3. Значимость: таблица DM-test + CI.
4. Практика: `ΔR`, доля успешных рекомендаций, лучший режим SARIMA.

Карточки верхнего уровня:
1. Прогнозные точки (созревшие/всего).
2. СППР запуски (использовано/всего).
3. Экономия на последнем запуске СППР.
4. Средняя экономия `E[ΔR]`.
5. Эффективность рекомендаций `P(ΔR>0)`.
6. Лучшая связка по RMSE.

Графики:
1. Heatmap `модель × горизонт` для `MASE` и `Pinball(0.9)`.
2. Калибровка интервалов: целевой 80% vs фактический `PICP`.
3. Барчарт `ΔR` по горизонтам.
4. Сравнение SARIMA-режимов.

## 8. Этапы внедрения в текущий код

Этап 1 (без миграций, быстро):
1. Добавить расчёт `sMAPE`, `MASE`, `RMSSE`, `Pinball`, `PICP`, `ACE`, `MIW`, `Winkler`.
2. Добавить CSV и блоки `chart_data`/`summary` в `evaluation_service.py`.
3. Добавить новые карточки и 2 графика на страницу `MonitoringEvaluation.vue`.

Этап 2 (диссертационный минимум):
1. Внедрить `strict_intersection=true` как default.
2. Добавить DM-test и bootstrap CI.
3. Добавить визуализацию значимости в UI.

Этап 3 (полный диссертационный):
1. Добавить rolling-origin backtest (`backtest_folds`).
2. Добавить отдельный раздел отчёта PDF по вероятностной верификации.
3. Включить сравнительный раздел «точность vs калибровка vs экономика».

## 9. Критерии готовности

Модуль считается готовым, если:
1. Для каждого горизонта есть таблица `model × metrics` по точечным и вероятностным критериям.
2. Для каждой модели рассчитан `PICP` и `ACE`.
3. Есть статистическое сравнение моделей (DM + CI).
4. Есть воспроизводимый `manifest.json` и PDF-отчёт.
5. Все выводы в UI совпадают с экспортированными CSV-артефактами.
