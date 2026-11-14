# ADR 002: Use uv for Python dependency management and a Makefile as the attendee command surface

- **Status:** Accepted
- **Date:** 2026-10-27
- **Context:** Workshop tooling, environment, and script execution (all modules)

## Context

The workshop repo is a full-stack app (FastAPI + PydanticAI backend, React + NVL
frontend) plus a growing set of operational scripts (scenario runner, SQLite seeder,
ontology activation, NAMS seeder, policy-change drift beat, eval scorecard). Attendees
run it from **GitHub Codespaces** or a **local clone**, with widely varying
command-line experience (REVIEW_FEEDBACK.md D1: unstated prerequisites; D3: attendees
reverse-engineering environment instead of learning the content).

Requirements:

1. **Reproducibility** — a pre-1.0 package (`neo4j-agent-memory`) must be pinned so a
   release can't break the workshop mid-session (review item F4).
2. **One command surface** — run-and-explore attendees should never need to know
   whether a step is "a Python script", "a uv command", or "two dev servers"; the
   instructor says one command, the room types one command.
3. **Codespaces/local parity** — identical behavior in the devcontainer and on a
   laptop, with no venv-activation rituals that trip first-timers.
4. **Sequenced beats** — each module is a series of scripted scenario beats; the
   command surface must map 1:1 onto the module structure so attendees can always see
   "what do I run now" and can catch up if they fall behind (review item G7).

## Decision

### uv for Python dependencies and virtual environments

- `pyproject.toml` + **committed `uv.lock`** define the environment; the
  `neo4j-agent-memory` version (and the PydanticAI/OpenAI pins) are locked — the
  lockfile is the workshop's protection against upstream releases (F4).
- `make setup` runs **`uv sync`** (creates `.venv`, installs exact locked versions).
- All Python scripts execute via **`uv run`** (e.g. `uv run scripts/run_scenario.py
  …`) — under the hood of Make targets; attendees never activate a venv manually.
- The devcontainer installs uv (it is already listed in the `.devcontainer` plan);
  local-clone pre-work installs it with the official one-line installer.
- The React/NVL frontend keeps **npm** for its own dependencies (uv is Python-only);
  Make orchestrates both ecosystems so attendees only ever see `make`.

### Makefile as the sole attendee-facing command surface

Every action an attendee or instructor needs is a `make` target. Full target surface
(documented in the outline's Repo Plan):

| Group | Targets |
|---|---|
| Setup & env | `make setup` (uv sync) · `make check` (env vars, Aura connectivity, OpenAI key, seeded SQLite — the module 0 / pre-work smoke test) · `make seed` (re-seed SQLite) · `make dev` (run FastAPI + Vite together) |
| Module beats | `make module-0` … `make module-5` — run that module's beats in order (also the catch-up lane: a fallen-behind attendee runs the current module's target to reproduce state) |
| Scenario scripts | `make s1-baseline` · `make s2-return` · `make s2-restart` · `make s3-default` · `make s3-ontology` · `make s3-enrich` · `make s4-refund` · `make s4-refund-repeat` · `make s4-fail` · `make s5-fresh-agent` |
| NAMS (module 5) | `make nams-check` (verify key + workspace) · `make nams-seed` · `make nams-distill` · `make nams-drift` (delete-entity drift beat, D4) · `make policy-change` (SQLite boundary demo) · `make nams-redistill` |
| Utilities | `make eval MODULE=N` (run isolated exact-fact/source-ID retrieval probes; no business tools) · `make reset-memory` (wipe the Neo4j memory graph for clean re-runs) · `make clean` |

- Per-module READMEs and slide decks reference **only** these targets; raw
  `uv`/`python`/`npm` invocations are considered internals.
- **Architecture (amended 2026-10-27, plan-review finding P1):** the full surface is
  **29 targets** (4 setup + 6 module beats + 10 scenarios + 6 NAMS + 3 utilities), and
  the outline's Repo Plan spec table is the **single source of truth**. There is **one
  root Makefile**; module targets resolve paths per folder via a `MODULE` variable
  (`make dev MODULE=3`) — module folders contain no per-folder Makefiles (see ADR 004).
  `make help` is generated from the spec table, and CI verifies the Makefile implements
  exactly the spec — documents and implementation cannot silently disagree.
- Scenario targets pace/serialize OpenAI calls (ADR 001 rate-limit mitigation).

## Alternatives considered

| | Verdict |
|---|---|
| **pip + venv + README instructions** | Rejected — activation rituals and unpinned installs are the classic first-timer failure mode; no lockfile story |
| **Poetry** | Rejected — heavier, slower resolution, no built-in Python interpreter management; uv is faster and already the Labs-ecosystem default |
| **`just` / `task` (command runners)** | Rejected — not preinstalled anywhere; `make` ships with macOS/Linux and the devcontainer |
| **npm scripts as orchestrator** | Rejected — Python-side execution becomes awkward stringly-typed glue; two ecosystems blurred instead of separated |
| **Docker Compose for everything** | Rejected for the app runtime — hot-reload pain for FastAPI/Vite during a live session, and it would add Docker-in-Codespaces complexity; the devcontainer already *is* the container |

## Consequences

**Positive:**
- **F4 (version pinning) substantially resolved**: `uv.lock` pins the exact package
  versions; the workshop can only break on an upstream release if the lockfile is
  deliberately updated.
- One memorizable verb (`make …`) for every action; the target list doubles as the
  workshop's table of contents.
- `uv sync` is fast (seconds, cached) → module 0 setup and Codespaces prebuilds get
  quicker (helps review A3).
- `make module-N` catch-up lanes give fallen-behind attendees a one-command path back
  to the room's current state (helps review G7) — combined with `make reset-memory`
  for clean re-runs.
- `make check` doubles as the pre-work smoke test requested by the producer review
  (G10): "run this, paste the output if it fails."

**Negative / accepted risks:**
- **Windows local-clone attendees** have no `make` by default → pre-work explicitly
  recommends Codespaces (or WSL) for Windows; the devcontainer path always works.
- **uv isn't preinstalled on local machines** → pre-work includes the one-line
  installer; Codespaces users get it in the devcontainer.
- **Two package ecosystems remain** (uv for Python, npm for the frontend) — accepted;
  Make hides the seam, and each ecosystem uses its native best tool.
- Makefile becomes a maintained artifact — targets must be kept in sync with module
  content (owned in the build phase; the outline's Repo Plan table is the spec).

## Related

- WORKSHOP_OUTLINE.md — Overview, The Arc, Module 0, Repo Plan (Makefile target table)
- ADR 001 — LLM-based entity extraction (rate-limit pacing implemented in scenario targets)
- ADR 003 — Codespaces-first delivery (lifecycle scripts invoke `uv sync` / `make seed`)
- REVIEW_FEEDBACK.md — items F4, D1, A3, G7, G10


## 2026-11-01 clarification: optional recipes

The 29-target Make surface remains the core participant workflow. Optional
instructor experiments and the standalone take-home API example may use explicitly
documented `uv run scripts/instructor.py ...` and `uv run scripts/monday_memory.py`.
These are short, reversible recipes rather than additional workshop beats; they
do not require new Make targets. Screenshot and scoped evidence-capture utilities
are facilitator tooling, likewise outside the attendee command-surface count.
