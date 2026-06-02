from django.db import migrations


AGENT_METRIC_TASK_NAMES = [
    "cpu_total",
    "cpu_kernel",
    "cpu_interrupts",
    "mem_usage",
    "swap_usage",
    "disk_usage",
    "disk_io",
    "storcli_errors",
    "storcli_temp",
    "net",
    "ping",
    "uptime",
    "process_count",
    "system_temperature",
]


def backfill_service_agents(apps, schema_editor):
    AgentStatus = apps.get_model("inventory_api", "AgentStatus")
    ServiceAgent = apps.get_model("inventory_api", "ServiceAgent")

    for agent_status in AgentStatus.objects.select_related("device").iterator():
        status_value = "error" if agent_status.status == "error" else "online"
        defaults = {
            "name": "TechTracker Agent",
            "installation_type": "legacy",
            "service_name": "TechTrackerAgent",
            "status": status_value,
            "last_status_message": agent_status.message or "",
            "last_seen_at": agent_status.updated_at,
            "metrics_config": {"enabled_tasks": list(AGENT_METRIC_TASK_NAMES)},
            "supported_metrics": list(AGENT_METRIC_TASK_NAMES),
        }
        agent, created = ServiceAgent.objects.get_or_create(
            device_id=agent_status.device_id,
            defaults=defaults,
        )
        if created:
            continue
        if not agent.last_seen_at or agent.last_seen_at < agent_status.updated_at:
            agent.status = status_value
            agent.last_status_message = agent_status.message or ""
            agent.last_seen_at = agent_status.updated_at
            if not agent.metrics_config:
                agent.metrics_config = {"enabled_tasks": list(AGENT_METRIC_TASK_NAMES)}
            if not agent.supported_metrics:
                agent.supported_metrics = list(AGENT_METRIC_TASK_NAMES)
            agent.save(update_fields=[
                "status",
                "last_status_message",
                "last_seen_at",
                "metrics_config",
                "supported_metrics",
                "updated_at",
            ])


class Migration(migrations.Migration):
    dependencies = [
        ("inventory_api", "0030_service_agents"),
    ]

    operations = [
        migrations.RunPython(backfill_service_agents, migrations.RunPython.noop),
    ]
