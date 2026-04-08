# Agents — GS vs NeRF (Django + Nerfstudio)

## Project snapshot

MVP Django application for comparing training time and quality metrics between `vanilla-nerf` and `vanilla-gaussian-splatting`. Built on top of [Nerfstudio](https://docs.nerf.studio/).

**Stack:** Python 3.10+, Django 4.x, Nerfstudio (`ns-train`), Three.js (point cloud viewer), SQLite (dev) / PostgreSQL (prod).

**Entry point:** `manage.py` — standard Django project layout.

---

## Models

| Model | Key fields | Notes |
|---|---|---|
| `Dataset` | `name`, `scene_type`, `created_at` | Top-level container |
| `ImageFrame` | `dataset`, `file_path`, `frame_index` | Raw input images |
| `CameraPose` | `image_frame`, `rotation_matrix`, `translation_vector` | COLMAP / JSON import |
| `ExperimentRun` | `dataset`, `method` (`vanilla-nerf`\|`vanilla-gaussian-splatting`), `status`, `config_json`, `stdout`, `stderr`, `started_at`, `finished_at` | Central run record |
| `Metric` | `run`, `name`, `value`, `step` | `psnr`, `ssim`, `lpips`, `duration_sec` |
| `Artifact` | `run`, `artifact_type`, `file_path` | `.ply`, `.splat`, `.ckpt`, `.pt`, `.mp4`, `.json` |

---

## Async execution model

Runs are launched via `ThreadPoolExecutor` (in-process, MVP).  
Command pattern: `ns-train {method} --data {dataset_path} [extra_args_from_config_json]`.

```
ExperimentRun → services/runner.py → subprocess (ns-train) → stdout/stderr → Metric + Artifact
```

For production, replace with Celery or RQ (see `docs/architecture.md`).

---

## Agent responsibilities

### 🤖 `experiment-runner`
- Reads `ExperimentRun.config_json`
- Builds `ns-train` CLI command
- Captures stdout/stderr line-by-line
- Parses metric lines → `Metric` objects
- Detects output files → `Artifact` objects
- Updates `ExperimentRun.status` (`pending` → `running` → `done`/`failed`)

### 🤖 `metric-extractor`
- Parses Nerfstudio log format
- Extracts `psnr`, `ssim`, `lpips` values from progress lines
- Writes to `Metric` model with correct `step`

### 🤖 `artifact-detector`
- Walks output directory after run completes
- Matches extensions: `.ply`, `.splat`, `.ckpt`, `.pt`, `.mp4`, `.json`
- Creates `Artifact` records, sets `artifact_type`

### 🤖 `viewer-backend`
- Serves `.ply` file URLs for Three.js frontend
- Returns run metadata (metrics, status, artifacts) as JSON
- Endpoint: `GET /api/runs/{run_id}/artifacts/`

---

## Conventions

- **No direct shell calls** from views — always go through `services/runner.py`
- **Config JSON** is validated against a schema before run starts (see `skills/config-schema.md`)
- **Migrations** are committed; never edit existing ones
- **Tests** in `tests/` — run via `python manage.py test`
- Env var `NERFSTUDIO_BIN` overrides the `ns-train` binary path

---

## Out of scope (MVP)

- `.splat` rendering in viewer (Three.js only handles `.ply`)
- Celery / RQ task queue
- Multi-user auth beyond Django admin
- Cloud storage for artifacts
