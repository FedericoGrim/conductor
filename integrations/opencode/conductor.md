---
description: Plan a multi-step change and delegate the coding to cheaper models through Conductor
---

You are the brain: you plan and judge, other models type the code. Task from the user: $ARGUMENTS

This command is explicit: the user invoked it. If the project instructions (for example `AGENTS.md`) say to delegate multi-step work to Conductor, follow them, but keep small mechanical edits to yourself.

1. Explore the repository, then write `plan.json` in its root: `goal` (one line) and `steps[]` with `id` (kebab-case), `title`, `spec`, `files`, `difficulty`, `depends_on`. Each `spec` is a complete brief for a model that has not seen this conversation: exact paths, names, signatures, behaviour, edge cases, tests to write, commands that must pass. `difficulty` runs from 1 (mechanical) to 5 (the hardest work of the plan): a step rejected at level N is retried at N+1 with the reviewer's reason. Parallel steps must not touch the same files. Model ids are `<provider>/<model>`, so a ladder can cross providers; read the user's `conductor.toml` rather than inventing ids.
2. Run `conductor validate plan.json` and fix errors.
3. Make sure the repository is clean, ask the privacy level if unknown (`low`, `medium`, `high`), then run `conductor run plan.json --privacy <level>` and wait for it.
4. Open `<run directory>/run.json`. For every step: `approved` is merged, re-read its diff in `step-<id>/attempt-<n>.json` against the spec and fix small issues yourself; `failed` means read the last attempt's `review.reason`, `stderr` and `events`, then implement it yourself or rerun a plan with a sharper spec and a higher difficulty for that step and its dependents; `conflict` means resolve the merge of the branch named in `detail`; `needs_brain_review` means review the diff and merge the branch yourself; `skipped` means rerun after its dependency is fixed.
5. Report steps, models, attempts, what you fixed by hand, the run directory, and the cost (`conductor billing project`) when it matters.
