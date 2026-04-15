# Skill: agent-orchestration-routing

Standardowe reguły routingu zadań użytkownika między agentami specjalistycznymi.

---

## Routing matrix

| Request type | Primary agent | Secondary agents | Notes |
|---|---|---|---|
| "How do I...?" / Architecture | `Plan` | Any specialist | For broad understanding |
| Feature end-to-end (UI+backend) | `feature-developer` | `qa-test-writer` | Forms, views, templates, services |
| Pipeline / ns-train / run start | `pipeline-implementer` | `experiment-runner`, `metric-extractor`, `artifact-detector` | Command building, execution, output parsing |
| Metrics parsing / log extraction | `metric-extractor` | `qa-test-writer` | New metric types, parsing logic |
| Artifact detection / cataloging | `artifact-detector` | `qa-test-writer` | New extensions, file discovery |
| Bug fix / unclear scope | `Plan` first | Then specialist | Decompose, then delegate |
| Tests / QA / coverage | `qa-test-writer` | Any specialist | For domain scenarios/edge cases |

---

## Decomposition template

When routing a task:

1. **Identify affected modules**
   - Model changes? → `feature-developer` or `pipeline-implementer`
   - View/form changes? → `feature-developer`
   - Service/runner changes? → `pipeline-implementer`
   - New metric? → `metric-extractor`
   - New artifact? → `artifact-detector`
   - Needs tests? → `qa-test-writer`

2. **Build dependency graph**
   ```
   Task A (no deps) → assign to Agent X
   Task B (depends on A) → assign to Agent Y, wait for X
   Task C (depends on A, B) → assign to Agent Z, wait for X & Y
   ```

3. **Order execution**
   - Run independent tasks in parallel (if possible)
   - Run dependent tasks sequentially

4. **Merge results**
   - Collect outputs from all agents
   - Validate combined code follows standards
   - Run final QA

---

## Output format

After orchestrating:

```
✅ **Completed tasks:**
  - [ ] Task 1 (Agent X) — file1.py modified
  - [ ] Task 2 (Agent Y) — file2.py + tests added
  - [ ] Task 3 (Agent Z) — refactor complete

⚠️ **Risks / notes:**
  - Potential performance issue in N+1 queries
  - Requires env var `NERFSTUDIO_BIN` on Windows

📋 **QA checklist:**
  - ✅ All tests passing
  - ✅ Type hints on new functions
  - ✅ No print() calls, logging used
  - ✅ No raw exceptions in views

🚀 **Next steps:**
  - (optional) Deploy to staging
  - (optional) Manual feature test
```

---

## Collaboration examples

### Scenario 1: Add metric export to CSV

**User request:** "Users should export metrics to CSV."

**Orchestrator decomposition:**
1. `feature-developer` → add export button + form in template + view
2. `pipeline-implementer` → add CSV serialization service
3. `qa-test-writer` → test view + service

**Execution order:** All can run in parallel; QA last.

### Scenario 2: Fix GPU detection in pipeline

**User request:** "ns-train not detecting GPU in training."

**Orchestrator decomposition:**
1. `Plan` → diagnose possible causes (env vars? CUDA path? command args?)
2. `pipeline-implementer` → adjust command building or env setup
3. `qa-test-writer` → add regression test for GPU flag

**Execution order:** Plan → implementer → QA.

### Scenario 3: Add new artifact type (e.g., `.obj` mesh)

**User request:** "Support `.obj` mesh files as artifacts."

**Orchestrator decomposition:**
1. `artifact-detector` → add `.obj` → `mesh` mapping
2. `feature-developer` → add mesh rendering template
3. `qa-test-writer` → test detection + view

**Execution order:** Detector (independent) → developer + QA (parallel).

---

## Blocking patterns

- **Never let a view implement business logic** — reroute to `pipeline-implementer` or `feature-developer`
- **Never skip tests** — always end with `qa-test-writer`
- **Never modify subprocess in views/models** — reroute to `pipeline-implementer`
- **Never add metrics parsing to runner.py** — reroute to `metric-extractor`


