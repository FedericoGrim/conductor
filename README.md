# Conductor

A brain model writes the plan; cheaper models write the code.

Conductor takes a `plan.json` produced by a planning model (Claude in Claude Code, or any model in OpenCode), runs each step in parallel inside its own git worktree through [OpenCode 2](https://opencode.ai) on a model picked by the step's difficulty, has every diff reviewed, escalates rejected steps to a stronger model, merges approved work, and logs everything per step and attempt.

## How a run works

1. The brain writes `plan.json`: steps with a spec, the files to touch, a difficulty from 1 (trivial) to N, and dependencies.
2. `conductor run plan.json --privacy medium` picks the profile from `conductor.toml`.
3. Every step whose dependencies are approved starts, up to `max_parallel` at once, in its own worktree branched from the current branch. The step runs `opencode run --format json --auto` on `tiers[difficulty - 1]`.
4. The reviewer model receives the spec and the diff and answers `{"ok": bool, "reason": str}`.
5. Rejected: the step restarts on the next tier with the reason in the prompt. Rejected on the strongest tier: `failed`, and its dependents are `skipped`.
6. Approved: the branch is merged into the current branch; a conflict is reported as `conflict` and the branch is kept for the brain.
7. `.conductor/runs/<timestamp>/run.json` summarises the run; `step-<id>/attempt-<n>.json` holds the prompt, the full OpenCode event transcript, the diff and the reviewer's verdict of every attempt.

## Privacy levels

| Level | Data | Models |
|---|---|---|
| `low` | providers may train on prompts | free models (OpenRouter `:free`, rate limited) |
| `medium` | paid, providers that do not retain or train (`data_collection = "deny"`) | cheapest paid models anywhere |
| `high` | EU data residency (`eu.openrouter.ai`, Business plan) | fewer, pricier models |

Levels are just named profiles in `conductor.toml`; add your own for other providers.

## Billing

| Command | Shows |
|---|---|
| `conductor billing` | credits left on every provider configured in `conductor.toml` |
| `conductor billing project` | what the current repository has cost, run by run |
| `conductor billing projects` | what the last 30 days have cost, split by project (`--days N` changes the period) |

Every attempt records what the worker spent (from OpenCode's `step_finish` events) and what the reviewer spent (when the provider reports `usage.cost`, as OpenRouter does); `run.json` totals them per step, per model and per run. Each finished run is also appended to `~/.local/share/conductor/ledger.jsonl`, which is what `billing projects` reads. Runs made before this feature show as `unknown` in `billing project` and are missing from `billing projects`.

Balances come from the provider behind each profile's `base_url`:

| Provider | What is shown | Needs |
|---|---|---|
| OpenRouter | purchased credits minus usage | a management key; with a normal key, the key's own limit and usage |
| Vercel AI Gateway | credit balance and total used | the gateway API key |
| Scaleway Generative APIs | consumption of the current month in EUR (pay as you go, no prepaid balance) | `SCW_ORGANIZATION_ID`, and a key allowed to read billing |

Other providers are listed with "no balance API known". Amounts are never converted between currencies.

## Setup

`conductor setup` is a terminal UI for `conductor.toml`, meant to be reopened whenever a provider changes its catalog or prices:

- profiles per privacy level: add, delete, choose the default;
- per profile: provider (OpenRouter, OpenRouter EU, Vercel AI Gateway, Scaleway, OpenCode Zen, DeepSeek, or hand-written), parallelism, reviewer (a tier or `brain`);
- tiers: pick models from the provider's own catalog, filter them by typing, or add an id by hand; move them up and down, delete them;
- API keys: type one and it is stored, masked, in `~/.local/share/conductor/auth.json` (mode `600`).

Keys are read from the environment first and from that file second. Saving rewrites the file and keeps the previous one as `conductor.toml.bak`; comments written by hand are lost, which is why the generated file carries a warning. The UI needs an interactive terminal; `--config` chooses another file.

## Install

```bash
npm i -g @opencode/cli@latest
opencode auth login            # the provider used in your profiles, e.g. OpenRouter
pipx install /path/to/conductor
conductor setup               # writes ~/.config/conductor/conductor.toml
```

Refresh the model lists from the command line with `python scripts/list-models.py --privacy medium`, or inside `conductor setup`.

## Use from a brain

- **Claude Code**: copy `integrations/claude-code/conductor/` to `~/.claude/skills/conductor/`.
- **OpenCode**: copy `integrations/opencode/conductor.md` to `~/.config/opencode/command/conductor.md`.

Both tell the brain to write `plan.json`, call `conductor run`, read `run.json`, and deal with `failed`, `conflict` and `needs_brain_review` steps (set `reviewer = "brain"` in a profile to review diffs yourself instead of paying a reviewer model).

## Plan format

```json
{
  "goal": "one line",
  "steps": [
    {"id": "core", "title": "...", "spec": "detailed instructions", "files": ["a.py"], "difficulty": 1, "depends_on": []},
    {"id": "cli", "spec": "...", "difficulty": 2, "depends_on": ["core"]}
  ]
}
```

Check it with `conductor validate plan.json`. Parallel steps must not touch the same files, or they will conflict at merge time.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e .[dev]
.venv/bin/pytest
pre-commit run --all-files
```
