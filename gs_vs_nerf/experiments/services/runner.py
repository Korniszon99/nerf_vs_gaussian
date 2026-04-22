from __future__ import annotations

# pyright: reportGeneralTypeIssues=false

import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from shutil import which
from typing import cast

from django.conf import settings
from django.utils import timezone

from experiments.models import ExperimentRun, Metric
from experiments.services.artifacts import collect_artifacts
from experiments.services.metrics import collect_metrics

logger = logging.getLogger(__name__)


class NerfstudioRunner:
    _BLENDER_SPLIT_FILES = ("transforms_train.json", "transforms_test.json", "transforms_val.json")
    _NERFSTUDIO_TRANSFORMS_FILE = "transforms.json"
    _IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".exr"}

    # Map Django model pipeline_type values to actual ns-train subcommand names.
    # vanilla-gaussian-splatting is not a valid ns-train subcommand; splatfacto is.
    _NS_TRAIN_METHOD_MAP: dict[str, str] = {
        "vanilla-gaussian-splatting": "splatfacto",
    }
    _PREPROCESS_SCRIPT_NAME = "preprocess.py"
    _PREPROCESSED_DATASET_DIR_NAME = "preprocessed_dataset"
    _COLMAP_REQUIRED_BASENAMES = ("cameras", "images", "points3D")

    def __init__(self) -> None:
        self.bin_name = str(getattr(settings, "NERFSTUDIO_BIN", "ns-train"))

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

        # Validate/prepare dataset path before building command
        try:
            prepared_dataset_path = self._prepare_dataset_for_run(run)
        except ValueError as exc:
            error_msg = f"Dataset validation failed: {exc}"
            logger.error("[Run %s] %s", run.pk, error_msg)
            run.mark_finished(success=False, error_message=error_msg)
            run.stderr_log = error_msg
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "stderr_log", "finished_at", "error_message"])
            return run

        command = self._ns_train_args_for_dataset(run, str(prepared_dataset_path))
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

    def _prepare_dataset_for_run(self, run: ExperimentRun) -> Path:
        """Validate dataset and auto-generate missing metadata when possible."""
        dataset_path = Path(run.dataset.data_path)
        try:
            self._validate_dataset_path(run)
            logger.info("[Run %s] Preprocessing skipped; required metadata already available.", run.pk)
            return dataset_path
        except ValueError:
            self._validate_dataset_base(dataset_path)
            if not self._pipeline_requires_preprocessing(run):
                raise
            if self._has_required_metadata_for_run(run, dataset_path):
                raise

            logger.info(
                "[Run %s] Missing metadata detected for pipeline '%s'; triggering preprocessing.",
                run.pk,
                self._resolve_pipeline_name(run),
            )

        preprocessed_path, preprocess_status = self._run_preprocess_script(run, dataset_path)
        self._validate_dataset_at_path(run, preprocessed_path)

        logger.info(
            "[Run %s] Preprocessing %s. Using dataset path: %s",
            run.pk,
            preprocess_status,
            preprocessed_path,
        )
        return preprocessed_path

    def _validate_dataset_path(self, run: ExperimentRun) -> None:
        """Validate that dataset path exists and contains images."""
        self._validate_dataset_at_path(run, Path(run.dataset.data_path))

    def _validate_dataset_at_path(self, run: ExperimentRun, dataset_path: Path) -> None:
        """Validate dataset structure and pipeline metadata for a specific path."""
        self._validate_dataset_base(Path(dataset_path))
        self._validate_pipeline_metadata(run, Path(dataset_path))

    def _validate_dataset_base(self, dataset_path: Path) -> None:
        """Validate generic dataset structure and image availability."""
        dataset_path = Path(dataset_path)
        logger.debug("[_validate_dataset_path] Checking dataset at: %s", dataset_path)

        if not dataset_path.exists():
            raise ValueError(f"Dataset path does not exist: {dataset_path}")

        if not dataset_path.is_dir():
            raise ValueError(f"Dataset path is not a directory: {dataset_path}")

        # Check for images in 'images/' subdirectory or in root
        images_dir = dataset_path / "images"
        images_found: list[Path] = []
        if images_dir.exists() and images_dir.is_dir():
            images_found = [f for f in images_dir.iterdir() if f.is_file() and f.suffix.lower() in self._IMAGE_EXTENSIONS]

        if not images_found:
            # Check in root directory as fallback
            images_found = [
                f for f in dataset_path.iterdir() if f.is_file() and f.suffix.lower() in self._IMAGE_EXTENSIONS
            ]

        if images_found:
            logger.info("[_validate_dataset_path] Dataset validated: %d local images found", len(images_found))
            return

        if self._has_valid_transforms_frame_paths(dataset_path):
            logger.info(
                "[_validate_dataset_path] Dataset validated via transforms.json frame file paths (no local images)."
            )
            return

        raise ValueError(
            "Dataset contains no local images and no valid transforms.json frame file paths. "
            f"Checked: {images_dir} and root of {dataset_path}"
        )

    def _has_valid_transforms_frame_paths(self, dataset_path: Path) -> bool:
        """Return True when transforms.json frames reference existing image files."""
        transforms_path = dataset_path / self._NERFSTUDIO_TRANSFORMS_FILE
        if not transforms_path.is_file():
            return False

        try:
            payload = json.loads(transforms_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not parse transforms.json at %s: %s", transforms_path, exc)
            return False

        frames = payload.get("frames")
        if not isinstance(frames, list) or not frames:
            return False

        valid_count = 0
        for frame in frames:
            if not isinstance(frame, dict):
                continue
            file_path_value = frame.get("file_path")
            if not isinstance(file_path_value, str) or not file_path_value:
                continue
            frame_path = Path(file_path_value)
            if not frame_path.is_absolute():
                frame_path = (dataset_path / frame_path).resolve()
            if frame_path.is_file() and frame_path.suffix.lower() in self._IMAGE_EXTENSIONS:
                valid_count += 1

        return valid_count > 0

    def _validate_pipeline_metadata(self, run: ExperimentRun, dataset_path: Path) -> None:
        """Validate pipeline-specific metadata; raise ValueError when required files are missing."""
        raw_pipeline = run.pipeline_type.value if hasattr(run.pipeline_type, "value") else str(run.pipeline_type)
        pipeline = self._NS_TRAIN_METHOD_MAP.get(raw_pipeline, raw_pipeline)

        if pipeline == "vanilla-nerf" and not self._has_blender_layout(dataset_path):
            expected = ", ".join(self._BLENDER_SPLIT_FILES)
            raise ValueError(
                "vanilla-nerf requires Blender metadata files in dataset root: "
                f"{expected}."
            )

        if pipeline == "splatfacto" and not self._has_nerfstudio_layout(dataset_path):
            message = "splatfacto requires Nerfstudio metadata file transforms.json in dataset root."
            if self._has_colmap_layout(dataset_path):
                message += (
                    " Found COLMAP layout (sparse/0), so convert it first with ns-process-data "
                    "to produce transforms.json."
                )
            elif (dataset_path / "sparse" / "0").is_dir():
                missing = ", ".join(self._missing_colmap_files(dataset_path))
                message += (
                    " Found sparse/0 directory but COLMAP outputs are incomplete. "
                    "Expected cameras/images/points3D (.bin or .txt). "
                    f"Missing: {missing}."
                )
            raise ValueError(message)

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
        return " ".join(command)

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
        return self._ns_train_args_for_dataset(run, str(run.dataset.data_path))

    def _ns_train_args_for_dataset(self, run: ExperimentRun, data_dir_str: str) -> list[str]:
        pipeline = self._resolve_pipeline_name(run)
        cfg = run.config_json or {}
        binary = str(self._resolve_binary())
        dataset_path = str(data_dir_str).replace("\\", "/")
        output_path = str(run.output_dir).replace("\\", "/")

        logger.debug("[_build_command] Dataset: %s", dataset_path)
        logger.debug("[_build_command] Output: %s", output_path)

        cmd: list[str] = []
        cmd.append(str(binary))
        cmd.append(str(pipeline))
        cmd.append("--data")
        cmd.append(str(dataset_path))
        cmd.append("--output-dir")
        cmd.append(str(output_path))
        cmd.append("--vis")
        cmd.append("viewer_legacy")

        if "max_num_iterations" in cfg:
            cmd.extend(["--max-num-iterations", str(cfg["max_num_iterations"])])

        if "downscale_factor" in cfg:
            cmd.extend(["--pipeline.datamanager.camera-res-scale-factor", str(cfg["downscale_factor"])])

        return cmd

    def _raw_pipeline_name(self, run: ExperimentRun) -> str:
        """Return the pipeline name as stored in ExperimentRun."""
        return run.pipeline_type.value if hasattr(run.pipeline_type, "value") else str(run.pipeline_type)

    def _resolve_pipeline_name(self, run: ExperimentRun) -> str:
        """Resolve ExperimentRun pipeline name to ns-train method name."""
        raw_pipeline = self._raw_pipeline_name(run)
        return self._NS_TRAIN_METHOD_MAP.get(raw_pipeline, raw_pipeline)


    def _pipeline_requires_preprocessing(self, run: ExperimentRun) -> bool:
        """Return True when pipeline metadata can be auto-generated by preprocess.py."""
        pipeline = self._resolve_pipeline_name(run)
        return pipeline in {"vanilla-nerf", "splatfacto"}

    def _has_required_metadata_for_run(self, run: ExperimentRun, dataset_path: Path) -> bool:
        """Return True when dataset contains required metadata for the selected pipeline."""
        pipeline = self._resolve_pipeline_name(run)
        if pipeline == "vanilla-nerf":
            return self._has_blender_layout(dataset_path)
        if pipeline == "splatfacto":
            return self._has_nerfstudio_layout(dataset_path)
        return True

    def _run_preprocess_script(self, run: ExperimentRun, dataset_path: Path) -> tuple[Path, str]:
        """Run standalone preprocessing script and return prepared dataset directory."""
        preprocess_script = Path(settings.BASE_DIR) / self._PREPROCESS_SCRIPT_NAME
        if not preprocess_script.is_file():
            raise ValueError(f"Preprocess script not found: {preprocess_script}")

        preprocess_input_path = self._resolve_preprocess_input_path(dataset_path)
        output_dataset_path = Path(run.output_dir) / self._PREPROCESSED_DATASET_DIR_NAME
        skip_colmap = self._has_colmap_layout(preprocess_input_path)
        if not skip_colmap and (preprocess_input_path / "sparse" / "0").is_dir():
            logger.warning(
                "[Run %s] sparse/0 exists, but required COLMAP files are incomplete (%s). "
                "Preprocess will run COLMAP instead of --skip-colmap.",
                run.pk,
                ", ".join(self._missing_colmap_files(preprocess_input_path)),
            )
        command = [
            sys.executable,
            str(preprocess_script),
            "--input-dir",
            str(preprocess_input_path),
            "--output-dir",
            str(output_dataset_path),
        ]
        if skip_colmap:
            command.append("--skip-colmap")

        logger.info(
            "[Run %s] Running preprocess script: input=%s output=%s skip_colmap=%s",
            run.pk,
            preprocess_input_path,
            output_dataset_path,
            skip_colmap,
        )

        completed = subprocess.run(
            command,
            cwd=str(Path(run.output_dir).parent),
            env=self._build_process_env(),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        if completed.returncode != 0:
            stderr_text = completed.stderr.strip()
            stdout_text = completed.stdout.strip()
            details = stderr_text or stdout_text
            if stderr_text and stdout_text and stdout_text != stderr_text:
                details = f"stderr: {stderr_text}; stdout: {stdout_text}"
            raise ValueError(f"Preprocess failed with exit code {completed.returncode}: {details}")

        parsed_output = self._parse_preprocess_output(completed.stdout)
        data_dir = parsed_output.get("output_dir") or parsed_output.get("data_dir") or str(output_dataset_path)
        status = parsed_output.get("status", "created")
        return Path(str(data_dir)), str(status)

    def _resolve_preprocess_input_path(self, dataset_path: Path) -> Path:
        """Return dataset root for preprocess when caller points at ``images/`` directory."""
        if dataset_path.name.lower() != "images":
            return dataset_path

        parent_path = dataset_path.parent
        if not parent_path.is_dir():
            return dataset_path

        if (parent_path / "images").resolve() != dataset_path.resolve():
            return dataset_path

        if not (parent_path / "sparse" / "0").is_dir():
            return dataset_path

        logger.warning(
            "Dataset path points to images/ but parent has sparse/0. Passing dataset root to preprocess: %s",
            parent_path,
        )
        return parent_path

    def _parse_preprocess_output(self, stdout_text: str) -> dict[str, str]:
        """Parse preprocess script stdout as JSON result object."""
        stripped = stdout_text.strip()
        if not stripped:
            return {}

        candidates = [stripped]
        candidates.extend(line.strip() for line in stripped.splitlines()[::-1] if line.strip())

        for candidate in candidates:
            # Support prefixed status lines, e.g. "[preprocess] done: { ... }".
            if "{" in candidate:
                candidate = candidate[candidate.index("{") :]
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return {str(key): str(value) for key, value in parsed.items() if value is not None}

        return {}

    def _has_blender_layout(self, dataset_path: Path) -> bool:
        """Return True if Blender split metadata files are present in dataset root."""
        return all((dataset_path / file_name).is_file() for file_name in self._BLENDER_SPLIT_FILES)

    def _has_colmap_layout(self, dataset_path: Path) -> bool:
        """Return True when sparse/0 contains required COLMAP reconstruction files."""
        sparse_root = dataset_path / "sparse" / "0"
        if not sparse_root.is_dir():
            return False

        return not self._missing_colmap_files(dataset_path)

    def _missing_colmap_files(self, dataset_path: Path) -> list[str]:
        """Return missing required COLMAP file basenames from sparse/0."""
        sparse_root = dataset_path / "sparse" / "0"
        missing: list[str] = []
        for base_name in self._COLMAP_REQUIRED_BASENAMES:
            has_bin = (sparse_root / f"{base_name}.bin").is_file()
            has_txt = (sparse_root / f"{base_name}.txt").is_file()
            if not (has_bin or has_txt):
                missing.append(base_name)
        return missing

    def _has_nerfstudio_layout(self, dataset_path: Path) -> bool:
        """Return True if Nerfstudio metadata file exists in dataset root."""
        return (dataset_path / self._NERFSTUDIO_TRANSFORMS_FILE).is_file()

    def _resolve_binary(self) -> str:
        candidate = Path(self.bin_name)
        if candidate.exists():
            return self.bin_name

        if any(sep in self.bin_name for sep in ("\\", "/")) or ":" in self.bin_name:
            return self.bin_name

        resolved = which(self.bin_name)
        if resolved:
            return resolved

        return str(self.bin_name)
