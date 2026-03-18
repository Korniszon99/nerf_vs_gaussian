from __future__ import annotations

from pathlib import Path

from django.db import models
from django.utils import timezone


class Dataset(models.Model):
    name = models.CharField(max_length=128, unique=True)
    description = models.TextField(blank=True)
    data_path = models.CharField(max_length=512)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name


class ImageFrame(models.Model):
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="images")
    image_file = models.FileField(upload_to="datasets/images/")
    frame_index = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["frame_index", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["dataset", "frame_index"],
                name="unique_frame_per_dataset",
            )
        ]

    def __str__(self) -> str:
        return f"{self.dataset.name}#{self.frame_index}"


class CameraPose(models.Model):
    image = models.OneToOneField(ImageFrame, on_delete=models.CASCADE, related_name="pose")
    tx = models.FloatField(default=0.0)
    ty = models.FloatField(default=0.0)
    tz = models.FloatField(default=0.0)
    qx = models.FloatField(default=0.0)
    qy = models.FloatField(default=0.0)
    qz = models.FloatField(default=0.0)
    qw = models.FloatField(default=1.0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Pose for {self.image}"


class ExperimentRun(models.Model):
    class PipelineType(models.TextChoices):
        VANILLA_NERF = "vanilla-nerf", "Vanilla NeRF"
        VANILLA_GS = "vanilla-gaussian-splatting", "Vanilla Gaussian Splatting"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    name = models.CharField(max_length=128)
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="runs")
    pipeline_type = models.CharField(max_length=32, choices=PipelineType.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    command = models.TextField(blank=True)
    config_json = models.JSONField(default=dict, blank=True)
    output_dir = models.CharField(max_length=512, blank=True)
    stdout_log = models.TextField(blank=True)
    stderr_log = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.pipeline_type})"

    @property
    def duration_seconds(self) -> float | None:
        if not self.started_at or not self.finished_at:
            return None
        return round((self.finished_at - self.started_at).total_seconds(), 3)

    def ensure_output_dir(self, base_path: Path) -> str:
        if not self.output_dir:
            self.output_dir = str(base_path / f"run_{self.pk}")
        return self.output_dir

    def mark_running(self) -> None:
        self.status = self.Status.RUNNING
        self.started_at = timezone.now()
        self.error_message = ""

    def mark_finished(self, success: bool, error_message: str = "") -> None:
        self.status = self.Status.SUCCESS if success else self.Status.FAILED
        self.finished_at = timezone.now()
        self.error_message = error_message


class Metric(models.Model):
    run = models.ForeignKey(ExperimentRun, on_delete=models.CASCADE, related_name="metrics")
    name = models.CharField(max_length=64)
    value = models.FloatField()
    step = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "step"]

    def __str__(self) -> str:
        return f"{self.name}={self.value}"


class Artifact(models.Model):
    class ArtifactType(models.TextChoices):
        POINT_CLOUD = "point_cloud", "Point Cloud"
        MODEL = "model", "Model"
        RENDER = "render", "Render"
        CHECKPOINT = "checkpoint", "Checkpoint"
        LOG = "log", "Log"

    run = models.ForeignKey(ExperimentRun, on_delete=models.CASCADE, related_name="artifacts")
    artifact_type = models.CharField(max_length=24, choices=ArtifactType.choices)
    file_path = models.CharField(max_length=512)
    label = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.label or Path(self.file_path).name

