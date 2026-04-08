# Architecture — GS vs NeRF

## System overview

```
Browser
  ├── Dashboard (Django template + Bootstrap 5)
  ├── Run detail + metrics chart (Chart.js)
  └── 3D Viewer (Three.js, .ply only)

Django (manage.py runserver / gunicorn)
  ├── experiments app
  │   ├── views.py        ← CRUD + run trigger
  │   ├── models.py       ← Dataset, ImageFrame, CameraPose,
  │   │                      ExperimentRun, Metric, Artifact
  │   └── services/
  │       ├── runner.py   ← ns-train wrapper
  │       ├── metrics.py  ← log parser
  │       └── artifacts.py ← file detector
  └── management/commands/run_experiment.py  ← CLI harness

Nerfstudio
  └── ns-train {method} --data {path} [kwargs]
      ├── outputs/{method}/{timestamp}/
      │   ├── *.ply / *.splat / *.ckpt / *.pt
      │   └── *.mp4 / *.json
      └── stdout → Metric records (psnr, ssim, lpips)

Database (SQLite dev / PostgreSQL prod)
```

---

## Data flow: creating and running an experiment

```
1. User: POST /experiments/runs/create/
      → ExperimentRun(status="pending") saved

2. View calls services.runner.start_run(run)
      → ThreadPoolExecutor.submit(_run_training, run)

3. _run_training(run):
      a. run.status = "running" → save
      b. Popen(["ns-train", method, "--data", ...])
      c. readline loop → metrics.parse_and_save(line, run)
      d. process.wait()
      e. duration_sec → Metric
      f. artifacts.detect_and_save(run, output_dir)
      g. run.status = "done" / "failed" → save

4. User polls GET /api/runs/{id}/status/  (htmx or JS)
      → returns {status, metrics[], artifacts[]}

5. Browser renders Three.js viewer with .ply URL
```

---

## Async model (MVP vs production)

### MVP (current)
`ThreadPoolExecutor` inside the Django process. Simple, zero dependencies.  
**Limitation:** server restart kills running jobs; no queue visibility.

### Production recommendation
Replace `runner.py` submit call with a Celery task:

```python
# Instead of:
executor.submit(_run_training, run)

# Use:
from experiments.tasks import run_training_task
run_training_task.delay(run.pk)
```

Celery workers run separately and survive server restarts.  
Redis or RabbitMQ as broker. Flower for queue dashboard.

---

## Viewer

The Three.js viewer (`static/js/viewer.js`) loads `.ply` point clouds via `PLYLoader`.

### `.splat` support (not yet implemented)
Two options:
1. **WebGL Gaussian Splatting renderer** — e.g. [antimatter15/splat](https://github.com/antimatter15/splat) or [mkkellogg/GaussianSplats3D](https://github.com/mkkellogg/GaussianSplats3D).
2. **Server-side conversion** — convert `.splat` → `.ply` during artifact detection.

Option 2 is simpler for MVP; Option 1 gives higher visual fidelity.

---

## Configuration schema

`ExperimentRun.config_json` accepts these keys:

| Key | Type | Default | ns-train flag |
|---|---|---|---|
| `max_num_iterations` | int | 30000 | `--max-num-iterations` |
| `downscale_factor` | float | 1.0 | `--downscale-factor` |
| `pipeline.model.eval_num_rays_per_chunk` | int | — | passthrough |

Unknown keys are ignored. Boolean values use `--flag` / `--no-flag` mapping.

---

## Database schema summary

See `experiments/models.py` for full field definitions.

```
Dataset ──< ImageFrame ──< CameraPose
    │
    └──< ExperimentRun ──< Metric
                      └──< Artifact
```

---

## Environment

| Variable | Required | Description |
|---|---|---|
| `DJANGO_SECRET_KEY` | yes | 50+ char random string |
| `NERFSTUDIO_BIN` | no | Override `ns-train` path |
| `DATABASE_URL` | no | defaults to SQLite |
| `MEDIA_ROOT` | no | artifact storage root |
