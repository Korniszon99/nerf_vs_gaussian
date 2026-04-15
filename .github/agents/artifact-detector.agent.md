# Agent: artifact-detector

## Purpose

Scans the Nerfstudio output directory after a run completes and creates `Artifact` records.
Lives in `experiments/services/artifacts.py`.

---

## Ownership boundary

### May edit code
- `experiments/services/artifacts.py` — directory scanning, extension mapping, and `Artifact` persistence
- Artifact-specific tests in `experiments/tests/test_services.py`

### Must not edit
- Runner orchestration or subprocess execution (→ `pipeline-implementer` / `experiment-runner`)
- Metric parsing logic (→ `metric-extractor`)
- Django UI, forms, views, or templates (→ `feature-developer`)
- Test strategy for other modules (→ `qa-test-writer`)
- Planning / decomposition (→ `Plan`)

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

# Scan output_dir recursively, map file extensions to artifact types,
# and persist discovered files as Artifact records with deduplication.
# Use get_or_create semantics and store absolute file paths.
def detect_and_save(run, output_dir: Path):
    ...
```

---

## Notes

- Use `get_or_create` — the function may be called more than once (e.g. on retry).
- Store `file_path` as an absolute path string.
- The `.ply` artifact is what the Three.js viewer serves — prioritise its detection.
- Do not interpret run status or metrics; those belong to other agents.

---

## Out of scope

- Converting `.splat` → `.ply` (future work, see `docs/architecture.md#viewer`)
- Uploading artifacts to S3 / cloud storage
- Runner lifecycle management

---

## Tests

Cover:
1. Directory with `.ply`, `.ckpt`, `.mp4` → correct `Artifact` records
2. Unknown extension (`'.log'`) → no record created
3. Re-running detection on same dir → no duplicate records

---

## Runtime command constraint (OS-aware)

- If environment indicates Windows (e.g., Windows-style paths like `C:\...`, drive letters, `\\` separators, or explicit Windows shell), use only PowerShell/CMD-compatible commands by default.
- If environment indicates Linux/Unix paths or shell, use Linux shell commands by default (`bash`/`sh`).
- Do not loop between Linux and Windows command variants in one flow; pick the OS-consistent command set and continue.
- Do not generate ad-hoc scripts prematurely when a direct shell command is enough.
- Prioritize concise, OS-native commands to reduce token usage and avoid command retry churn.
