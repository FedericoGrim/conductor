# Conductor

A brain model writes the plan; cheaper models write the code.

Conductor takes a `plan.json` produced by a planning model (Claude in Claude Code, or any model in OpenCode), runs each step in parallel inside its own git worktree through [OpenCode 2](https://opencode.ai) on a model picked by the step's difficulty, has every diff reviewed, escalates rejected steps to a stronger model, merges approved work, and logs everything per step and attempt.

## How a run works

1. The brain writes `plan.json`: steps with a spec, the files to touch, a difficulty from 1 (trivial) to 5 (hard), and dependencies.
2. `conductor run plan.json --privacy medium` picks the profile from `conductor.toml`.
3. Every step whose dependencies are approved starts, up to `max_parallel` at once, in its own worktree branched from the current branch. The step runs `opencode run --format json --auto` on the first model of its difficulty level, `tiers[difficulty - 1]`. A level may list fallback models after the first one.
4. The reviewer model receives the spec and the diff and answers `{"ok": bool, "reason": str}`. `reviewer` may also list fallbacks.
5. Rejected: the step restarts on the first usable model of the next difficulty level with the reason in the prompt, possibly on a different provider. Rejected on level 5: `failed`, and its dependents are `skipped`.
   - Model or provider error: the step never escalates on an error. OpenCode retries rate limits, server and network errors by itself; after `retry.transient_attempts` of those retries (default 3, per profile) Conductor stops the worker. A transient error or an unsuitable model (context exceeded, unknown model) moves to the next model of the same level, on a fresh worktree; an unusable provider (bad key, no credit) is also excluded for the rest of the run. When no model of the level is left, the step is `unavailable`; an unclassified error ends it as `failed` at once. Each fallback is its own attempt, with the classified error in its `error`.
   - Reviewer error: an HTTP or network failure, a missing key or an unparseable verdict moves to the next reviewer without costing the worker a level, and an unusable reviewer provider is excluded for the run (separately from the workers, whose keys live in OpenCode). The failed reviewers are listed in the attempt's `review_fallbacks`. When every reviewer fails, the diff goes to the brain as `needs_brain_review`, with the error in `review.error`; the run goes on and the step is never approved.
6. Question: when the spec leaves open a decision with different consequences, the worker stops before changing files and ends its reply with a `QUESTION:` block. The step becomes `needs_answer` (not reviewed, not escalated, nothing merged), the question is in `run.json`, and its dependents are `skipped`. The brain answers it, or asks the user, and reruns the step with `answers`.
7. Approved: the branch is merged into the current branch; a conflict is reported as `conflict` and the branch is kept for the brain.
8. `.conductor/runs/<timestamp>/run.json` summarises the run; `step-<id>/attempt-<n>.json` holds the prompt, the full OpenCode event transcript, the diff and the reviewer's verdict of every attempt.

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

`conductor setup` is a terminal UI for `conductor.toml`, meant to be reopened whenever a provider changes its catalog or prices. Conductor ships three complete profiles (`low`, `medium`, `high`), so the UI opens on something that already works: you change a model, not the structure. The shipped ladders pick the strongest model per dollar at each difficulty level (SWE-bench Verified and Pro, plus measured cost per task); the reasoning is in decision 008. Every paid level and reviewer also falls back on a second provider that keeps the profile's data policy — the DeepSeek API for `low`, Vercel AI Gateway without prompt training for `medium`, Scaleway in Paris for `high` — so an OpenRouter outage does not stop a run (decision 014). Those fallbacks need `DEEPSEEK_API_KEY`, `AI_GATEWAY_API_KEY` or `SCALEWAY_API_KEY`; without the key a fallback is simply skipped.

- profiles per privacy level: the three built-in ones plus any you add, with one marked as default;
- per profile: **five difficulty levels**, each a model or an ordered list of a model and its fallbacks (`f`/`F` add a fallback from the catalog or typed, `x` drops the last one), and the reviewer (a model, a list — `v` adds a fallback, `V` clears them — or `brain`; a model reviewer needs an `https` base URL, because Conductor sends it the API key);
- providers: OpenRouter, OpenRouter EU, Vercel AI Gateway, Scaleway, OpenCode Zen, DeepSeek, or one typed by hand, each with its own `base_url` and key variable. A profile may use several of them, so level 1 can run on OpenRouter, level 3 on Scaleway and level 5 on Vercel;
- models: picked from the providers' own catalogs, filtered by typing, or an id typed by hand;
- API keys: type one and it is stored, masked, in `~/.local/share/conductor/auth.json` (mode `600`).

A model id is `<provider>/<model>`, and the provider is the one declared in the same profile, which is how a rejected step can escalate onto another provider. `conductor.toml.example` shows the format.

### Upstream routing on a gateway

OpenRouter picks an upstream provider for each model. To pin one for a single model, add a table inside the provider; the key is the model id without the provider prefix:

```toml
[privacy.medium.providers.openrouter.models."deepseek/deepseek-v4.1-flash"]
request_options = { provider = { order = ["relace"], allow_fallbacks = true } }
```

These options are merged over the provider's `request_options` (the model wins) and apply to both the worker and the reviewer when that model is chosen. The slug comes from `https://openrouter.ai/api/v1/models/<author>/<model>/endpoints` (`relace`, `deepinfra`, `morph`, ...). Prefer `order` with fallbacks over `only` with `allow_fallbacks = false`: Conductor stops the worker after the retry limit and never escalates on an error, so a single pinned upstream turning down requests turns into an `unavailable` step. The provider's own `request_options` are also written at provider level in each worktree's `opencode.json`, and OpenCode's small model (titles, summaries) is pinned to the first model of level 1, so requests OpenCode makes on its own keep the profile's data policy. Pinning does not bypass `data_collection = "deny"`: if the pinned upstream does not meet the policy, the request is refused.

Keys are read from the environment first and from that file second. Saving rewrites the file and keeps the previous one as `conductor.toml.bak`; comments written by hand are lost, which is why the generated file carries a warning. The UI needs an interactive terminal; `--config` chooses another file.

## Move the settings to another machine

Settings belong to the installation, not to the repository. Profiles, providers, the five levels, reviewers and per-model routing travel as a file:

```bash
conductor config export ./conductor-settings.toml   # or with no path: ./conductor-settings.toml
conductor config import ./conductor-settings.toml   # keeps the previous file as .bak
conductor config path                               # which file is in use
```

The exported file carries a `[conductor]` table with `schema`, `version` and `exported_at`, followed by the configuration itself, so it stays readable and diffable. **API keys are never exported**: keys live in `~/.local/share/conductor/auth.json` or in the environment. After an import, Conductor lists the variables that are still missing.

An import replaces the configuration; the previous file is kept next to it with a `.bak` suffix. A file with a newer `schema` is refused instead of being half-read.

## Install

```bash
npm i -g @opencode/cli@latest
opencode auth login            # the provider used in your profiles, e.g. OpenRouter
pipx install /path/to/conductor
conductor setup               # edit the built-in profiles, writes ~/.config/conductor/conductor.toml
```

Refresh the model lists from the command line with `python scripts/list-models.py --privacy medium`, or inside `conductor setup`.

## Use from a brain

- **Claude Code**: copy `integrations/claude-code/conductor/` to `~/.claude/skills/conductor/`. The skill declares itself for multi-step changes, so it can load without being named; it stays out of one-line fixes and exploratory work.
- **OpenCode**: copy `integrations/opencode/conductor.md` to `~/.config/opencode/command/conductor.md`. A command is always explicit: invoke it with `/conductor`.

Both tell the brain to write `plan.json`, call `conductor run`, read `run.json`, and deal with `failed`, `unavailable`, `needs_answer`, `conflict` and `needs_brain_review` steps (set `reviewer = "brain"` in a profile to review diffs yourself instead of paying a reviewer model).

No skill can force the agent to delegate. To make it reliable, add a line to the repository's instructions (for example `CLAUDE.md`):

```markdown
Multi-step changes (two or more steps, or several files) go through the `conductor` skill: write `plan.json`, run `conductor run`, then review `run.json`. Keep one-line fixes local.
```

## Plan format

```json
{
  "goal": "one line",
  "steps": [
    {"id": "core", "title": "...", "spec": "detailed instructions", "files": ["a.py"], "difficulty": 1, "depends_on": []},
    {"id": "cli", "spec": "...", "difficulty": 2, "depends_on": ["core"],
     "answers": [{"question": "Exit code on bad input?", "answer": "2, message on stderr"}]}
  ]
}
```

`difficulty` is 1 to 5 and picks the level of the chosen profile. `answers` is optional: the brain adds it when it reruns a step that stopped with a question, and the worker receives it in its prompt. Check it with `conductor validate plan.json`; when a `conductor.toml` is found (or given with `--config`), it also warns about levels and reviewers that rely on a single provider. Parallel steps must not touch the same files, or they will conflict at merge time.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e .[dev]
.venv/bin/pytest
pre-commit run --all-files
```
