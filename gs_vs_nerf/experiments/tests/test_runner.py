"""Testy NerfstudioRunner — mockuje subprocess, nie wywołuje ns-train."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import TestCase

from experiments.models import Dataset, ExperimentRun, Metric
from experiments.services.metrics import parse_and_save
from experiments.services.runner import NerfstudioRunner


class RunnerBuildCommandTests(TestCase):
    """Testy budowania komendy ns-train."""

    def setUp(self) -> None:
        self.dataset = Dataset.objects.create(name="scene", data_path="/data/scene")
        self.run = ExperimentRun.objects.create(
            name="test-nerf",
            dataset=self.dataset,
            pipeline_type=ExperimentRun.PipelineType.VANILLA_NERF,
            output_dir="/tmp/out/run_1",
            config_json={},
        )

    def test_build_command_baseline(self) -> None:
        runner = NerfstudioRunner()
        with patch.object(runner, "_resolve_binary", return_value="ns-train"):
            cmd = runner._build_command(self.run)

        self.assertEqual(cmd[0], "ns-train")
        self.assertEqual(cmd[1], "vanilla-nerf")
        self.assertIn("--data", cmd)
        self.assertIn("scene", cmd[3])
        self.assertIn("--output-dir", cmd)
        self.assertIn("--vis", cmd)
        self.assertIn("viewer_legacy", cmd)
        self.assertNotIn("none", cmd)

    def test_build_command_is_deterministic(self) -> None:
        runner = NerfstudioRunner()
        with patch.object(runner, "_resolve_binary", return_value="ns-train"):
            cmd = runner._build_command(self.run)
            command_string = runner._command_to_string(cmd)

        self.assertIn("ns-train", command_string)
        self.assertIn("vanilla-nerf", command_string)
        self.assertIn("--data", command_string)
        self.assertIn("--output-dir", command_string)

    def test_build_command_with_max_iterations(self) -> None:
        self.run.config_json = {"max_num_iterations": 1000}
        with patch.object(NerfstudioRunner(), "_resolve_binary", return_value="ns-train"):
            cmd = NerfstudioRunner()._build_command(self.run)
        self.assertIn("--trainer.max-num-iterations", cmd)
        self.assertIn("1000", cmd)

    def test_build_command_with_downscale_factor(self) -> None:
        self.run.config_json = {"downscale_factor": 2}
        with patch.object(NerfstudioRunner(), "_resolve_binary", return_value="ns-train"):
            cmd = NerfstudioRunner()._build_command(self.run)
        self.assertIn("--pipeline.datamanager.camera-res-scale-factor", cmd)
        self.assertIn("2", cmd)

    def test_normalize_dataset_path_keeps_windows_absolute_path(self) -> None:
        runner = NerfstudioRunner()
        normalized = runner._normalize_dataset_path(r"C:\datasets\scene one")

        # Should convert backslash to forward slash
        self.assertNotIn("\\", normalized)
        self.assertIn("/", normalized)
        self.assertIn("scene one", normalized)

    @patch("experiments.services.runner.which", return_value="C:/env/Scripts/ns-train.exe")
    def test_resolve_binary_uses_which(self, mock_which) -> None:
        runner = NerfstudioRunner()
        self.assertEqual(runner._resolve_binary(), "C:/env/Scripts/ns-train.exe")
        mock_which.assert_called_once_with("ns-train")

    @patch("experiments.services.runner.which", return_value=None)
    @patch("pathlib.Path.exists", return_value=True)
    def test_resolve_binary_prefers_explicit_path(self, mock_exists, mock_which) -> None:
        runner = NerfstudioRunner()
        runner.bin_name = r"C:\tools\ns-train.exe"

        self.assertEqual(runner._resolve_binary(), r"C:\tools\ns-train.exe")
        mock_exists.assert_called_once()
        mock_which.assert_not_called()

    @patch("experiments.services.runner.which", return_value=None)
    @patch("pathlib.Path.exists", return_value=False)
    def test_resolve_binary_falls_back_to_configured_name(self, mock_exists, mock_which) -> None:
        runner = NerfstudioRunner()
        runner.bin_name = "ns-train-custom"

        self.assertEqual(runner._resolve_binary(), "ns-train-custom")
        mock_exists.assert_called_once()
        mock_which.assert_called_once_with("ns-train-custom")


class DatasetValidationTests(TestCase):
    """Testy walidacji ścieżki datasetu."""

    def setUp(self) -> None:
        self.runner = NerfstudioRunner()

    def test_validate_dataset_path_rejects_nonexistent_path(self) -> None:
        """Walidacja rzuca ValueError gdy ścieżka datasetu nie istnieje."""
        dataset = Dataset.objects.create(name="missing", data_path="/nonexistent/path")
        run = ExperimentRun.objects.create(
            name="test",
            dataset=dataset,
            pipeline_type=ExperimentRun.PipelineType.VANILLA_NERF,
        )

        with self.assertRaises(ValueError) as ctx:
            self.runner._validate_dataset_path(run)

        self.assertIn("does not exist", str(ctx.exception))

    def test_validate_dataset_path_rejects_non_directory(self) -> None:
        """Walidacja rzuca ValueError gdy ścieżka datasetu jest plikiem, nie katalogiem."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "file.txt"
            file_path.write_text("test")

            dataset = Dataset.objects.create(name="file-dataset", data_path=str(file_path))
            run = ExperimentRun.objects.create(
                name="test",
                dataset=dataset,
                pipeline_type=ExperimentRun.PipelineType.VANILLA_NERF,
            )

            with self.assertRaises(ValueError) as ctx:
                self.runner._validate_dataset_path(run)

            self.assertIn("not a directory", str(ctx.exception))

    def test_validate_dataset_path_accepts_images_in_subdirectory(self) -> None:
        """Walidacja akceptuje dataset z zdjęciami w images/ podkatalogu."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            images_dir = tmp_path / "images"
            images_dir.mkdir()
            (images_dir / "frame_001.jpg").write_text("fake image")

            dataset = Dataset.objects.create(name="valid-dataset", data_path=str(tmp_path))
            run = ExperimentRun.objects.create(
                name="test",
                dataset=dataset,
                pipeline_type=ExperimentRun.PipelineType.VANILLA_NERF,
            )

            # Should not raise
            self.runner._validate_dataset_path(run)

    def test_validate_dataset_path_accepts_images_in_root(self) -> None:
        """Walidacja akceptuje dataset z zdjęciami w root katalogiem."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            (tmp_path / "frame_001.png").write_text("fake image")

            dataset = Dataset.objects.create(name="root-images-dataset", data_path=str(tmp_path))
            run = ExperimentRun.objects.create(
                name="test",
                dataset=dataset,
                pipeline_type=ExperimentRun.PipelineType.VANILLA_NERF,
            )

            # Should not raise
            self.runner._validate_dataset_path(run)

    def test_validate_dataset_path_accepts_polish_characters(self) -> None:
        """Walidacja akceptuje ścieżki z polskimi znakami jeśli zawierają zdjęcia."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            dataset_dir = tmp_path / "Iłża_dataset"
            dataset_dir.mkdir()
            images_dir = dataset_dir / "images"
            images_dir.mkdir()
            (images_dir / "zdjęcie_001.tif").write_text("fake image")

            dataset = Dataset.objects.create(name="polish-dataset", data_path=str(dataset_dir))
            run = ExperimentRun.objects.create(
                name="test",
                dataset=dataset,
                pipeline_type=ExperimentRun.PipelineType.VANILLA_NERF,
            )

            # Should not raise
            self.runner._validate_dataset_path(run)

    def test_validate_dataset_path_rejects_empty_directory(self) -> None:
        """Walidacja rzuca ValueError gdy katalog nie zawiera zdjęć."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            dataset = Dataset.objects.create(name="empty-dataset", data_path=str(tmp_path))
            run = ExperimentRun.objects.create(
                name="test",
                dataset=dataset,
                pipeline_type=ExperimentRun.PipelineType.VANILLA_NERF,
            )

            with self.assertRaises(ValueError) as ctx:
                self.runner._validate_dataset_path(run)

            self.assertIn("no images", str(ctx.exception))

    def test_validate_dataset_path_recognizes_various_image_formats(self) -> None:
        """Walidacja rozpoznaje różne formaty obrazów: jpg, png, tif, exr."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            images_dir = tmp_path / "images"
            images_dir.mkdir()
            (images_dir / "test.jpg").write_text("jpg")
            (images_dir / "test.png").write_text("png")
            (images_dir / "test.tif").write_text("tif")
            (images_dir / "test.exr").write_text("exr")

            dataset = Dataset.objects.create(name="multi-format-dataset", data_path=str(tmp_path))
            run = ExperimentRun.objects.create(
                name="test",
                dataset=dataset,
                pipeline_type=ExperimentRun.PipelineType.VANILLA_NERF,
            )

            # Should not raise
            self.runner._validate_dataset_path(run)


class RunnerExecutionTests(TestCase):
    """Testy wykonania runu — subprocess jest mockowany."""

    def setUp(self) -> None:
        self.dataset = Dataset.objects.create(name="scene-b", data_path="/data/scene-b")
        self.run = ExperimentRun.objects.create(
            name="test-run",
            dataset=self.dataset,
            pipeline_type=ExperimentRun.PipelineType.VANILLA_GS,
            output_dir="/tmp/out/run_test",
            config_json={},
        )

    def _make_mock_completed_process(
        self,
        stdout_content: str = "",
        stderr_content: str = "",
        returncode: int = 0,
    ) -> MagicMock:
        """Create a mock CompletedProcess-like object for subprocess.run."""
        proc = MagicMock()
        proc.stdout = stdout_content
        proc.stderr = stderr_content
        proc.returncode = returncode
        return proc

    @patch("experiments.services.runner.collect_artifacts")
    @patch("experiments.services.runner.collect_metrics")
    @patch("experiments.services.runner.subprocess.run")
    def test_successful_run_marks_success(self, mock_run, mock_metrics, mock_artifacts) -> None:
        """Run zakończony kodem 0 -> status success, metryki i artefakty zbierane."""
        mock_run.return_value = self._make_mock_completed_process("Training step 1\nTraining step 2\n", "", 0)

        runner = NerfstudioRunner()
        with patch.object(runner, "_validate_dataset_path"):
            result = runner.run(self.run)

        self.run.refresh_from_db()
        self.assertEqual(result.status, ExperimentRun.Status.SUCCESS)
        self.assertEqual(self.run.status, ExperimentRun.Status.SUCCESS)
        self.assertIsNotNone(self.run.started_at)
        self.assertIsNotNone(self.run.finished_at)
        self.assertEqual(self.run.duration_seconds, result.duration_seconds)
        mock_metrics.assert_called_once_with(self.run)
        mock_artifacts.assert_called_once_with(self.run)
        self.assertTrue(Metric.objects.filter(run=self.run, name="duration_sec").exists())

    def test_run_validates_dataset_and_marks_failed_if_invalid(self) -> None:
        """Run z invalid datasetu → status failed, bez uruchomienia Popen."""
        self.dataset.data_path = "/nonexistent/path"
        self.dataset.save(update_fields=["data_path"])

        runner = NerfstudioRunner()
        result = runner.run(self.run)

        self.assertEqual(result.status, ExperimentRun.Status.FAILED)
        self.assertIn("validation failed", result.error_message)
        self.assertIn("does not exist", result.stderr_log)

    @patch("experiments.services.runner.subprocess.run")
    def test_failed_run_marks_failed_and_keeps_stderr_message(self, mock_run) -> None:
        """Run zakończony kodem != 0 -> status failed i komunikat zawiera stderr."""
        mock_run.return_value = self._make_mock_completed_process("", "Error: something went wrong\n", 2)

        runner = NerfstudioRunner()
        with patch.object(runner, "_validate_dataset_path"):
            runner.run(self.run)

        self.run.refresh_from_db()
        self.assertEqual(self.run.status, ExperimentRun.Status.FAILED)
        self.assertIn("failed with exit code 2", self.run.error_message)
        self.assertIn("stderr: Error: something went wrong", self.run.error_message)
        self.assertIn("Error: something went wrong", self.run.stderr_log)

    @patch("experiments.services.runner.subprocess.run")
    def test_missing_binary_marks_failed(self, mock_run) -> None:
        """Brak ns-train binary (FileNotFoundError) -> status failed."""
        mock_run.side_effect = FileNotFoundError("ns-train: command not found")

        runner = NerfstudioRunner()
        with patch.object(runner, "_validate_dataset_path"):
            runner.run(self.run)

        self.run.refresh_from_db()
        self.assertEqual(self.run.status, ExperimentRun.Status.FAILED)
        self.assertIn("ns-train: command not found", self.run.error_message)

    @patch("experiments.services.runner.subprocess.run")
    def test_missing_dataset_path_still_launches_and_captures_process_error(self, mock_run) -> None:
        """Ścieżka datasetu jest tylko normalizowana dla komendy; błąd ma wrócić z procesu."""
        self.run.dataset.data_path = r"C:\missing\dataset"
        self.run.dataset.save(update_fields=["data_path"])
        mock_run.return_value = self._make_mock_completed_process("", "Dataset missing\n", 2)

        runner = NerfstudioRunner()
        with patch.object(runner, "_validate_dataset_path"):
            with patch.object(runner, "_resolve_binary", return_value="ns-train"):
                runner.run(self.run)

        self.run.refresh_from_db()
        self.assertEqual(self.run.status, ExperimentRun.Status.FAILED)
        self.assertIn("failed with exit code 2", self.run.error_message)
        self.assertIn("Dataset missing", self.run.stderr_log)
        # Command should contain forward slash, not backslash (Windows compatibility)
        self.assertIn("C:/missing/dataset", self.run.command)

    @patch("experiments.services.runner.subprocess.run")
    def test_stdout_captured_in_log(self, mock_run) -> None:
        """Stdout procesu jest zapisywany w run.stdout_log."""
        mock_run.return_value = self._make_mock_completed_process("line one\nline two\n", "", 1)

        runner = NerfstudioRunner()
        with patch.object(runner, "_validate_dataset_path"):
            runner.run(self.run)

        self.run.refresh_from_db()
        self.assertIn("line one", self.run.stdout_log)
        self.assertIn("line two", self.run.stdout_log)

    @patch("experiments.services.runner.collect_artifacts")
    @patch("experiments.services.runner.collect_metrics")
    @patch("experiments.services.runner.subprocess.run")
    def test_run_persists_command_and_output_dir(self, mock_run, _mock_metrics, _mock_artifacts) -> None:
        mock_run.return_value = self._make_mock_completed_process("done\n", "", 0)
        runner = NerfstudioRunner()
        with patch.object(runner, "_validate_dataset_path"):
            with patch.object(runner, "_resolve_binary", return_value=r"C:\tools\ns-train.exe"):
                runner.run(self.run)

        self.run.refresh_from_db()
        self.assertIn("C:\\tools\\ns-train.exe", self.run.command)
        self.assertIn("--output-dir", self.run.command)
        self.assertTrue(self.run.output_dir)

    @patch("experiments.services.runner.subprocess.run")
    def test_run_calls_subprocess_with_utf8_decoding_and_utf8_env(self, mock_run) -> None:
        """Regresja: subprocess.run musi dostać UTF-8 env oraz parametry dekodowania."""
        mock_run.return_value = self._make_mock_completed_process("ok\n", "", 0)

        runner = NerfstudioRunner()
        with patch.object(runner, "_validate_dataset_path"):
            runner.run(self.run)

        _args, kwargs = mock_run.call_args
        self.assertTrue(kwargs.get("text"))
        self.assertEqual(kwargs.get("encoding"), "utf-8")
        self.assertEqual(kwargs.get("errors"), "replace")

        process_env = kwargs.get("env")
        self.assertIsInstance(process_env, dict)
        self.assertEqual(process_env.get("PYTHONUTF8"), "1")
        self.assertEqual(process_env.get("PYTHONIOENCODING"), "utf-8")


class MetricParserTests(TestCase):
    """Testy parsera metryk Nerfstudio."""

    def setUp(self) -> None:
        self.dataset = Dataset.objects.create(name="metrics-dataset", data_path="/data/metrics")
        self.run = ExperimentRun.objects.create(
            name="metrics-run",
            dataset=self.dataset,
            pipeline_type=ExperimentRun.PipelineType.VANILLA_NERF,
            output_dir="/tmp/out/metrics_run",
            config_json={},
        )

    def test_parse_json_line_creates_metrics(self) -> None:
        parse_and_save('{"step": 1000, "psnr": 24.31, "ssim": 0.812, "lpips": 0.183}', self.run)

        metrics = list(Metric.objects.filter(run=self.run).order_by("name"))
        self.assertEqual([(m.name, m.value, m.step) for m in metrics], [
            ("lpips", 0.183, 1000),
            ("psnr", 24.31, 1000),
            ("ssim", 0.812, 1000),
        ])

    def test_parse_text_line_creates_metrics(self) -> None:
        parse_and_save("[step 42] psnr=25.5 ssim=0.9 lpips=0.12", self.run)

        metrics = list(Metric.objects.filter(run=self.run).order_by("name"))
        self.assertEqual([(m.name, m.value, m.step) for m in metrics], [
            ("lpips", 0.12, 42),
            ("psnr", 25.5, 42),
            ("ssim", 0.9, 42),
        ])

    def test_garbage_line_does_not_write(self) -> None:
        parse_and_save("totally unrelated output", self.run)

        self.assertFalse(Metric.objects.filter(run=self.run).exists())

    def test_json_without_step_uses_default_step(self) -> None:
        """Jeśli w JSON nie ma step, parser używa domyślnego kroku."""
        parse_and_save('{"psnr": 30.0}', self.run)

        metric = Metric.objects.get(run=self.run, name="psnr")
        self.assertEqual(metric.step, 0)
        self.assertEqual(metric.value, 30.0)
