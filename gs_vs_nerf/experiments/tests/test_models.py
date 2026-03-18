from django.test import TestCase
from django.utils import timezone

from experiments.models import Artifact, CameraPose, Dataset, ExperimentRun, ImageFrame, Metric


class ModelSmokeTests(TestCase):
    def test_create_dataset_images_pose_and_run(self):
        dataset = Dataset.objects.create(name="room", data_path="/tmp/room")
        image = ImageFrame.objects.create(dataset=dataset, frame_index=1, image_file="datasets/images/1.png")
        pose = CameraPose.objects.create(image=image, tx=1.0, ty=2.0, tz=3.0)
        run = ExperimentRun.objects.create(
            name="nerf run",
            dataset=dataset,
            pipeline_type=ExperimentRun.PipelineType.VANILLA_NERF,
        )
        Metric.objects.create(run=run, name="psnr", value=24.5, step=1000)
        Artifact.objects.create(
            run=run,
            artifact_type=Artifact.ArtifactType.POINT_CLOUD,
            file_path="/tmp/output/cloud.ply",
            label="cloud",
        )

        run.started_at = timezone.now()
        run.finished_at = timezone.now()
        run.save(update_fields=["started_at", "finished_at"])

        self.assertEqual(dataset.images.count(), 1)
        self.assertEqual(str(pose), f"Pose for {image}")
        self.assertIsNotNone(run.duration_seconds)
        self.assertEqual(run.metrics.count(), 1)
        self.assertEqual(run.artifacts.count(), 1)

