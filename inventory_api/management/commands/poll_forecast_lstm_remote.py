from django.core.management.base import BaseCommand
import time

from inventory_api.forecasting.lstm_remote_service import poll_lstm_remote_runs


class Command(BaseCommand):
    help = "Poll remote LSTM jobs and import completed forecasts into DB."

    def add_arguments(self, parser):
        parser.add_argument("--run-id", type=int, help="Check only this ForecastRun id")
        parser.add_argument("--serial", type=str, help="Check only this device serial")
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument("--poll-interval-sec", type=float, default=10.0)
        parser.add_argument("--daemon", action="store_true", help="Run forever and poll queue repeatedly")
        parser.add_argument("--idle-sleep-sec", type=float, default=15.0, help="Sleep between daemon poll cycles")

    def handle(self, *args, **options):
        limit = max(1, int(options.get("limit") or 20))
        poll_interval_sec = max(1.0, float(options.get("poll_interval_sec") or 10.0))

        def run_once():
            return poll_lstm_remote_runs(
                run_id=options.get("run_id"),
                serial=options.get("serial"),
                limit=limit,
                poll_interval_sec=poll_interval_sec,
            )

        if not options.get("daemon"):
            payload = run_once()
            self.stdout.write(self.style.SUCCESS(str(payload)))
            return

        idle_sleep_sec = max(1.0, float(options.get("idle_sleep_sec") or 15.0))
        self.stdout.write(self.style.SUCCESS("Starting LSTM remote poll daemon"))
        while True:
            payload = run_once()
            self.stdout.write(str(payload))
            time.sleep(idle_sleep_sec)
