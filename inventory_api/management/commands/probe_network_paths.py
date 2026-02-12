from django.core.management.base import BaseCommand, CommandError

from inventory_api.network_probe import run_network_probe


class Command(BaseCommand):
    help = "Проверяет сетевые пути (NetworkPath) и пишет результаты в RawMetric/NetworkOutage."

    def add_arguments(self, parser):
        parser.add_argument('--path-id', type=int, default=None, help='Проверить только один NetworkPath по ID')
        parser.add_argument('--no-store', action='store_true', help='Не записывать метрики в RawMetric (только обновить состояние)')
        parser.add_argument('--respect-interval', action='store_true', help='Учитывать interval_sec каждого пути')

    def handle(self, *args, **options):
        path_id = options.get('path_id')
        store_metrics = not options.get('no_store', False)
        respect_interval = options.get('respect_interval', False)

        try:
            stats = run_network_probe(path_id=path_id, save_metrics=store_metrics, respect_interval=respect_interval)
        except Exception as exc:
            raise CommandError(f'Probe failed: {exc}')

        self.stdout.write(self.style.SUCCESS(
            "ok "
            f"checked={stats['checked']} "
            f"skipped={stats['skipped']} "
            f"interval_skipped={stats['interval_skipped']} "
            f"up={stats['up']} "
            f"down={stats['down']} "
            f"opened={stats['outages_opened']} "
            f"closed={stats['outages_closed']} "
            f"metrics={stats['metrics_created']}"
        ))
