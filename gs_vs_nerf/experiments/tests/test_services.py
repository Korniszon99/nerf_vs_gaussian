"""Testy serwisów eksperymentów."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from experiments.models import Dataset, ExperimentRun, Metric
from experiments.services.metrics import parse_and_save


class MetricExtractorTests(TestCase):
    """Testy parsowania metryk Nerfstudio."""

    def setUp(self) -> None:
        self.dataset = Dataset.objects.create(name="metric-dataset", data_path="/tmp/dataset")
        self.run = ExperimentRun.objects.create(
            name="metric-run",
            dataset=self.dataset,
            pipeline_type=ExperimentRun.PipelineType.VANILLA_NERF,
            output_dir="/tmp/out",
        )

    def test_parse_json_metric_line(self) -> None:
        parse_and_save('{"step": 1000, "psnr": 24.31, "ssim": 0.812, "lpips": 0.183}', self.run)

        self.assertEqual(Metric.objects.filter(run=self.run).count(), 3)
        self.assertTrue(Metric.objects.filter(run=self.run, name="psnr", step=1000, value=24.31).exists())
        self.assertTrue(Metric.objects.filter(run=self.run, name="ssim", step=1000, value=0.812).exists())
        self.assertTrue(Metric.objects.filter(run=self.run, name="lpips", step=1000, value=0.183).exists())

    def test_parse_text_metric_line(self) -> None:
        parse_and_save("[step 42] psnr=25.5 ssim=0.901 lpips=0.120", self.run)

        self.assertEqual(Metric.objects.filter(run=self.run).count(), 3)
        self.assertTrue(Metric.objects.filter(run=self.run, name="psnr", step=42, value=25.5).exists())
        self.assertTrue(Metric.objects.filter(run=self.run, name="ssim", step=42, value=0.901).exists())
        self.assertTrue(Metric.objects.filter(run=self.run, name="lpips", step=42, value=0.12).exists())

    def test_parse_garbage_line_no_write(self) -> None:
        parse_and_save("this is not a metric line", self.run)

        self.assertEqual(Metric.objects.filter(run=self.run).count(), 0)

    def test_parse_duplicate_updates_existing_metric(self) -> None:
        parse_and_save('[step 100] psnr=10.0', self.run)
        parse_and_save('[step 100] psnr=11.5', self.run)

        self.assertEqual(Metric.objects.filter(run=self.run, name="psnr", step=100).count(), 1)
        self.assertEqual(Metric.objects.get(run=self.run, name="psnr", step=100).value, 11.5)

    def test_parse_json_without_step_defaults_to_zero(self) -> None:
        parse_and_save('{"psnr": 19.75}', self.run)

        metric = Metric.objects.get(run=self.run, name="psnr")
        self.assertEqual(metric.step, 0)
        self.assertEqual(metric.value, 19.75)

    @patch("experiments.services.metrics.logger")
    def test_invalid_json_line_is_ignored(self, mock_logger) -> None:
        parse_and_save('{"step": 1, "psnr": invalid}', self.run)

        self.assertEqual(Metric.objects.count(), 0)
        mock_logger.debug.assert_called()

