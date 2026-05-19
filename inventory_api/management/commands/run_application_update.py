from django.core.management.base import BaseCommand, CommandError

from inventory_api.release_management import run_update_job


class Command(BaseCommand):
    help = "Runs a queued TechTracker application update job."

    def add_arguments(self, parser):
        parser.add_argument("--job-id", type=int, required=True)

    def handle(self, *args, **options):
        job_id = options["job_id"]
        try:
            job = run_update_job(job_id)
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"Update job {job.id} finished with status {job.status}"))
