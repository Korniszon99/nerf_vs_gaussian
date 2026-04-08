from __future__ import annotations

import subprocess
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from experiments.models import ExperimentRun, Metric
from experiments.services.artifacts import collect_artifacts
from experiments.services.metrics import collect_metrics


class NerfstudioRunner:
    def __init__(self) -> None:
        self.bin_name = getattr(settings, "NERFSTUDIO_BIN", "ns-train")

    def run(self, run: ExperimentRun) -> ExperimentRun:
        output_base = Path(settings.MEDIA_ROOT) / "runs"
        output_base.mkdir(parents=True, exist_ok=True)

        run.ensure_output_dir(output_base)
        command = self._build_command(run)
        run.command = " ".join(command)
        run.mark_running()
        run.save(update_fields=["output_dir", "command", "status", "started_at", "error_message"])

        start = timezone.now()
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        run.stdout_log = result.stdout
        run.stderr_log = result.stderr

        if result.returncode == 0:
            run.mark_finished(success=True)
            collect_metrics(run)
            collect_artifacts(run)
        else:
            run.mark_finished(success=False, error_message="Nerfstudio zakończone błędem")

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

        elapsed = (run.finished_at - start).total_seconds()
        Metric.objects.create(run=run, name="duration_sec", value=elapsed, step=0)
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
            "--viewer.quit-on-train-completion",
            "True",
        ]

        if "max_num_iterations" in cfg:
            cmd.extend(["--trainer.max-num-iterations", str(cfg["max_num_iterations"])])

        if "downscale_factor" in cfg:
            cmd.extend(["--pipeline.datamanager.camera-res-scale-factor", str(cfg["downscale_factor"])])

        return cmd

    def _collect_metrics(self, run: ExperimentRun) -> None:
        matches = METRIC_REGEX.findall(run.stdout_log + "\n" + run.stderr_log)
        seen = set()
        for name, value in matches:
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            Metric.objects.create(run=run, name=key, value=float(value), step=0)

        metrics_file = Path(run.output_dir) / "metrics.json"
        if metrics_file.exists():
            payload = json.loads(metrics_file.read_text(encoding="utf-8"))
            for metric_name, metric_value in payload.items():
                if isinstance(metric_value, (int, float)):
                    Metric.objects.get_or_create(
                        run=run,
                        name=metric_name,
                        step=0,
                        defaults={"value": float(metric_value)},
                    )

    def _collect_artifacts(self, run: ExperimentRun) -> None:
        output_dir = Path(run.output_dir)
        if not output_dir.exists():
            return

        for ext in ("*.ply", "*.splat", "*.ckpt", "*.pt", "*.mp4", "*.json"):
            for path in output_dir.rglob(ext):
                if path.name == "metrics.json":
                    continue
                art_type = self._guess_artifact_type(path)
                Artifact.objects.get_or_create(
                    run=run,
                    file_path=str(path),
                    defaults={"artifact_type": art_type, "label": path.name},
                )

    @staticmethod
    def _guess_artifact_type(path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix in {".ply", ".splat"}:
            return Artifact.ArtifactType.POINT_CLOUD
        if suffix in {".ckpt", ".pt"}:
            return Artifact.ArtifactType.CHECKPOINT
        if suffix == ".mp4":
            return Artifact.ArtifactType.RENDER
        if suffix == ".json":
            return Artifact.ArtifactType.LOG
        return Artifact.ArtifactType.MODEL

