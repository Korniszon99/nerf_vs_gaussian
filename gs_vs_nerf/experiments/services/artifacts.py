from pathlib import Path

from experiments.models import Artifact, ExperimentRun


def collect_artifacts(run: ExperimentRun) -> None:
    """Scan output directory and create Artifact records for generated files."""
    output_dir = Path(run.output_dir)
    if not output_dir.exists():
        return

    for ext in ("*.ply", "*.splat", "*.ckpt", "*.pt", "*.mp4", "*.json"):
        for path in output_dir.rglob(ext):
            if path.name == "metrics.json":
                continue
            art_type = _guess_artifact_type(path)
            Artifact.objects.get_or_create(
                run=run,
                file_path=str(path),
                defaults={"artifact_type": art_type, "label": path.name},
            )


def _guess_artifact_type(path: Path) -> str:
    """Determine artifact type based on file extension."""
    suffix = path.suffix.lower()
    if suffix in {".ply", ".splat"}:
        return Artifact.ArtifactType.POINT_CLOUD
    if suffix in {".ckpt", ".pt"}:
        return Artifact.ArtifactType.CHECKPOINT
    if suffix == ".mp4":
        return Artifact.ArtifactType.RENDER
    if suffix == ".json":
        return Artifact.ArtifactType.LOG
    return Artifact.ArtifactType.MODEL