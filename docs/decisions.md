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

## 008 — Default ladders chosen on capability per cost
- **Date:** 2026-11-11
- **Status:** Accepted
- **Context:** The first defaults were plausible but never compared: `medium` paid for Claude Opus on the hardest level, and `high` used Mistral models that score below their price class. Escalating on a weak model wastes a whole attempt.
- **Decision:** The default ladders follow one rule: at each level, the model with the best measured capability per task dollar, keeping the data policy of the profile. `small` evidence (November 2026): DeepSeek V4 Pro 0813 resolves 96.4% of SWE-bench Verified at roughly $0.10 per task, GLM-5.3 95.4% at $0.34, GPT-5.6 Luna 93.0% at $0.04, GLM-5.3 Flash 92.0% at $0.02, DeepSeek V4 Flash 0731 88.8% at $0.01, while Claude Opus 5 resolves 97.0% at $1.29. The ladders therefore end on DeepSeek V4 Pro on `medium` and on Claude Opus 5.5 only where the EU endpoint has nothing cheaper at that level. `low` keeps two free models first; `medium` and `high` never use `:free`. Reviewers are GPT-5.6 Luna (input-heavy, strong) except `low`, which uses GLM-5.3 Flash.
- **Alternatives:** Claude Opus everywhere (best absolute quality, 12–30× the cost per task); cheapest model at every level (escalation would carry all the work); no defaults at all (the UI would ask the user to research this themselves).
- **Consequences:** The shipped ladders go stale as prices and models move; `conductor setup` exists to refresh them. Benchmarks are vendor-run unless stated, so a model can underperform its listing in Conductor's own runs; `run.json` costs per model are the place to check the real numbers.

## 009 — Request options per model, for gateway upstream routing
- **Date:** 2026-11-11
- **Status:** Accepted
- **Context:** One OpenRouter model is served by many upstreams at very different prices and quality (DeepSeek V4.1 Flash: $0.006/M input on Relace, $0.14/M on DeepInfra fp8). OpenCode already supports per-model `options.provider` routing, but Conductor applied one `request_options` to every model of a gateway, so pinning an upstream for one model was impossible.
- **Decision:** `Provider.model_options` maps a model id (without the provider prefix) to request options. `Profile.options_for(model)` deep-merges them over the provider options, with the model winning, and both `privacy.opencode_config` and the reviewer use it. `conductor setup` reads and rewrites the section without an editor for it (issue #23).
- **Alternatives:** One gateway entry per upstream (OpenCode has a single provider id per gateway, so it would need fake provider names); a global `sort = "price"` for every model (loses control and can select a weak fp4 upstream on a hard task).
- **Consequences:** Upstream choice becomes part of the configuration and of the logged cost, which makes runs reproducible. Pinning with `only` and no fallbacks turns an upstream outage into a failed step, because model errors are not retried; the documentation recommends `order` with fallbacks. Pinned upstreams still obey the profile's data policy.

## 010 — Settings export and import as a readable file, never with keys
- **Date:** 2026-11-11
- **Status:** Accepted
- **Context:** The configuration is per installation and lives outside the repository, so moving it to another machine or rebuilding an instance meant copying files by hand — and the first attempt at refreshing defaults overwrote a configuration that existed only there. Putting personal model choices in the repository would make everyone's defaults someone else's taste.
- **Decision:** `conductor config export` writes the whole configuration (profiles, providers, five levels, reviewers, per-model routing) to a TOML file with a trailing `[conductor]` table carrying `schema`, `version` and `exported_at`. `conductor config import` validates it, refuses a newer schema, keeps the previous file as `.bak`, writes atomically and reports the API-key variables that are missing. `conductor config path` prints the file in use. Keys and the spend ledger are not part of the export.
- **Alternatives:** Put the user's profiles in the repository (personal taste in everyone's defaults, and defaults are then never a clean baseline); a single JSON bundle with the configuration as an opaque string (not diffable, not hand-editable); include `auth.json` (copies secrets around, against the security rule that keys never leave the machine).
- **Consequences:** Import replaces rather than merges; merging profiles adds ambiguity (same name, different providers) and is deferred. The metadata table sits last because TOML top-level keys cannot follow a table header. A file exported by a newer conductor with an unknown schema is refused, not partially applied.

## 011 — Fallback models within a difficulty level
- **Date:** 2026-11-11
- **Status:** Accepted (2026-11-12)
- **Context:** Decision 007 gives every level exactly one model, and CLAUDE.md forbids retrying on model errors other than a reviewer rejection. A single provider outage therefore fails the step and skips its dependents; an HTTP error from the reviewer aborts the run. Decision 009 already lists this as a consequence of pinning upstreams.
- **Decision:** A level is an ordered list of models; a plain string stays a one-model list. The reviewer is a list too. Errors are classified:
  - *transient* (429, 5xx, network): OpenCode retries these itself, with its own backoff and no limit. Conductor reads the event stream while the worker runs, stops the process once it has seen more than `retry.transient_attempts` `retry` events (default 3, per profile), then moves to the next model. There is no `backoff_seconds`: the wait is OpenCode's;
  - *provider unusable* (401, 402, missing key): move to the next model on a different provider and exclude that provider for the rest of the run;
  - *model unsuitable* (context exceeded, unknown model): move to the next model;
  - *unclassified*: the step fails, as today.

  Verified on OpenCode 2.2.7 against a fake OpenAI-compatible provider: errors that are not retried end with exit code 1 and an `error` event; retried ones emit `retry` events and never end on their own. The event's `error.type` gives the class: `provider.rate-limit`, `provider.internal` and `provider.transport` are transient; `provider.auth` and `provider.quota` make the provider unusable; `provider.no-route`, and `provider.invalid-request` whose message mentions the context length, make the model unsuitable. Any other type is unclassified.

  A level exhausted by errors ends the step as `unavailable`; it never escalates, so an outage cannot move work onto a pricier level. A reviewer rejection still escalates. Fallback models must belong to providers of the same profile, so the profile's data policy holds. Every fallback starts on a fresh worktree. Attempt records list each fallback with its error class, and costs are those of the model that actually ran. Reviewer errors (HTTP failures and unparseable verdicts) move to the next reviewer without costing the worker a level; when every reviewer has failed, the step becomes `needs_brain_review` instead of aborting the run, and it is never approved.
- **Alternatives:** Gateway fallbacks only (`allow_fallbacks` covers upstreams of one model, not a gateway outage or a direct provider); escalating on errors (outages turn into cost surprises); retrying any error blindly (hides real failures, burns budget).
- **Consequences:** Replaces the "one model each" part of 007 and the "do not retry" rule. The configuration stays backward compatible. `conductor setup` edits lists, and the shipped defaults gain a direct provider next to OpenRouter, with second models chosen with the rule of 008, so a gateway outage is covered too (at the price of a second key). `validate` warns when every model of a level sits on one provider. The classification follows OpenCode's error types, which can change between releases: an unknown type is unclassified and fails the step visibly rather than being retried. The worker runner must stream events instead of waiting for the process to end.

## 012 — Autonomy levels: ask, guided, free
- **Date:** 2026-11-11
- **Status:** Proposed
- **Context:** Workers are told not to ask questions (#30). `--auto` is always passed, so every permission request is approved. Approved steps are always merged unless `reviewer = "brain"`. There is no way to say how much a worker may decide alone, although simple steps deserve more freedom than migrations.
- **Decision:** `conductor run --autonomy ask|guided|free` sets a ceiling for the run, with a default in the profile. A step may lower it with `"autonomy"`, never raise it, so the planner cannot grant itself freedom.
  - `ask`: any doubt or permission request pauses the step as `needs_decision`; merges are manual; escalation stops one level above the starting one.
  - `guided`: the worker decides mechanical choices and those covered by the instructions, otherwise it stops; permission requests are denied and the worker continues without them; merge is automatic after verification and review; every choice beyond the spec is listed in the handoff.
  - `free`: the worker decides and lists its choices; confirm-class actions inside the worktree are allowed (`--auto`).

  At every level: no push, publish or release, no writes outside the worktree, no secrets in the diff, no merge into `main` or `develop`, and `stop_after` points are honoured. These are `deny` rules, which `--auto` cannot approve.
- **Alternatives:** A single `auto_approve` boolean (too coarse: it mixes permissions, questions and merging); reusing the privacy levels (mixes data handling with decision authority); letting the brain set autonomy per step without a ceiling.
- **Consequences:** Depends on the question state (#30), on manual merge, and on detecting rejected permissions in the event stream, because `ask` in `opencode run` rejects instead of asking. The precedence between the worktree's `opencode.json` and an agent's own rules must be verified: agent rules come last and could silently override the level. `ask` costs more brain tokens; `free` moves review after the fact.

## 013 — Steps name an agent; domain context comes from the agent
- **Date:** 2026-11-11
- **Status:** Proposed
- **Context:** Every step runs OpenCode's default agent, so domain rules and standards are repeated in each `spec`. An external source (AIKernel) already builds role + skill compositions with context trimmed per role, but Conductor cannot use them.
- **Decision:** Conductor stays domain-agnostic and ships no roles. A step gains an optional `agent` (passed as `--agent`) and an optional `review_agent`. A profile may name an environment directory, run with `OPENCODE_CONFIG_DIR` and `--standalone`, that provides those agents. The difficulty level still chooses the model (`-m`); the agent provides context and permissions. With `review_agent`, the review runs as a read-only `opencode run --agent` inside the worktree after verification and must end with the JSON verdict; the HTTP reviewer remains for profiles without agents. `validate --agents DIR` checks that the named agents exist.
- **Alternatives:** Built-in roles such as backend, frontend and devops (duplicates the agent source and puts domain knowledge into the executor); a fixed role list in the plan format (ties plans to one taxonomy, while roles are trades and domains are skills); keeping everything in `spec` (status quo: repeated tokens, no shared standards).
- **Consequences:** The contract with the agent source shrinks to agent names and a directory. Reviews through OpenCode cost more per call but see the repository and the domain rules, which addresses part of #32 and allows a `claude-agent` reviewer (#31). Whether `-m` overrides the model declared by an agent must be verified. A misspelled agent fails at `validate`, not in the middle of a run.

## 014 — Default fallbacks on a second provider per profile
- **Date:** 2026-11-12
- **Status:** Accepted
- **Context:** Decision 011 lets a level list fallback models, but the shipped profiles used OpenRouter only, so an OpenRouter outage still stopped every run. Each profile has its own data policy, so one direct provider cannot serve all three.
- **Decision:** Each paid level and each reviewer falls back on the same model on a second provider when it exists there, otherwise on the strongest model per cost that provider offers (rule of 008). `low` uses the DeepSeek API (training allowed; data processed in China), and its free levels fall back on other free OpenRouter models, so an outage never turns a free level into spending. `medium` uses Vercel AI Gateway with `disallowPromptTraining`, which costs nothing extra; `privacy.py` unwraps Vercel's `providerOptions` for OpenCode, which wraps model options itself. `high` uses Scaleway Generative APIs in Paris, which does not train on prompts. Sources: the providers' public price lists and the OpenRouter catalog on 2026-11-12.
- **Alternatives:** A second model on OpenRouter only (no extra key, but no protection against a gateway outage); Scaleway for every profile (one key, but a small catalog, so `medium` and `low` would lose the same-model fallbacks); no default fallbacks (outages stay a user problem).
- **Consequences:** Three more key variables (`DEEPSEEK_API_KEY`, `AI_GATEWAY_API_KEY`, `SCALEWAY_API_KEY`). Without them a fallback is an unusable provider and is excluded for the run, which is harmless. Fallbacks can cost much more than the primary: on Vercel, GLM-5.3 is about 20× and DeepSeek V4 Pro about 12× the OpenRouter price. On `high` the level-5 fallback (GLM-5.3) is weaker than Claude Opus 5.5. `validate` still warns about the free levels of `low`, which rely on OpenRouter alone. Choices per level remain editable with `conductor setup`.

## 015 — Workers stop on open decisions; the brain answers through the plan
- **Date:** 2026-11-12
- **Status:** Accepted
- **Context:** The worker prompt said "Do not ask questions; make reasonable choices", so a design choice the spec did not cover (a name, an edge case, an alternative with different consequences) was taken silently by the cheapest model and found only in the diff. The intent is the opposite: a worker in doubt goes back to the brain, and a brain in doubt goes back to the user (#30).
- **Decision:** The prompt keeps mechanical choices and those settled by the spec, the code or earlier answers with the worker; any other decision with different consequences makes the worker stop before changing files and end its reply with a block starting `QUESTION:`, with the options, their consequences and what it has established. Conductor reads only the final text part of the attempt (OpenCode `text` event, verified on 2.2.7). Such an attempt ends the step as `needs_answer`: no review, no escalation, nothing merged, dependents `skipped`, the question in the attempt and in `run.json`. The brain answers when the spec or decisions already taken settle it, otherwise it asks the user, then reruns a plan with that step and an `answers` list of `{question, answer}`, which goes into the worker prompt. The step starts over on a fresh worktree.
- **Alternatives:** `conductor resume <run>` (needs run state on disk and a new command, while the brain already reruns subsets of a plan for failed steps); continuing the OpenCode session with `--session` (fewer tokens, but the worktree and the session must survive between runs); a dedicated tool or file written by the worker (more moving parts than a marker in text the worker already produces).
- **Consequences:** The plan format gains an optional field, so plans stay compatible. Work done before the question is discarded, which is why the prompt asks the worker to stop before changing files. The marker is untrusted text: stored and shown, never executed. How often cheap models ask, too much or never, is unknown until measured (#37); the prompt is the place to tune it. The autonomy levels of decision 012 build on this state.

## 016 — Verified review: plan commands first, then explicit criteria
- **Date:** 2026-11-12
- **Status:** Accepted
- **Context:** The reviewer received only the spec and the diff and was asked a generic question (#32). It ran nothing, so it could not know whether tests passed, and the plan had no place for the domain rules a change must respect: everything lived in the free text of `spec`.
- **Decision:** The plan gains optional `verify` commands (plan level, replaced or dropped per step), `verify_timeout`, `rules` and a `rules_file` inside the repository. After an attempt without a question, Conductor runs the step's commands with `sh -c` in the worktree, with `CONDUCTOR_REPO` pointing at the main repository (the worktree has no virtualenv); the first failure rejects the attempt with the command's output as the reason, without calling the reviewer, and the step escalates. The reviewer then judges four explicit criteria: the spec is complete, new behaviour has tests in the diff, the declared domain rules hold, no obvious bug or security issue. It receives the rules and the commands that passed in their own sections, and still answers strict JSON. TDD is enforced as "tests in the diff plus passing commands"; the brain may still split tests and code into two steps.
- **Alternatives:** A mandatory test-only step before every implementation step (doubles steps and cost, and makes no sense for docs or configuration); sending the whole touched files to the reviewer (more cost; invariants the diff cannot show go into the rules, and a full review in the repository is the read-only review agent of #36); commands as argument lists without a shell (no variables, so the brain would have to write absolute paths).
- **Consequences:** The plan format changes in a compatible way. A failing verification costs no reviewer call. Commands come from the plan, never from worker output, but they execute files the worker may have changed, which is no more than the worker can already run in its worktree with `--auto`. Steps running the whole suite in parallel multiply the load; the integrations advise the step's own tests. A missing or oversized `rules_file` stops the run before any attempt.

## 017 — Claude Code as a worker harness, chosen by the provider
- **Date:** 2026-11-13
- **Status:** Accepted
- **Context:** Anthropic does not officially support using the Claude subscription through third-party harnesses, so the `claude-agent` provider of OpenCode is out (#31). The best use of the Claude models is to run them through Claude Code (`claude -p`), and the harness should not be fixed per profile: a ladder may want Claude on one level and OpenCode on another.
- **Decision:** The harness is a property of the provider (`harness`, default `opencode`), so the model the plan picks selects the harness; a later task-based rule hooks into the same choice. A provider managed by its harness has neither `base_url` nor `api_key_env`: it is not written to the worktree `opencode.json`, is skipped by `conductor billing` and cannot be a reviewer. The Claude Code worker runs `claude -p --output-format stream-json --verbose --no-session-persistence --setting-sources project --disable-slash-commands --permission-mode acceptEdits --allowedTools=Bash --model <alias> <prompt>`. `--setting-sources project` keeps the user's personal skills, commands and hooks out of a worker's prompt; `acceptEdits` lets it write inside the worktree and denies writes outside, with `Bash` the one extra permission. Retries (`system`/`api_retry` events) feed the same retry limit as OpenCode, and errors map from the HTTP status of the retry or of the `result` event. A subscription reports an estimated cost, recorded under `cost.subscription` and never summed into the billed totals.
- **Alternatives:** Keep `claude-agent` inside OpenCode (Anthropic does not support it); `--dangerously-skip-permissions` (unbounded, and `--auto` is already the most Conductor allows); leave the user's settings loaded (their personal skills reach an unrelated repository, verified); a `harness` field per profile (one harness for a whole ladder, so Claude and OpenCode could not be mixed).
- **Consequences:** Needs the `claude` CLI and a subscription login, both outside Conductor. The `stream-json` and `result` shapes can change across Claude Code releases; a new event type is ignored, and an unknown error stays unclassified, so it fails visibly. A subscription limit (five-hour or weekly) arrives as a `429` and turns the step `unavailable` rather than failed, which is right for the work but means a run can stop for quota. A model reviewer over Claude Code is deferred to #36, and the harness choice by task type to the measurements of #37.

## 018 — The target repository's git hooks apply to workers too
- **Date:** 2026-11-13
- **Status:** Accepted
- **Context:** The first real run on this repository (#31) crashed: the worker produced a correct diff, but its commit message `conductor: ...` was refused by the repository's `conventional-pre-commit` hook, the `git commit` error was not handled, and the whole run stopped with an unfinished `run.json`. Earlier tests used repositories without hooks. The same hooks also run ruff, formatters and `mypy --strict`, and the brain's own commits must pass them.
- **Decision:** Conductor never bypasses the target's hooks (no `--no-verify`). Worker commits and merges use Conventional Commit messages (`chore(conductor): apply step <id> attempt <n>`, `chore(conductor): merge <branch>`), which release-please ignores. A hook that fixes files and fails is retried once with its fixes staged; a hook that still refuses the commit rejects the attempt like a failed verification, with its output as the reason for the next level and in the attempt's `commit_rejection`; it is never a provider error. A hook that refuses the merge makes the step `conflict` with the hook output and keeps the branch. Any unexpected error inside a step fails that step, and the run goes on.
- **Alternatives:** `--no-verify` on worker commits (the work would reach the branch unchecked and the brain would meet the failures later, on its own commits); turning hook failures into model errors (they are about the work, not the provider, so they must escalate with feedback).
- **Consequences:** Slow hooks (`mypy`) lengthen every attempt; a faster type-check hook is tracked as optional in #55. The worker sees hook failures as review feedback, which is useful for lint and type errors.

## 019 — OpenCode workers see no skills and read the target's CLAUDE.md
- **Date:** 2026-11-13
- **Status:** Accepted
- **Context:** In the #37 runs, 3 of 10 OpenCode attempts loaded the user's personal `dev-workflow` skill, which OpenCode discovers in `~/.claude/skills` and `~/.agents/skills` as well as its own directories (#61). The skill says "no code before an approved plan": GPT-5.6 Luna presented a plan or asked "approve the plan?" and wrote nothing, costing a level each time. A real check listed 18 personal skills available to a worker; their text would also reach the profile's provider. The same check showed that OpenCode 2 reads `AGENTS.md` only, so OpenCode workers had never seen this repository's `CLAUDE.md`, while Claude Code workers do (decision 017).
- **Decision:** The `opencode.json` written in each worktree carries `permissions: [{"action": "skill", "resource": "*", "effect": "deny"}]`: no skill is advertised or loadable, including the target repository's own, which matches the Claude Code worker (no skills after decision 017). When the target has a `CLAUDE.md` and no `AGENTS.md`, the file also lists `"instructions": ["CLAUDE.md"]`. Verified on a throwaway clone: 18 skills without the rule, none with it; with `instructions`, the worker quotes `CLAUDE.md` without reading any file.
- **Alternatives:** Deny only the user's skills by name (the list changes whenever the user adds one, and IDs do not say where a skill comes from); keep project skills (a worker gets its brief from Conductor's prompt; an allow-list can come later if a target needs one); a worker prompt telling the model to ignore skills (models follow skill text over a general rule, as seen).
- **Consequences:** A target repository that relies on its own OpenCode skills does not get them in workers. Other global OpenCode sources (a global `AGENTS.md`, MCP servers, plugins) are not blocked; the user has none today, and they belong to a later check if that changes.

## 020 — Workers get a working brief and propose their commit message
- **Date:** 2026-11-14
- **Status:** Accepted
- **Context:** The bare prompt cost attempts in the #37 runs: a model presented a plan or asked "approve the plan?" instead of doing the work, and mypy errors the worker could have seen in its own worktree surfaced only as hook rejections. Meanwhile the `chore(conductor)` fallback left Conductor's work out of release-please's CHANGELOG, so the generated release notes hid what these models actually changed.
- **Decision:** Every prompt opens with one short working brief, for every harness: the plan is already approved, do the work now and write tests first, stay in scope, run the step's `verify` commands yourself, and remember Conductor commits through the repository's git hooks. The worker ends its reply with a `COMMIT: <subject>` line proposing the commit message. Conductor commits the attempt with the plan's `commit` field when the step has one, else the worker's proposal when it matches the strict Conventional Commit regex, else the fallback `chore(conductor): apply step <id> attempt <n>`; the body names the step, the attempt and the model. The reviewer judges the proposed message against the diff and rejects one that does not describe it or has the wrong type. `conductor validate` checks the plan's optional `commit` field. Updates 018.
- **Alternatives:** A separate cheap model writing the message after approval (one more call, latency and failure point, and an `--amend` that reruns the git hooks on every attempt); keeping a fixed `chore` message (still hid the work from the CHANGELOG and gave the reviewer nothing to judge).
- **Consequences:** The plan format gains an optional `commit` field, so plans stay compatible and a step only uses it when the brain already knows the right subject. The `COMMIT:` marker is untrusted worker text: read strictly, gated by the regex, with the fallback retained. The reviewer now names the commit message as a criterion, and release-please's CHANGELOG shows Conductor's changes under their real types. Refs #62 #64.

## 021 — Reviewer verdicts name a category; passed checks settle theirs
- **Date:** 2026-11-14
- **Status:** Accepted
- **Context:** In the #62/#64 run the reviewer rejected two correct attempts with all checks green (a "missing import" that existed, a validation that had already happened), $0.59 of $0.75 and two needless escalations. The reviewer already received the check results but not what they rule out: nothing told it that a passed type check or test run settles those problems, or that the diff shows only part of each file.
- **Decision:** The reviewer prompt says passed checks settle their problems and unseen code is not missing, and the verification section starts with an all-passed line. Every rejection names a category from a closed list (`types`, `imports`, `syntax`, `format`, `lint`, `failing-tests`, `spec`, `missing-tests`, `domain`, `logic`, `security`, `commit`); a missing or unknown category is an unparseable verdict and moves to the next reviewer. Code, not a model, marks a rejection suspicious when a passed `verify` command of a known tool covers its category (by tool name; `ruff format` counts as a formatter only). For now suspicious rejections are only recorded, still escalating; a second opinion is decided later with the measurements of #65.
- **Alternatives:** Matching words in the reason (fragile both ways); asking a model whether the error is settled (one more call); sending the reviewer more context (more tokens on every review).
- **Consequences:** A weak reviewer that omits the category produces more unparseable verdicts; the category is data for #65. Updates 016. Refs #68.
