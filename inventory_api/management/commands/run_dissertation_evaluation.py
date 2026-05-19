from django.core.management.base import BaseCommand

from inventory_api.forecasting.evaluation_service import run_dissertation_evaluation


class Command(BaseCommand):
    help = (
        "Build dissertation evaluation artifacts: RMSE/MAE by forecast model and "
        "economic delta-R from decision runs."
    )

    def add_arguments(self, parser):
        parser.add_argument("--serial", type=str, help="Only evaluate this device serial")
        parser.add_argument("--days-back", type=int, default=120, help="How many days back to include")
        parser.add_argument("--horizons", type=str, default="24h,7d,30d", help="Comma-separated horizons")
        parser.add_argument("--model-kinds", type=str, default="sarima,lstm,ensemble", help="Comma-separated model kinds")
        parser.add_argument("--baseline-action-code", type=str, default="no_action", help="Action code used as reactive baseline for delta-R")
        parser.add_argument("--output-dir", type=str, default="research/evaluation", help="Directory where artifacts are written")
        parser.add_argument("--tag", type=str, default="", help="Optional suffix for run folder name")
        parser.add_argument(
            "--strict-intersection",
            type=int,
            default=1,
            help="Use only keys where all selected models have fact data (1/0)",
        )
        parser.add_argument(
            "--enable-stat-tests",
            type=int,
            default=1,
            help="Enable DM-tests and bootstrap CI (1/0)",
        )
        parser.add_argument(
            "--bootstrap-samples",
            type=int,
            default=300,
            help="Bootstrap iterations for CI metrics (50..2000)",
        )
        parser.add_argument(
            "--bootstrap-block-size",
            type=int,
            default=0,
            help="Moving-block length L for bootstrap (0 = auto)",
        )

    def handle(self, *args, **options):
        horizons = [h.strip() for h in str(options.get("horizons") or "").split(",") if h.strip()]
        model_kinds = [m.strip() for m in str(options.get("model_kinds") or "").split(",") if m.strip()]

        payload = run_dissertation_evaluation(
            serial=options.get("serial") or None,
            days_back=max(1, int(options.get("days_back") or 120)),
            horizons=horizons or None,
            model_kinds=model_kinds or None,
            baseline_action_code=options.get("baseline_action_code") or "no_action",
            output_dir=options.get("output_dir") or "research/evaluation",
            tag=options.get("tag") or None,
            strict_intersection=bool(int(options.get("strict_intersection", 1))),
            enable_stat_tests=bool(int(options.get("enable_stat_tests", 1))),
            bootstrap_samples=max(50, min(2000, int(options.get("bootstrap_samples") or 300))),
            bootstrap_block_size=(
                max(2, int(options.get("bootstrap_block_size")))
                if int(options.get("bootstrap_block_size") or 0) > 0 else None
            ),
        )

        self.stdout.write(self.style.SUCCESS("Dissertation evaluation completed"))
        self.stdout.write(self.style.SUCCESS(str(payload)))
