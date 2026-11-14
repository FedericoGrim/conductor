# Model benchmark

A rerunnable benchmark that measures, per worker model: which real tasks of this repository Conductor solves, at what cost, and how accurate the fixed reviewer is (#65). `scripts/benchmark.py run` runs the jobs, `scripts/benchmark.py report` prints the summary. Results go to `benchmarks/results/` (git-ignored); the per-model summary goes into [docs/measurements.md](../docs/measurements.md).

## What is measured

Every task in `benchmarks/tasks/` is a piece of this repository's own history: a real commit, a spec written by the brain as it would be for a real plan (exact interfaces, so that the hidden tests can run), and the test files of the solution commit as hidden tests. Each candidate model runs the tasks through Conductor like any worker and is scored against the ground truth of the solution commit, not against the reviewer's taste:

- **Solved** — the jobs that ended approved with the hidden tests passing.
- **Cost** — worker plus fixed reviewer in dollars per job, dollars per solved job, and the mean time per job.
- **Reviewer accuracy** — the reviewer is the same model in every profile, so only the worker changes between runs; false rejections and false approvals measure how far its verdicts are to be trusted.

## How a job works

A job is one profile × task × repetition:

1. **A throwaway copy of the starting commit.** The task's `base` commit is extracted with `git archive` into a fresh repository: one commit (`chore: benchmark base`), the tracked files only, no history, no remote, no other branches — the worker starts exactly where the task started. The copy's `.venv` is a symlink to this repository's (kept out of diffs through `.git/info/exclude`), and the repository's own git hooks are installed in it (`pre-commit install --hook-type pre-commit --hook-type commit-msg`), so the worker's commit goes through the same pre-commit hooks as in a real run.
2. **A one-step plan at difficulty 5.** One step, built from the task. Difficulty 5 is the last level, so every level of the profile is the same candidate model and there is **exactly one attempt**: an approval ends the job, and a rejection has no next tier to escalate to. The plan's `verify` is the repository's own checks — `pytest -q`, `ruff check conductor tests`, `mypy --strict conductor tests` — run through `$CONDUCTOR_REPO`, which is the copy.
3. **A real Conductor run:** `conductor run <plan> --config benchmarks/profiles.toml --privacy <profile> --repo <copy>`, the same hooks, verification and review as any run, with the full output in `<out>/logs/<job>.log`.
4. **The worker's commit** is picked up after the run: the merged `HEAD` when the step was approved, otherwise the branch `conductor/<run>/<step>-<attempts>` that Conductor keeps for a rejected attempt; a run that committed nothing has nothing to check.
5. **The hidden tests are checked on that commit, and only there.** The commit is checked out as a detached worktree, the task's `hidden_tests` files are read from the solution commit (`git show <solution>:<path>`) and written next to the worker's own tests as `tests/hidden_<name>.py`, and pytest runs exactly those files (600 s timeout; a timeout counts as a failure). They are written after the run and appear in no plan or spec, so the worker never sees them.
6. One JSON record per job is appended to `<out>/results.jsonl`; unless `--keep`, the copy is deleted.

## What an outcome means

| Outcome | Meaning |
|---|---|
| **solved** | the step was approved and the hidden tests pass on the worker's commit |
| **false rejection** | the reviewer rejected the attempt although the hidden tests pass |
| **false approval** | the step was approved although the hidden tests fail |
| **suspicious** | a rejection whose category a passed verify command already settles (the rule in `conductor/rejections.py`); it stays a rejection and is counted apart |
| **error** | lost to the provider or the harness, not to the model: `unavailable`, no run at all, or `failed` without a review; counted in the totals line, not against the model |

A job that produced no commit to check (a question, a conflict, a crashed run) has no hidden-test verdict: none of the three job flags is set.

## Task file format

One JSON file per task in `benchmarks/tasks/`, named `<id>.json` — `https-only` as the example:

```json
{
  "id": "https-only",
  "title": "Never send the reviewer key to a base URL that is not https",
  "difficulty": 1,
  "base": "b8bf431",
  "solution": "7cb879e",
  "hidden_tests": ["tests/test_reviewer.py", "tests/test_config.py"],
  "files": ["conductor/config.py", "conductor/reviewer.py", "tests/test_config.py", "tests/test_reviewer.py"],
  "spec": "..."
}
```

| Field | Meaning |
|---|---|
| `id` | unique; also the step id and the report's task key |
| `title` | one line; the plan's goal |
| `difficulty` | the task's difficulty, 1–5, as it would be planned in a real run; recorded for the report's per-difficulty columns, while the benchmark itself always runs the step at difficulty 5 |
| `base` | the commit a job starts from: the parent of `solution` |
| `solution` | the commit that solved the task; the hidden tests are read from it |
| `hidden_tests` | the test files that cover the change, taken whole from the solution commit (repository-root paths) |
| `files` | the files the worker may touch; the step's `files` |
| `spec` | the task text the worker receives; the step's `spec`, self-contained (the worker sees only the copy) |

## Adding a task

1. Pick the commit that did the work as `solution` and its parent as `base`.
2. List in `hidden_tests` the test files the commit added or changed.
3. Write `spec` from the issue, self-contained.
4. Check by hand that the hidden tests **fail on `base`** and **pass on `solution`**, and that `solution` is clean under `ruff check conductor tests` and `mypy --strict conductor tests`. A task whose hidden tests already pass on `base` measures nothing, and a solution that fails the plan's own verify makes every job fail on the ground truth instead of on the model.

## Adding a candidate

A candidate is one profile in `benchmarks/profiles.toml`, named after its model (`bench-<model>`) like the shipped ones:

- the same model in all five `tiers`: the plan's fixed difficulty 5 must always pick the candidate, and no attempt may fall back to another model;
- the fixed reviewer `openrouter/openai/gpt-5.6-luna`, the same in every profile, so only the worker changes between runs;
- `max_parallel = 1` and a single `openrouter` provider with `api_key_env = "OPENROUTER_API_KEY"` and `request_options = { provider = { data_collection = "deny" } }`.

Run one candidate with `--profiles bench-<model>`; unknown profile or task names are refused before anything is spent.

## Commands

```bash
python scripts/benchmark.py run [--profiles bench-a,bench-b] [--tasks id1,id2] \
       [--repeat 3] [--budget 12] [--parallel 4] [--out DIR] \
       [--config benchmarks/profiles.toml] [--conductor PATH] [--keep]
python scripts/benchmark.py report <results directory or results.jsonl>
```

| Option | Meaning |
|---|---|
| `--profiles` | comma-separated profile names (default: every profile in the file) |
| `--tasks` | comma-separated task ids (default: every task) |
| `--repeat` | repetitions per profile and task (default 3); the job count is profiles × tasks × repeat |
| `--budget` | USD cap of the whole run (default 12): once the spend recorded so far reaches it, the jobs not started yet are skipped and counted in a line at the end; jobs already running finish |
| `--parallel` | jobs running at the same time (default 4), each in its own copy |
| `--out` | output directory (default `benchmarks/results/<timestamp>`) |
| `--config` | the profiles file (default `benchmarks/profiles.toml`) |
| `--conductor` | the `conductor` executable (default: `conductor` from `PATH`) |
| `--keep` | keep the throwaway copies for inspection |

`run` prints one line per job — `bench-glm-5-3-flash-https-only-1: approved  solved=True  cost=0.0412 USD` — and exits non-zero only when the benchmark itself failed (a bad task or profile, a copy that could not be built); a rejected or failed step is a result, not an error. `report` prints the Markdown summary of one run: a row per model (solved per difficulty, cost, dollars per solved job, mean time, rejections, false rejections, false approvals, suspicious), a row per task (solved per model) and a totals line with the job count, the total cost and the errors.

## Results

A run writes everything under its output directory, by default `benchmarks/results/<timestamp>/` (git-ignored):

- `results.jsonl` — one JSON record per job: `profile`, `model`, `task`, `difficulty`, `repetition`, `status`, `attempts`, `cost`, `seconds`, `review` (the last attempt's verdict: `ok`, `category`, `suspicious`), `hidden_ok`, and the flags `solved`, `false_rejection`, `false_approval`;
- `plans/` (the generated plans), `logs/` (the full Conductor output per job) and `work/` (the copies and check worktrees, deleted after the job unless `--keep`).

The summary printed by `report` is what goes into [docs/measurements.md](../docs/measurements.md), next to the measurement protocol.

## It spends real money

Every job runs the real `conductor` against real providers and pays the worker and the fixed reviewer, and every finished run is appended to the real ledger (`~/.local/share/conductor/ledger.jsonl`, which `conductor billing projects` reads) under the throwaway copy's path. `--budget` caps what a run may spend. The workers are authenticated like any OpenCode worker (`opencode auth login`); the fixed reviewer needs `OPENROUTER_API_KEY` in the environment or in `auth.json`.
