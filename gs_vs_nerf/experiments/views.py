from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import CameraPoseForm, DatasetForm, ExperimentRunForm, ImageFrameForm
from .models import Artifact, CameraPose, Dataset, ExperimentRun, ImageFrame
from .tasks import launch_run_async


def dashboard(request):
    datasets = Dataset.objects.all()[:10]
    runs = ExperimentRun.objects.select_related("dataset").all()[:15]
    return render(request, "experiments/dashboard.html", {"datasets": datasets, "runs": runs})


def dataset_create(request):
    if request.method == "POST":
        form = DatasetForm(request.POST)
        if form.is_valid():
            dataset = form.save()
            messages.success(request, "Dataset zapisany.")
            return redirect("experiments:dataset_detail", pk=dataset.pk)
    else:
        form = DatasetForm()
    return render(request, "experiments/dataset_form.html", {"form": form})


def dataset_detail(request, pk: int):
    dataset = get_object_or_404(Dataset, pk=pk)
    image_form = ImageFrameForm()
    images = dataset.images.select_related("pose")
    return render(
        request,
        "experiments/dataset_detail.html",
        {"dataset": dataset, "images": images, "image_form": image_form},
    )


@require_POST
def image_upload(request, pk: int):
    dataset = get_object_or_404(Dataset, pk=pk)
    form = ImageFrameForm(request.POST, request.FILES)
    if form.is_valid():
        image = form.save(commit=False)
        image.dataset = dataset
        image.save()
        CameraPose.objects.get_or_create(image=image)
        messages.success(request, "Zdjęcie dodane.")
    else:
        messages.error(request, f"Błąd walidacji: {form.errors}")
    return redirect("experiments:dataset_detail", pk=dataset.pk)


def pose_edit(request, image_id: int):
    image = get_object_or_404(ImageFrame, pk=image_id)
    pose, _ = CameraPose.objects.get_or_create(image=image)
    if request.method == "POST":
        form = CameraPoseForm(request.POST, instance=pose)
        if form.is_valid():
            form.save()
            messages.success(request, "Orientacja kamery zaktualizowana.")
            return redirect("experiments:dataset_detail", pk=image.dataset_id)
    else:
        form = CameraPoseForm(instance=pose)
    return render(request, "experiments/pose_form.html", {"form": form, "image": image})


def run_create(request):
    if request.method == "POST":
        form = ExperimentRunForm(request.POST)
        if form.is_valid():
            run = form.save()
            run.output_dir = str(Path(settings.MEDIA_ROOT) / "runs" / f"run_{run.pk}")
            run.save(update_fields=["output_dir"])
            messages.success(request, "Eksperyment utworzony.")
            return redirect("experiments:run_detail", pk=run.pk)
    else:
        form = ExperimentRunForm()
    return render(request, "experiments/run_form.html", {"form": form})


def run_detail(request, pk: int):
    run = get_object_or_404(ExperimentRun.objects.select_related("dataset"), pk=pk)
    metrics = run.metrics.all()
    artifacts = run.artifacts.all()
    cloud = next((a for a in artifacts if Path(a.file_path).suffix.lower() in {".ply", ".splat"}), None)
    cloud_url = artifact_to_media_url(cloud) if cloud else ""
    return render(
        request,
        "experiments/run_detail.html",
        {
            "run": run,
            "metrics": metrics,
            "artifacts": artifacts,
            "cloud_url": cloud_url,
        },
    )


@require_POST
def run_start(request, pk: int):
    run = get_object_or_404(ExperimentRun, pk=pk)
    if run.status == ExperimentRun.Status.RUNNING:
        messages.info(request, "Run już jest uruchomiony.")
    else:
        launch_run_async(run.pk)
        messages.success(request, "Run został uruchomiony asynchronicznie.")
    return redirect("experiments:run_detail", pk=run.pk)


def run_artifacts_json(request, pk: int):
    run = get_object_or_404(ExperimentRun, pk=pk)
    payload = []
    for artifact in run.artifacts.all():
        payload.append(
            {
                "id": artifact.pk,
                "type": artifact.artifact_type,
                "label": artifact.label,
                "path": artifact.file_path,
                "url": artifact_to_media_url(artifact),
            }
        )
    return JsonResponse({"artifacts": payload})


def artifact_to_media_url(artifact: Artifact | None) -> str:
    if not artifact:
        return ""
    path = Path(artifact.file_path)
    media_root = Path(settings.MEDIA_ROOT)
    try:
        rel = path.relative_to(media_root)
    except ValueError as exc:
        raise Http404("Artifact nie jest pod MEDIA_ROOT") from exc
    return f"{settings.MEDIA_URL}{rel.as_posix()}"

