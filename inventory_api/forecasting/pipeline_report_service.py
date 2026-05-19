from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import json
import math
import textwrap

from PIL import Image, ImageDraw, ImageFont

from django.conf import settings
from django.utils import timezone

from inventory_api.models import (
    AgentStatus,
    DecisionRun,
    Device,
    ForecastPoint,
    ForecastRun,
    RawMetric,
    StateEstimate,
)
from inventory_api.forecasting.risk_assessment_service import (
    RiskAssessmentError,
    evaluate_risk_assessment,
)

PAGE_SIZE = (1240, 1754)
PAGE_BG = (255, 255, 255)
CARD_BG = (248, 250, 252)
CARD_BORDER = (219, 229, 239)
TEXT_MAIN = (15, 23, 42)
TEXT_MUTED = (100, 116, 139)
GREEN = (16, 185, 129)
BLUE = (14, 165, 233)
ORANGE = (249, 115, 22)
AMBER = (245, 158, 11)
RED = (239, 68, 68)
SLATE = (71, 85, 105)

METRIC_MAP = {
    "cpu_load_total": ("Загрузка CPU", "%"),
    "mem_usage_percent": ("Использование памяти", "%"),
    "net_bytes_sent": ("Трафик исходящий", "KB/s"),
    "net_bytes_recv": ("Трафик входящий", "KB/s"),
    "ping_latency_gateway": ("Ping до шлюза", "ms"),
    "system_temperature": ("Температура системы", "C"),
    "storcli_drive_temperature": ("Температура диска RAID", "C"),
    "storcli_predictive_failure_count": ("Predictive Failure Count", "count"),
    "storcli_drive_wear_percent": ("Износ диска RAID", "%"),
    "storcli_ssd_wear_percent": ("Износ SSD", "%"),
    "nvme_percentage_used": ("NVMe wear used", "%"),
}


def _try_load_font(size: int):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def _fit_to_page(image: Image.Image, page_size=PAGE_SIZE, margin=36):
    page_w, page_h = page_size
    max_w = page_w - margin * 2
    max_h = page_h - margin * 2
    img = image.convert("RGB")
    scale = min(max_w / img.width, max_h / img.height, 1.0)
    new_size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
    img = img.resize(new_size, resample=Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (page_w, page_h), color=PAGE_BG)
    x = (page_w - img.width) // 2
    y = (page_h - img.height) // 2
    canvas.paste(img, (x, y))
    return canvas


def _build_pdf_report(pdf_path: Path, page_images: list[Path]) -> bool:
    pages = []
    for image_path in page_images:
        if not image_path.exists():
            continue
        try:
            with Image.open(image_path) as image:
                pages.append(_fit_to_page(image))
        except Exception:
            continue
    if not pages:
        return False
    first, rest = pages[0], pages[1:]
    first.save(pdf_path, format="PDF", resolution=150.0, save_all=True, append_images=rest)
    return True


def _base_dir() -> Path:
    base = Path(getattr(settings, "BASE_DIR", Path.cwd())) / "research" / "pipeline_reports"
    base.mkdir(parents=True, exist_ok=True)
    return base.resolve()


def _evaluation_base_dir() -> Path:
    base = Path(getattr(settings, "BASE_DIR", Path.cwd())) / "research" / "evaluation"
    base.mkdir(parents=True, exist_ok=True)
    return base.resolve()


def _as_float(value, default=None):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(out) or math.isinf(out):
        return default
    return out


def _fmt_dt(value) -> str:
    if not value:
        return "—"
    try:
        dt = timezone.localtime(value)
    except Exception:
        return "—"
    return dt.strftime("%d.%m.%Y, %H:%M")


def _freshness_label(value) -> str:
    if not value:
        return "нет данных"
    try:
        diff = max(0, int((timezone.now() - value).total_seconds() // 60))
    except Exception:
        return "нет данных"
    if diff <= 1:
        return "только что"
    if diff < 60:
        return f"{diff} мин назад"
    hours = diff // 60
    mins = diff % 60
    if hours < 24:
        return f"{hours} ч {mins} мин назад"
    days = hours // 24
    return f"{days} д {hours % 24} ч назад"


def _fmt_pct(value) -> str:
    num = _as_float(value, None)
    if num is None:
        return "—"
    return f"{num * 100.0:.1f}%"


def _fmt_money(value) -> str:
    num = _as_float(value, None)
    if num is None:
        return "—"
    return f"{num:,.0f} ₽".replace(",", " ")


def _metric_label(code: str) -> str:
    return METRIC_MAP.get(str(code or "").strip().lower(), (str(code or "Метрика"), ""))[0]


def _metric_unit(code: str) -> str:
    return METRIC_MAP.get(str(code or "").strip().lower(), (str(code or "Метрика"), ""))[1]


def _fmt_metric_value(value, code: str) -> str:
    num = _as_float(value, None)
    if num is None:
        return "—"
    unit = _metric_unit(code)
    digits = 2 if unit == "count" else 1
    return f"{num:.{digits}f}{(' ' + unit) if unit else ''}"


def _human_model(value: str) -> str:
    value = str(value or "").strip().lower()
    if value == "ensemble":
        return "Оркестр"
    if value == "sarima":
        return "SARIMA"
    if value == "lstm":
        return "LSTM"
    return value or "—"


def _human_horizon(value: str) -> str:
    value = str(value or "").strip().lower()
    if value == "24h":
        return "24 часа"
    if value == "7d":
        return "7 дней"
    if value == "30d":
        return "30 дней"
    return value or "—"


def _risk_label(value) -> str:
    raw = _as_float(value, 0.0) or 0.0
    if raw >= 0.85:
        return "Критический"
    if raw >= 0.65:
        return "Высокий"
    if raw >= 0.40:
        return "Средний"
    return "Низкий"


def _risk_color(value):
    raw = _as_float(value, 0.0) or 0.0
    if raw >= 0.85:
        return RED
    if raw >= 0.65:
        return AMBER
    if raw >= 0.40:
        return BLUE
    return GREEN


def _state_label(value: str) -> str:
    value = str(value or "").strip().lower()
    if value == "s0":
        return "S0 - Норма"
    if value == "s1":
        return "S1 - Деградация"
    if value == "s2":
        return "S2 - Предаварийное"
    return "Нет оценки"


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _latest_evaluation(serial: str):
    rows = []
    for child in _evaluation_base_dir().iterdir():
        if not child.is_dir() or not child.name.startswith("run_"):
            continue
        manifest_path = child / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = _read_json(manifest_path)
        except Exception:
            continue
        config = manifest.get("config") or {}
        if str(config.get("serial") or "").strip() != serial:
            continue
        rows.append({
            "run_id": child.name,
            "generated_at": manifest.get("generated_at"),
            "summary": manifest.get("summary") or {},
            "manifest": manifest,
        })
    rows.sort(key=lambda row: str(row.get("generated_at") or ""), reverse=True)
    return rows[0] if rows else None


def _history_window_days(horizon: str) -> int:
    if horizon == "24h":
        return 3
    if horizon == "7d":
        return 7
    return 14


def _card(draw: ImageDraw.ImageDraw, box, title: str, value: str, note: str = "", accent=None):
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=20, fill=CARD_BG, outline=CARD_BORDER, width=2)
    title_font = _try_load_font(20)
    value_font = _try_load_font(34)
    note_font = _try_load_font(18)
    draw.text((x0 + 24, y0 + 18), title, font=title_font, fill=TEXT_MUTED)
    draw.text((x0 + 24, y0 + 52), value, font=value_font, fill=(accent or TEXT_MAIN))
    if note:
        note_lines = textwrap.wrap(note, width=max(20, int((x1 - x0) / 16)))[:3]
        draw.multiline_text((x0 + 24, y0 + 102), "\n".join(note_lines), font=note_font, fill=SLATE, spacing=5)


def _draw_pill(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, fill):
    font = _try_load_font(18)
    bbox = draw.textbbox((x, y), text, font=font)
    width = (bbox[2] - bbox[0]) + 26
    height = (bbox[3] - bbox[1]) + 16
    draw.rounded_rectangle((x, y, x + width, y + height), radius=999, fill=fill)
    draw.text((x + 13, y + 8), text, font=font, fill=(255, 255, 255))
    return width


def _new_page(title: str, subtitle: str):
    image = Image.new("RGB", PAGE_SIZE, color=PAGE_BG)
    draw = ImageDraw.Draw(image)
    title_font = _try_load_font(40)
    subtitle_font = _try_load_font(20)
    draw.text((52, 36), title, font=title_font, fill=TEXT_MAIN)
    draw.text((52, 88), subtitle, font=subtitle_font, fill=TEXT_MUTED)
    return image, draw


def _draw_wrapped_text(draw: ImageDraw.ImageDraw, xy, text: str, width_chars: int, font_size: int = 18, fill=SLATE, line_spacing: int = 5):
    font = _try_load_font(font_size)
    lines = []
    for paragraph in str(text or "").splitlines() or [""]:
        wrapped = textwrap.wrap(paragraph, width=max(10, width_chars)) or [""]
        lines.extend(wrapped)
    draw.multiline_text(xy, "\n".join(lines), font=font, fill=fill, spacing=line_spacing)


def _build_chart_geometry(history_rows: list[dict], forecast_rows: list[dict], box):
    x0, y0, x1, y1 = box
    chart_left = x0 + 18
    chart_right = x1 - 18
    chart_top = y0 + 40
    chart_bottom = y1 - 28

    def _downsample(rows, limit):
        if len(rows) <= limit:
            return rows
        step = max(1, math.ceil(len(rows) / limit))
        sampled = rows[::step]
        if sampled[-1] is not rows[-1]:
            sampled.append(rows[-1])
        return sampled[-limit:]

    history = [
        {"value": _as_float(row.get("value"), None)}
        for row in _downsample(history_rows, 72)
        if _as_float(row.get("value"), None) is not None
    ]
    forecast = [
        {
            "value": _as_float(row.get("y_hat"), None),
            "lower": _as_float(row.get("p10"), _as_float(row.get("y_hat"), None)),
            "upper": _as_float(row.get("p90"), _as_float(row.get("y_hat"), None)),
        }
        for row in _downsample(forecast_rows, 120)
        if _as_float(row.get("y_hat"), None) is not None
    ]
    total_count = max(2, len(history) + max(1, len(forecast)))
    all_values = [row["value"] for row in history] + [row["value"] for row in forecast] + [row["lower"] for row in forecast] + [row["upper"] for row in forecast]
    if not all_values:
        return [], [], []
    min_value = min(all_values)
    max_value = max(all_values)
    if max_value <= min_value:
        min_value -= 1.0
        max_value += 1.0
    margin = max(0.5, (max_value - min_value) * 0.08)
    min_value -= margin
    max_value += margin
    scale_x = max(1, chart_right - chart_left)
    scale_y = max(1, chart_bottom - chart_top)

    def _point(index, value):
        x = chart_left + (index / (total_count - 1)) * scale_x
        y = chart_bottom - ((value - min_value) / (max_value - min_value)) * scale_y
        return (x, y)

    history_points = [_point(idx, row["value"]) for idx, row in enumerate(history)]
    forecast_points = [_point(len(history) - 1 + idx + 1 if history else idx, row["value"]) for idx, row in enumerate(forecast)]
    band_polygon = []
    lower = []
    upper = []
    for idx, row in enumerate(forecast):
        series_index = len(history) - 1 + idx + 1 if history else idx
        lower.append(_point(series_index, row["lower"]))
        upper.append(_point(series_index, row["upper"]))
    if lower and upper:
        band_polygon = lower + list(reversed(upper))
    return history_points, forecast_points, band_polygon


def _draw_metric_chart(draw: ImageDraw.ImageDraw, box, chart: dict):
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=20, fill=CARD_BG, outline=CARD_BORDER, width=2)
    draw.text((x0 + 18, y0 + 14), chart.get("title") or "Метрика", font=_try_load_font(22), fill=TEXT_MAIN)
    draw.text((x0 + 18, y0 + 46), chart.get("subtitle") or "", font=_try_load_font(17), fill=TEXT_MUTED)
    label_color = _risk_color(chart.get("risk"))
    pill_text = chart.get("risk_label")
    if pill_text:
        _draw_pill(draw, x1 - 170, y0 + 14, pill_text, label_color)

    history_points, forecast_points, band_polygon = _build_chart_geometry(chart.get("history") or [], chart.get("forecast") or [], box)
    chart_left = x0 + 18
    chart_right = x1 - 18
    chart_top = y0 + 78
    chart_bottom = y1 - 34
    draw.line((chart_left, chart_bottom, chart_right, chart_bottom), fill=(203, 213, 225), width=2)
    if band_polygon:
        draw.polygon(band_polygon, fill=(254, 240, 138))
    if len(history_points) >= 2:
        draw.line(history_points, fill=BLUE, width=4)
    if len(forecast_points) >= 2:
        draw.line(forecast_points, fill=ORANGE, width=4)

    footer_left = chart.get("footer_left") or ""
    footer_right = chart.get("footer_right") or ""
    draw.text((x0 + 18, y1 - 26), footer_left, font=_try_load_font(16), fill=TEXT_MUTED)
    bbox = draw.textbbox((0, 0), footer_right, font=_try_load_font(16))
    draw.text((x1 - 18 - (bbox[2] - bbox[0]), y1 - 26), footer_right, font=_try_load_font(16), fill=TEXT_MUTED)


def _build_snapshot(*, serial: str, horizon: str, decision_mode: str, forecast_horizons: list[str] | None = None):
    device = Device.objects.filter(serial_number=serial).select_related("device_type").first()
    if not device:
        raise RuntimeError("Устройство не найдено")

    raw_row = RawMetric.objects.filter(device=device).order_by("-timestamp", "-id").first()
    agent_row = AgentStatus.objects.filter(device=device).order_by("-updated_at", "-id").first()

    runs = {}
    for model_kind in ("sarima", "lstm", "ensemble"):
        runs[model_kind] = ForecastRun.objects.filter(device=device, model_kind=model_kind).order_by("-created_at", "-id").first()

    successful = [
        row for row in runs.values()
        if row is not None and str(row.status).lower() == "success"
    ]
    successful.sort(key=lambda row: row.created_at or timezone.now(), reverse=True)
    dominant_run = successful[0] if successful else None

    state_row = None
    state_candidates = [runs.get("ensemble"), runs.get("lstm"), runs.get("sarima")]
    for candidate in state_candidates:
        if not candidate or str(candidate.status).lower() != "success":
            continue
        row = StateEstimate.objects.filter(device=device, horizon=horizon, run=candidate).order_by("-timestamp", "-id").first()
        if row is not None:
            state_row = row
            break

    risk_payload = None
    risk_result = None
    risk_error = ""
    try:
        risk_payload = evaluate_risk_assessment(
            serial=serial,
            horizons=[horizon],
            preferred_model_kind="auto",
            personalized_thresholds=True,
            threshold_lookback_days=60,
            markov_lookback_days=120,
            markov_smoothing=1.0,
            type_blend=0.35,
            overall_weight_markov=0.65,
            history_limit=12,
        )
        horizons = risk_payload.get("horizons") if isinstance(risk_payload, dict) else []
        if isinstance(horizons, list):
            risk_result = next((row for row in horizons if str(row.get("horizon") or "") == horizon), horizons[0] if horizons else None)
    except RiskAssessmentError as exc:
        risk_error = str(exc)
    except Exception as exc:
        risk_error = f"Расчет риска недоступен: {exc}"

    decision_row = DecisionRun.objects.filter(device=device, horizon=horizon, mode=decision_mode).select_related("recommended_action").order_by("-created_at", "-id").first()
    evaluation = _latest_evaluation(serial)

    chart_rows = []
    if dominant_run is not None:
        points = list(
            ForecastPoint.objects
            .filter(run=dominant_run, horizon=horizon)
            .order_by("metric_code", "target_ts", "id")
            .values("metric_code", "target_ts", "y_hat", "p10", "p90")
        )
        grouped_points = {}
        for row in points:
            grouped_points.setdefault(str(row.get("metric_code") or "").strip(), []).append(row)
        risk_metric_rows = sorted(
            list((risk_result or {}).get("metrics") or []),
            key=lambda row: (_as_float(row.get("risk"), 0.0) or 0.0),
            reverse=True,
        )
        metric_codes = []
        for row in risk_metric_rows:
            code = str(row.get("metric_code") or "").strip()
            if code and code not in metric_codes:
                metric_codes.append(code)
        for code in sorted(grouped_points.keys()):
            if code and code not in metric_codes:
                metric_codes.append(code)
        metric_codes = metric_codes[:3]
        since = (raw_row.timestamp if raw_row else timezone.now()) - timedelta(days=_history_window_days(horizon))
        for code in metric_codes:
            history_rows = list(
                RawMetric.objects
                .filter(device=device, code=code, timestamp__gte=since)
                .order_by("timestamp", "id")
                .values("timestamp", "value")
            )
            risk_meta = next((row for row in risk_metric_rows if str(row.get("metric_code") or "") == code), None)
            metric_points = grouped_points.get(code) or []
            last_forecast = metric_points[-1] if metric_points else None
            chart_rows.append({
                "metric_code": code,
                "title": _metric_label(code),
                "subtitle": f"{_human_model(dominant_run.model_kind)} • {_metric_unit(code) or 'без ед. изм.'}",
                "history": history_rows,
                "forecast": metric_points,
                "risk": _as_float((risk_meta or {}).get("risk"), None),
                "risk_label": _risk_label((risk_meta or {}).get("risk")) if risk_meta else "",
                "footer_left": f"История {len(history_rows)} • прогноз {len(metric_points)}",
                "footer_right": f"Финал {_fmt_metric_value(last_forecast.get('y_hat') if last_forecast else None, code)}",
            })

    return {
        "generated_at": timezone.now(),
        "device": device,
        "raw": raw_row,
        "agent": agent_row,
        "runs": runs,
        "dominant_run": dominant_run,
        "state": state_row,
        "risk_payload": risk_payload,
        "risk": risk_result,
        "risk_error": risk_error,
        "decision": decision_row,
        "evaluation": evaluation,
        "chart_rows": chart_rows,
        "horizon": horizon,
        "decision_mode": decision_mode,
        "forecast_horizons": forecast_horizons or [],
    }


def _render_overview_page(path: Path, snapshot: dict):
    device = snapshot["device"]
    image, draw = _new_page(
        title="Сводный отчёт полного цикла",
        subtitle=(
            f"Устройство: {device.name} ({device.serial_number}) • Горизонт риска/СППР: {_human_horizon(snapshot['horizon'])} • "
            f"Режим СППР: {'Bayes + AHP' if snapshot['decision_mode'] == 'advanced' else 'Bayes'} • "
            f"Сформирован: {_fmt_dt(snapshot['generated_at'])}"
        ),
    )

    top_y = 150
    _card(draw, (52, top_y, 590, top_y + 180), "Свежесть метрик", _freshness_label(snapshot.get("raw").timestamp if snapshot.get("raw") else snapshot.get("agent").updated_at if snapshot.get("agent") else None), f"Последняя метрика: {_fmt_dt(snapshot.get('raw').timestamp) if snapshot.get('raw') else '—'}")
    dominant_run = snapshot.get("dominant_run")
    dominant_value = f"{_human_model(dominant_run.model_kind)} • {_human_horizon(snapshot['horizon'])}" if dominant_run else "Нет готового прогноза"
    dominant_note = f"run #{dominant_run.id} • {_fmt_dt(dominant_run.created_at)}" if dominant_run else "Сначала нужен успешный SARIMA/LSTM/оркестр"
    _card(draw, (620, top_y, 1188, top_y + 180), "Основной прогноз", dominant_value, dominant_note, accent=BLUE if dominant_run else TEXT_MAIN)

    state_row = snapshot.get("state")
    state_value = _state_label(state_row.state) if state_row else "Нет оценки"
    state_note = f"S0 {_fmt_pct(state_row.p_s0)} • S1 {_fmt_pct(state_row.p_s1)} • S2 {_fmt_pct(state_row.p_s2)} • уверенность {_fmt_pct(state_row.confidence)}" if state_row else "Оценка состояния ещё не рассчитана"
    _card(draw, (52, top_y + 210, 590, top_y + 390), "Состояние S0/S1/S2", state_value, state_note, accent=GREEN if state_row and state_row.state == 's0' else AMBER if state_row and state_row.state == 's1' else RED if state_row and state_row.state == 's2' else TEXT_MAIN)

    risk_row = snapshot.get("risk")
    risk_value = _fmt_pct(risk_row.get("overall_risk")) if risk_row else "Нет расчёта"
    risk_note = (
        f"Риск по метрикам {_fmt_pct(risk_row.get('metric_aggregate_risk'))} • Марков S2 {_fmt_pct(risk_row.get('markov_projected_p_s2'))}"
        if risk_row else (snapshot.get("risk_error") or "Расчёт риска недоступен")
    )
    _card(draw, (620, top_y + 210, 1188, top_y + 390), "Интегральный риск отказа", risk_value, risk_note, accent=_risk_color((risk_row or {}).get("overall_risk")))

    decision_row = snapshot.get("decision")
    decision_value = decision_row.recommended_action.name if decision_row and decision_row.recommended_action_id else "Нет рекомендации"
    decision_note = (
        f"Ожидаемые потери {_fmt_money((decision_row.risk_snapshot or {}).get('expected_loss', None))} • запуск {_fmt_dt(decision_row.created_at)}"
        if decision_row else "Для этого горизонта/режима ещё нет готового запуска СППР"
    )
    _card(draw, (52, top_y + 420, 590, top_y + 600), "Рекомендация СППР", decision_value, decision_note, accent=GREEN if decision_row else TEXT_MAIN)

    evaluation = snapshot.get("evaluation") or {}
    summary = evaluation.get("summary") or {}
    insights = summary.get("insights") or {}
    best_rmse = insights.get("best_rmse") or {}
    eval_value = (
        f"{_human_model(best_rmse.get('model_kind'))} • {_human_horizon(best_rmse.get('horizon'))} • RMSE {(_as_float(best_rmse.get('rmse'), 0.0) or 0.0):.3f}"
        if best_rmse else "Подтвержденной верификации нет"
    )
    eval_note = (
        f"Покрытие фактом {_fmt_pct(summary.get('forecast_coverage'))} • средний ΔR {_fmt_money((summary.get('delta_r') or {}).get('delta_r_mean'))}"
        if evaluation else "Оценка точности появится после сравнения прогноза с наступившим фактом"
    )
    _card(draw, (620, top_y + 420, 1188, top_y + 600), "Подтверждённая точность прогноза", eval_value, eval_note, accent=BLUE if evaluation else TEXT_MAIN)

    draw.text((52, 805), "Структурно-функциональная схема", font=_try_load_font(28), fill=TEXT_MAIN)
    draw.text((52, 845), "От сбора метрик до формального решения СППР.", font=_try_load_font(18), fill=TEXT_MUTED)

    nodes = [
        ("Сбор метрик", _freshness_label(snapshot.get("raw").timestamp if snapshot.get("raw") else None), BLUE),
        ("SARIMA + LSTM", dominant_value, ORANGE if dominant_run else SLATE),
        ("Состояние S0/S1/S2", state_value, GREEN if state_row and state_row.state == 's0' else AMBER if state_row and state_row.state == 's1' else RED if state_row and state_row.state == 's2' else SLATE),
        ("Оценка риска", risk_value, _risk_color((risk_row or {}).get("overall_risk"))),
        ("СППР", decision_value, GREEN if decision_row else SLATE),
    ]
    node_y = 905
    node_w = 206
    for idx, (title, value, color) in enumerate(nodes):
        x0 = 52 + idx * 228
        x1 = x0 + node_w
        draw.rounded_rectangle((x0, node_y, x1, node_y + 150), radius=18, fill=CARD_BG, outline=color, width=3)
        draw.text((x0 + 18, node_y + 16), title, font=_try_load_font(18), fill=TEXT_MUTED)
        _draw_wrapped_text(draw, (x0 + 18, node_y + 50), value, width_chars=15, font_size=22, fill=TEXT_MAIN)
        if idx < len(nodes) - 1:
            draw.line((x1 + 8, node_y + 74, x1 + 22, node_y + 74), fill=(148, 163, 184), width=4)
            draw.polygon([(x1 + 22, node_y + 74), (x1 + 10, node_y + 66), (x1 + 10, node_y + 82)], fill=(148, 163, 184))

    draw.rounded_rectangle((52, 1110, 1188, 1325), radius=18, fill=(252, 255, 247), outline=(187, 247, 208), width=2)
    draw.text((74, 1132), "Ключевые выводы", font=_try_load_font(24), fill=TEXT_MAIN)
    bullets = [
        f"1. Доминирующий прогноз: {dominant_value}.",
        f"2. Интегральный риск отказа: {risk_value} ({_risk_label((risk_row or {}).get('overall_risk')) if risk_row else 'нет расчёта'}).",
        f"3. Состояние системы: {state_value}.",
        f"4. Итог СППР: {decision_value}.",
        "5. Подтвержденная точность читается отдельно от текущего запуска, только по уже наступившему факту.",
    ]
    _draw_wrapped_text(draw, (74, 1174), "\n".join(bullets), width_chars=86, font_size=20, fill=SLATE, line_spacing=8)
    image.save(path, format="PNG")


def _render_charts_page(path: Path, snapshot: dict):
    image, draw = _new_page(
        title="Мини-графики последнего run",
        subtitle="Компактный визуальный слой: хвост истории + прогноз y_hat + интервал p10-p90 по ключевым метрикам.",
    )
    chart_rows = snapshot.get("chart_rows") or []
    if not chart_rows:
        draw.rounded_rectangle((52, 170, 1188, 360), radius=18, fill=CARD_BG, outline=CARD_BORDER, width=2)
        draw.text((78, 198), "Для выбранного устройства пока нет готовых прогнозных рядов на этом горизонте.", font=_try_load_font(24), fill=TEXT_MAIN)
        draw.text((78, 242), "Сначала нужен успешный run оркестра/SARIMA/LSTM с точками прогноза.", font=_try_load_font(18), fill=TEXT_MUTED)
        image.save(path, format="PNG")
        return

    boxes = [
        (52, 172, 1188, 620),
        (52, 652, 1188, 1100),
        (52, 1132, 1188, 1580),
    ]
    for chart, box in zip(chart_rows[:3], boxes):
        _draw_metric_chart(draw, box, chart)

    draw.rounded_rectangle((52, 1606, 1188, 1692), radius=16, fill=(248, 250, 252), outline=CARD_BORDER, width=2)
    draw.text((76, 1628), "Пояснение", font=_try_load_font(20), fill=TEXT_MAIN)
    _draw_wrapped_text(
        draw,
        (190, 1628),
        "Синий хвост показывает последние реальные наблюдения. Оранжевая линия показывает прогнозные точки на выбранном горизонте. Светлая зона — диапазон неопределенности p10-p90. Если прогнозная линия систематически растет и приближается к критическим порогам, это затем отражается в риске отказа и рекомендации СППР.",
        width_chars=92,
        font_size=17,
        fill=TEXT_MUTED,
    )
    image.save(path, format="PNG")


def _render_metrics_page(path: Path, snapshot: dict):
    image, draw = _new_page(
        title="Детализация качества, риска и решения",
        subtitle="Сводка тех показателей, которые система использует для итоговой интерпретации полного цикла.",
    )

    evaluation = snapshot.get("evaluation") or {}
    summary = evaluation.get("summary") or {}
    insights = summary.get("insights") or {}
    risk_row = snapshot.get("risk") or {}
    decision_row = snapshot.get("decision")
    state_row = snapshot.get("state")

    _card(draw, (52, 170, 376, 340), "Покрытие фактом", _fmt_pct(summary.get("forecast_coverage")), (insights.get("coverage_note") or "Подтвержденная точность появляется только при наличии факта."))
    best_rmse = insights.get("best_rmse") or {}
    rmse_value = f"{_human_model(best_rmse.get('model_kind'))} • {(_as_float(best_rmse.get('rmse'), 0.0) or 0.0):.3f}" if best_rmse else "Нет данных"
    _card(draw, (398, 170, 722, 340), "Лучшая связка по RMSE", rmse_value, _human_horizon(best_rmse.get("horizon")))
    best_pinball = insights.get("best_pinball") or {}
    pinball_value = f"{_human_model(best_pinball.get('model_kind'))} • {(_as_float(best_pinball.get('pinball_avg'), 0.0) or 0.0):.3f}" if best_pinball else "Нет данных"
    _card(draw, (744, 170, 1068, 340), "Лучшая связка по Pinball", pinball_value, _human_horizon(best_pinball.get("horizon")))
    delta = summary.get("delta_r") or {}
    _card(draw, (52, 368, 376, 538), "Средний экономический эффект", _fmt_money(delta.get("delta_r_mean")), f"Медиана {_fmt_money(delta.get('delta_r_median'))} • доля ΔR>0 {_fmt_pct(delta.get('share_positive'))}")
    _card(draw, (398, 368, 722, 538), "Итоговый риск отказа", _fmt_pct(risk_row.get("overall_risk")), f"Риск по метрикам {_fmt_pct(risk_row.get('metric_aggregate_risk'))} • Марков S2 {_fmt_pct(risk_row.get('markov_projected_p_s2'))}", accent=_risk_color(risk_row.get("overall_risk")))
    _card(draw, (744, 368, 1068, 538), "Итоговое состояние", _state_label(state_row.state if state_row else ""), f"S0 {_fmt_pct(state_row.p_s0 if state_row else None)} • S1 {_fmt_pct(state_row.p_s1 if state_row else None)} • S2 {_fmt_pct(state_row.p_s2 if state_row else None)}")

    draw.rounded_rectangle((52, 580, 1188, 940), radius=18, fill=CARD_BG, outline=CARD_BORDER, width=2)
    draw.text((78, 606), "Топ риск-метрик на горизонте", font=_try_load_font(24), fill=TEXT_MAIN)
    metrics = list((risk_row or {}).get("metrics") or [])
    metrics = sorted(metrics, key=lambda row: (_as_float(row.get("risk"), 0.0) or 0.0), reverse=True)[:5]
    if metrics:
        start_y = 658
        for idx, row in enumerate(metrics):
            y = start_y + idx * 48
            code = str(row.get("metric_code") or "")
            risk_text = _fmt_pct(row.get("risk"))
            contrib = _fmt_pct(row.get("contribution"))
            text = f"{idx + 1}. {_metric_label(code)} • риск {risk_text} • вклад {contrib} • p90 {_fmt_metric_value(row.get('p90'), code)}"
            draw.text((82, y), text, font=_try_load_font(20), fill=TEXT_MAIN)
    else:
        draw.text((82, 680), "Для выбранного горизонта список риск-метрик пока не собран.", font=_try_load_font(20), fill=TEXT_MUTED)

    draw.rounded_rectangle((52, 970, 1188, 1460), radius=18, fill=(252, 255, 247), outline=(187, 247, 208), width=2)
    draw.text((78, 998), "Итоговое решение СППР", font=_try_load_font(24), fill=TEXT_MAIN)
    if decision_row:
        draw.text((78, 1048), f"Рекомендованное действие: {decision_row.recommended_action.name if decision_row.recommended_action_id else '—'}", font=_try_load_font(28), fill=TEXT_MAIN)
        draw.text((78, 1092), f"Режим: {'Bayes + AHP' if decision_row.mode == 'advanced' else 'Bayes'} • запуск {_fmt_dt(decision_row.created_at)}", font=_try_load_font(18), fill=TEXT_MUTED)
        explanation = decision_row.explanation if isinstance(decision_row.explanation, dict) else {}
        risk_context = explanation.get("risk_context") if isinstance(explanation, dict) else {}
        active_metrics = list(risk_context.get("active_metrics") or [])
        metric_names = ", ".join(_metric_label(row.get("metric_code")) for row in active_metrics[:6]) or "не переданы"
        detail_lines = [
            f"Действие выбрано как вариант с минимальными ожидаемыми потерями среди допустимых альтернатив.",
            f"Активные риск-метрики в расчёте: {metric_names}.",
            f"Контекст риска из snapshot: общий риск {_fmt_pct((decision_row.risk_snapshot or {}).get('overall_risk'))}, S2 {_fmt_pct((decision_row.risk_snapshot or {}).get('p_s2'))}.",
        ]
        _draw_wrapped_text(draw, (78, 1140), "\n".join(detail_lines), width_chars=88, font_size=20, fill=SLATE, line_spacing=8)
    else:
        draw.text((78, 1060), "Для выбранного горизонта и режима готовый запуск СППР не найден.", font=_try_load_font(22), fill=TEXT_MUTED)

    image.save(path, format="PNG")


def build_pipeline_summary_report(*, serial: str, horizon: str = "30d", decision_mode: str = "bayes", forecast_horizons: list[str] | None = None) -> dict:
    snapshot = _build_snapshot(
        serial=str(serial or "").strip(),
        horizon=str(horizon or "30d").strip() or "30d",
        decision_mode=(str(decision_mode or "bayes").strip() or "bayes"),
        forecast_horizons=[str(item).strip() for item in (forecast_horizons or []) if str(item).strip()],
    )

    stamp = timezone.localtime(timezone.now()).strftime("%Y%m%d_%H%M%S")
    safe_serial = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in serial)
    run_dir = _base_dir() / f"pipeline_{stamp}_{safe_serial}"
    run_dir.mkdir(parents=True, exist_ok=True)

    page1 = run_dir / "pipeline_overview_page.png"
    page2 = run_dir / "pipeline_charts_page.png"
    page3 = run_dir / "pipeline_metrics_page.png"
    pdf_path = run_dir / "pipeline_summary_report.pdf"
    snapshot_path = run_dir / "snapshot.json"

    snapshot_path.write_text(json.dumps({
        "serial": serial,
        "horizon": horizon,
        "decision_mode": decision_mode,
        "generated_at": snapshot["generated_at"].isoformat(),
        "dominant_run_id": snapshot["dominant_run"].id if snapshot.get("dominant_run") else None,
        "evaluation_run_id": (snapshot.get("evaluation") or {}).get("run_id"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    _render_overview_page(page1, snapshot)
    _render_charts_page(page2, snapshot)
    _render_metrics_page(page3, snapshot)
    ok = _build_pdf_report(pdf_path, [page1, page2, page3])
    if not ok:
        raise RuntimeError("Не удалось собрать PDF-отчёт полного цикла")

    return {
        "pdf_path": pdf_path,
        "run_dir": run_dir,
        "file_name": pdf_path.name,
    }
