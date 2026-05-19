from __future__ import annotations

from dataclasses import dataclass
import math

from django.db import transaction

from inventory_api.forecasting.risk_assessment_service import evaluate_risk_assessment
from inventory_api.models import (
    DecisionAction,
    DecisionCriterion,
    DecisionFeedback,
    DecisionPolicy,
    DecisionPolicyAHPPairwise,
    DecisionPolicyLoss,
    DecisionRun,
    DecisionRunAHP,
    DecisionRunScore,
    DecisionRunUtility,
    Device,
    RawMetric,
)


CR_THRESHOLD = 0.10
CRITICAL_RISK_THRESHOLD = 0.85

RI_TABLE = {
    1: 0.0,
    2: 0.0,
    3: 0.58,
    4: 0.90,
    5: 1.12,
    6: 1.24,
    7: 1.32,
    8: 1.41,
    9: 1.45,
    10: 1.49,
}


ALL_METRIC_GROUPS = ["cpu", "memory", "disk", "network", "temperature", "degradation", "other"]


DEFAULT_ACTIONS = [
    {
        "code": "replace_ssd_now",
        "name": "Экстренно заменить SSD",
        "description": "Немедленная замена диска при высоком риске деградации RAID/SSD.",
        "constraints_json": {
            "metric_codes": ["storcli_predictive_failure_count", "storcli_drive_wear_percent", "storcli_drive_temperature"],
            "metric_groups": ["disk", "degradation", "temperature"],
            "source_models": ["sarima", "lstm", "ensemble"],
            "metric_match_mode": "any",
            "reversibility_penalty": 0.92,
            "automation_level": 0.25,
        },
    },
    {
        "code": "replace_ssd_in_window",
        "name": "Планово заменить SSD в окно",
        "description": "Замена диска в регламентное окно, если риск высокий, но не аварийный.",
        "constraints_json": {
            "metric_codes": ["storcli_predictive_failure_count", "storcli_drive_wear_percent", "storcli_drive_temperature"],
            "metric_groups": ["disk", "degradation", "temperature"],
            "source_models": ["sarima", "lstm", "ensemble"],
            "metric_match_mode": "any",
            "requires_maintenance_window": True,
            "maintenance_start_hour": 22,
            "maintenance_end_hour": 6,
            "reversibility_penalty": 0.72,
            "automation_level": 0.35,
        },
    },
    {
        "code": "run_disk_diagnostics",
        "name": "Запустить глубокую диагностику дисков",
        "description": "Углубленная проверка SMART/RAID, сбор дополнительной диагностики перед заменой.",
        "constraints_json": {
            "metric_codes": ["storcli_predictive_failure_count", "storcli_drive_wear_percent", "storcli_drive_temperature"],
            "metric_groups": ["disk", "degradation"],
            "source_models": ["sarima", "lstm", "ensemble"],
            "metric_match_mode": "any",
            "reversibility_penalty": 0.18,
            "automation_level": 0.76,
        },
    },
    {
        "code": "live_migration",
        "name": "Live migration нагрузки",
        "description": "Перенос критичной нагрузки на резервный узел без длительного простоя.",
        "constraints_json": {
            "metric_groups": ["cpu", "memory", "network", "temperature", "disk"],
            "source_models": ["sarima", "lstm", "ensemble"],
            "metric_match_mode": "any",
            "requires_reserve_host": True,
            "reversibility_penalty": 0.30,
            "automation_level": 0.70,
        },
    },
    {
        "code": "failover_to_backup_host",
        "name": "Фейловер на резервный хост",
        "description": "Аварийное переключение сервиса на заранее подготовленный резерв.",
        "constraints_json": {
            "metric_groups": ["cpu", "memory", "network", "temperature", "disk", "degradation"],
            "source_models": ["sarima", "lstm", "ensemble"],
            "metric_match_mode": "any",
            "requires_reserve_host": True,
            "reversibility_penalty": 0.45,
            "automation_level": 0.55,
        },
    },
    {
        "code": "rebalance_cluster_load",
        "name": "Ребалансировать нагрузку кластера",
        "description": "Перераспределить нагрузку между узлами, чтобы снизить локальный перегрев/перегрузку.",
        "constraints_json": {
            "metric_groups": ["cpu", "memory", "network"],
            "source_models": ["sarima", "lstm", "ensemble"],
            "metric_match_mode": "any",
            "reversibility_penalty": 0.24,
            "automation_level": 0.66,
        },
    },
    {
        "code": "throttle_cpu_limit",
        "name": "Ограничить CPU/частоту",
        "description": "Временно снизить CPU-нагрузку для стабилизации температуры и риска отказа.",
        "constraints_json": {
            "metric_codes": ["cpu_load_total", "system_temperature"],
            "metric_groups": ["cpu", "temperature"],
            "source_models": ["sarima", "lstm", "ensemble"],
            "metric_match_mode": "any",
            "reversibility_penalty": 0.14,
            "automation_level": 0.82,
        },
    },
    {
        "code": "restart_memory_services",
        "name": "Перезапустить memory-heavy сервисы",
        "description": "Точечный перезапуск процессов с утечками/пиковым потреблением RAM.",
        "constraints_json": {
            "metric_codes": ["mem_usage_percent"],
            "metric_groups": ["memory"],
            "source_models": ["sarima", "lstm", "ensemble"],
            "metric_match_mode": "any",
            "reversibility_penalty": 0.22,
            "automation_level": 0.62,
        },
    },
    {
        "code": "tune_memory_capacity",
        "name": "Расширить/перенастроить память",
        "description": "Изменить memory limits, tune swappiness или увеличить выделенную память.",
        "constraints_json": {
            "metric_codes": ["mem_usage_percent"],
            "metric_groups": ["memory"],
            "source_models": ["sarima", "lstm", "ensemble"],
            "metric_match_mode": "any",
            "requires_maintenance_window": True,
            "maintenance_start_hour": 22,
            "maintenance_end_hour": 6,
            "reversibility_penalty": 0.52,
            "automation_level": 0.45,
        },
    },
    {
        "code": "isolate_network_path",
        "name": "Изолировать проблемный сетевой путь",
        "description": "Переключить маршрут/интерфейс, исключить деградирующий network path.",
        "constraints_json": {
            "metric_codes": ["ping_latency_gateway", "net_bytes_sent", "net_bytes_recv"],
            "metric_groups": ["network"],
            "source_models": ["sarima", "lstm", "ensemble"],
            "metric_match_mode": "any",
            "reversibility_penalty": 0.34,
            "automation_level": 0.60,
        },
    },
    {
        "code": "apply_network_qos",
        "name": "Применить QoS/троттлинг сети",
        "description": "Ограничить/приоритизировать трафик для стабилизации задержек и потерь.",
        "constraints_json": {
            "metric_codes": ["ping_latency_gateway", "net_bytes_sent", "net_bytes_recv"],
            "metric_groups": ["network"],
            "source_models": ["sarima", "lstm", "ensemble"],
            "metric_match_mode": "any",
            "reversibility_penalty": 0.20,
            "automation_level": 0.80,
        },
    },
    {
        "code": "boost_cooling",
        "name": "Усилить охлаждение",
        "description": "Повысить профиль вентиляторов/проверить воздушный поток и пыль.",
        "constraints_json": {
            "metric_codes": ["system_temperature", "storcli_drive_temperature"],
            "metric_groups": ["temperature", "disk"],
            "source_models": ["sarima", "lstm", "ensemble"],
            "metric_match_mode": "any",
            "reversibility_penalty": 0.24,
            "automation_level": 0.55,
        },
    },
    {
        "code": "patch_firmware_drivers",
        "name": "Обновить firmware/драйверы",
        "description": "Плановое обновление firmware, драйверов и low-level зависимостей.",
        "constraints_json": {
            "metric_groups": ["cpu", "memory", "network", "temperature", "disk", "degradation"],
            "source_models": ["sarima", "lstm", "ensemble"],
            "metric_match_mode": "any",
            "requires_maintenance_window": True,
            "maintenance_start_hour": 22,
            "maintenance_end_hour": 6,
            "reversibility_penalty": 0.66,
            "automation_level": 0.36,
        },
    },
    {
        "code": "emergency_maintenance_now",
        "name": "Экстренное обслуживание немедленно",
        "description": "Срочное обслуживание без ожидания окна при критическом риске.",
        "constraints_json": {
            "metric_groups": ALL_METRIC_GROUPS,
            "source_models": ["sarima", "lstm", "ensemble"],
            "metric_match_mode": "any",
            "reversibility_penalty": 0.82,
            "automation_level": 0.22,
        },
    },
    {
        "code": "defer_to_night",
        "name": "Отложить до ночного окна",
        "description": "Перенести обслуживание в ближайшее регламентное окно.",
        "constraints_json": {
            "metric_groups": ALL_METRIC_GROUPS,
            "source_models": ["sarima", "lstm", "ensemble"],
            "metric_match_mode": "any",
            "requires_maintenance_window": True,
            "maintenance_start_hour": 22,
            "maintenance_end_hour": 6,
            "reversibility_penalty": 0.30,
            "automation_level": 0.50,
        },
    },
    {
        "code": "no_action",
        "name": "Наблюдение без вмешательства",
        "description": "Не менять конфигурацию, усилить мониторинг и контроль риска.",
        "constraints_json": {
            "metric_groups": ALL_METRIC_GROUPS,
            "source_models": ["sarima", "lstm", "ensemble"],
            "metric_match_mode": "any",
            "reversibility_penalty": 0.05,
            "automation_level": 0.95,
        },
    },
]

DEFAULT_CRITERIA = [
    {
        "code": "reliability",
        "name": "Надежность",
        "description": "Снижение вероятности отказа и ущерба в S0/S1/S2.",
        "default_priority": 0.25,
    },
    {
        "code": "sla",
        "name": "Доступность (SLA)",
        "description": "Минимизация простоя и влияния на доступность сервисов.",
        "default_priority": 0.19,
    },
    {
        "code": "time_to_recover",
        "name": "Скорость восстановления",
        "description": "Сколько времени требуется, чтобы вернуть систему в рабочий режим.",
        "default_priority": 0.15,
    },
    {
        "code": "cost",
        "name": "Стоимость",
        "description": "Прямые финансовые затраты на выполнение действия.",
        "default_priority": 0.14,
    },
    {
        "code": "ops_load",
        "name": "Трудозатраты команды",
        "description": "Нагрузка на инженеров эксплуатации.",
        "default_priority": 0.10,
    },
    {
        "code": "reversibility",
        "name": "Обратимость изменения",
        "description": "Насколько легко откатить действие, если эффект оказался нежелательным.",
        "default_priority": 0.09,
    },
    {
        "code": "automation_level",
        "name": "Автоматизируемость",
        "description": "Насколько действие можно выполнить скриптом/оркестратором без ручных ошибок.",
        "default_priority": 0.08,
    },
]

DEFAULT_POLICY_LOSS_PROFILES = {
    "replace_ssd_now": {
        "base": {"loss_s0": 29_000, "loss_s1": 21_000, "loss_s2": 15_000, "fixed_cost": 18_000, "downtime_minutes": 45, "ops_effort": 0.80},
        "scale_7d": (1.03, 1.15, 1.20),
        "scale_30d": (1.08, 1.28, 1.35),
        "notes": "Экстренная замена: дорогая в S0, но наиболее эффективна против риска деградации диска.",
    },
    "replace_ssd_in_window": {
        "base": {"loss_s0": 18_000, "loss_s1": 16_500, "loss_s2": 24_000, "fixed_cost": 13_000, "downtime_minutes": 30, "ops_effort": 0.60},
        "scale_7d": (1.05, 1.20, 1.55),
        "scale_30d": (1.10, 1.35, 2.00),
        "notes": "Плановая замена: баланс стоимости и риска, но в S2 медленнее экстренной.",
    },
    "run_disk_diagnostics": {
        "base": {"loss_s0": 5_000, "loss_s1": 9_000, "loss_s2": 42_000, "fixed_cost": 3_500, "downtime_minutes": 5, "ops_effort": 0.30},
        "scale_7d": (1.00, 1.35, 1.75),
        "scale_30d": (1.05, 1.70, 2.60),
        "notes": "Диагностика: дешева в S0, но не устраняет физическую деградацию при S2.",
    },
    "live_migration": {
        "base": {"loss_s0": 12_000, "loss_s1": 9_500, "loss_s2": 11_000, "fixed_cost": 7_000, "downtime_minutes": 12, "ops_effort": 0.55},
        "scale_7d": (1.04, 1.18, 1.30),
        "scale_30d": (1.09, 1.35, 1.65),
        "notes": "Live migration: снижает риск остановки сервиса за счет переноса нагрузки.",
    },
    "failover_to_backup_host": {
        "base": {"loss_s0": 14_000, "loss_s1": 11_000, "loss_s2": 9_000, "fixed_cost": 8_500, "downtime_minutes": 15, "ops_effort": 0.65},
        "scale_7d": (1.06, 1.20, 1.28),
        "scale_30d": (1.12, 1.38, 1.62),
        "notes": "Фейловер: дороже в S0, но эффективен при высоких рисках по нескольким метрикам.",
    },
    "rebalance_cluster_load": {
        "base": {"loss_s0": 7_000, "loss_s1": 8_500, "loss_s2": 26_000, "fixed_cost": 4_200, "downtime_minutes": 3, "ops_effort": 0.35},
        "scale_7d": (1.02, 1.30, 1.55),
        "scale_30d": (1.06, 1.65, 2.20),
        "notes": "Ребаланс: хорошо при перегрузках CPU/RAM, хуже при физической деградации оборудования.",
    },
    "throttle_cpu_limit": {
        "base": {"loss_s0": 2_600, "loss_s1": 6_200, "loss_s2": 28_000, "fixed_cost": 1_200, "downtime_minutes": 0, "ops_effort": 0.20},
        "scale_7d": (1.00, 1.35, 1.65),
        "scale_30d": (1.02, 1.80, 2.35),
        "notes": "CPU throttling: быстрый стабилизатор, но не устраняет корневую причину на длинном горизонте.",
    },
    "restart_memory_services": {
        "base": {"loss_s0": 4_300, "loss_s1": 7_200, "loss_s2": 35_000, "fixed_cost": 2_400, "downtime_minutes": 8, "ops_effort": 0.30},
        "scale_7d": (1.01, 1.30, 1.70),
        "scale_30d": (1.05, 1.75, 2.45),
        "notes": "Перезапуск сервисов: краткосрочно снижает риск RAM, но не заменяет архитектурные изменения.",
    },
    "tune_memory_capacity": {
        "base": {"loss_s0": 11_000, "loss_s1": 9_000, "loss_s2": 18_000, "fixed_cost": 6_000, "downtime_minutes": 10, "ops_effort": 0.45},
        "scale_7d": (1.05, 1.20, 1.35),
        "scale_30d": (1.10, 1.40, 1.80),
        "notes": "Тюнинг памяти: эффективен на средних/длинных горизонтах при системной нехватке RAM.",
    },
    "isolate_network_path": {
        "base": {"loss_s0": 7_000, "loss_s1": 7_600, "loss_s2": 14_000, "fixed_cost": 3_800, "downtime_minutes": 4, "ops_effort": 0.35},
        "scale_7d": (1.03, 1.22, 1.40),
        "scale_30d": (1.08, 1.45, 1.95),
        "notes": "Изоляция маршрута: эффективна при деградации latency/throughput.",
    },
    "apply_network_qos": {
        "base": {"loss_s0": 3_400, "loss_s1": 5_900, "loss_s2": 22_000, "fixed_cost": 1_800, "downtime_minutes": 0, "ops_effort": 0.25},
        "scale_7d": (1.00, 1.30, 1.60),
        "scale_30d": (1.04, 1.70, 2.25),
        "notes": "QoS: быстро и дешево, но в S2 может быть недостаточно без смены топологии.",
    },
    "boost_cooling": {
        "base": {"loss_s0": 4_500, "loss_s1": 7_000, "loss_s2": 17_000, "fixed_cost": 2_500, "downtime_minutes": 2, "ops_effort": 0.30},
        "scale_7d": (1.01, 1.26, 1.45),
        "scale_30d": (1.05, 1.58, 2.10),
        "notes": "Охлаждение: снижает термориск, особенно полезно при совмещенных рисках CPU+Disk.",
    },
    "patch_firmware_drivers": {
        "base": {"loss_s0": 10_000, "loss_s1": 9_000, "loss_s2": 21_000, "fixed_cost": 4_500, "downtime_minutes": 25, "ops_effort": 0.50},
        "scale_7d": (1.04, 1.18, 1.35),
        "scale_30d": (1.10, 1.35, 1.90),
        "notes": "Firmware/driver patch: полезен для устойчивости, но требует контролируемого окна работ.",
    },
    "emergency_maintenance_now": {
        "base": {"loss_s0": 22_000, "loss_s1": 14_000, "loss_s2": 12_000, "fixed_cost": 9_000, "downtime_minutes": 35, "ops_effort": 0.70},
        "scale_7d": (1.05, 1.18, 1.25),
        "scale_30d": (1.12, 1.35, 1.55),
        "notes": "Экстренное обслуживание: оправдано при критическом риске, но дорого и инвазивно в S0.",
    },
    "defer_to_night": {
        "base": {"loss_s0": 5_500, "loss_s1": 13_000, "loss_s2": 65_000, "fixed_cost": 3_000, "downtime_minutes": 20, "ops_effort": 0.30},
        "scale_7d": (1.02, 1.35, 1.90),
        "scale_30d": (1.08, 1.95, 3.30),
        "notes": "Отложенное вмешательство: приемлемо в S0/S1, крайне рискованно при S2.",
    },
    "no_action": {
        "base": {"loss_s0": 800, "loss_s1": 22_000, "loss_s2": 220_000, "fixed_cost": 0, "downtime_minutes": 0, "ops_effort": 0.08},
        "scale_7d": (1.00, 1.70, 1.95),
        "scale_30d": (1.10, 2.60, 3.90),
        "notes": "Наблюдение без вмешательства: дешево при S0, но резко увеличивает потери при S2.",
    },
}


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return min(hi, max(lo, float(v)))


def _as_float(value, default=0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return float(default)
    if not math.isfinite(out):
        return float(default)
    return out


def _build_default_loss_row(action_code: str, horizon: str) -> dict:
    profile = DEFAULT_POLICY_LOSS_PROFILES.get(str(action_code or "").strip())
    if not profile:
        return {
            "loss_s0": 0.0,
            "loss_s1": 0.0,
            "loss_s2": 0.0,
            "fixed_cost": 0.0,
            "downtime_minutes": 0.0,
            "ops_effort": 0.0,
            "notes": "Профиль стоимости не задан, заполните вручную.",
        }

    base = profile.get("base") or {}
    s0 = _as_float(base.get("loss_s0"), 0.0)
    s1 = _as_float(base.get("loss_s1"), 0.0)
    s2 = _as_float(base.get("loss_s2"), 0.0)

    scale = (1.0, 1.0, 1.0)
    if horizon == "7d":
        scale = profile.get("scale_7d") or scale
    elif horizon == "30d":
        scale = profile.get("scale_30d") or scale

    return {
        "loss_s0": round(s0 * _as_float(scale[0], 1.0), 2),
        "loss_s1": round(s1 * _as_float(scale[1], 1.0), 2),
        "loss_s2": round(s2 * _as_float(scale[2], 1.0), 2),
        "fixed_cost": round(_as_float(base.get("fixed_cost"), 0.0), 2),
        "downtime_minutes": round(_as_float(base.get("downtime_minutes"), 0.0), 2),
        "ops_effort": round(_as_float(base.get("ops_effort"), 0.0), 3),
        "notes": str(profile.get("notes") or ""),
    }


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        out = [str(item).strip().lower() for item in value if str(item).strip()]
        return out
    if isinstance(value, str):
        out = [item.strip().lower() for item in value.split(",") if item.strip()]
        return out
    return []


def _metric_groups_for_code(metric_code: str) -> set[str]:
    raw = str(metric_code or "").strip().lower()
    groups: set[str] = set()
    if "cpu" in raw:
        groups.add("cpu")
    if raw.startswith("mem_") or "memory" in raw:
        groups.add("memory")
    if raw.startswith("net_") or "network" in raw or "ping" in raw or "latency" in raw:
        groups.add("network")
    if "disk" in raw or "ssd" in raw or "nvme" in raw or "storcli" in raw:
        groups.add("disk")
    if "temp" in raw or "temperature" in raw:
        groups.add("temperature")
    if "wear" in raw or "tbw" in raw or "predictive_failure" in raw:
        groups.add("degradation")
    if not groups:
        groups.add("other")
    return groups


def _extract_risk_context(
    *,
    risk_payload: dict | None,
    horizon: str,
    min_risk: float,
    min_contribution: float,
    top_k_fallback: int,
) -> dict:
    payload = risk_payload if isinstance(risk_payload, dict) else {}
    horizon_rows = payload.get("horizons") if isinstance(payload.get("horizons"), list) else []
    row = None
    for candidate in horizon_rows:
        if str(candidate.get("horizon") or "") == str(horizon):
            row = candidate
            break
    if row is None and horizon_rows:
        row = horizon_rows[0]
    if row is None:
        row = {}

    metrics = row.get("metrics") if isinstance(row.get("metrics"), list) else []
    normalized = []
    for item in metrics:
        code = str(item.get("metric_code") or "").strip().lower()
        if not code:
            continue
        risk = _as_float(item.get("risk"), 0.0)
        contribution = _as_float(item.get("contribution"), 0.0)
        normalized.append({
            "metric_code": code,
            "risk": risk,
            "contribution": contribution,
            "method": item.get("method"),
            "risk_level": item.get("risk_level"),
            "groups": sorted(_metric_groups_for_code(code)),
        })

    normalized.sort(key=lambda x: (_as_float(x["risk"], 0.0), _as_float(x["contribution"], 0.0)), reverse=True)

    selected = [
        item
        for item in normalized
        if _as_float(item.get("risk"), 0.0) >= float(min_risk)
        or _as_float(item.get("contribution"), 0.0) >= float(min_contribution)
    ]
    if not selected:
        selected = normalized[:max(1, int(top_k_fallback))]

    active_codes = [item["metric_code"] for item in selected]
    active_groups: set[str] = set()
    for item in selected:
        active_groups.update(item.get("groups") or [])

    return {
        "horizon": row.get("horizon") or horizon,
        "model_kind_used": str(row.get("model_kind_used") or "unknown"),
        "run_id_used": row.get("run_id_used"),
        "min_risk_gate": float(min_risk),
        "min_contribution_gate": float(min_contribution),
        "active_metric_codes": active_codes,
        "active_metric_groups": sorted(active_groups),
        "active_metrics": selected,
        "all_metrics_ranked": normalized,
    }


def _action_matches_risk_context(action: DecisionAction, risk_context: dict) -> tuple[bool, list[str], dict]:
    constraints = action.constraints_json if isinstance(action.constraints_json, dict) else {}

    configured_metric_codes = _as_list(constraints.get("metric_codes"))
    configured_metric_groups = _as_list(constraints.get("metric_groups"))
    configured_source_models = _as_list(constraints.get("source_models"))
    metric_match_mode = str(constraints.get("metric_match_mode") or "any").strip().lower()
    if metric_match_mode not in {"any", "all"}:
        metric_match_mode = "any"

    active_codes = {str(item).strip().lower() for item in (risk_context.get("active_metric_codes") or []) if str(item).strip()}
    active_groups = {str(item).strip().lower() for item in (risk_context.get("active_metric_groups") or []) if str(item).strip()}
    source_model = str(risk_context.get("model_kind_used") or "").strip().lower()

    reasons: list[str] = []
    relevant = True

    if configured_source_models and source_model and source_model not in set(configured_source_models):
        relevant = False
        reasons.append(f"Источник прогноза '{source_model}' не входит в source_models действия.")

    # Strict behavior for dissertation workflow:
    # when risk context already points to active metrics, actions without explicit
    # metric binding are excluded from recommendation ranking.
    if active_codes and not configured_metric_codes and not configured_metric_groups:
        relevant = False
        reasons.append("Действие не привязано к риск-метрикам (metric_codes/metric_groups).")

    if configured_metric_codes:
        configured_set = set(configured_metric_codes)
        if metric_match_mode == "all":
            ok = configured_set.issubset(active_codes)
        else:
            ok = bool(configured_set.intersection(active_codes))
        if not ok:
            relevant = False
            reasons.append("Действие не связано с активными риск-метриками.")

    if configured_metric_groups:
        configured_group_set = set(configured_metric_groups)
        if metric_match_mode == "all":
            ok = configured_group_set.issubset(active_groups)
        else:
            ok = bool(configured_group_set.intersection(active_groups))
        if not ok:
            relevant = False
            reasons.append("Группа действия не совпадает с группами активных риск-метрик.")

    meta = {
        "has_metric_binding": bool(configured_metric_codes or configured_metric_groups),
        "has_source_binding": bool(configured_source_models),
        "metric_match_mode": metric_match_mode,
        "configured_metric_codes": configured_metric_codes,
        "configured_metric_groups": configured_metric_groups,
        "configured_source_models": configured_source_models,
        "active_metric_codes": sorted(active_codes),
        "active_metric_groups": sorted(active_groups),
        "source_model_used": source_model,
    }
    return relevant, reasons, meta


def bootstrap_decision_defaults(*, created_by=None):
    actions = {}
    for row in DEFAULT_ACTIONS:
        obj, _ = DecisionAction.objects.update_or_create(
            code=row["code"],
            defaults={
                "name": row["name"],
                "description": row["description"],
                "constraints_json": row["constraints_json"],
                "is_active": True,
            },
        )
        actions[obj.code] = obj

    criteria = {}
    for row in DEFAULT_CRITERIA:
        obj, _ = DecisionCriterion.objects.update_or_create(
            code=row["code"],
            defaults={
                "name": row["name"],
                "description": row["description"],
                "is_active": True,
            },
        )
        criteria[obj.code] = obj

    defaults = []
    for horizon in ("24h", "7d", "30d"):
        policy_name = f"Базовая политика СППР ({horizon})"
        legacy_horizon_names = [
            f"Базовая политика КСППР ({horizon})",
            f"Базовая политика СППР ({horizon})",
            "Базовая политика КСППР",
            "Базовая политика СППР",
        ]
        policy = (
            DecisionPolicy.objects
            .filter(
                scope="global",
                horizon=horizon,
                version=1,
                name__in=legacy_horizon_names,
            )
            .order_by("id")
            .first()
        )
        if policy is None:
            policy = DecisionPolicy.objects.create(
                name=policy_name,
                version=1,
                horizon=horizon,
                scope="global",
                is_active=True,
                notes="Автоматически созданная базовая политика.",
                created_by=created_by,
            )
        else:
            changed = False
            if policy.name != policy_name:
                policy.name = policy_name
                changed = True
            if not policy.is_active:
                policy.is_active = True
                changed = True
            if "базовая" not in str(policy.notes or "").lower():
                policy.notes = "Автоматически созданная базовая политика."
                changed = True
            if changed:
                policy.save(update_fields=["name", "is_active", "notes", "updated_at"])

        defaults.append(policy)
        _ensure_policy_loss_defaults(policy, actions)
        _ensure_policy_ahp_defaults(policy, criteria)
    return defaults


def _ensure_policy_loss_defaults(policy: DecisionPolicy, actions: dict[str, DecisionAction]):
    for code, action in actions.items():
        row = _build_default_loss_row(code, policy.horizon)
        DecisionPolicyLoss.objects.update_or_create(
            policy=policy,
            action=action,
            defaults=row,
        )


def _ensure_policy_ahp_defaults(policy: DecisionPolicy, criteria: dict[str, DecisionCriterion]):
    priorities = {str(row["code"]): _as_float(row.get("default_priority"), 1.0) for row in DEFAULT_CRITERIA}
    criteria_codes = [code for code in priorities if code in criteria]
    for i, ci in enumerate(criteria_codes):
        for cj in criteria_codes[i + 1:]:
            wi = max(1e-9, _as_float(priorities.get(ci), 1.0))
            wj = max(1e-9, _as_float(priorities.get(cj), 1.0))
            ratio = wi / wj
            value = round(_clamp(ratio, 1 / 9, 9.0), 4)
            DecisionPolicyAHPPairwise.objects.update_or_create(
                policy=policy,
                criterion_i=criteria[ci],
                criterion_j=criteria[cj],
                defaults={"value": value},
            )


def _select_policy(*, device: Device, horizon: str, policy_id: int | None = None) -> DecisionPolicy:
    if policy_id:
        row = DecisionPolicy.objects.filter(id=policy_id).first()
        if not row:
            raise RuntimeError("Policy not found")
        return row

    qs = DecisionPolicy.objects.filter(is_active=True, horizon=horizon)
    by_device = qs.filter(scope="device", device=device).order_by("-version", "-id").first()
    if by_device:
        return by_device
    by_type = qs.filter(scope="device_type", device_type=device.device_type).order_by("-version", "-id").first()
    if by_type:
        return by_type
    by_global = qs.filter(scope="global").order_by("-version", "-id").first()
    if by_global:
        return by_global
    # Auto-bootstrap if nothing configured yet.
    defaults = bootstrap_decision_defaults()
    for row in defaults:
        if row.horizon == horizon:
            return row
    return defaults[0]


def _latest_metric_value(device: Device, code: str) -> float | None:
    row = (
        RawMetric.objects
        .filter(device=device, code=code)
        .order_by("-timestamp", "-id")
        .first()
    )
    if not row:
        return None
    try:
        return float(row.value)
    except Exception:
        return None


def _check_constraints(device: Device, action: DecisionAction) -> tuple[bool, list[str]]:
    constraints = action.constraints_json if isinstance(action.constraints_json, dict) else {}
    reasons = []
    allowed = True

    if constraints.get("requires_reserve_host"):
        reserve = _latest_metric_value(device, "reserve_host_available")
        if reserve is None or reserve < 0.5:
            allowed = False
            reasons.append("Нет подтверждения доступности резервного хоста.")

    if constraints.get("requires_maintenance_window"):
        now_hour = __import__("datetime").datetime.now().hour
        start_h = int(constraints.get("maintenance_start_hour", 22))
        end_h = int(constraints.get("maintenance_end_hour", 6))
        in_window = now_hour >= start_h or now_hour < end_h
        if not in_window:
            allowed = False
            reasons.append("Сейчас не окно регламентного обслуживания.")

    return allowed, reasons


def _risk_probabilities(device: Device, horizon: str, overall_weight_markov: float = 0.65) -> dict:
    payload = evaluate_risk_assessment(
        device_id=device.id,
        horizons=[horizon],
        preferred_model_kind="auto",
        overall_weight_markov=_clamp(overall_weight_markov, 0.0, 1.0),
    )
    horizons = payload.get("horizons") or []
    if not horizons:
        return {
            "p_s0": 0.34,
            "p_s1": 0.33,
            "p_s2": 0.33,
            "p_s0_current": 0.34,
            "p_s1_current": 0.33,
            "p_s2_current": 0.33,
            "overall_risk": 0.33,
            "markov_projected_p_s2": 0.33,
            "metric_aggregate_risk": 0.33,
            "state_probability_source": "fallback",
            "risk_payload": payload,
        }

    def _state_probs(raw: dict | None) -> tuple[float | None, float | None, float | None]:
        row_raw = raw if isinstance(raw, dict) else {}
        p0 = _as_float(row_raw.get("s0"), None)
        p1 = _as_float(row_raw.get("s1"), None)
        p2 = _as_float(row_raw.get("s2"), None)
        if p0 is None or p1 is None or p2 is None:
            return None, None, None
        p0 = _clamp(p0)
        p1 = _clamp(p1)
        p2 = _clamp(p2)
        total = p0 + p1 + p2
        if total <= 1e-12:
            return None, None, None
        return p0 / total, p1 / total, p2 / total

    row = horizons[0]
    current = row.get("current_state") if isinstance(row.get("current_state"), dict) else {}
    projected = row.get("projected_state") if isinstance(row.get("projected_state"), dict) else {}
    p0_current, p1_current, p2_current = _state_probs(current)
    p0_projected, p1_projected, p2_projected = _state_probs(projected)
    use_projected = p0_projected is not None and p1_projected is not None and p2_projected is not None
    p0 = p0_projected if use_projected else (p0_current if p0_current is not None else 0.34)
    p1 = p1_projected if use_projected else (p1_current if p1_current is not None else 0.33)
    p2 = p2_projected if use_projected else (p2_current if p2_current is not None else 0.33)

    return {
        "p_s0": p0,
        "p_s1": p1,
        "p_s2": p2,
        "p_s0_current": p0_current if p0_current is not None else 0.34,
        "p_s1_current": p1_current if p1_current is not None else 0.33,
        "p_s2_current": p2_current if p2_current is not None else 0.33,
        "overall_risk": _as_float(row.get("overall_risk"), 0.33),
        "markov_projected_p_s2": _as_float(row.get("markov_projected_p_s2"), 0.33),
        "metric_aggregate_risk": _as_float(row.get("metric_aggregate_risk"), 0.33),
        "state_probability_source": "projected_state" if use_projected else "current_state",
        "risk_payload": payload,
    }


def _normalize_inverse(values: dict[int, float]) -> dict[int, float]:
    if not values:
        return {}
    xs = list(values.values())
    lo = min(xs)
    hi = max(xs)
    if hi - lo <= 1e-9:
        return {k: 1.0 for k in values}
    out = {}
    for k, v in values.items():
        out[k] = _clamp(1.0 - ((v - lo) / (hi - lo)))
    return out


@dataclass
class AhpResult:
    criteria: list[DecisionCriterion]
    matrix: list[list[float]]
    weights: dict[str, float]
    lambda_max: float
    ci: float
    cr: float
    is_consistent: bool


def _build_ahp(policy: DecisionPolicy) -> AhpResult:
    criteria = list(DecisionCriterion.objects.filter(is_active=True).order_by("id"))
    if not criteria:
        raise RuntimeError("No active criteria configured")

    idx = {c.id: i for i, c in enumerate(criteria)}
    n = len(criteria)
    a = [[1.0 if i == j else 1.0 for j in range(n)] for i in range(n)]

    pairs = DecisionPolicyAHPPairwise.objects.filter(policy=policy, criterion_i_id__in=idx, criterion_j_id__in=idx)
    for row in pairs:
        i = idx[row.criterion_i_id]
        j = idx[row.criterion_j_id]
        if i == j:
            continue
        v = max(1e-9, _as_float(row.value, 1.0))
        a[i][j] = v
        a[j][i] = 1.0 / v

    # power iteration
    w = [1.0 / n for _ in range(n)]
    for _ in range(120):
        nw = [sum(a[i][j] * w[j] for j in range(n)) for i in range(n)]
        s = sum(nw)
        if s <= 0:
            break
        nw = [x / s for x in nw]
        diff = sum(abs(nw[i] - w[i]) for i in range(n))
        w = nw
        if diff < 1e-10:
            break

    aw = [sum(a[i][j] * w[j] for j in range(n)) for i in range(n)]
    ratios = [aw[i] / w[i] for i in range(n) if w[i] > 1e-12]
    lambda_max = sum(ratios) / len(ratios) if ratios else float(n)
    ci = 0.0 if n <= 1 else max(0.0, (lambda_max - n) / (n - 1))
    ri = RI_TABLE.get(n, 1.49)
    cr = 0.0 if ri <= 1e-12 else ci / ri
    weights = {criteria[i].code: _clamp(w[i], 0.0, 1.0) for i in range(n)}
    s = sum(weights.values())
    if s > 0:
        weights = {k: v / s for k, v in weights.items()}
    return AhpResult(
        criteria=criteria,
        matrix=a,
        weights=weights,
        lambda_max=lambda_max,
        ci=ci,
        cr=cr,
        is_consistent=cr <= CR_THRESHOLD,
    )


def get_policy_ahp_matrix(policy: DecisionPolicy) -> dict:
    ahp = _build_ahp(policy)
    return {
        "policy_id": policy.id,
        "criteria": [{"id": c.id, "code": c.code, "name": c.name} for c in ahp.criteria],
        "matrix": ahp.matrix,
        "weights": ahp.weights,
        "lambda_max": ahp.lambda_max,
        "ci": ahp.ci,
        "cr": ahp.cr,
        "is_consistent": ahp.is_consistent,
        "cr_threshold": CR_THRESHOLD,
    }


def upsert_policy_ahp_pairs(policy: DecisionPolicy, pairs: list[dict]):
    ids = set(DecisionCriterion.objects.filter(is_active=True).values_list("id", flat=True))
    for row in pairs:
        ci = int(row["criterion_i"])
        cj = int(row["criterion_j"])
        if ci not in ids or cj not in ids:
            raise RuntimeError("Invalid criterion id in pairwise matrix")
        if ci == cj:
            continue
        val = max(1e-9, _as_float(row.get("value"), 1.0))
        crit_i = DecisionCriterion.objects.get(id=ci)
        crit_j = DecisionCriterion.objects.get(id=cj)
        DecisionPolicyAHPPairwise.objects.update_or_create(
            policy=policy,
            criterion_i=crit_i,
            criterion_j=crit_j,
            defaults={"value": val},
        )


def validate_policy_ahp(policy: DecisionPolicy) -> dict:
    return get_policy_ahp_matrix(policy)


def _criterion_penalty(criterion_code: str, loss_row: DecisionPolicyLoss, probs: dict) -> float:
    constraints = loss_row.action.constraints_json if isinstance(loss_row.action.constraints_json, dict) else {}
    if criterion_code == "reliability":
        return (
            probs["p_s0"] * _as_float(loss_row.loss_s0, 0.0)
            + probs["p_s1"] * _as_float(loss_row.loss_s1, 0.0)
            + probs["p_s2"] * _as_float(loss_row.loss_s2, 0.0)
        )
    if criterion_code == "sla":
        return max(0.0, _as_float(loss_row.downtime_minutes, 0.0))
    if criterion_code == "time_to_recover":
        return max(0.0, _as_float(loss_row.downtime_minutes, 0.0) + 45.0 * _as_float(loss_row.ops_effort, 0.0))
    if criterion_code == "cost":
        return max(0.0, _as_float(loss_row.fixed_cost, 0.0))
    if criterion_code == "ops_load":
        return max(0.0, _as_float(loss_row.ops_effort, 0.0))
    if criterion_code == "reversibility":
        return _clamp(_as_float(constraints.get("reversibility_penalty"), 0.5), 0.0, 1.0)
    if criterion_code == "automation_level":
        return 1.0 - _clamp(_as_float(constraints.get("automation_level"), 0.5), 0.0, 1.0)
    return 0.0


def _resolve_device(*, serial: str | None, device_id: int | None) -> Device:
    qs = Device.objects.all()
    if serial:
        qs = qs.filter(serial_number=serial)
    if device_id:
        qs = qs.filter(id=device_id)
    row = qs.first()
    if not row:
        raise RuntimeError("Device not found")
    return row


@transaction.atomic
def run_decision_recommendation(
    *,
    serial: str | None = None,
    device_id: int | None = None,
    horizon: str = "24h",
    policy_id: int | None = None,
    mode: str = "bayes",
    user=None,
    bayes_weight: float = 0.5,
    ahp_weight: float = 0.5,
    sensitivity_weights: dict | None = None,
    overall_weight_markov: float = 0.65,
    risk_metric_min_risk: float = 0.08,
    risk_metric_min_contribution: float = 0.03,
    risk_metric_top_k_fallback: int = 3,
) -> DecisionRun:
    device = _resolve_device(serial=serial, device_id=device_id)
    policy = _select_policy(device=device, horizon=horizon, policy_id=policy_id)
    losses = list(DecisionPolicyLoss.objects.filter(policy=policy).select_related("action"))
    if not losses:
        bootstrap_decision_defaults(created_by=user)
        losses = list(DecisionPolicyLoss.objects.filter(policy=policy).select_related("action"))
    if not losses:
        raise RuntimeError("Policy has no actions/loss rows")

    risk = _risk_probabilities(device, horizon, overall_weight_markov=overall_weight_markov)
    probs = {"p_s0": risk["p_s0"], "p_s1": risk["p_s1"], "p_s2": risk["p_s2"]}
    risk_context = _extract_risk_context(
        risk_payload=risk.get("risk_payload"),
        horizon=horizon,
        min_risk=_clamp(risk_metric_min_risk, 0.0, 1.0),
        min_contribution=_clamp(risk_metric_min_contribution, 0.0, 1.0),
        top_k_fallback=max(1, int(risk_metric_top_k_fallback)),
    )
    critical_risk_mode = (
        _as_float(risk.get("overall_risk"), 0.0) >= CRITICAL_RISK_THRESHOLD
        or _as_float(risk.get("markov_projected_p_s2"), 0.0) >= CRITICAL_RISK_THRESHOLD
    )

    expected_loss_map = {}
    action_allowed = {}
    excluded_reasons = {}
    action_relevance = {}
    for row in losses:
        action = row.action
        infra_allowed, infra_reasons = _check_constraints(device, action)
        relevance_allowed, relevance_reasons, relevance_meta = _action_matches_risk_context(action, risk_context)
        action_relevance[action.id] = relevance_meta
        allowed = bool(infra_allowed and relevance_allowed)
        reasons = list(infra_reasons) + list(relevance_reasons)
        if critical_risk_mode and action.code == "no_action":
            allowed = False
            reasons.append("При критическом риске no_action отключено автоматически.")
        action_allowed[action.id] = allowed
        excluded_reasons[action.id] = reasons
        expected_loss_map[action.id] = (
            probs["p_s0"] * _as_float(row.loss_s0, 0.0)
            + probs["p_s1"] * _as_float(row.loss_s1, 0.0)
            + probs["p_s2"] * _as_float(row.loss_s2, 0.0)
            + _as_float(row.fixed_cost, 0.0)
        )

    bayes_util_map = _normalize_inverse(expected_loss_map)

    ahp_result = _build_ahp(policy)
    weights = dict(ahp_result.weights)
    if sensitivity_weights:
        tmp = {}
        for key, value in (sensitivity_weights or {}).items():
            if key in weights:
                tmp[key] = max(0.0, _as_float(value, 0.0))
        if tmp and sum(tmp.values()) > 0:
            s = sum(tmp.values())
            weights = {k: v / s for k, v in tmp.items()}

    criteria_codes = [c.code for c in ahp_result.criteria]
    criterion_penalty_maps = {code: {} for code in criteria_codes}
    for row in losses:
        for code in criteria_codes:
            criterion_penalty_maps[code][row.action_id] = _criterion_penalty(code, row, probs)

    criterion_util_maps = {code: _normalize_inverse(vals) for code, vals in criterion_penalty_maps.items()}
    ahp_util_map = {}
    for row in losses:
        score = 0.0
        for code in criteria_codes:
            score += _as_float(weights.get(code), 0.0) * _as_float(criterion_util_maps.get(code, {}).get(row.action_id), 0.0)
        ahp_util_map[row.action_id] = _clamp(score)

    wb = max(0.0, _as_float(bayes_weight, 0.5))
    wa = max(0.0, _as_float(ahp_weight, 0.5))
    if mode != "advanced":
        wb, wa = 1.0, 0.0
    else:
        s = wb + wa
        if s <= 1e-12:
            wb, wa = 0.5, 0.5
        else:
            wb, wa = wb / s, wa / s

    final_scores = {}
    for row in losses:
        action_id = row.action_id
        final_scores[action_id] = wb * _as_float(bayes_util_map.get(action_id), 0.0) + wa * _as_float(ahp_util_map.get(action_id), 0.0)

    allowed_items = [row for row in losses if action_allowed.get(row.action_id)]
    any_metric_bound = any((action_relevance.get(row.action_id) or {}).get("has_metric_binding") for row in losses)
    any_source_bound = any((action_relevance.get(row.action_id) or {}).get("has_source_binding") for row in losses)

    if not allowed_items and (any_metric_bound or any_source_bound):
        raise RuntimeError(
            "Нет действий, связанных с активными риск-метриками/источником прогноза. "
            "Настройте привязки действий в Настройках СППР (metric_codes / metric_groups / source_models)."
        )
    if not allowed_items:
        allowed_items = list(losses)

    ranked = sorted(
        allowed_items,
        key=lambda row: (-_as_float(final_scores.get(row.action_id), 0.0), _as_float(expected_loss_map.get(row.action_id), 0.0)),
    )
    recommended = ranked[0].action if ranked else losses[0].action

    run = DecisionRun.objects.create(
        device=device,
        policy=policy,
        horizon=horizon,
        mode="advanced" if mode == "advanced" else "bayes",
        status="success",
        risk_snapshot={
            "p_s0": probs["p_s0"],
            "p_s1": probs["p_s1"],
            "p_s2": probs["p_s2"],
            "p_s0_current": risk.get("p_s0_current"),
            "p_s1_current": risk.get("p_s1_current"),
            "p_s2_current": risk.get("p_s2_current"),
            "state_probability_source": risk.get("state_probability_source"),
            "overall_risk": risk["overall_risk"],
            "markov_projected_p_s2": risk["markov_projected_p_s2"],
            "metric_aggregate_risk": risk["metric_aggregate_risk"],
            "risk_payload": risk.get("risk_payload"),
        },
        recommended_action=recommended,
        explanation={
            "mode": mode,
            "bayes_formula": "R(a_i)=sum_j P(S_j|X_t)*L(a_i,S_j)",
            "final_formula": (
                "score=bayes_utility" if mode != "advanced"
                else "score=w_bayes*bayes_utility + w_ahp*ahp_utility"
            ),
            "weights": {"w_bayes": wb, "w_ahp": wa},
            "risk_context": risk_context,
            "ahp_consistency": {
                "lambda_max": ahp_result.lambda_max,
                "ci": ahp_result.ci,
                "cr": ahp_result.cr,
                "threshold": CR_THRESHOLD,
                "is_consistent": ahp_result.is_consistent,
            },
        },
        created_by=user,
    )

    score_rows = []
    for row in losses:
        action_id = row.action_id
        score_rows.append({
            "action": row.action,
            "expected_loss": _as_float(expected_loss_map.get(action_id), 0.0),
            "bayes_utility": _as_float(bayes_util_map.get(action_id), 0.0),
            "ahp_utility": _as_float(ahp_util_map.get(action_id), 0.0),
            "final_score": _as_float(final_scores.get(action_id), 0.0),
            "allowed": action_allowed.get(action_id, True),
            "excluded_reasons": excluded_reasons.get(action_id, []),
        })

    score_rows.sort(key=lambda item: (-item["allowed"], -item["final_score"], item["expected_loss"]))
    rank = 1
    for item in score_rows:
        DecisionRunScore.objects.create(
            run=run,
            action=item["action"],
            expected_loss=item["expected_loss"],
            bayes_utility=item["bayes_utility"],
            ahp_utility=item["ahp_utility"],
            final_score=item["final_score"],
            rank=rank,
            is_recommended=item["action"].id == recommended.id,
            explanation={
                "allowed": item["allowed"],
                "excluded_reasons": item["excluded_reasons"],
                "relevance": action_relevance.get(item["action"].id) or {},
                "inputs": {
                    "p_s0": probs["p_s0"],
                    "p_s1": probs["p_s1"],
                    "p_s2": probs["p_s2"],
                    "p_s0_current": risk.get("p_s0_current"),
                    "p_s1_current": risk.get("p_s1_current"),
                    "p_s2_current": risk.get("p_s2_current"),
                    "state_probability_source": risk.get("state_probability_source"),
                    "loss_s0": _as_float(next(r for r in losses if r.action_id == item["action"].id).loss_s0),
                    "loss_s1": _as_float(next(r for r in losses if r.action_id == item["action"].id).loss_s1),
                    "loss_s2": _as_float(next(r for r in losses if r.action_id == item["action"].id).loss_s2),
                },
            },
        )
        rank += 1

    if mode == "advanced":
        DecisionRunAHP.objects.create(
            run=run,
            weights=weights,
            lambda_max=ahp_result.lambda_max,
            ci=ahp_result.ci,
            cr=ahp_result.cr,
            is_consistent=ahp_result.is_consistent,
            matrix=ahp_result.matrix,
        )
        util_batch = []
        criterion_map = {c.code: c for c in ahp_result.criteria}
        for row in losses:
            for code in criteria_codes:
                criterion = criterion_map.get(code)
                if not criterion:
                    continue
                util_batch.append(
                    DecisionRunUtility(
                        run=run,
                        action=row.action,
                        criterion=criterion,
                        utility=_as_float(criterion_util_maps.get(code, {}).get(row.action_id), 0.0),
                        evidence={
                            "criterion_code": code,
                            "penalty": _as_float(criterion_penalty_maps.get(code, {}).get(row.action_id), 0.0),
                        },
                    )
                )
        if util_batch:
            DecisionRunUtility.objects.bulk_create(util_batch, batch_size=200)

    return run


@transaction.atomic
def create_decision_feedback(
    *,
    run: DecisionRun,
    actual_action_id: int | None,
    outcome_state: str,
    outage_minutes: float,
    incident_cost: float,
    notes: str,
    user=None,
) -> DecisionFeedback:
    actual_action = DecisionAction.objects.filter(id=actual_action_id).first() if actual_action_id else None
    feedback, _ = DecisionFeedback.objects.update_or_create(
        run=run,
        defaults={
            "actual_action": actual_action,
            "outcome_state": outcome_state,
            "outage_minutes": max(0.0, _as_float(outage_minutes, 0.0)),
            "incident_cost": max(0.0, _as_float(incident_cost, 0.0)),
            "notes": notes or "",
            "created_by": user,
        },
    )
    return feedback
