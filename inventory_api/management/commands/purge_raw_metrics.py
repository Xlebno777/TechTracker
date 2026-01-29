from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from inventory_api.models import MonitoringSetting, RawMetric, Device


class Command(BaseCommand):
    help = "Удаляет сырые метрики старше retention_days для каждого устройства."

    def add_arguments(self, parser):
        parser.add_argument(
            '--default-days',
            type=int,
            default=365,
            help='Retention по умолчанию, если для устройства нет настроек.'
        )

    def handle(self, *args, **options):
        default_days = options['default_days']
        now = timezone.now()
        total_deleted = 0

        settings_map = {
            s.device_id: s.retention_days
            for s in MonitoringSetting.objects.all()
        }

        for device in Device.objects.all().only('id'):
            retention_days = settings_map.get(device.id, default_days)
            cutoff = now - timedelta(days=retention_days)
            deleted, _ = RawMetric.objects.filter(device=device, timestamp__lt=cutoff).delete()
            total_deleted += deleted

        self.stdout.write(self.style.SUCCESS(f"Deleted {total_deleted} raw metrics."))
