---
name: conductor
description: Use when the user asks for a multi-step code change in a git repository — a feature, a refactor, or a bug fix that spans several files or needs an ordered plan — and the typing should go to cheaper models while Claude plans, reviews and merges. Do not use for a one-line fix, a question, exploratory reading, or a repository with uncommitted work.
---

# Conductor

You are the brain. You plan and judge; other models type the code.

Use Conductor when the work has at least two steps, or one step that touches several files with a clear specification. Do the work yourself when the change is mechanical, when the user is still exploring, or when the repository is dirty.

## 1. Write the plan

Explore the repository first. Then write `plan.json` in the repository root:

- `goal`: one line.
- `steps[]`: `id` (kebab-case), `title`, `spec`, `files`, `difficulty`, `depends_on`.
- `spec` is the whole brief for a model that has not read this conversation: exact file paths, function names and signatures, behaviour, edge cases, tests to write, commands that must pass. Never assume context.
- `difficulty`: 1 = mechanical (boilerplate, docs, small tests), 2 = ordinary feature work, 3 = tricky logic or several moving parts, 4 = concurrency, migrations or security-sensitive code, 5 = the hardest work of the plan. There are five levels in a profile; a step rejected at level N is retried at N+1 with the reviewer's reason in the prompt.
- Steps that run in parallel (no dependency between them) must not touch the same files.
- A tier may live on a different provider from the one before it: model ids are `<provider>/<model>` and the provider comes from the user's `conductor.toml`. Do not invent ids; ask, or read the profile with `conductor setup` first.

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
- `failed`: every level was rejected or OpenCode hit an unclassified error. Read the last attempt's `review.reason`, `stderr` and `events`, then implement the step yourself or rewrite its spec with a higher `difficulty` and rerun a plan containing only that step and its unfinished dependents.
- `unavailable`: every model of the level hit a model or provider error (rate limit, outage, bad key, no credit, context exceeded), not a judgement on the work. Read the last attempt's `error`; rerun the step later, or with another `--privacy` profile, or implement it yourself. Do not raise its `difficulty` for this. If the error is a key or credit problem, tell the user.
- `conflict`: the branch named in `detail` is kept; resolve the merge yourself.
- `needs_brain_review`: the profile has `reviewer = "brain"`, or the reviewer failed (the last attempt's `review.error` says why); read the diff and merge the branch yourself if correct, otherwise rerun with a sharper spec.
- `skipped`: a dependency did not get approved; rerun once it is fixed.

Check the cost when it matters: `conductor billing project` for this repository, `conductor billing` for the providers' balances.

## 4. Report

Summarise: steps and their status, models and attempts, what you fixed by hand, the run directory, and the cost if the user asked about it.
