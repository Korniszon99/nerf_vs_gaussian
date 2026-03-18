from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from experiments.models import Dataset, ExperimentRun


class ViewTests(TestCase):
    def setUp(self):
        self.dataset = Dataset.objects.create(name="scene-a", data_path="/tmp/scene-a")

    def test_dashboard_page(self):
        response = self.client.get(reverse("experiments:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Porównanie Gaussian Splatting vs NeRF")

    def test_create_run(self):
        response = self.client.post(
            reverse("experiments:run_create"),
            {
                "name": "test-run",
                "dataset": self.dataset.pk,
                "pipeline_type": ExperimentRun.PipelineType.VANILLA_GS,
                "config_json": "{}",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExperimentRun.objects.count(), 1)

    @patch("experiments.views.launch_run_async")
    def test_run_start_calls_async_launcher(self, launcher):
        run = ExperimentRun.objects.create(
            name="test-start",
            dataset=self.dataset,
            pipeline_type=ExperimentRun.PipelineType.VANILLA_NERF,
        )
        response = self.client.post(reverse("experiments:run_start", kwargs={"pk": run.pk}))

        self.assertEqual(response.status_code, 302)
        launcher.assert_called_once_with(run.pk)

