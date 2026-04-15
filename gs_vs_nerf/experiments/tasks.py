from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from django.db import transaction

from experiments.models import ExperimentRun
from experiments.services.runner import NerfstudioRunner

logger = logging.getLogger(__name__)
executor = ThreadPoolExecutor(max_workers=2)


def execute_run(run_id: int) -> None:
    run = ExperimentRun.objects.select_related("dataset").get(pk=run_id)
    runner = NerfstudioRunner()
    runner.run(run)


def launch_run_async(run_id: int) -> None:
    def _wrapped_execute() -> None:
        try:
            execute_run(run_id)
        except Exception:
            logger.exception("[Run %s] Failed to execute asynchronous run", run_id)
            try:
                run = ExperimentRun.objects.get(pk=run_id)
                run.mark_finished(success=False, error_message="Failed to start run asynchronously")
                run.save(update_fields=["status", "finished_at", "error_message"])
            except Exception:
                logger.exception("[Run %s] Could not persist async launch failure", run_id)

    transaction.on_commit(lambda: executor.submit(_wrapped_execute))
