# Conductor

A brain model writes the plan; cheaper models write the code.

Conductor takes a `plan.json` produced by a planning model (Claude in Claude Code, or any model in OpenCode), runs each step in parallel inside its own git worktree through OpenCode on a model picked by the step's difficulty, has every diff reviewed, escalates rejected steps to a stronger model, and logs everything per step and attempt.
