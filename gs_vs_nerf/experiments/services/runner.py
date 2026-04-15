from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from shutil import which

from django.conf import settings
from django.utils import timezone

from experiments.models import ExperimentRun, Metric
from experiments.services.artifacts import collect_artifacts
from experiments.services.metrics import collect_metrics

logger = logging.getLogger(__name__)


class NerfstudioRunner:
    def __init__(self) -> None:
        self.bin_name = getattr(settings, "NERFSTUDIO_BIN", "ns-train")

    def _build_process_env(self) -> dict[str, str]:
        """Build process environment forcing UTF-8 I/O for subprocess execution."""
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env.setdefault("TERM", "xterm-256color")
        return env

    def run(self, run: ExperimentRun) -> ExperimentRun:
        """Launch ns-train, capture logs, and persist final status."""
        output_base = Path(settings.MEDIA_ROOT) / "runs"
        output_base.mkdir(parents=True, exist_ok=True)

        run.ensure_output_dir(output_base)
        Path(run.output_dir).mkdir(parents=True, exist_ok=True)

        # Validate dataset path before building command
        try:
            self._validate_dataset_path(run)
        except ValueError as exc:
            error_msg = f"Dataset validation failed: {exc}"
            logger.error("[Run %s] %s", run.pk, error_msg)
            run.mark_finished(success=False, error_message=error_msg)
            run.stderr_log = error_msg
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "stderr_log", "finished_at", "error_message"])
            return run

        command = self._build_command(run)
        run.command = self._command_to_string(command)
        run.stdout_log = ""
        run.stderr_log = ""
        run.error_message = ""
        run.save(update_fields=["output_dir", "command", "stdout_log", "stderr_log", "error_message"])

        logger.info("[Run %s] Launching: %s", run.pk, run.command)

        process_env = self._build_process_env()

        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".stdout") as stdout_file:
            with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".stderr") as stderr_file:
                stdout_path = Path(stdout_file.name)
                stderr_path = Path(stderr_file.name)

        completed_process: subprocess.CompletedProcess[str] | None = None
        try:
            completed_process = subprocess.run(
                command,
                cwd=str(Path(run.output_dir).parent),
                env=process_env,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )
        except Exception as exc:
            error_msg = f"Exception during process start: {exc}"
            logger.exception("[Run %s] %s", run.pk, error_msg)
            run.mark_finished(success=False, error_message=error_msg)
            run.stderr_log = error_msg
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "stderr_log", "finished_at", "error_message"])
            stdout_path.unlink(missing_ok=True)
            stderr_path.unlink(missing_ok=True)
            return run

        run.mark_running()
        run.save(update_fields=["status", "started_at", "error_message"])

        stdout_text = completed_process.stdout or ""
        stderr_text = completed_process.stderr or ""
        stdout_path.write_text(stdout_text, encoding="utf-8", errors="replace")
        stderr_path.write_text(stderr_text, encoding="utf-8", errors="replace")

        returncode = completed_process.returncode

        stdout_log = self._read_text(stdout_path)
        stderr_log = self._read_text(stderr_path)
        if stdout_log:
            run.stdout_log = stdout_log
        if stderr_log:
            run.stderr_log = stderr_log

        logger.info("[Run %s] Process finished with code: %s", run.pk, returncode)

        if returncode == 0:
            run.mark_finished(success=True)
            logger.info("[Run %s] Collecting metrics and artifacts...", run.pk)
            try:
                collect_metrics(run)
            except Exception as exc:
                logger.exception("[Run %s] Error collecting metrics: %s", run.pk, exc)
            try:
                collect_artifacts(run)
            except Exception as exc:
                logger.exception("[Run %s] Error collecting artifacts: %s", run.pk, exc)
        else:
            error_message = self._build_failure_message(returncode, stderr_log)
            run.mark_finished(success=False, error_message=error_message)
            logger.error("[Run %s] Error: %s", run.pk, run.error_message)

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

        stdout_path.unlink(missing_ok=True)
        stderr_path.unlink(missing_ok=True)

        elapsed = (run.finished_at - run.started_at).total_seconds() if run.started_at and run.finished_at else 0
        Metric.objects.create(run=run, name="duration_sec", value=elapsed, step=0)
        logger.info("[Run %s] Completed in %.1fs", run.pk, elapsed)
        return run

    def _validate_dataset_path(self, run: ExperimentRun) -> None:
        """Validate that dataset path exists and contains images."""
        dataset_path = Path(run.dataset.data_path)
        logger.debug("[_validate_dataset_path] Checking dataset at: %s", dataset_path)

        if not dataset_path.exists():
            raise ValueError(f"Dataset path does not exist: {dataset_path}")

        if not dataset_path.is_dir():
            raise ValueError(f"Dataset path is not a directory: {dataset_path}")

        # Check for images in 'images/' subdirectory or in root
        images_dir = dataset_path / "images"
        image_extensions = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".exr"}

        images_found = []
        if images_dir.exists() and images_dir.is_dir():
            images_found = [f for f in images_dir.iterdir() if f.suffix.lower() in image_extensions]

        if not images_found:
            # Check in root directory as fallback
            images_found = [f for f in dataset_path.iterdir() if f.is_file() and f.suffix.lower() in image_extensions]

        if not images_found:
            raise ValueError(
                f"Dataset contains no images. Checked: {images_dir} and root of {dataset_path}"
            )

        logger.info("[_validate_dataset_path] Dataset validated: %d images found", len(images_found))

    def _normalize_dataset_path(self, raw_path: str) -> str:
        """Normalize dataset path: resolve to absolute and convert backslash to forward slash."""
        path = Path(raw_path)
        try:
            resolved = path.resolve()
            # Convert backslash to forward slash for ns-train compatibility on Windows
            normalized = str(resolved).replace("\\", "/")
            logger.debug("[_normalize_dataset_path] %s -> %s", raw_path, normalized)
            return normalized
        except Exception as exc:
            logger.warning("[_normalize_dataset_path] Failed to resolve %s: %s", raw_path, exc)
            return str(raw_path).replace("\\", "/")

    def _command_to_string(self, command: list[str]) -> str:
        return subprocess.list2cmdline(command)

    def _read_text(self, path: Path) -> str:
        if not path.exists():
            return ""
        try:
            return path.read_bytes().decode("utf-8", errors="replace")
        except Exception as exc:
            logger.warning("[_read_text] Failed to read %s: %s", path, exc)
            return ""

    def _build_failure_message(self, returncode: int, stderr_log: str) -> str:
        stderr_tail = stderr_log.strip().splitlines()[-1] if stderr_log.strip() else ""
        if stderr_tail:
            return f"ns-train failed with exit code {returncode}. stderr: {stderr_tail}"
        return f"ns-train failed with exit code {returncode}"

    def _build_command(self, run: ExperimentRun) -> list[str]:
        pipeline = run.pipeline_type.value if hasattr(run.pipeline_type, "value") else str(run.pipeline_type)
        cfg = run.config_json or {}
        binary = self._resolve_binary()
        dataset_path = self._normalize_dataset_path(str(run.dataset.data_path))
        output_path = str(Path(run.output_dir).resolve()).replace("\\", "/")

        logger.debug("[_build_command] Dataset: %s", dataset_path)
        logger.debug("[_build_command] Output: %s", output_path)

        cmd = [
            binary,
            pipeline,
            "--data",
            dataset_path,
            "--output-dir",
            output_path,
            "--vis",
            "viewer_legacy",
        ]

        if "max_num_iterations" in cfg:
            cmd.extend(["--max-num-iterations", str(cfg["max_num_iterations"])])

        if "downscale_factor" in cfg:
            cmd.extend(["--pipeline.datamanager.camera-res-scale-factor", str(cfg["downscale_factor"])])

        return cmd

    def _resolve_binary(self) -> str:
        candidate = Path(self.bin_name)
        if candidate.exists():
            return str(candidate)

        resolved = which(str(self.bin_name))
        if resolved:
            return resolved

        return self.bin_name
