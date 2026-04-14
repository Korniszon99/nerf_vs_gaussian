from __future__ import annotations

import logging
import subprocess
import threading
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from experiments.models import ExperimentRun, Metric
from experiments.services.artifacts import collect_artifacts
from experiments.services.metrics import collect_metrics

logger = logging.getLogger(__name__)


class NerfstudioRunner:
    def __init__(self) -> None:
        self.bin_name = getattr(settings, "NERFSTUDIO_BIN", "ns-train")

    def run(self, run: ExperimentRun) -> ExperimentRun:
        """
        Uruchamia ns-train asynchronicznie i streamuje stdout/stderr.

        Flow:
        1. Ustaw status=running, started_at=now()
        2. Uruchom subprocess z Popen (nie run())
        3. Czytaj stdout/stderr równolegle (wątki) — unikamy deadlocka przy pełnych buforach
        4. Po zakończeniu: finished_at, duration, metryki, artefakty
        """
        output_base = Path(settings.MEDIA_ROOT) / "runs"
        output_base.mkdir(parents=True, exist_ok=True)

        run.ensure_output_dir(output_base)
        # Utwórz katalog wyjściowy przed uruchomieniem procesu
        Path(run.output_dir).mkdir(parents=True, exist_ok=True)

        command = self._build_command(run)
        run.command = " ".join(command)
        run.mark_running()
        run.save(update_fields=["output_dir", "command", "status", "started_at", "error_message"])

        logger.info(f"[Run {run.pk}] Uruchamiam: {' '.join(command)}")

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
            )

            # Czytaj stdout i stderr równolegle żeby uniknąć deadlocka przy pełnych buforach
            def _drain_stdout() -> None:
                assert process.stdout is not None
                for line in iter(process.stdout.readline, ""):
                    if line:
                        stdout_lines.append(line)
                        logger.debug(f"[Run {run.pk}] STDOUT: {line.rstrip()}")
                        if len(stdout_lines) % 10 == 0:
                            run.stdout_log = "".join(stdout_lines)
                            run.save(update_fields=["stdout_log"])

            def _drain_stderr() -> None:
                assert process.stderr is not None
                for line in iter(process.stderr.readline, ""):
                    if line:
                        stderr_lines.append(line)
                        logger.debug(f"[Run {run.pk}] STDERR: {line.rstrip()}")

            t_out = threading.Thread(target=_drain_stdout, daemon=True)
            t_err = threading.Thread(target=_drain_stderr, daemon=True)
            t_out.start()
            t_err.start()
            t_out.join()
            t_err.join()

            returncode = process.wait()
            run.stdout_log = "".join(stdout_lines)
            run.stderr_log = "".join(stderr_lines)

            logger.info(f"[Run {run.pk}] Proces zakończony z kodem: {returncode}")

            if returncode == 0:
                run.mark_finished(success=True)
                logger.info(f"[Run {run.pk}] Zbieranie metryk i artefaktów...")
                collect_metrics(run)
                collect_artifacts(run)
            else:
                run.mark_finished(success=False, error_message=f"ns-train exit code: {returncode}")
                logger.error(f"[Run {run.pk}] Błąd: {run.error_message}")

        except Exception as exc:
            run.mark_finished(success=False, error_message=str(exc))
            run.stderr_log = f"Exception: {exc}\n" + "".join(stderr_lines)
            logger.error(f"[Run {run.pk}] Exception: {exc}", exc_info=True)

        run.finished_at = timezone.now()
        run.save(
            update_fields=[
                "status",
                "stdout_log",
                "stderr_log",
                "finished_at",
                "error_message",
            ]
        )

        elapsed = (run.finished_at - run.started_at).total_seconds() if run.started_at and run.finished_at else 0
        Metric.objects.create(run=run, name="duration_sec", value=elapsed, step=0)
        logger.info(f"[Run {run.pk}] Ukończono w {elapsed:.1f}s")
        return run

    def _build_command(self, run: ExperimentRun) -> list[str]:
        pipeline = run.pipeline_type
        cfg = run.config_json or {}
        cmd = [
            self.bin_name,
            pipeline,
            "--data",
            run.dataset.data_path,
            "--output-dir",
            run.output_dir,
            "--vis",
            "none",  # Wyłącz viewer — nie potrzebny w trybie batch
        ]

        if "max_num_iterations" in cfg:
            cmd.extend(["--trainer.max-num-iterations", str(cfg["max_num_iterations"])])

        if "downscale_factor" in cfg:
            cmd.extend(["--pipeline.datamanager.camera-res-scale-factor", str(cfg["downscale_factor"])])

        return cmd