from __future__ import annotations

import json
from pathlib import Path

from conductor.autonomy import forbidden_commands

PERMISSION_EXTENSION_NAME = "pi_permissions.ts"

# The patterns come from autonomy.py, never duplicated here: OpenCode, Claude Code and Pi must
# hold a worker to the same fixed denials.
_SOURCE = r"""import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

// Generated from conductor.autonomy.forbidden_commands(): do not edit by hand.
const FORBIDDEN = __FORBIDDEN__;

function matches(command: string, pattern: string): boolean {
  const source = pattern
    .split("*")
    .map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .join(".*");
  return new RegExp(`^${source}$`).test(command);
}

export default function (pi: ExtensionAPI) {
  pi.on("tool_call", (event) => {
    if (event.toolName !== "bash") {
      return;
    }
    const command = event.input.command;
    if (typeof command !== "string") {
      return;
    }
    const denied = FORBIDDEN.find((pattern: string) => matches(command, pattern));
    if (denied === undefined) {
      return;
    }
    return { block: true, reason: `CONDUCTOR_DENY: ${denied}` };
  });
}
"""

PERMISSION_EXTENSION = _SOURCE.replace(
    "__FORBIDDEN__", json.dumps(list(forbidden_commands()), indent=2)
)


def write_permission_extension(agent_dir: Path) -> Path:
    """Write the generated Pi extension into the attempt's agent directory."""
    agent_dir.mkdir(parents=True, exist_ok=True)
    path = agent_dir / PERMISSION_EXTENSION_NAME
    path.write_text(PERMISSION_EXTENSION)
    return path
