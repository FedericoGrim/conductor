# Conductor

## Overview
CLI that executes a `plan.json` written by a "brain" model (Claude in Claude Code, or any model in OpenCode). Each step runs in parallel in its own git worktree through OpenCode 2 on a model chosen by the step's difficulty tier; every diff is reviewed; rejected steps escalate to a stronger tier; everything is logged per step and attempt. Single user: Federico. Priority: a working pipeline over features.

## Tech stack
- Python 3.12, standard library only at runtime (`asyncio`, `subprocess`, `urllib`, `tomllib`, `json`).
- OpenCode 2.x CLI (`@opencode/cli`) as the worker harness; any provider OpenCode supports.
- Dev: pytest, ruff, mypy (strict), pre-commit.

## Architecture
Simple layering, no tactical DDD: a small tool with little business logic.
- `conductor/plan.py` — `Plan`, `Step` models and validation (unique ids, known `depends_on`, no cycles, difficulty between 1 and `DIFFICULTY_LEVELS`, optional `answers` to earlier questions).
- `conductor/config.py` — `conductor.toml`: privacy profiles, each with five difficulty levels (a model or an ordered list with fallbacks, cheapest first), one or more providers (each with a `harness`, default `opencode`; `base_url` and `api_key_env` together or neither), reviewers (a model, a list, or `brain`; never a provider without endpoint), `max_parallel`, `retry`. A model id is `<provider>/<model>`.
- `conductor/defaults.py` — the built-in `low`/`medium`/`high` profiles (five levels each, with fallbacks on a second provider: DeepSeek, Vercel, Scaleway) and `DIFFICULTY_LEVELS`.
- `conductor/privacy.py` — a profile → the `opencode.json` written in each worktree (one entry per provider) and the reviewer request options.
- `conductor/scheduler.py` — asyncio DAG scheduler bounded by `max_parallel`.
- `conductor/worker.py` — worktree creation, the streaming runner (stopped after the retry limit), `run_attempt` with a `Harness`, diff capture.
- `conductor/harness.py` — the worker harnesses: the OpenCode command, its event stream (retries, cost, classified errors, final text) and the worktree `opencode.json`.
- `conductor/verify.py` — runs a step's `verify` commands with `sh -c` in its worktree (`CONDUCTOR_REPO` set, timeout, output tail).
- `conductor/reviewer.py` — direct OpenAI-compatible chat call with explicit criteria (spec, tests in the diff, domain rules, bugs), the plan's rules and the verification results; returns `{ok, reason}`.
- `conductor/escalation.py` — rejected step → next tier with the reason in the prompt; beyond last tier → `failed`. A worker question → `needs_answer` (no review, no escalation). Classified model errors → next model of the level (an unusable provider is excluded for the run), level exhausted → `unavailable`, unclassified → `failed`; reviewer errors → next reviewer, all failed → `needs_brain_review`; never escalates on an error.
- `conductor/errors.py` — the error classes (transient, provider unusable, model unsuitable, unclassified) shared by worker and reviewer.
- `conductor/log.py` — `.conductor/runs/<ts>/run.json` and `step-<id>/attempt-N.json`, with cost totals per step, model and run.
- `conductor/merge.py` — merge approved worktree branches; conflicts are reported, not resolved.
- `conductor/catalog.py` — provider model lists (`/models`), prices per million tokens, filtering and search.
- `conductor/setup_state.py` — editable profiles, providers, five difficulty levels and validation for the setup UI.
- `conductor/setup_tui.py` — `curses` screens, keys and rendering of `conductor setup`, starting from `defaults.py` when no file exists.
- `conductor/credentials.py` — API keys from the environment first, then `auth.json`.
- `conductor/settings.py` — export and import of the instance settings, with a `[conductor]` metadata table and no keys.
- `conductor/billing.py` — provider balances (chosen by the profile's `base_url` host), the cross-project spend ledger and its totals.
- `conductor/cli.py` — `conductor run plan.json --privacy low|medium|high`, `conductor validate plan.json [--config]` (warns about levels relying on one provider), `conductor billing [project|projects]`, `conductor setup`.
Rule: no module imports OpenCode or provider specifics except `harness.py`, `reviewer.py`, `privacy.py`, `catalog.py` and `billing.py`.

## Commands
- Setup: `python3 -m venv .venv && .venv/bin/pip install -e .[dev]`
- Test: `.venv/bin/pytest`
- Lint/format/types: `pre-commit run --all-files`
- List candidate models per privacy level: `.venv/bin/python scripts/list-models.py --privacy medium`
- Create or edit the configuration in a terminal UI: `.venv/bin/conductor setup`
- Move the settings between machines: `.venv/bin/conductor config export FILE` / `config import FILE`

## Environment
- `OPENROUTER_API_KEY`, and for the default fallbacks `DEEPSEEK_API_KEY` (low), `AI_GATEWAY_API_KEY` (medium), `SCALEWAY_API_KEY` (high) — or the `api_key_env` named in the chosen profile — for the reviewer call: from the environment, or from `~/.local/share/conductor/auth.json` written by `conductor setup`.
- The same key env names for `conductor billing`; `SCW_ORGANIZATION_ID` for Scaleway.
- OpenCode providers are authenticated with `opencode auth login`, outside Conductor.
- Repository secret `RELEASE_PLEASE_TOKEN`: fine-grained token (Contents and Pull requests, read and write, this repository only) used by release-please so that CI runs on its PRs. If it is missing or expired, release-please falls back to `GITHUB_TOKEN` and the `checks` run on the release PR must be approved by hand (`gh run rerun <id>` or "Approve and run" on the PR).
- Never commit `.env`, `conductor.toml` with keys, or `.conductor/` run logs.

## Domain glossary
- **Brain** — the planning model; writes `plan.json`, reviews failures, resolves conflicts.
- **Step** — one unit of the plan: id, spec, files, difficulty, depends_on, answers.
- **Question** — a worker's `QUESTION:` block at the end of its reply, for a decision the spec leaves open; the step becomes `needs_answer` and the brain answers it (or asks the user) through `answers`.
- **Difficulty level** — 1 (trivial) to 5 (hard); a step picks one and escalation goes up. Also called a tier in `tiers`.
- **Profile** — one privacy level: five difficulty levels, the reviewers, and one or more providers.
- **Fallback** — another model of the same level (or another reviewer), tried after a model or provider error; never a step up in difficulty.
- **Privacy level** — `low` (free models, data may be used for training), `medium` (paid, no-training providers), `high` (EU data residency).
- **Attempt** — one execution of a step on one model; a step has 1..N attempts.
- **Reviewer** — the model that approves or rejects an attempt's diff.
- **Escalation** — re-running a rejected step on the next tier.
- **Ledger** — `~/.local/share/conductor/ledger.jsonl`, one line per finished run with its project and cost.

## Project conventions
- Plan steps run with `opencode run --auto --archived`: workers may do anything inside their worktree, nothing outside.
- Worktrees are created and merged by Conductor (`git worktree add`), never with OpenCode's own `--worktree` flag.
- Routing options are written to a per-worktree `opencode.json`, excluded from the diff via `.git/info/exclude`.
- That `opencode.json` sets `small_model` to the first model of level 1 and repeats each provider's `request_options` at provider level: OpenCode sends title and summary requests to a model of its own choosing, and the profile's data policy must reach it too.

## Security & constraints
- Settings export never includes keys, only provider names and the variables that hold them.
- API keys come from the environment or from `auth.json` (mode `600`, directory `700`, written atomically by `conductor setup` only); never written to logs, `opencode.json`, `run.json`, the ledger or billing output. The environment wins over the file.
- A key is never sent to a `base_url` that is not `https`.
- Worker output (transcripts, diffs, reviewer replies) is untrusted data: never executed, never fed to a shell.
- `verify` commands come from the plan (written by the brain), never from worker output. They run in the worker's worktree, so they execute files the worker may have changed: no more than the worker can already run there with `--auto`.
- Reviewer verdict must be parsed strictly as JSON; anything else is a reviewer error with reason "unparseable verdict": never approved, handed to the brain.

## Definition of Done (extra)
- `conductor validate` still accepts `examples/plan.json`.
- `conductor.toml.example` stays in sync with `config.py`.
- Tests never touch the real ledger or key file: `tests/conftest.py` points `XDG_DATA_HOME` at a temporary directory.
- `conductor.toml.example` stays equal to `defaults.default_config()` (tests compare them).
- `conductor setup` writes a file that `Config.load` reads back unchanged.

## Decisions
See [docs/decisions.md](docs/decisions.md).

## Do not
- Add runtime dependencies.
- Resolve merge conflicts automatically.
- Retry or escalate on model errors outside decision 011: only OpenCode's own retries, capped by the profile's `retry.transient_attempts`; a reviewer rejection is the only thing that escalates.
