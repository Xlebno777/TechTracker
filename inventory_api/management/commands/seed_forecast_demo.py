from django.core.management.base import BaseCommand

from inventory_api.forecasting.demo_seed import seed_demo_forecasts


class Command(BaseCommand):
    help = "Seed synthetic forecast/state data for UI validation."

    def add_arguments(self, parser):
        parser.add_argument("--serial", type=str, help="Only for this device serial")
        parser.add_argument("--runs", type=int, default=1, help="How many runs per device")
        parser.add_argument("--clear", action="store_true", help="Delete previous demo data first")
        parser.add_argument("--no-raw-history", action="store_true", help="Do not generate synthetic raw metrics history")
        parser.add_argument("--raw-history-days", type=int, default=30, help="Synthetic raw history depth in days")

    def handle(self, *args, **options):
        payload = seed_demo_forecasts(
            serial=options.get("serial"),
            runs=options.get("runs") or 1,
            clear_existing=bool(options.get("clear")),
            with_raw_history=not bool(options.get("no_raw_history")),
            raw_history_days=max(1, int(options.get("raw_history_days") or 30)),
        )
        self.stdout.write(self.style.SUCCESS(str(payload)))
