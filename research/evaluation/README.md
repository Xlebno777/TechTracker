# Пакет верификации для диссертации

Этот модуль автоматизирует расчет критериев эффективности из главы 7:
- технические: `RMSE`, `MAE` (и `MAPE` как вспомогательный);
- экономические: `ΔR = R(без системы) - R(с системой)`.

## Запуск

```bash
source .venv/bin/activate
python manage.py run_dissertation_evaluation \
  --days-back 120 \
  --horizons 24h,7d,30d \
  --model-kinds sarima,lstm,ensemble \
  --baseline-action-code no_action \
  --output-dir research/evaluation
```

Опционально по одному устройству:

```bash
python manage.py run_dissertation_evaluation --serial HOST-001
```

## Что формируется

Для каждого запуска создается папка `research/evaluation/run_YYYYMMDD_HHMMSS[_tag]/`:

- `forecast_point_errors.csv` — покомпонентные ошибки прогноза (`y_hat` vs факт).
- `forecast_metrics_by_bucket.csv` — метрики по `(model_kind, horizon, metric_code)`.
- `forecast_metrics_by_model_horizon.csv` — агрегированные метрики по `(model_kind, horizon)`.
- `forecast_metrics_by_model.csv` — агрегированные метрики по модели.
- `decision_delta_r_runs.csv` — ΔR по каждому запуску СППР.
- `decision_delta_r_by_horizon.csv` — агрегаты ΔR по горизонтам.
- `decision_delta_r_summary.csv` — общий итог ΔR.
- `dissertation_evaluation_report.md` — краткий отчет для текста диссертации.
- `manifest.json` — конфигурация запуска и пути ко всем артефактам.

## Важное замечание

`ΔR` считается как сравнение с реактивным baseline-действием (по умолчанию `no_action`) на основе ожидаемых потерь из decision layer.  
Если baseline-действие отсутствует в run, такой run исключается из расчета ΔR.
