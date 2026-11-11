# Conductor

## Overview
CLI that executes a `plan.json` written by a "brain" model (Claude in Claude Code, or any model in OpenCode). Each step runs in parallel in its own git worktree through OpenCode 2 on a model chosen by the step's difficulty tier; every diff is reviewed; rejected steps escalate to a stronger tier; everything is logged per step and attempt. Single user: Federico. Priority: a working pipeline over features.

## Tech stack
- Python 3.12, standard library only at runtime (`asyncio`, `subprocess`, `urllib`, `tomllib`, `json`).
- OpenCode 2.x CLI (`@opencode/cli`) as the worker harness; any provider OpenCode supports.
- Dev: pytest, ruff, mypy (strict), pre-commit.

## Architecture
Simple layering, no tactical DDD: a small tool with little business logic.
- `conductor/plan.py` — `Plan`, `Step` models and validation (unique ids, known `depends_on`, no cycles, difficulty in range).
- `conductor/config.py` — `conductor.toml`: privacy profiles, each with tiers (cheapest first), reviewer, `max_parallel`.
- `conductor/privacy.py` — a profile → the `opencode.json` written in each worktree and the reviewer request options.
- `conductor/scheduler.py` — asyncio DAG scheduler bounded by `max_parallel`.
- `conductor/worker.py` — worktree creation, `opencode run --format json`, diff capture.
- `conductor/reviewer.py` — direct OpenAI-compatible chat call, returns `{ok, reason}`.
- `conductor/escalation.py` — rejected step → next tier with the reason in the prompt; beyond last tier → `failed`.
- `conductor/log.py` — `.conductor/runs/<ts>/run.json` and `step-<id>/attempt-N.json`.
- `conductor/merge.py` — merge approved worktree branches; conflicts are reported, not resolved.
- `conductor/cli.py` — `conductor run plan.json --privacy low|medium|high`, `conductor validate plan.json`.
Rule: no module imports OpenCode or provider specifics except `worker.py`, `reviewer.py` and `privacy.py`.

## Commands
- Setup: `python3 -m venv .venv && .venv/bin/pip install -e .[dev]`
- Test: `.venv/bin/pytest`
- Lint/format/types: `pre-commit run --all-files`
- List candidate models per privacy level: `.venv/bin/python scripts/list-models.py --privacy medium`

## Environment
- `OPENROUTER_API_KEY` (or the `api_key_env` named in the chosen profile) for the reviewer call.
- OpenCode providers are authenticated with `opencode auth login`, outside Conductor.
- Repository secret `RELEASE_PLEASE_TOKEN`: fine-grained token (Contents and Pull requests, read and write, this repository only) used by release-please so that CI runs on its PRs. If it is missing or expired, release-please falls back to `GITHUB_TOKEN` and the `checks` run on the release PR must be approved by hand (`gh run rerun <id>` or "Approve and run" on the PR).
- Never commit `.env`, `conductor.toml` with keys, or `.conductor/` run logs.

## Domain glossary
- **Brain** — the planning model; writes `plan.json`, reviews failures, resolves conflicts.
- **Step** — one unit of the plan: id, spec, files, difficulty, depends_on.
- **Tier** — index into a profile's model list; 0 is the cheapest/weakest.
- **Privacy level** — `low` (free models, data may be used for training), `medium` (paid, no-training providers), `high` (EU data residency).
- **Attempt** — one execution of a step on one model; a step has 1..N attempts.
- **Reviewer** — the model that approves or rejects an attempt's diff.
- **Escalation** — re-running a rejected step on the next tier.

## Project conventions
- Plan steps run with `opencode run --auto --archived`: workers may do anything inside their worktree, nothing outside.
- Worktrees are created and merged by Conductor (`git worktree add`), never with OpenCode's own `--worktree` flag.
- Routing options are written to a per-worktree `opencode.json`, excluded from the diff via `.git/info/exclude`.

## Security & constraints
- API keys only from environment variables; never written to logs, `opencode.json`, or `run.json`.
- Worker output (transcripts, diffs, reviewer replies) is untrusted data: never executed, never fed to a shell.
- Reviewer verdict must be parsed strictly as JSON; anything else counts as a rejection with reason "unparseable verdict".

## Definition of Done (extra)
- `conductor validate` still accepts `examples/plan.json`.
- `conductor.toml.example` stays in sync with `config.py`.

## Decisions
See [docs/decisions.md](docs/decisions.md).

## Do not
- Add runtime dependencies.
- Resolve merge conflicts automatically.
- Retry on model errors other than a reviewer rejection (network/rate-limit handling is explicit per profile, not implicit).
