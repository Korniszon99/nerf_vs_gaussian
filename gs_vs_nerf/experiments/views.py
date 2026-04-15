from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from .forms import CameraPoseForm, DatasetForm, ExperimentRunForm, ImageFrameForm
from .models import Artifact, CameraPose, Dataset, ExperimentRun, ImageFrame
from .tasks import launch_run_async


def artifact_to_media_url(artifact: Artifact) -> str:
    """Convert an artifact's absolute file_path to a MEDIA_URL-relative URL."""
    try:
        rel = Path(artifact.file_path).relative_to(settings.MEDIA_ROOT)
        return settings.MEDIA_URL + str(rel).replace("\\", "/")
    except ValueError:
        return ""


def dashboard(request):
    datasets = Dataset.objects.all()[:10]
    runs = ExperimentRun.objects.select_related("dataset").all()[:15]
    return render(request, "experiments/dashboard.html", {"datasets": datasets, "runs": runs})


def dataset_create(request):
    if request.method == "POST":
        form = DatasetForm(request.POST)
        if form.is_valid():
            dataset = form.save()
            # Auto-importuj zdjęcia z folderu
            from experiments.services.dataset_import import import_images_from_folder
            result = import_images_from_folder(dataset)

            messages.success(
                request,
                f"Dataset '{dataset.name}' zapisany. "
                f"Zaimportowano {result['imported']} zdjęć."
            )
            if result["skipped"]:
                messages.info(request, f"Pominięto {len(result['skipped'])} plików.")
            if result["errors"]:
                for error in result["errors"][:3]:  # Pokaż max 3 błędy
                    messages.error(request, f"Błąd: {error}")
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
            "run": ExperimentRun.objects.select_related("dataset").get(pk=run.pk),
            "metrics": metrics,
            "artifacts": artifacts,
            "cloud_url": cloud_url,
        },
    )


@require_POST
def run_start(request, pk: int):
    run = get_object_or_404(ExperimentRun.objects.select_related("dataset"), pk=pk)
    if run.status == ExperimentRun.Status.RUNNING:
        messages.info(request, "Run już jest uruchomiony.")
    elif not run.dataset_id:
        messages.error(request, "Run nie ma przypisanego datasetu.")
    elif not run.dataset.images.exists():
        messages.error(request, "Dataset nie zawiera żadnych zdjęć — nie można uruchomić runa. Zaimportuj najpierw zdjęcia.")
    else:
        try:
            # Najpierw pokaż stan oczekiwania w UI, potem przejdź do uruchomienia async.
            run.status = ExperimentRun.Status.PENDING
            if run.started_at is None:
                run.started_at = timezone.now()
            run.error_message = ""
            run.finished_at = None
            run.save(update_fields=["status", "started_at", "error_message", "finished_at"])

            launch_run_async(run.pk)
            messages.success(request, "Run został uruchomiony asynchronicznie.")
        except Exception:
            run.status = ExperimentRun.Status.FAILED
            run.finished_at = timezone.now()
            run.error_message = "Failed to start run asynchronously"
            run.save(update_fields=["status", "finished_at", "error_message"])
            messages.error(request, "Nie udało się uruchomić runa.")
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


def run_logs_json(request, pk: int):
    """Zwraca live stdout/stderr runa w JSON (do auto-refresh)."""
    run = get_object_or_404(ExperimentRun.objects.select_related("dataset"), pk=pk)
    return JsonResponse(
        {
            "status": run.status,
            "stdout": run.stdout_log,
            "stderr": run.stderr_log,
            "error_message": run.error_message,
            "command": run.command,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "duration_seconds": run.duration_seconds,
            "dataset_path": run.dataset.data_path if run.dataset_id else "",
            "output_dir": run.output_dir,
        }
    )


@require_POST
def dataset_reimport_images(request, pk: int):
    """Re-importuj zdjęcia z folderu datasetu."""
    dataset = get_object_or_404(Dataset, pk=pk)
    from experiments.services.dataset_import import import_images_from_folder
    result = import_images_from_folder(dataset)

    messages.success(request, f"Zaimportowano {result['imported']} nowych zdjęć.")
    if result["skipped"]:
        messages.info(request, f"Pominięto {len(result['skipped'])} plików (duplikaty lub nieznane rozszerzenia).")
    if result["errors"]:
        for error in result["errors"][:3]:
            messages.error(request, f"Błąd: {error}")

    return redirect("experiments:dataset_detail", pk=dataset.pk)


class DatasetSetupGuideView(TemplateView):
    """Prezentacyjny poradnik przygotowania datasetu pod pipeline Nerfstudio."""

    template_name = "experiments/dataset_setup_guide.html"

