# Measuring what Conductor saves

Conductor claims that a brain writing plans and cheaper models writing code is more productive than the brain writing everything. This page is the protocol for checking that claim on real work, and the register where the results go (#37).

With a handful of tasks the result is an order of magnitude, not a statistic. That is enough to decide whether Conductor is worth it.

## What is compared

- **Without Conductor:** the M1 milestone (0.5.0), written entirely by the brain in one OpenCode session. Its numbers are in [Baseline](#baseline-m1-without-conductor).
- **With Conductor:** the tasks of M2 and later, each planned by the brain and run with `conductor run`.

The tasks are not the same, so the comparison is per unit of delivered work (commits, lines, steps), not per task. If a cleaner comparison is needed later, two or three tasks are done both ways on two branches.

## What is recorded for every task

| Number | Source |
|---|---|
| **Active user time** | Written down by hand: the user says when the real work on the task starts and ends (not the elapsed time). No tool can measure it. |
| **Brain tokens** | The brain's OpenCode session (`opencode session export <id>`): input, output, reasoning, cache read and cache write of the planning model, counted from the task's start to its PR. |
| **Worker and reviewer cost** | `run.json` of each run and the ledger: dollars per model, and the subscription estimate for Claude Code workers (`cost.subscription`). |
| **Elapsed time to PR** | From the start of the task to the PR being opened. |
| **Quality** | Steps approved on the first attempt, escalations, steps the brain finished by hand, fix commits after the run, problems found in review. |
| **Size** | Commits, lines added and removed, lines of tests (`git diff --shortstat`). |

The brain on a subscription costs nothing in dollars, so its weight is measured in tokens of the strongest model: those are what a quota limits. Cache reads are listed apart, because they cost a fraction of fresh input.

## Rules

- **Learning runs are discarded.** The first two runs (2026-11-13: the run that crashed on the git hooks and the smoke test on a throwaway clone) do not count.
- **Test runs are not counted.** Runs whose project lives under `/tmp` are trials of Conductor itself, not work.
- **No invented numbers.** A number that was not recorded is written "n/a", never estimated.
- **Only numbers leave a session.** The brain's transcript is read only for token counts and model names, never for its text.

## Baseline: M1 without Conductor

M1 (#30, #32, #34, plus the fixes #44 and #46), in session `ses_e2f8d95e…` on 2026-11-12, from 16:48 to 23:54, split from the #31 work in the same session at the merge of PR #49.

| Number | Value |
|---|---|
| Active user time | n/a (not recorded at the time) |
| Elapsed time | 7 h 06 min, with 17 user messages |
| Brain | Claude Opus (subscription), 281 replies |
| Brain tokens | input 592, output 169,301, reasoning 46,464, cache write 969,779, cache read 56,926,176 |
| Workers and reviewer | none |
| Size | 39 commits, 39 files, +2,465 / −294 lines, of which tests +1,415 / −64 |

## Register

One row per task with Conductor, from the first counted run on.

| Task | Active user time | Elapsed to PR | Brain tokens (output + reasoning) | Brain tokens (cache read) | Workers + reviewer | Steps (first try / total) | Hand fixes | Size |
|---|---|---|---|---|---|---|---|---|
| #37: protocol and `conductor stats` (2026-11-13) | 33 min (16:51–17:24) | 38 min | 38,148 (26,924 + 11,224), 50 replies of Claude Opus | 8,025,162 | $1.068 in 3 runs | 1 / 4 (10 attempts) | 2 commits (a missing case in `stats-report`), 2 reruns of `stats-cli` with a sharper spec | 7 commits, 13 files, +1,469 / −7, tests +625 |

Notes on the #37 row:
- The brain tokens cover the task from its start to the PR; the cache read is the brain re-reading its context, not new work.
- 3 of the 10 attempts were wasted by #61 (the worker loaded the user's personal `dev-workflow` skill and stopped to present a plan or ask for approval): $0.023 directly, plus the escalations they caused.
- One rejection was wrong: run alone, `stats-cli` was reviewed on its diff only, without knowing that `conductor/stats.py` already existed (#36).
- The worker commits were renamed by hand from `chore(conductor): apply step ...` to `feat(...)` so that release-please sees them (#62).

## Model benchmark (#65, 2026-11-14)

Eight candidate worker models ran the five tasks of `benchmarks/tasks/` through Conductor, three repetitions each, on one throwaway copy per job with the repository's own hooks, verification and a fixed reviewer (`openrouter/openai/gpt-5.6-luna`). 120 jobs, 8 × 5 × 3, for a total of **$5.92** (about $6.4 with the trial and the discarded first runs). Details and the raw records: `scripts/benchmark.py`, `benchmarks/README.md`.

The hidden tests barely separate the models: every candidate except `deepseek-v4-pro-0813` passes them on every job, so the differences come from the reviewer, not from correctness. A rejection whose only defect was the commit type is counted apart: the reviewer demanded `feat` where the worker wrote `fix`, on tasks whose real commit was `fix`.

| Model | Correct (hidden tests) | Solved (approved) | Cost | $/correct | Mean time | Commit-type only rejections | Other rejections with the tests green | False approvals |
|---|---|---|---|---|---|---|---|---|
| `anthropic/claude-haiku-5.5` | 15/15 | 12/15 | 0.180 | 0.0120 | 54.8 s | 3 | 0 | 0 |
| `deepseek/deepseek-v4-flash-0731` | 15/15 | 11/15 | 0.410 | 0.0273 | 138.2 s | 1 | 3 | 0 |
| `z-ai/glm-5.3-flash` | 15/15 | 11/15 | 0.442 | 0.0295 | 123.2 s | 1 | 3 | 0 |
| `minimax/minimax-m3.1-flash` | 15/15 | 14/15 | 0.464 | 0.0309 | 115.7 s | 1 | 0 | 0 |
| `z-ai/glm-5.3` | 15/15 | 12/15 | 1.921 | 0.1281 | 134.4 s | 1 | 2 | 0 |
| `openai/gpt-5.6-luna` | 14/15 | 11/15 | 0.250 | 0.0178 | 68.7 s | 2 | 1 | 0 |
| `deepseek/deepseek-v4.1-flash-1017` | 14/15 | 9/15 | 0.262 | 0.0187 | 93.8 s | 4 | 1 | 0 |
| `deepseek/deepseek-v4-pro-0813` | 12/15 | 8/15 | 1.991 | 0.1659 | 179.0 s | 2 | 2 | 2 |

What the numbers say:
- **Answering #65:** `claude-haiku-5.5` costs the least per correct job ($0.012, five times less than `deepseek-v4-flash-0731`) and is the fastest (55 s), `minimax-m3.1-flash` is the most reliable on approvals (14/15), and the two models the ladders used for the hard levels, `glm-5.3` and `deepseek-v4-pro-0813`, are the most expensive and the least reliable. The new ladders follow that: cheap, fast models first, with the old expensive ones out of `medium`.
- **The reviewer costs more than it looks:** most rejection verdicts were wrong or pedantic, and the only two false approvals (2 of 120) are its (`deepseek-v4-pro-0813`, `hook-rejection`). This is the evidence the second opinion of #68 should be decided on.
- **A first run of `gpt-5.6-luna` failed 12 of 15 jobs with `provider.rate-limit`** (`new-account-rpm`, 20 requests per minute): those are errors of the provider, not of the model, and were rerun one job at a time.
- Limits: one cheap-to-medium model per job, five tasks from one Python repository, three repetitions, and only `medium` measured; `low` and `high` reuse the same models where their providers have them.
