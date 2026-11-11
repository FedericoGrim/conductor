# Decision Log

Significant decisions for this project. Newest at the bottom. Entries are never deleted.

---

## 001 — Python standard library, workers driven through `opencode run`
- **Date:** 2026-11-10
- **Status:** Accepted
- **Context:** Conductor orchestrates long-running model processes; it waits almost all the time. It must be easy to distribute next to two different harnesses (Claude Code and OpenCode).
- **Decision:** Python 3.12 with no runtime dependencies. Workers are spawned as `opencode run --format json` subprocesses; the NDJSON event stream is the transcript.
- **Alternatives:** Go (single binary, but slower to iterate on an unproven flow); TypeScript against `opencode serve` and `@opencode/client` (finer session control, but couples Conductor to OpenCode's internal API).
- **Consequences:** Needs a Python interpreter; parsing of the CLI's JSON output must track OpenCode releases. A later port to Go or to the SDK stays possible since the logic is isolated in `worker.py`.

## 002 — Conductor owns the git worktrees
- **Date:** 2026-11-10
- **Status:** Accepted
- **Context:** OpenCode 2 can create a worktree itself (`opencode run --worktree`), but Conductor must diff, review and merge each step's work and so must know the worktree path and branch.
- **Decision:** Conductor runs `git worktree add` per attempt and launches OpenCode with that directory as working directory. Approved branches are merged by Conductor; conflicts are reported to the brain.
- **Alternatives:** OpenCode `--worktree` (path chosen by OpenCode, would have to be parsed from events).
- **Consequences:** Deterministic paths and branch names; Conductor must clean up worktrees.

## 003 — Privacy level selects a provider profile, written per worktree
- **Date:** 2026-11-10
- **Status:** Accepted
- **Context:** Model cost and data handling differ a lot by provider and region (free models allow training; EU endpoints cost more). Two runs with different privacy must not interfere.
- **Decision:** `conductor.toml` holds one profile per privacy level (`low`, `medium`, `high`) with base URL, request options, model tiers and reviewer. The profile is materialised as an `opencode.json` inside each worktree (project-level config that OpenCode discovers) and reused for the reviewer's direct API call.
- **Alternatives:** Editing the global OpenCode config (shared state across runs); OpenRouter-only routing flags (would exclude direct and EU cloud providers).
- **Consequences:** Any OpenAI-compatible provider works for the reviewer; worker providers are whatever OpenCode supports. Profiles must be kept up to date as model catalogs change (`scripts/list-models.py`).

## 004 — Spend ledger in the user data directory
- **Date:** 2026-11-11
- **Status:** Accepted
- **Context:** Run logs live in each repository's `.conductor/runs`, so nothing can answer "how much did I spend last month, and on which project" without knowing where every project is.
- **Decision:** Each finished run appends one JSON line (project root, run, finish time, provider, cost, cost by model) to `$XDG_DATA_HOME/conductor/ledger.jsonl` (default `~/.local/share/conductor/`). `conductor billing projects` reads only the ledger; `conductor billing project` reads the repository's own `run.json` files. Costs are taken as reported: OpenCode's `step_finish` events for workers, `usage.cost` for the reviewer.
- **Alternatives:** Scanning `.conductor/runs` in a configured list of repositories (needs the list, loses history when a repository is deleted); querying each provider's usage API (cannot split by project, differs per provider).
- **Consequences:** A project is identified by its path, so a moved repository counts as a new project. The ledger is append-only and grows by one line per run. Reviewer calls on providers that do not report a cost are counted as zero. Runs older than this decision are not in the ledger.

## 005 — API keys stored next to the spend ledger, environment first
- **Date:** 2026-11-11
- **Status:** Accepted
- **Context:** The setup UI has to accept keys, otherwise it cannot leave a working configuration behind. Until now keys came only from environment variables, which is safe but unfriendly to a single user who runs Conductor from different shells.
- **Decision:** `conductor setup` stores keys in `$XDG_DATA_HOME/conductor/auth.json` (default `~/.local/share/conductor/`), one JSON object of environment-variable name to key. The file is written atomically with mode `600` inside a `700` directory. `credentials.api_key` returns the environment value first and the stored one second, so an exported variable always wins and nothing changes for existing setups. The reviewer and `conductor billing` read it through that function.
- **Alternatives:** Keyring (extra dependency, `secret-tool`/DBus not always present); ask for the key on every run (breaks unattended runs); keep environment-only and let the UI just print which variable to export (no dependency risk, but the setup UI could not leave a working configuration).
- **Consequences:** A key sits in clear text on disk, protected by file permissions only — the same trade-off `gh` and OpenCode make. Anything able to read the user's home can read it. The file is not in any repository logging path and is never printed.

## 006 — A privacy profile spans several providers, the model id names its provider
- **Date:** 2026-11-11
- **Status:** Accepted
- **Context:** A privacy level is about how a task's data may be handled, not about one vendor. Pinning one provider per level forced duplicating levels to mix a cheap model with a stronger one from elsewhere, and escalation could not leave the provider that rejected.
- **Decision:** `Profile.providers` is a map from provider name to `base_url`, `api_key_env` and `request_options`. Tier and reviewer ids are `<provider>/<model>`, and that prefix selects the provider. `privacy.opencode_config` writes one entry per provider with the models that profile uses. The old flat form (`provider`, `base_url`, `api_key_env` on the profile) is still read as a single-provider profile.
- **Alternatives:** One profile per provider with a global privacy level on top (two axes to configure, more files, harder UI); routing by price at runtime (no reproducible runs, cost surprises).
- **Consequences:** A typo in the prefix is a configuration error caught at load. Every provider still needs its own credentials in OpenCode (`opencode auth login`) and, for the reviewer and billing, in `auth.json` or the environment.

## 007 — Five fixed difficulty levels and built-in profiles
- **Date:** 2026-11-11
- **Status:** Accepted
- **Context:** The setup UI asked the user to invent the shape of a profile. The number of tiers was implicit and changed behaviour of escalation; an empty configuration meant nothing ran at all.
- **Decision:** `DIFFICULTY_LEVELS = 5` in `plan.py` and `defaults.py`. Every profile has exactly five levels, each with a model; the setup UI refuses to save with an empty level. `defaults.py` ships `low`, `medium` and `high` complete, `conductor setup` starts from them when no file exists, and `conductor.toml.example` is generated from them. `conductor run` still requires a file, so nothing is spent on defaults nobody chose.
- **Alternatives:** Free-length tier lists padded with the strongest model (ambiguous escalation); starting the UI from an empty configuration (forces understanding the file format before the first run).
- **Consequences:** Plans with difficulty above 5 are rejected. Adding a level means changing one constant and the tests around it; profiles written before this decision keep working but need the missing levels filled before `validate` accepts a high difficulty.
