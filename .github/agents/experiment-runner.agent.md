# Agent: experiment-runner

## Purpose

Launches Nerfstudio training runs, captures output, and persists results.  
Lives in `experiments/services/runner.py`.

---

## Input contract

Receives an `ExperimentRun` instance with:
- `run.dataset` → `Dataset` with a valid `data_path` on disk
- `run.method` → `"vanilla-nerf"` or `"vanilla-gaussian-splatting"`
- `run.config_json` → optional dict, e.g. `{"max_num_iterations": 5000, "downscale_factor": 0.5}`

---

## Execution flow

```
1. Validate config_json against schema (skills/config-schema.md)
2. Build CLI command:
   ns-train {method} --data {dataset.data_path} [--{k} {v} for k,v in config_json]
3. Set run.status = "running", run.started_at = now()  →  save()
4. Launch subprocess via ThreadPoolExecutor
5. Stream stdout/stderr line-by-line:
   a. Append to run.stdout / run.stderr buffers
   b. Pass each line to metric-extractor agent
6. On process exit:
   a. Set run.finished_at = now()
   b. duration_sec = (finished_at - started_at).total_seconds()
   c. Write Metric(run, "duration_sec", duration_sec)
   d. Call artifact-detector agent on output directory
   e. Set run.status = "done" if returncode == 0 else "failed"
   f. save()
```

---

## Binary resolution

```python
import os, shutil

def _get_nerfstudio_bin() -> str:
    env = os.environ.get("NERFSTUDIO_BIN")
    if env:
        return env
    found = shutil.which("ns-train")
    if found:
        return found
    raise EnvironmentError("ns-train not found. Set NERFSTUDIO_BIN env var.")
```

---

## Error handling

- `EnvironmentError` if binary missing → set `run.status = "failed"`, write error to `run.stderr`
- `subprocess.TimeoutExpired` → kill process, same failure path
- Never raise to the view layer — catch all exceptions in the executor callback

---

## Thread safety

- Write to `run.stdout` / `run.stderr` only inside the thread.
- Call `run.save(update_fields=["stdout","stderr","status","finished_at"])` — not full `.save()` — to avoid race conditions.

---

## Testing guidance

```python
# Patch the binary and subprocess in tests:
@patch("experiments.services.runner._get_nerfstudio_bin", return_value="/usr/bin/ns-train")
@patch("experiments.services.runner.subprocess.Popen")
def test_start_run_success(mock_popen, mock_bin):
    ...
```
