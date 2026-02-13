from django.core.management.base import BaseCommand

from inventory_api.network_map_builder import build_network_map_snapshot


class Command(BaseCommand):
    help = "Строит снимок автокарты сети (по связности NetworkPath)."

    def add_arguments(self, parser):
        parser.add_argument('--window-hours', type=int, default=24, help='Окно анализа reachability (часы), default=24')
        parser.add_argument('--keep-last', type=int, default=720, help='Сколько последних снимков хранить, default=720')

    def handle(self, *args, **options):
        payload = build_network_map_snapshot(
            window_hours=options['window_hours'],
            keep_last=options['keep_last'],
        )

        if payload.get('status') != 'ok':
            self.stderr.write(self.style.ERROR(f"Network map build failed: {payload.get('error') or 'unknown error'}"))
            return

        self.stdout.write(self.style.SUCCESS(
            "Network map snapshot built: "
            f"id={payload.get('snapshot_id')} "
            f"nodes={payload.get('node_count')} "
            f"edges={payload.get('edge_count')} "
            f"duration_ms={payload.get('build_duration_ms')}"
        ))
