# Agent System — GS vs NeRF

This directory contains specialized agent definitions for orchestrating development on this Django + Nerfstudio MVP.

---

## What is an agent?

An agent is a specialized assistant that owns a particular domain or workflow. Each agent has:
- **A focused mission** (e.g., "implement the actual pipeline", "deliver end-to-end features")
- **Clear scope** (which files, modules, or layers they touch)
- **Collaboration rules** (which agents they delegate to, which ones delegate to them)
- **Testing/QA guardrails** (how to validate their work)

---

## Agent map

### Core execution agents (existing)

| Agent | Mission | Scope |
|---|---|---|
| `experiment-runner` | Launch Nerfstudio training, capture output | `experiments/services/runner.py` |
| `metric-extractor` | Parse logs, extract metrics | `experiments/services/metrics.py` |
| `artifact-detector` | Scan output, find `.ply`, `.ckpt`, etc. | `experiments/services/artifacts.py` |

### Orchestration agent (NEW)

| Agent | Mission | Scope |
|---|---|---|
| `orchestrator` | Route user requests to specialists, merge results | Central coordinator |

### Implementation agents (NEW)

| Agent | Mission | Scope |
|---|---|---|
| `pipeline-implementer` | Build and maintain pipeline layer | `experiments/services/runner.py`, CLI, models |
| `feature-developer` | Deliver end-to-end Django features | Forms, views, templates, URLs, services |
| `qa-test-writer` | Test coverage and mocking strategy | `experiments/tests/*` |

### Planning agent (existing)

| Agent | Mission | Scope |
|---|---|---|
| `Plan` | Architecture and decomposition | Strategic planning |

---

## How to use the agent system

### For a user request

1. **You (user) submit request to `orchestrator`**
   > "I want to add metrics export to CSV"

2. **`orchestrator` decomposes**
   - Identify subtasks (UI button, form, service, tests)
   - Route each to the right agent
   - Define dependencies

3. **Agents execute in parallel (if independent)**
   - `feature-developer` → adds form + view + template
   - `pipeline-implementer` → adds export service
   - `qa-test-writer` → adds tests

4. **`orchestrator` merges and validates**
   - All code follows style/standards
   - Tests pass
   - Return summary

---

## Routing cheatsheet

| Need | Agent | Secondary |
|---|---|---|
| "How does X work?" | `Plan` | Any specialist |
| UI + form + view | `feature-developer` | `qa-test-writer` |
| Pipeline / ns-train | `pipeline-implementer` | `experiment-runner`, `metric-extractor`, `artifact-detector` |
| New metric type | `metric-extractor` | `qa-test-writer` |
| New artifact type | `artifact-detector` | `qa-test-writer` |
| Bug fix / unclear | `Plan` first | Then specialist |
| Tests / coverage | `qa-test-writer` | Domain specialist for scenarios |

---

## Agent files

Each agent has a `.agent.md` file describing:
- Purpose and scope
- Responsibilities
- Code standards
- Delegation rules
- Interface contracts
- Testing guidance

**Location:** `.github/agents/`

---

## Shared skills

Reusable workflows, patterns, and checklists live in `.github/skills/`:

- `agent-orchestration-routing.md` — how orchestrator routes tasks
- `pipeline-command-mapping.md` — safe CLI argument building
- `django-feature-delivery-mvp.md` — feature delivery checklist
- `test-mocking-nerfstudio.md` — Nerfstudio mocking patterns
- `config-schema.md` — config JSON validation (existing)
- `ns-train-command.md` — CLI reference (existing)
- `ply-viewer.md` — Three.js viewer (existing)

---

## Collaboration example

**User:** "Runs are too slow on Windows. Let me add a downscale option."

**Orchestrator decides:**
1. `Plan` → decompose (model field, form, UI, service, tests)
2. `feature-developer` → add form field + UI
3. `pipeline-implementer` → map config to CLI arg
4. `qa-test-writer` → test the feature

**Execution:**
- Plan first (10 min)
- Then features 1+2+3 in parallel (30 min)
- QA final (10 min)
- Total: ~40 min

**Output:**
✅ Model field added
✅ Form updated
✅ CLI mapping working
✅ All tests green
✅ No regressions

---

## Best practices

- **Always start with `orchestrator`** if you have a user request (not an expert question)
- **Delegate early** — don't implement code if a specialist agent exists
- **Merge and validate** — orchestrator always runs final QA before delivery
- **Document** — each agent has clear scope; respect it
- **Test** — every new service function gets ≥1 test via `qa-test-writer`

---

## See also

- `agents.md` — agent responsibilities and models
- `.github/skills/` — shared reusable workflows
- `.github/copilot-instructions.md` — project conventions


