# Agent: qa-test-writer

## Purpose

Creates and maintains comprehensive test coverage for services, views, commands, and integrations with a focus on Nerfstudio mocking and deterministic behavior.

---

## Scope

### Test modules
- `experiments/tests/test_services.py` — service layer tests
- `experiments/tests/test_runner.py` — runner-specific tests
- `experiments/tests/test_views.py` — view and form tests
- `experiments/tests/test_models.py` — model behavior tests
- `experiments/tests/test_dataset_import.py` — dataset import service tests

### Testing approach
- Unit tests for service functions
- Integration tests for view→service flows
- Mocking of external dependencies (subprocess, file I/O)
- pytest-django fixtures for database isolation

### Out of scope
- End-to-end tests (these are manual or CI/CD integration tests)
- Performance/load testing
- Frontend JavaScript testing (Three.js viewer)

---

## Nerfstudio mocking rules

**Golden rule:** Never invoke real `ns-train` in tests.

### Subprocess mocking pattern

```python
from unittest.mock import patch, MagicMock
import pytest

@pytest.mark.django_db
@patch("experiments.services.runner.subprocess.Popen")
def test_start_run_captures_output(mock_popen):
    # Setup mock process
    mock_process = MagicMock()
    mock_process.stdout = iter([
        b"INFO: Step 0, PSNR: 19.5, SSIM: 0.45\n",
        b"INFO: Step 1000, PSNR: 22.3, SSIM: 0.55\n",
    ])
    mock_process.stderr = iter([])
    mock_process.returncode = 0
    mock_popen.return_value = mock_process
    
    # Test logic
    run = ExperimentRun.objects.create(dataset=..., method="vanilla-nerf")
    start_run(run)
    
    # Assertions
    run.refresh_from_db()
    assert run.status == "success"
    assert Metric.objects.filter(run=run, name="psnr").count() == 2
```

---

## Test requirements

### Service functions
- **Every new service function requires at least one test**
- Test happy path (success case)
- Test error case (exception handling, graceful degradation)
- Test state persistence (DB writes, file creation)

Example:
```python
@pytest.mark.django_db
def test_start_run_success():
    """Test successful run start and metric capture."""
    ...

@pytest.mark.django_db
def test_start_run_missing_dataset_path():
    """Test graceful failure when dataset path does not exist."""
    ...
```

### Views
- Test that GET renders the correct template
- Test that POST creates/updates records
- Test permission checks (if any)
- Test error page rendering

### Forms
- Test validation rules
- Test custom validators
- Test error messages

---

## Test fixtures

Use pytest-django fixtures for repeatability:

```python
@pytest.fixture
def dataset():
    """Create a test dataset with mock images."""
    return Dataset.objects.create(
        name="test_scene",
        scene_type="indoor",
        data_path="/tmp/test_images"
    )

@pytest.fixture
def experiment_run(dataset):
    """Create a test run ready for execution."""
    return ExperimentRun.objects.create(
        dataset=dataset,
        method="vanilla-nerf",
        status="pending",
        config_json={"max_num_iterations": 1000}
    )
```

---

## Coverage checklist

For each modification:

1. **Service changes** — mock external calls, test state transitions
2. **View changes** — test GET/POST flows, error rendering
3. **Form changes** — test validation, custom validators
4. **Model changes** — test methods, constraints
5. **Integrations** — test service→view→model flows end-to-end (still mocked)

---

## Delegation

- **Realistic execution scenarios** → `experiment-runner` (ask for edge cases)
- **Sample log lines for parser tests** → `metric-extractor` (ask for format)
- **Artifact matrix** → `artifact-detector` (ask for coverage)

---

## Test execution

```bash
# Run all tests
python manage.py test

# Run specific test module
python manage.py test experiments.tests.test_services

# Run with coverage
pytest --cov=experiments --cov-report=html
```

---

## Standards

- Use `pytest` + `pytest-django` (not Django's built-in TestCase)
- All tests must pass before code merge
- Target minimum 80% coverage on new code
- Mocking >= real process calls

---

## Runtime command constraint (OS-aware)

- If environment indicates Windows (e.g., Windows-style paths like `C:\...`, drive letters, `\\` separators, or explicit Windows shell), use only PowerShell/CMD-compatible commands by default.
- If environment indicates Linux/Unix paths or shell, use Linux shell commands by default (`bash`/`sh`).
- Do not loop between Linux and Windows command variants in one flow; pick the OS-consistent command set and continue.
- Do not generate ad-hoc scripts prematurely when a direct shell command is enough.
- Prioritize concise, OS-native commands to reduce token usage and avoid command retry churn.
