# Skill: test-mocking-nerfstudio

Strategia testowania integracji Nerfstudio bez realnego uruchomienia procesu.

---

## Core principle

**Never invoke real `ns-train` in tests.** Mock all process execution and file I/O.

---

## Mocking subprocess.Popen

### Basic pattern

```python
from unittest.mock import patch, MagicMock, Mock
import pytest

@pytest.mark.django_db
@patch("experiments.services.runner.subprocess.Popen")
def test_start_run_success(mock_popen):
    # Setup mock process
    mock_process = MagicMock()
    mock_process.stdout = iter([
        b"INFO: Step 0, PSNR: 19.5, SSIM: 0.45\n",
        b"INFO: Step 1000, PSNR: 22.3, SSIM: 0.55\n",
    ])
    mock_process.stderr = iter([])
    mock_process.returncode = 0
    mock_popen.return_value = mock_process
    
    # Execute
    run = ExperimentRun.objects.create(...)
    start_run(run)
    
    # Verify
    run.refresh_from_db()
    assert run.status == "success"
    assert Metric.objects.filter(run=run, name="psnr").count() == 2
```

### Advanced: assert command arguments

```python
@patch("experiments.services.runner.subprocess.Popen")
def test_start_run_builds_correct_command(mock_popen):
    mock_process = MagicMock()
    mock_process.stdout = iter([])
    mock_process.stderr = iter([])
    mock_process.returncode = 0
    mock_popen.return_value = mock_process
    
    run = ExperimentRun.objects.create(
        dataset=dataset,
        method="vanilla-nerf",
        config_json={"max_num_iterations": 2000}
    )
    start_run(run)
    
    # Assert Popen called with correct args
    mock_popen.assert_called_once()
    args, kwargs = mock_popen.call_args
    assert args[0][0] == "ns-train"  # binary name
    assert args[0][1] == "vanilla-nerf"  # method
    assert "--data" in args[0]
    assert "--trainer.max-num-iterations" in args[0]
```

---

## Stubbing stdout/stderr for metrics parsing

### Sample Nerfstudio log lines

```
INFO: Step 0, PSNR: 19.5, SSIM: 0.45, LPIPS: 0.32, duration: 0.05s, per step: 0.05s
INFO: Step 1000, PSNR: 22.3, SSIM: 0.55, LPIPS: 0.28, duration: 105.2s, per step: 0.105s
INFO: Step 2000, PSNR: 24.1, SSIM: 0.62, LPIPS: 0.25, duration: 210.4s, per step: 0.105s
```

### Mock as byte stream

```python
@patch("experiments.services.runner.subprocess.Popen")
def test_metrics_parsed_correctly(mock_popen):
    mock_process = MagicMock()
    mock_process.stdout = iter([
        b"INFO: Step 0, PSNR: 19.5, SSIM: 0.45\n",
        b"INFO: Step 1000, PSNR: 22.3, SSIM: 0.55\n",
    ])
    mock_process.stderr = iter([])
    mock_process.returncode = 0
    mock_popen.return_value = mock_process
    
    run = ExperimentRun.objects.create(...)
    start_run(run)
    
    # Verify metrics created
    metrics = Metric.objects.filter(run=run, name="psnr")
    assert metrics.count() == 2
    assert metrics.first().value == "19.5"
    assert metrics.last().value == "22.3"
```

---

## Testing artifact detection

### Mock file system / os.walk

```python
from pathlib import Path
from unittest.mock import patch, MagicMock

@patch("experiments.services.artifacts.Path.rglob")
def test_detect_artifacts(mock_rglob):
    # Mock discovered files
    mock_files = [
        MagicMock(suffix=".ply", is_file=lambda: True),
        MagicMock(suffix=".ckpt", is_file=lambda: True),
        MagicMock(suffix=".log", is_file=lambda: True),  # ignored
    ]
    mock_rglob.return_value = mock_files
    
    run = ExperimentRun.objects.create(...)
    artifacts = detect_and_save(run, Path("/output"))
    
    # Verify
    assert len(artifacts) == 2  # .log skipped
    assert any(a.artifact_type == "point_cloud" for a in artifacts)
    assert any(a.artifact_type == "checkpoint" for a in artifacts)
```

---

## Testing status transitions

```python
@pytest.mark.django_db
@patch("experiments.services.runner.subprocess.Popen")
def test_run_status_transitions(mock_popen):
    mock_process = MagicMock()
    mock_process.stdout = iter([])
    mock_process.stderr = iter([])
    mock_process.returncode = 0
    mock_popen.return_value = mock_process
    
    run = ExperimentRun.objects.create(status="pending")
    assert run.status == "pending"
    
    start_run(run)
    
    run.refresh_from_db()
    assert run.status == "success"
    assert run.started_at is not None
    assert run.finished_at is not None
```

---

## Testing error handling

```python
@pytest.mark.django_db
@patch("experiments.services.runner.subprocess.Popen")
def test_run_handles_subprocess_error(mock_popen):
    # Simulate process failure
    mock_popen.side_effect = FileNotFoundError("ns-train not found")
    
    run = ExperimentRun.objects.create(...)
    start_run(run)  # should not raise
    
    run.refresh_from_db()
    assert run.status == "failed"
    assert "ns-train not found" in run.stderr
```

---

## Test fixtures (pytest-django)

```python
@pytest.fixture
def dataset():
    """Create a test dataset."""
    return Dataset.objects.create(
        name="test_scene",
        scene_type="indoor",
        data_path="/tmp/test_images"
    )

@pytest.fixture
def experiment_run(dataset):
    """Create a test run."""
    return ExperimentRun.objects.create(
        dataset=dataset,
        method="vanilla-nerf",
        status="pending",
        config_json={"max_num_iterations": 1000}
    )
```

---

## Coverage targets

- Service functions: 100% (all paths mocked)
- Views: 80%+ (GET, POST, errors)
- Models: 100% (methods, constraints)
- Integration: 70%+ (happy path + main error cases)

---

## Running tests

```bash
# All tests
python manage.py test

# Specific module
python manage.py test experiments.tests.test_services

# With coverage
pip install coverage
coverage run --source='experiments' manage.py test
coverage report
```


