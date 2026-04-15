from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from experiments.models import Artifact, Dataset, ExperimentRun, ImageFrame


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
        # Dodaj zdjęcie do datasetu
        ImageFrame.objects.create(dataset=self.dataset, image_file="test.jpg", frame_index=0)

        response = self.client.post(reverse("experiments:run_start", kwargs={"pk": run.pk}))

        self.assertEqual(response.status_code, 302)
        launcher.assert_called_once_with(run.pk)
        run.refresh_from_db()
        self.assertEqual(run.status, ExperimentRun.Status.PENDING)
        # started_at is reset to None by the view; the runner sets it when it actually begins
        self.assertIsNone(run.started_at)
        self.assertIsNone(run.finished_at)
        self.assertEqual(run.error_message, "")

    @patch("experiments.views.launch_run_async", side_effect=RuntimeError("boom"))
    def test_run_start_marks_failed_when_async_launch_errors(self, _launcher):
        run = ExperimentRun.objects.create(
            name="test-start-fail",
            dataset=self.dataset,
            pipeline_type=ExperimentRun.PipelineType.VANILLA_GS,
        )
        # Dodaj zdjęcie do datasetu
        ImageFrame.objects.create(dataset=self.dataset, image_file="test.jpg", frame_index=0)

        response = self.client.post(reverse("experiments:run_start", kwargs={"pk": run.pk}))

        self.assertEqual(response.status_code, 302)
        run.refresh_from_db()
        self.assertEqual(run.status, ExperimentRun.Status.FAILED)
        self.assertEqual(run.error_message, "Failed to start run asynchronously")
        self.assertIsNotNone(run.finished_at)

    @patch("experiments.views.launch_run_async")
    def test_run_start_retries_failed_run(self, launcher):
        """Ponowne uruchomienie failed runa powinno wyczyścić logi i status."""
        from django.utils import timezone
        run = ExperimentRun.objects.create(
            name="test-retry",
            dataset=self.dataset,
            pipeline_type=ExperimentRun.PipelineType.VANILLA_NERF,
            status=ExperimentRun.Status.FAILED,
            error_message="previous error",
            stdout_log="old stdout",
            stderr_log="old stderr",
            started_at=timezone.now(),
            finished_at=timezone.now(),
        )
        ImageFrame.objects.create(dataset=self.dataset, image_file="img.jpg", frame_index=1)

        response = self.client.post(reverse("experiments:run_start", kwargs={"pk": run.pk}))

        self.assertEqual(response.status_code, 302)
        launcher.assert_called_once_with(run.pk)
        run.refresh_from_db()
        self.assertEqual(run.status, ExperimentRun.Status.PENDING)
        self.assertIsNone(run.started_at)
        self.assertIsNone(run.finished_at)
        self.assertEqual(run.error_message, "")
        self.assertEqual(run.stdout_log, "")
        self.assertEqual(run.stderr_log, "")

    def test_run_detail_shows_retry_button_for_failed_run(self):
        """Test że strona run_detail zawiera przycisk 'Ponów' dla failed runa."""
        run = ExperimentRun.objects.create(
            name="test-failed-button",
            dataset=self.dataset,
            pipeline_type=ExperimentRun.PipelineType.VANILLA_NERF,
            status=ExperimentRun.Status.FAILED,
            error_message="ns-train failed",
        )

        response = self.client.get(reverse("experiments:run_detail", kwargs={"pk": run.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ponów run")

    def test_run_start_rejects_dataset_without_images(self):
        """Test że run_start pokazuje error jeśli dataset nie ma zdjęć."""
        run = ExperimentRun.objects.create(
            name="test-start-no-images",
            dataset=self.dataset,
            pipeline_type=ExperimentRun.PipelineType.VANILLA_NERF,
        )
        # Dataset bez zdjęć — test powinien odrzucić

        response = self.client.post(reverse("experiments:run_start", kwargs={"pk": run.pk}))

        self.assertEqual(response.status_code, 302)
        # Sprawdź, że wiadomość error jest w response (messages framework)
        messages = list(response.wsgi_request._messages)
        error_found = any("zdjęć" in str(msg).lower() for msg in messages)
        self.assertTrue(error_found, "Powinno być info o braku zdjęć")

    def test_run_logs_json_returns_current_status_and_paths(self):
        run = ExperimentRun.objects.create(
            name="test-logs",
            dataset=self.dataset,
            pipeline_type=ExperimentRun.PipelineType.VANILLA_NERF,
            status=ExperimentRun.Status.RUNNING,
            stdout_log="out",
            stderr_log="err",
            output_dir="/tmp/run-logs",
        )

        response = self.client.get(reverse("experiments:run_logs_json", kwargs={"pk": run.pk}))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], ExperimentRun.Status.RUNNING)
        self.assertEqual(payload["stdout"], "out")
        self.assertEqual(payload["stderr"], "err")
        self.assertEqual(payload["dataset_path"], self.dataset.data_path)
        self.assertEqual(payload["output_dir"], "/tmp/run-logs")

    def test_run_artifacts_json_returns_empty_url_outside_media_root(self):
        run = ExperimentRun.objects.create(
            name="test-artifacts",
            dataset=self.dataset,
            pipeline_type=ExperimentRun.PipelineType.VANILLA_NERF,
        )
        Artifact.objects.create(
            run=run,
            artifact_type=Artifact.ArtifactType.MODEL,
            file_path="/tmp/media/runs/run_1/model.ply",
            label="model",
        )

        response = self.client.get(reverse("experiments:run_artifacts_json", kwargs={"pk": run.pk}))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["artifacts"]), 1)
        self.assertEqual(payload["artifacts"][0]["label"], "model")
        self.assertEqual(payload["artifacts"][0]["path"], "/tmp/media/runs/run_1/model.ply")
        self.assertEqual(payload["artifacts"][0]["url"], "")
