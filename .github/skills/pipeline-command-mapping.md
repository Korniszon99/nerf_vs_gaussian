# Skill: pipeline-command-mapping

Mapowanie konfiguracji `ExperimentRun` na argumenty CLI `ns-train`.

---

## Standards

1. **Build arguments as a list** (not shell string)
   ```python
   # ✅ Good
   args = ["ns-train", method, "--data", dataset_path, "--trainer.max-num-iterations", "5000"]
   subprocess.Popen(args, ...)
   
   # ❌ Bad (shell injection risk)
   cmd = f"ns-train {method} --data {dataset_path}"
   subprocess.Popen(cmd, shell=True, ...)
   ```

2. **Validate dataset path before execution**
   ```python
   from pathlib import Path
   
   data_path = Path(run.dataset.data_path)
   if not data_path.exists():
       raise ValidationError(f"Dataset path does not exist: {data_path}")
   ```

3. **Config JSON mapping**
   - `max_num_iterations` → `--trainer.max-num-iterations`
   - `downscale_factor` → `--pipeline.datamanager.camera-res-scale-factor`
   - Add more as needed (document in config schema)

4. **Capture stdout/stderr**
   ```python
   process = subprocess.Popen(
       args,
       stdout=subprocess.PIPE,
       stderr=subprocess.PIPE,
       text=True,  # text mode for string handling
       bufsize=1   # line-buffered
   )
   ```

5. **Parse output streams**
   - Pass each line to `metric-extractor` service
   - Append to `run.stdout` / `run.stderr` buffers
   - Persist metrics as `Metric` objects

6. **Lifecycle states**
   ```
   pending
       ↓ (on start)
   running (set started_at)
       ↓ (on exit)
   success OR failed (set finished_at, duration_sec)
   ```

---

## Example: Command synthesis

```python
def build_ns_train_command(run: ExperimentRun) -> list[str]:
    """
    Build ns-train CLI command from ExperimentRun config.
    
    Args:
        run: ExperimentRun with method, dataset, config_json
    
    Returns:
        List of command arguments (safe for subprocess.Popen)
    
    Raises:
        ValidationError: if dataset path missing or config invalid
    """
    # Validate
    if not Path(run.dataset.data_path).exists():
        raise ValidationError(f"Dataset not found: {run.dataset.data_path}")
    
    # Build base command
    args = [
        get_nerfstudio_bin(),  # resolves ns-train path
        run.method,
        "--data",
        str(run.dataset.data_path),
    ]
    
    # Add optional config
    if run.config_json:
        for key, value in run.config_json.items():
            # Map known keys
            if key == "max_num_iterations":
                args.extend(["--trainer.max-num-iterations", str(value)])
            elif key == "downscale_factor":
                args.extend(["--pipeline.datamanager.camera-res-scale-factor", str(value)])
            # Add others as discovered
    
    return args
```

---

## Error handling

- **Missing binary** → set `run.status = "failed"`, log and write to `run.stderr`
- **Invalid dataset path** → same
- **Config validation failure** → same
- **Subprocess timeout** → kill process, set `run.status = "failed"`
- **Never raise to the view layer** → catch all in executor thread

---

## Thread safety

- Do not directly modify `run.status` and flush to DB from multiple threads
- Use `run.save(update_fields=["status", "stdout", "stderr"])` to avoid race conditions
- Consider adding a lock around status updates for high-concurrency scenarios


