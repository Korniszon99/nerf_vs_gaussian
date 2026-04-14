# Agent: artifact-detector

## Purpose

Scans the Nerfstudio output directory after a run completes and creates `Artifact` records.  
Lives in `experiments/services/artifacts.py`.

---

## Input

- `run: ExperimentRun` — the completed run
- `output_dir: Path` — root of `ns-train` output (typically `outputs/{method}/{timestamp}/`)

---

## Extension → artifact_type mapping

| Extension | `artifact_type` |
|---|---|
| `.ply` | `point_cloud` |
| `.splat` | `gaussian_splat` |
| `.ckpt` | `checkpoint` |
| `.pt` | `checkpoint` |
| `.mp4` | `render_video` |
| `.json` | `metadata` |

Unknown extensions are skipped silently.

---

## Detection logic

```python
from pathlib import Path
from experiments.models import Artifact, ExperimentRun

EXT_MAP = {
    ".ply":   "point_cloud",
    ".splat": "gaussian_splat",
    ".ckpt":  "checkpoint",
    ".pt":    "checkpoint",
    ".mp4":   "render_video",
    ".json":  "metadata",
}

def detect_and_save(run: ExperimentRun, output_dir: Path) -> list[Artifact]:
    created = []
    for path in output_dir.rglob("*"):
        if not path.is_file():
            continue
        atype = EXT_MAP.get(path.suffix.lower())
        if atype is None:
            continue
        artifact, _ = Artifact.objects.get_or_create(
            run=run,
            file_path=str(path),
            defaults={"artifact_type": atype},
        )
        created.append(artifact)
    return created
```

---

## Notes

- Use `get_or_create` — the function may be called more than once (e.g. on retry).
- Store `file_path` as an absolute path string.
- The `.ply` artifact is what the Three.js viewer serves — prioritise its detection.

---

## Out of scope

- Converting `.splat` → `.ply` (future work, see `docs/architecture.md#viewer`)
- Uploading artifacts to S3 / cloud storage

---

## Tests

Cover:
1. Directory with `.ply`, `.ckpt`, `.mp4` → correct `Artifact` records
2. Unknown extension (`'.log'`) → no record created
3. Re-running detection on same dir → no duplicate records
