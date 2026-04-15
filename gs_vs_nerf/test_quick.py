#!/usr/bin/env python
"""Quick test to verify the runner module loads and basic structure is correct."""

import os
import sys
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gs_vs_nerf.settings")
django.setup()

from experiments.services.runner import NerfstudioRunner
from experiments.models import Dataset, ExperimentRun

# Test 1: Can we instantiate the runner?
runner = NerfstudioRunner()
print(f"✓ NerfstudioRunner instantiated: {runner}")
print(f"  - bin_name: {runner.bin_name}")

# Test 2: Can we create test data?
dataset = Dataset.objects.create(name="test-quick", data_path="/tmp/test")
run = ExperimentRun.objects.create(
    name="quick-test",
    dataset=dataset,
    pipeline_type=ExperimentRun.PipelineType.VANILLA_NERF,
    config_json={},
)
print(f"✓ Created test data: {run}")

# Test 3: Can we build a command?
cmd = runner._build_command(run)
print(f"✓ Built command: {' '.join(cmd)}")

# Test 4: Basic status transitions
run.mark_running()
print(f"✓ Status running: {run.status}")
run.mark_finished(success=True)
print(f"✓ Status success: {run.status}")

# Cleanup
run.delete()
dataset.delete()

print("\n✅ All quick tests passed!")

