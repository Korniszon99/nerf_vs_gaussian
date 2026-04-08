# GitHub Copilot — project instructions

## What this project is

Django + Nerfstudio MVP that benchmarks `vanilla-nerf` vs `vanilla-gaussian-splatting` on user-supplied datasets.  
See `.agents.md` for the full model and service map.

---

## Code style

- **Python:** PEP 8, type hints on all function signatures, docstrings on public methods.
- **Django:** class-based views preferred; `ModelForm` for forms; `select_related` / `prefetch_related` to avoid N+1.
- **JavaScript (Three.js viewer):** ES modules, no jQuery. Keep viewer logic in `static/js/viewer.js`.
- **Templates:** Bootstrap 5 utility classes only — no custom CSS unless in `static/css/main.css`.

---

## File layout (key paths)

```
gs_nerf/              ← Django project settings
experiments/          ← main app
  models.py           ← Dataset, ImageFrame, CameraPose, ExperimentRun, Metric, Artifact
  views.py
  urls.py
  services/
    runner.py         ← ns-train wrapper (ThreadPoolExecutor)
    metrics.py        ← log parser
    artifacts.py      ← file detector
  templates/experiments/
  management/commands/
    run_experiment.py ← CLI harness
static/
  js/viewer.js        ← Three.js .ply viewer
.github/
  agents/             ← per-agent instruction files
  docs/               ← architecture docs
  skills/             ← reusable skill snippets for agents
```

---

## Django patterns to follow

```python
# Good — typed service function
def start_run(run: ExperimentRun) -> None:
    """Launch ns-train in a thread pool and update run status."""
    ...

# Bad — business logic in view
def run_detail(request, pk):
    run = ExperimentRun.objects.get(pk=pk)
    subprocess.run(...)   # never here
```

Always use `get_object_or_404` in views. Never expose raw exceptions to templates.

---

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `NERFSTUDIO_BIN` | `ns-train` | Path to ns-train binary |
| `DJANGO_SECRET_KEY` | (required) | Django secret |
| `DATABASE_URL` | SQLite | DB connection string |

---

## Testing

- Every new service function needs at least one unit test in `tests/test_services.py`.
- Mock `subprocess.run` — never call real `ns-train` in tests.
- Use `pytest-django` fixtures for DB tests.

---

## Do not

- Import `subprocess` in `views.py` or `models.py`
- Commit `.env` files or API keys
- Add new Python dependencies without updating `requirements.txt`
- Use `print()` for logging — use `import logging; logger = logging.getLogger(__name__)`
