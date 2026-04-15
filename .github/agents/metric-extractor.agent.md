# Agent: metric-extractor

## Purpose

Parses Nerfstudio training log output line-by-line and writes `Metric` records to the database.
Lives in `experiments/services/metrics.py`.

---

## Ownership boundary

### May edit code
- `experiments/services/metrics.py` — parsing rules, normalization, and `Metric` persistence
- Metric-specific tests in `experiments/tests/test_services.py`

### Must not edit
- Runner orchestration or subprocess execution (→ `pipeline-implementer` / `experiment-runner`)
- Artifact detection logic (→ `artifact-detector`)
- Django UI, forms, views, or templates (→ `feature-developer`)
- Test strategy for other modules (→ `qa-test-writer`)
- Planning / decomposition (→ `Plan`)

---

## Input

A single line of stdout/stderr text from `ns-train`, plus the `ExperimentRun` instance.

---

## Nerfstudio log format (reference)

Nerfstudio emits progress lines in this approximate format:

```
[step 1000] psnr=24.31 ssim=0.812 lpips=0.183
```

or from the JSON reporter:

```json
{"step": 1000, "psnr": 24.31, "ssim": 0.812, "lpips": 0.183}
```

Both formats must be supported. JSON takes precedence when a line starts with `{`.

---

## Metric names and types

| Name | Type | Unit |
|---|---|---|
| `psnr` | `float` | dB (higher = better) |
| `ssim` | `float` | 0–1 (higher = better) |
| `lpips` | `float` | 0–1 (lower = better) |
| `duration_sec` | `float` | seconds (written by runner, not this agent) |

---

## Parsing logic

```python
import re, json
from experiments.models import Metric, ExperimentRun

_JSON_RE = re.compile(r'^\s*\{')
_KV_RE   = re.compile(r'(\w+)=([\d.]+)')
_STEP_RE = re.compile(r'\[step\s+(\d+)\]')
TRACKED  = {"psnr", "ssim", "lpips"}

def parse_and_save(line: str, run: ExperimentRun) -> None:
    step, values = None, {}

    if _JSON_RE.match(line):
        try:
            data = json.loads(line)
            step = data.get("step")
            values = {k: float(v) for k, v in data.items() if k in TRACKED}
        except json.JSONDecodeError:
            return
    else:
        m = _STEP_RE.search(line)
        if m:
            step = int(m.group(1))
        values = {k: float(v) for k, v in _KV_RE.findall(line) if k in TRACKED}

    for name, value in values.items():
        run.metrics.create(name=name, value=value, step=step)
```

---

## Do not

- Write metrics with duplicate `(run, name, step)` — use `update_or_create` if re-parsing is possible
- Block the calling thread with slow DB writes — batch inserts are fine for bulk re-import
- Silently swallow `json.JSONDecodeError` without at least a debug log
- Expand into artifact scanning, runner status, or view-layer concerns

---

## Tests

Cover:
1. Clean JSON line → correct `Metric` objects
2. `[step N] key=val` text line → correct `Metric` objects
3. Garbage line → no writes, no exception
4. Missing `step` field → `Metric.step = None` (allowed)

---

## Runtime command constraint (OS-aware)

- If environment indicates Windows (e.g., Windows-style paths like `C:\...`, drive letters, `\\` separators, or explicit Windows shell), use only PowerShell/CMD-compatible commands by default.
- If environment indicates Linux/Unix paths or shell, use Linux shell commands by default (`bash`/`sh`).
- Do not loop between Linux and Windows command variants in one flow; pick the OS-consistent command set and continue.
- Do not generate ad-hoc scripts prematurely when a direct shell command is enough.
- Prioritize concise, OS-native commands to reduce token usage and avoid command retry churn.
