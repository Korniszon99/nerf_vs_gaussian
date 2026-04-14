"""Testy NerfstudioRunner — mockuje subprocess, nie wywołuje ns-train."""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

from django.test import TestCase

from experiments.models import Dataset, ExperimentRun, Metric
from experiments.services.runner import NerfstudioRunner


def _make_stream(*lines: str) -> io.StringIO:
    """Zwraca obiekt StringIO, który zachowuje się jak stream procesu z readline()."""
    return io.StringIO("".join(lines))


def _mock_process(stdout_lines: list[str], stderr_lines: list[str], returncode: int) -> MagicMock:
    """Buduje mock subprocess.Popen z właściwymi strumieniami i kodem powrotu."""
    proc = MagicMock()
    proc.stdout = _make_stream(*stdout_lines)
    proc.stderr = _make_stream(*stderr_lines)
    proc.wait.return_value = returncode
    proc.returncode = returncode
    return proc


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
        cmd = runner._build_command(self.run)

        self.assertEqual(cmd[0], "ns-train")
        self.assertEqual(cmd[1], "vanilla-nerf")
        self.assertIn("--data", cmd)
        self.assertIn("/data/scene", cmd)
        self.assertIn("--output-dir", cmd)
        self.assertIn("--vis", cmd)
        self.assertIn("none", cmd)
        # Stara flaga nie powinna być używana
        self.assertNotIn("--viewer.quit-on-train-completion", cmd)

    def test_build_command_with_max_iterations(self) -> None:
        self.run.config_json = {"max_num_iterations": 1000}
        cmd = NerfstudioRunner()._build_command(self.run)
        self.assertIn("--trainer.max-num-iterations", cmd)
        self.assertIn("1000", cmd)

    def test_build_command_with_downscale_factor(self) -> None:
        self.run.config_json = {"downscale_factor": 2}
        cmd = NerfstudioRunner()._build_command(self.run)
        self.assertIn("--pipeline.datamanager.camera-res-scale-factor", cmd)
        self.assertIn("2", cmd)


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

    @patch("experiments.services.runner.collect_artifacts")
    @patch("experiments.services.runner.collect_metrics")
    @patch("subprocess.Popen")
    def test_successful_run_marks_success(self, mock_popen, mock_metrics, mock_artifacts) -> None:
        """Run zakończony kodem 0 → status success, metryki i artefakty zbierane."""
        mock_popen.return_value = _mock_process(
            ["Training step 1\n", "Training step 2\n"], [], 0
        )

        NerfstudioRunner().run(self.run)

        self.run.refresh_from_db()
        self.assertEqual(self.run.status, ExperimentRun.Status.SUCCESS)
        self.assertIsNotNone(self.run.finished_at)
        mock_metrics.assert_called_once_with(self.run)
        mock_artifacts.assert_called_once_with(self.run)
        # Powinien być metryka duration_sec
        self.assertTrue(Metric.objects.filter(run=self.run, name="duration_sec").exists())

    @patch("subprocess.Popen")
    def test_failed_run_marks_failed(self, mock_popen) -> None:
        """Run zakończony kodem != 0 → status failed."""
        mock_popen.return_value = _mock_process([], ["Error: something went wrong\n"], 1)

        NerfstudioRunner().run(self.run)

        self.run.refresh_from_db()
        self.assertEqual(self.run.status, ExperimentRun.Status.FAILED)
        self.assertIn("exit code: 1", self.run.error_message)

    @patch("subprocess.Popen")
    def test_missing_binary_marks_failed(self, mock_popen) -> None:
        """Brak ns-train binary (FileNotFoundError) → status failed."""
        mock_popen.side_effect = FileNotFoundError("ns-train: command not found")

        NerfstudioRunner().run(self.run)

        self.run.refresh_from_db()
        self.assertEqual(self.run.status, ExperimentRun.Status.FAILED)
        self.assertIn("ns-train: command not found", self.run.error_message)

    @patch("subprocess.Popen")
    def test_run_sets_status_running_before_process(self, mock_popen) -> None:
        """Status running jest zapisywany PRZED uruchomieniem procesu."""
        statuses: list[str] = []

        def side_effect(*args, **kwargs):
            # Sprawdź status w momencie tworzenia procesu
            self.run.refresh_from_db()
            statuses.append(self.run.status)
            raise FileNotFoundError("no binary")

        mock_popen.side_effect = side_effect
        NerfstudioRunner().run(self.run)

        self.assertEqual(statuses[0], ExperimentRun.Status.RUNNING)

    @patch("subprocess.Popen")
    def test_stdout_captured_in_log(self, mock_popen) -> None:
        """Stdout procesu jest zapisywany w run.stdout_log."""
        mock_popen.return_value = _mock_process(
            ["line one\n", "line two\n"], [], 1
        )

        NerfstudioRunner().run(self.run)

        self.run.refresh_from_db()
        self.assertIn("line one", self.run.stdout_log)
        self.assertIn("line two", self.run.stdout_log)
