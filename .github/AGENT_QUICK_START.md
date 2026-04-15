# Quick start — Using the agent system

---

## You have a task? Start here:

### 1. Submit to `orchestrator`

**Example prompt to send to GitHub Copilot:**
```
@orchestrator: Add a feature to pause/resume training runs mid-execution.
```

### 2. Orchestrator routes work

The orchestrator will:
- Analyze your request
- Break it into subtasks
- Assign to specialists
- Run final QA

### 3. You get result summary

```
✅ Completed:
  - [ ] Model: added pause_requested field
  - [ ] Service: implemented pause logic
  - [ ] View: added pause button
  - [ ] Tests: 5 new tests, all passing

⚠️ Notes:
  - Requires graceful subprocess termination on Windows
  - No persistence across process restarts (MVP)

🚀 Next:
  - Consider Celery integration for production
```

---

## Examples by task type

### "Add a new feature"
→ Send to `@orchestrator` (it routes to `feature-developer` + others)

### "Fix the pipeline execution"
→ Send to `@orchestrator` (it routes to `pipeline-implementer` + tests)

### "Write comprehensive tests"
→ Send to `@qa-test-writer` (or `@orchestrator` if uncertain)

### "How does metric extraction work?"
→ Send to `@Plan` (for architecture), then domain specialist

### "Implement metric persistence for new GPU metric"
→ Send to `@orchestrator` (it routes to `metric-extractor` + tests)

---

## Agent addresses

In Copilot prompts, use `@agent-name` or describe what you want done.

- `@orchestrator` — central routing for user tasks
- `@pipeline-implementer` — ns-train orchestration
- `@feature-developer` — Django UI/forms/views
- `@qa-test-writer` — tests and validation
- `@Plan` — architecture and decomposition
- `@experiment-runner` — run execution specifics
- `@metric-extractor` — metric parsing
- `@artifact-detector` — output file discovery

---

## Project constraints to remember

All agents follow these rules from `.github/copilot-instructions.md`:

✅ **Do:**
- Type hints on all functions
- Docstrings on public methods
- Class-based views in Django
- `select_related` / `prefetch_related` for queries
- Logging via `logging` module

❌ **Don't:**
- Import `subprocess` in views/models
- Use `print()` — use logging
- Commit `.env` files
- Expose raw exceptions to templates
- Skip tests for new code

---

## See also

- `.github/agents/README.md` — agent system overview
- `agents.md` — agent responsibilities and models
- `.github/skills/` — reusable workflows and patterns
- `.github/copilot-instructions.md` — project conventions


