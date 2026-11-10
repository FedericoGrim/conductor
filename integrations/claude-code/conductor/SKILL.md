---
name: conductor
description: Delegate the coding of an approved plan to cheaper models through Conductor. Use when the user says "conductor", "delegate the implementation", "run the plan with conductor", or wants a plan executed by other models while Claude stays the planner and reviewer.
---

# Conductor

You are the brain. You plan and judge; other models type the code.

## 1. Write the plan

Explore the repository first. Then write `plan.json` in the repository root:

- `goal`: one line.
- `steps[]`: `id` (kebab-case), `title`, `spec`, `files`, `difficulty`, `depends_on`.
- `spec` is the whole brief for a model that has not read this conversation: exact file paths, function names and signatures, behaviour, edge cases, tests to write, commands that must pass. Never assume context.
- `difficulty`: 1 = mechanical (boilerplate, docs, small tests), 2 = ordinary feature work, 3 = tricky logic, concurrency, security-sensitive code. Match the number of tiers in the user's `conductor.toml` (default 3).
- Steps that run in parallel (no dependency between them) must not touch the same files.

Run `conductor validate plan.json` and fix any error.

## 2. Execute

Ask the user which privacy level to use if they have not said (`low`, `medium`, `high`), then run in the background:

```bash
conductor run plan.json --privacy <level>
```

The repository must be clean (commit or stash first). Do not edit files while it runs.

## 3. Read the result

The command prints the run directory. Open `<run>/run.json` and handle each step:

- `approved`: merged already. Read the diff in `step-<id>/attempt-<n>.json` and double-check it against the spec; fix small issues yourself.
- `failed`: every tier was rejected or OpenCode errored. Read the last attempt's `review.reason`, `stderr` and `events`, then either implement the step yourself or rewrite its spec and rerun a plan containing only that step and its unfinished dependents.
- `conflict`: the branch named in `detail` is kept; resolve the merge yourself.
- `needs_brain_review`: the profile has `reviewer = "brain"`; read the diff and merge the branch yourself if correct, otherwise rerun with a sharper spec.
- `skipped`: a dependency did not get approved; rerun once it is fixed.

Finish with a short summary for the user: steps, models used, attempts, what you corrected by hand, and the run directory for the full transcripts.
