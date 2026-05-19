from django.core.management.base import BaseCommand

from inventory_api.forecasting.lstm_remote_service import run_lstm_remote_forecasts


class Command(BaseCommand):
    help = "Submit forecast jobs to remote LSTM service and optionally wait for results."

    def add_arguments(self, parser):
        parser.add_argument("--serial", type=str, help="Only for this device serial")
        parser.add_argument("--lookback-days", type=int, default=60)
        parser.add_argument("--freq", type=str, default="1h")
        parser.add_argument("--horizons", type=str, default="24h,7d,30d")
        parser.add_argument("--metric-codes", type=str, default="")
        parser.add_argument("--no-wait", action="store_true", help="Do not wait for terminal job status")
        parser.add_argument("--poll-interval-sec", type=float, default=2.0)
        parser.add_argument("--max-wait-sec", type=float, default=120.0)
        parser.add_argument("--max-retries", type=int, default=5)

    def handle(self, *args, **options):
        horizons = [h.strip() for h in (options.get("horizons") or "").split(",") if h.strip()]
        metric_codes = [m.strip() for m in (options.get("metric_codes") or "").split(",") if m.strip()]

        payload = run_lstm_remote_forecasts(
            serial=options.get("serial"),
            lookback_days=max(1, int(options.get("lookback_days") or 60)),
            freq=options.get("freq") or "1h",
            horizons=horizons or None,
            metric_codes=metric_codes or None,
            wait_for_result=not bool(options.get("no_wait")),
            poll_interval_sec=float(options.get("poll_interval_sec") or 2.0),
            max_wait_sec=float(options.get("max_wait_sec") or 120.0),
            max_retries=max(0, int(options.get("max_retries") or 5)),
        )
        self.stdout.write(self.style.SUCCESS(str(payload)))
