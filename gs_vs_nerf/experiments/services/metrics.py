import json
import re
from pathlib import Path

from experiments.models import ExperimentRun, Metric

METRIC_REGEX = re.compile(r"(?P<name>psnr|ssim|lpips)\s*[:=]\s*(?P<value>\d+\.?\d*)", re.IGNORECASE)


def collect_metrics(run: ExperimentRun) -> None:
    """Extract and store metrics from Nerfstudio run logs and metrics.json file."""
    matches = METRIC_REGEX.findall(run.stdout_log + "\n" + run.stderr_log)
    seen = set()
    for name, value in matches:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        Metric.objects.create(run=run, name=key, value=float(value), step=0)

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