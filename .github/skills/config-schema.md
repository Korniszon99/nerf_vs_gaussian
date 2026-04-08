# Skill: ExperimentRun config JSON schema

Validation schema and helper for `ExperimentRun.config_json`.

---

## Allowed keys

| Key | Type | Description |
|---|---|---|
| `max_num_iterations` | int ≥ 1 | Training steps |
| `downscale_factor` | float 0.1–1.0 | Image downscale ratio |
| `save_only_latest_checkpoint` | bool | Disk-space saving mode |
| `pipeline.model.eval_num_rays_per_chunk` | int | Eval ray batch size |
| `pipeline.datamanager.train_num_rays_per_batch` | int | Train ray batch size |

Unknown keys are passed through to ns-train as-is (with a warning log).

---

## Validator

```python
# experiments/services/config_validator.py
from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)

SCHEMA: dict[str, tuple[type, Any, Any]] = {
    # key: (expected_type, min, max)  — None = no bound
    "max_num_iterations":    (int,   1,    None),
    "downscale_factor":      (float, 0.1,  1.0),
    "save_only_latest_checkpoint": (bool, None, None),
}


def validate_config(config: dict) -> dict:
    """
    Validate and coerce config_json values.
    Returns a cleaned dict. Logs warnings for unknown keys.
    Raises ValueError for invalid values.
    """
    if not isinstance(config, dict):
        raise ValueError("config_json must be a JSON object.")

    cleaned = {}
    for key, value in config.items():
        if key not in SCHEMA:
            logger.warning("Unknown config key %r — passing through to ns-train.", key)
            cleaned[key] = value
            continue

        expected_type, low, high = SCHEMA[key]
        try:
            value = expected_type(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"config key {key!r}: expected {expected_type.__name__}, got {type(value).__name__}") from exc

        if low is not None and value < low:
            raise ValueError(f"config key {key!r}: {value} < minimum {low}")
        if high is not None and value > high:
            raise ValueError(f"config key {key!r}: {value} > maximum {high}")

        cleaned[key] = value

    return cleaned
```

---

## Usage in runner

```python
from experiments.services.config_validator import validate_config

def start_run(run: ExperimentRun) -> None:
    config = validate_config(run.config_json or {})
    run.config_json = config
    run.save(update_fields=["config_json"])
    ...
```

---

## Example valid config

```json
{
  "max_num_iterations": 5000,
  "downscale_factor": 0.5
}
```

## Example invalid config (raises ValueError)

```json
{
  "max_num_iterations": -1,
  "downscale_factor": 2.5
}
```
