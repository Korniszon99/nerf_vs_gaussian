# Agents — GS vs NeRF (Django + Nerfstudio)

## Project snapshot

MVP Django application for comparing training time and quality metrics between `vanilla-nerf` and `vanilla-gaussian-splatting`. Built on top of [Nerfstudio](https://docs.nerf.studio/).

**Stack:** Python 3.10 (recommended on Windows), Django 5.x, Nerfstudio (`ns-train`), Three.js (point cloud viewer), SQLite (dev) / PostgreSQL (prod).

**Entry point:** `manage.py` — standard Django project layout.

---

## Models

| Model | Key fields | Notes |
|---|---|---|
| `Dataset` | `name`, `description`, `data_path`, `created_at` | Top-level container |
| `ImageFrame` | `dataset`, `image_file`, `frame_index`, `created_at` | Raw input images |
| `CameraPose` | `image`, `tx`, `ty`, `tz`, `qx`, `qy`, `qz`, `qw`, `created_at` | Per-image pose (translation + quaternion) |
| `ExperimentRun` | `name`, `dataset`, `pipeline_type` (`vanilla-nerf`\|`vanilla-gaussian-splatting`), `status`, `command`, `config_json`, `output_dir`, `stdout_log`, `stderr_log`, `error_message`, `started_at`, `finished_at`, `created_at` | Central run record; statuses: `pending`/`running`/`success`/`failed` |
| `Metric` | `run`, `name`, `value`, `step`, `created_at` | Includes `psnr`, `ssim`, `lpips`, `duration_sec` |
| `Artifact` | `run`, `artifact_type`, `file_path`, `label`, `created_at` | `.ply`, `.splat`, `.ckpt`, `.pt`, `.mp4`, `.json` |

---

## Async execution model

Runs are launched in-process via `experiments/tasks.py` using `ThreadPoolExecutor(max_workers=2)`.  
Command pattern: `ns-train {pipeline} --data {dataset_path} [known_extra_args_from_config_json]`.

```
ExperimentRun → tasks.launch_run_async → ThreadPoolExecutor → tasks.execute_run → services/runner.NerfstudioRunner.run → subprocess (ns-train) → stdout/stderr → Metric + Artifact
```

For production, replace with Celery or RQ (see `docs/architecture.md`).

---

## Agent responsibilities

### 🤖 `experiment-runner`
- Reads `ExperimentRun.config_json`
- Builds `ns-train` CLI command (maps `vanilla-gaussian-splatting` → `splatfacto`)
- Validates dataset layout (`images/` or root images) and required metadata files per pipeline
- Captures stdout/stderr line-by-line
- Parses metric lines → `Metric` objects
- Detects output files → `Artifact` objects
- Updates `ExperimentRun.status` (`pending` → `running` → `success`/`failed`)

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
- Endpoint: `GET /api/runs/{run_id}/logs/`

---

## Orchestration layer (NEW)

### 🤖 `orchestrator`
**Central coordinator** for user-facing tasks and agent delegation.

- Analyzes user requirements, decomposes into subtasks
- Routes tasks to specialized agents based on domain (pipeline, feature, metrics, artifacts, tests)
- Tracks dependencies and execution order
- Merges results and runs final QA validation
- Outputs concise status: completed tasks, risks, next steps

**When to use:** Start here for any user request; orchestrator will route to specialists.

**Collaborators:** All other agents (Plan, pipeline-implementer, feature-developer, qa-test-writer, experiment-runner, metric-extractor, artifact-detector)

---

## Implementation agents (NEW)

### 🤖 `pipeline-implementer`
**Owns** the actual Nerfstudio pipeline orchestration layer.

- Implements and maintains `experiments/services/runner.py`
- Manages `ExperimentRun` lifecycle and status transitions
- Builds safe CLI commands from config JSON
- Orchestrates subprocess execution, output streaming, and metric parsing
- Interfaces with `metric-extractor` and `artifact-detector` for result processing

**Scope:** Service-layer pipeline logic; no subprocess in views/models.

### 🤖 `feature-developer`
**Owns** end-to-end Django features (forms, views, templates, services).

- Implements Django forms (`ModelForm`), class-based views (CBV), URLs, templates
- Ensures N+1 query avoidance with `select_related` / `prefetch_related`
- Keeps views thin; moves business logic to services
- Integrates features with pipeline / metrics / artifacts as needed

**Scope:** UI, forms, views, templates, URL routing.

### 🤖 `qa-test-writer`
**Owns** test coverage for services, views, and commands.

- Mocks subprocess execution; never calls real `ns-train` in tests
- Ensures every new service function has ≥1 unit test
- Tests view→service flows, error handling, status transitions
- Uses pytest-django fixtures for DB isolation

**Scope:** Unit tests, integration tests, mocking strategy.

---

## Skills (NEW)

See `.github/skills/` for reusable workflows:

- `agent-orchestration-routing.md` — how to route tasks between agents
- `pipeline-command-mapping.md` — safe CLI argument building for `ns-train`
- `django-feature-delivery-mvp.md` — MVP feature delivery checklist
- `test-mocking-nerfstudio.md` — mocking patterns for Nerfstudio tests

---

## Conventions

- **No direct shell calls** from views — always go through `services/runner.py`
- **Config JSON** is parsed in forms; runner currently applies known keys (e.g. `max_num_iterations`, `downscale_factor`)
- **Migrations** are committed; never edit existing ones
- **Tests** in `experiments/tests/` — run via `python manage.py test` (from Django project directory with `manage.py`)
- **Debug run command**: `python manage.py run_experiment <run_id>`
- Env var `NERFSTUDIO_BIN` overrides the `ns-train` binary path

---

## Out of scope (MVP)

- `.splat` rendering in viewer (Three.js only handles `.ply`)
- Celery / RQ task queue
- Multi-user auth beyond Django admin
- Cloud storage for artifacts
