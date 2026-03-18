from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from experiments.models import ExperimentRun
from experiments.services.runner import NerfstudioRunner

executor = ThreadPoolExecutor(max_workers=2)


def execute_run(run_id: int) -> None:
    run = ExperimentRun.objects.select_related("dataset").get(pk=run_id)
    runner = NerfstudioRunner()
    runner.run(run)


def launch_run_async(run_id: int) -> None:
    executor.submit(execute_run, run_id)

