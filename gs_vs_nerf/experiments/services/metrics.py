from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from experiments.models import ExperimentRun, Metric

logger = logging.getLogger(__name__)

_JSON_RE = re.compile(r'^\s*\{')
_KV_RE = re.compile(r'(\w+)=([\d.]+)')
_STEP_RE = re.compile(r'\[step\s+(\d+)\]')
_TRACKED = {"psnr", "ssim", "lpips"}


def _normalize_step(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _save_metric(run: ExperimentRun, name: str, value: float, step: int | None) -> None:
    Metric.objects.update_or_create(
        run=run,
        name=name,
        step=0 if step is None else step,
        defaults={"value": value},
    )


def parse_and_save(line: str, run: ExperimentRun) -> None:
    """Parse one Nerfstudio log line and save tracked metrics."""
    step: int | None = None
    values: dict[str, float] = {}

    if _JSON_RE.match(line):
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            logger.debug("Skipping invalid metric JSON line for run %s: %s", run.pk, line)
            return

        step = _normalize_step(data.get("step"))
        for key in _TRACKED:
            if key in data:
                try:
                    values[key] = float(data[key])
                except (TypeError, ValueError):
                    continue
    else:
        match = _STEP_RE.search(line)
        if match:
            step = int(match.group(1))
        for name, value in _KV_RE.findall(line):
            key = name.lower()
            if key in _TRACKED:
                try:
                    values[key] = float(value)
                except ValueError:
                    continue

    for name, value in values.items():
        _save_metric(run, name, value, step)


def collect_metrics(run: ExperimentRun) -> None:
    """Extract and store metrics from Nerfstudio run logs and metrics.json file."""
    log_path = Path(run.output_dir) / "log.txt"
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            parse_and_save(line, run)

    metrics_file = Path(run.output_dir) / "metrics.json"
    if metrics_file.exists():
        payload = json.loads(metrics_file.read_text(encoding="utf-8"))
        for metric_name, metric_value in payload.items():
            if isinstance(metric_value, (int, float)):
                Metric.objects.get_or_create(
                    run=run,
                    name=metric_name,
                    step=0,
                    defaults={"value": float(metric_value)},
                )