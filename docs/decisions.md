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
