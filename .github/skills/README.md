# Skills — Reusable workflows

This directory contains reusable patterns, checklists, and technical guidelines for agents.

---

## What is a skill?

A skill is a documented procedure, checklist, or technical pattern that agents reference when implementing features or fixes.

**Examples:**
- "How to build `ns-train` CLI args safely"
- "Checklist for delivering an MVP feature"
- "Testing patterns for Nerfstudio integration"

---

## Existing skills

### `config-schema.md`
Validation schema for `ExperimentRun.config_json`.
- Required fields, types, constraints
- Used by `pipeline-implementer` when building commands

### `ns-train-command.md`
Reference for `ns-train` CLI arguments.
- Available options for `vanilla-nerf` and `vanilla-gaussian-splatting`
- Used by `pipeline-implementer` for command synthesis

### `ply-viewer.md`
Integration guide for Three.js `.ply` viewer.
- Frontend API expectations
- Used by `feature-developer` and `artifact-detector`

---

## New skills (added)

### `agent-orchestration-routing.md`
**Used by:** `orchestrator`

How to decompose user requests, route to agents, and merge results.
- Routing matrix (request type → agent)
- Decomposition template
- Collaboration examples

### `pipeline-command-mapping.md`
**Used by:** `pipeline-implementer`

Safe practices for building `ns-train` CLI arguments.
- Argument list vs. shell string safety
- Dataset path validation
- Config JSON mapping
- Thread safety and error handling

### `django-feature-delivery-mvp.md`
**Used by:** `feature-developer`

End-to-end checklist for Django feature implementation.
- Model → Form → View → URL → Template → Service → Tests
- N+1 query avoidance
- Error handling patterns
- Bootstrap 5 only

### `test-mocking-nerfstudio.md`
**Used by:** `qa-test-writer`

Patterns and examples for mocking Nerfstudio in tests.
- Mock `subprocess.Popen`
- Stub stdout/stderr payloads
- Artifact detection mocking
- Fixture and coverage examples

---

## How agents use skills

**Example workflow:**

1. User asks for new feature
2. `orchestrator` reads `agent-orchestration-routing.md`
3. `orchestrator` routes to `feature-developer`
4. `feature-developer` reads `django-feature-delivery-mvp.md`
5. `feature-developer` implements feature following checklist
6. `orchestrator` routes to `qa-test-writer`
7. `qa-test-writer` reads `test-mocking-nerfstudio.md`
8. `qa-test-writer` adds tests using patterns from skill

---

## Adding new skills

When you discover a repeatable pattern:

1. Create `.md` file with clear title
2. Add "Used by: Agent name(s)" section
3. Include examples and code snippets
4. Reference in relevant agent docs
5. Update this README

**Template:**
```markdown
# Skill: skill-name

**Used by:** Agent name(s)

## Purpose

Brief description.

## Pattern

Step-by-step or code example.

## Examples

Real usage.

## References

Links to related docs/code.
```

---

## Skill discovery

- Read `agents.md` for agent responsibilities
- Read `.github/agents/README.md` for orchestration overview
- Read `.github/AGENT_QUICK_START.md` for examples
- Browse `.github/skills/` for specific patterns


