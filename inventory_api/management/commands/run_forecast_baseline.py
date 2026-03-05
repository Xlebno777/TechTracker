from django.core.management.base import BaseCommand

from inventory_api.forecasting.baseline_service import run_baseline_forecasts


class Command(BaseCommand):
    help = "Run local preprocessing + SARIMA baseline and save ForecastRun/ForecastPoint/StateEstimate."

    def add_arguments(self, parser):
        parser.add_argument("--serial", type=str, help="Only for this device serial")
        parser.add_argument("--lookback-days", type=int, default=60)
        parser.add_argument("--freq", type=str, default="1h")
        parser.add_argument("--horizons", type=str, default="24h,7d,30d")
        parser.add_argument("--metric-codes", type=str, default="")
        parser.add_argument("--no-stl-components", action="store_true")

    def handle(self, *args, **options):
        horizons = [h.strip() for h in (options.get("horizons") or "").split(",") if h.strip()]
        metric_codes = [m.strip() for m in (options.get("metric_codes") or "").split(",") if m.strip()]

        payload = run_baseline_forecasts(
            serial=options.get("serial"),
            lookback_days=max(1, int(options.get("lookback_days") or 60)),
            freq=options.get("freq") or "1h",
            horizons=horizons or None,
            metric_codes=metric_codes or None,
            save_stl_components=not bool(options.get("no_stl_components")),
        )
        self.stdout.write(self.style.SUCCESS(str(payload)))
