from django.contrib import admin

from .models import Artifact, CameraPose, Dataset, ExperimentRun, ImageFrame, Metric


@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    list_display = ("name", "data_path", "created_at")
    search_fields = ("name", "data_path")


@admin.register(ImageFrame)
class ImageFrameAdmin(admin.ModelAdmin):
    list_display = ("dataset", "frame_index", "created_at")
    list_filter = ("dataset",)


@admin.register(CameraPose)
class CameraPoseAdmin(admin.ModelAdmin):
    list_display = ("image", "tx", "ty", "tz", "qw", "qx", "qy", "qz")


class MetricInline(admin.TabularInline):
    model = Metric
    extra = 0


class ArtifactInline(admin.TabularInline):
    model = Artifact
    extra = 0


@admin.register(ExperimentRun)
class ExperimentRunAdmin(admin.ModelAdmin):
    list_display = ("name", "dataset", "pipeline_type", "status", "created_at")
    list_filter = ("pipeline_type", "status")
    inlines = [MetricInline, ArtifactInline]

