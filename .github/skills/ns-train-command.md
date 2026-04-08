# Skill: ns-train command builder

Reusable logic for constructing `ns-train` CLI commands from an `ExperimentRun`.

---

## Function signature

```python
def build_ns_train_command(run: "ExperimentRun") -> list[str]:
    """Return the ns-train argv list for the given run."""
```

---

## Implementation

```python
import os
import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from experiments.models import ExperimentRun


BOOL_FLAGS: set[str] = set()  # extend if needed


def _get_bin() -> str:
    env = os.environ.get("NERFSTUDIO_BIN")
    if env:
        return env
    found = shutil.which("ns-train")
    if found:
        return found
    raise EnvironmentError(
        "ns-train not found on PATH. Set the NERFSTUDIO_BIN environment variable."
    )


def build_ns_train_command(run: "ExperimentRun") -> list[str]:
    cmd = [_get_bin(), run.method, "--data", str(run.dataset.data_path)]

    config: dict = run.config_json or {}
    for key, value in config.items():
        flag = "--" + key.replace("_", "-")
        if isinstance(value, bool):
            cmd.append(flag if value else "--no-" + key.replace("_", "-"))
        else:
            cmd += [flag, str(value)]

    return cmd
```

---

## Usage example

```python
from .skills.ns_train_command import build_ns_train_command

cmd = build_ns_train_command(run)
# → ["ns-train", "vanilla-nerf", "--data", "/data/lego",
#    "--max-num-iterations", "5000", "--downscale-factor", "0.5"]

process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
```

---

## Test cases

```python
def test_basic_command(run_factory):
    run = run_factory(method="vanilla-nerf", config_json={})
    cmd = build_ns_train_command(run)
    assert cmd[1] == "vanilla-nerf"
    assert "--data" in cmd

def test_config_flags(run_factory):
    run = run_factory(config_json={"max_num_iterations": 1000, "downscale_factor": 0.5})
    cmd = build_ns_train_command(run)
    assert "--max-num-iterations" in cmd
    assert "1000" in cmd

def test_bool_flag(run_factory):
    run = run_factory(config_json={"save_only_latest_checkpoint": True})
    cmd = build_ns_train_command(run)
    assert "--save-only-latest-checkpoint" in cmd
```
