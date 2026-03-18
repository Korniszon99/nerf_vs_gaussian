from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from experiments.models import ExperimentRun
from experiments.services.runner import NerfstudioRunner


class Command(BaseCommand):
    help = "Uruchamia pojedynczy run eksperymentu synchronicznie"

    def add_arguments(self, parser):
        parser.add_argument("run_id", type=int)

    def handle(self, *args, **options):
        run_id = options["run_id"]
        try:
            run = ExperimentRun.objects.select_related("dataset").get(pk=run_id)
        except ExperimentRun.DoesNotExist as exc:
            raise CommandError(f"Run {run_id} nie istnieje") from exc

        self.stdout.write(self.style.NOTICE(f"Start run {run_id}: {run.pipeline_type}"))
        NerfstudioRunner().run(run)
        run.refresh_from_db()
        self.stdout.write(self.style.SUCCESS(f"Koniec. Status: {run.status}"))

