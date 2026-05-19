# Диссертационный отчет верификации модели

- Время расчета: `2026-04-21T13:21:12.197663+00:00`
- Прогнозный интервал: `2026-04-16T00:00:00+00:00` → `2026-05-16T00:00:00+00:00`
- Интервал факта: `2026-04-16T00:00:00+00:00` → `2026-05-16T00:00:00+00:00`
- Фильтр устройства: `DEMO-SARIMA-001`
- Forecast run IDs: `264, 265, 266`
- Горизонты: `7d`
- Модели: `sarima, lstm, ensemble`
- Базовое реактивное действие для ΔR: `no_action`
- Bootstrap итераций: `300`
- Bootstrap размер блока L: `auto`

## 1. Технические критерии (глава 7.1)

- Всего прогнозных точек: `3864`
- Точек с найденным фактом (сырое покрытие): `3864` (100.0%)
- Точек в финальном сравнении моделей: `3528` (91.3%)
- Strict intersection: `True` (ключей: `1176`)
- Артефакт: `/home/zulixo/projects/TechTracker/research/evaluation/run_20260421_132112/forecast_metrics_by_model_horizon.csv`

| Модель | Горизонт | N | MAE | RMSE | MAPE |
| --- | --- | --- | --- | --- | --- |
| ensemble | 7d | 1176 | 25.8123 | 57.5797 | 22.36% |
| sarima | 7d | 1176 | 26.7113 | 59.4610 | 22.78% |
| lstm | 7d | 1176 | 35.0812 | 88.4347 | 28.96% |

### 1.1. Вероятностные метрики и устойчивость

- Артефакт: `/home/zulixo/projects/TechTracker/research/evaluation/run_20260421_132112/forecast_prob_metrics_by_model_horizon.csv`

| Модель | Горизонт | N | sMAPE | MASE | RMSSE | Pinball(avg) |
| --- | --- | --- | --- | --- | --- | --- |
| ensemble | 7d | 1176 | 12.49% | 0.4180 | 0.3247 | 8.9059 |
| lstm | 7d | 1176 | 14.22% | 0.5057 | 0.4051 | 12.7373 |
| sarima | 7d | 1176 | 13.39% | 0.4698 | 0.3707 | 9.2138 |

### 1.2. Калибровка интервалов (80%)

- Артефакт: `/home/zulixo/projects/TechTracker/research/evaluation/run_20260421_132112/forecast_interval_calibration_by_model_horizon.csv`

| Модель | Горизонт | N | PICP80 | ACE80 | MIW | Winkler80 |
| --- | --- | --- | --- | --- | --- | --- |
| ensemble | 7d | 1176 | 59.10% | 20.90% | 44.0731 | 138.1160 |
| lstm | 7d | 1176 | 55.10% | 24.90% | 55.9267 | 206.7137 |
| sarima | 7d | 1176 | 52.89% | 27.11% | 46.3676 | 142.8565 |

### 1.3. Статистическая значимость (DM-test)

- Артефакт: `/home/zulixo/projects/TechTracker/research/evaluation/run_20260421_132112/forecast_dm_tests.csv`

| Горизонт | Модель A | Модель B | N | DM-stat | p-value | Значимо (0.05) | Победитель |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 7d | lstm | ensemble | 0 | - | - | Нет | - |
| 7d | sarima | ensemble | 1176 | 6.6127 | 0.0000 | Да | ensemble |
| 7d | sarima | lstm | 0 | - | - | Нет | - |

### 1.4. Доверительные интервалы метрик (moving block bootstrap CI95)

- Артефакт: `/home/zulixo/projects/TechTracker/research/evaluation/run_20260421_132112/forecast_bootstrap_ci.csv`

| Модель | Горизонт | Метрика | N | Оценка | CI95 low | CI95 high | B | L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ensemble | 7d | mase | 1176 | 0.4180 | 0.4039 | 0.4378 | 300 | 21 |
| lstm | 7d | mase | 1176 | 0.5057 | 0.4734 | 0.5402 | 300 | 21 |
| sarima | 7d | mase | 1176 | 0.4698 | 0.4525 | 0.4881 | 300 | 21 |
| ensemble | 7d | pinball_avg | 1176 | 8.9059 | 8.1532 | 9.6082 | 300 | 21 |
| lstm | 7d | pinball_avg | 1176 | 12.7373 | 10.7406 | 14.9659 | 300 | 21 |
| sarima | 7d | pinball_avg | 1176 | 9.2138 | 8.3303 | 10.1788 | 300 | 21 |
| ensemble | 7d | rmse | 1176 | 57.5797 | 53.1535 | 62.2047 | 300 | 21 |
| lstm | 7d | rmse | 1176 | 88.4347 | 75.7542 | 100.4290 | 300 | 21 |
| sarima | 7d | rmse | 1176 | 59.4610 | 54.3763 | 64.5230 | 300 | 21 |

### 1.5. Сравнение режимов SARIMA

- Артефакт: `/home/zulixo/projects/TechTracker/research/evaluation/run_20260421_132112/forecast_metrics_by_variant_horizon.csv`

| Режим SARIMA | Горизонт | N | MAE | RMSE | MAPE |
| --- | --- | --- | --- | --- | --- |
| SARIMA • STL + возврат сезонности | 7d | 1176 | 26.7113 | 59.4610 | 22.78% |

## 2. Экономический критерий (глава 7.2)

- Запусков СППР в периоде: `2`
- Запусков, где есть сравнение с baseline `no_action`: `2`
- Запусков без baseline-строки: `0`
- Среднее ΔR: `497614.30`
- Медиана ΔR: `497614.30`
- Доля положительного эффекта (ΔR > 0): `100.00%`
- Артефакт: `/home/zulixo/projects/TechTracker/research/evaluation/run_20260421_132112/decision_delta_r_by_horizon.csv`

| Горизонт | N | ΔR среднее | ΔR медиана | Доля ΔR>0 |
| --- | --- | --- | --- | --- |
| 30d | 2 | 497614.30 | 497614.30 | 100.00% |

## 3. Формулы и интерпретация

- RMSE = sqrt(mean((y_hat - y_actual)^2))
- MAE = mean(abs(y_hat - y_actual))
- sMAPE = mean(2*abs(y_hat-y)/(abs(y)+abs(y_hat)+eps))
- MASE = MAE / MAE(seasonal naive), RMSSE = RMSE / RMSE(seasonal naive)
- Pinball(q) для q={0.1,0.5,0.9}: качество квантильного прогноза
- PICP80 = доля фактов внутри [p10, p90], ACE80 = |PICP80 - 0.80|
- MIW = средняя ширина интервала, Winkler80 = штраф узкого/некалиброванного интервала
- Block bootstrap CI95: ресемплинг contiguous-блоков длины L для учета временной зависимости ошибок
- ΔR = R(без системы) - R(с системой), где baseline = реактивное действие

## 4. Что делать дальше

1. Повысить покрытие фактом (сейчас coverage зависит от совпадения target_ts и raw history).
2. Добавить отдельный backtest pipeline по фиксированным срезам времени.
3. Зафиксировать контрольные экспериментальные наборы для сравнения версий модели.
