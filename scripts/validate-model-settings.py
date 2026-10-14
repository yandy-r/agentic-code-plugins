#!/usr/bin/env python3
"""Verify native runtime configs match ycc/settings/models.json declarations."""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

from generate_opencode_plugin import expected_agent_ids, validate_agent_models

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS = json.loads((REPO_ROOT / "ycc/settings/models.json").read_text(encoding="utf-8"))["targets"]
errors: list[str] = []


def expect(actual: object, wanted: object, label: str) -> None:
    if actual != wanted:
        errors.append(f"{label}: got {actual!r}, expected {wanted!r}")


# Claude native settings
claude = json.loads((REPO_ROOT / "ycc/settings/settings.json").read_text(encoding="utf-8"))
expect(claude.get("model"), MODELS["claude"]["main"]["model"], "Claude main model")
expect(
    claude.get("modelSettings", {}).get(MODELS["claude"]["main"]["model"], {}).get("effortLevel"),
    MODELS["claude"]["main"]["effort"],
    "Claude main effort",
)
expect(
    claude.get("env", {}).get("CLAUDE_CODE_SUBAGENT_MODEL"),
    MODELS["claude"]["subagent"]["model"],
    "Claude subagent model",
)
expect(
    claude.get("env", {}).get("CLAUDE_CODE_SUBAGENT_MODEL_FORCE"),
    "1",
    "Claude subagent model force",
)
expect(
    claude.get("modelSettings", {}).get("claude-opus-5", {}).get("effortLevel"),
    MODELS["claude"]["subagent"]["effort"],
    "Claude subagent effort",
)

# Codex native config
codex = tomllib.loads((REPO_ROOT / ".codex-plugin/config/config.toml").read_text(encoding="utf-8"))
expect(codex.get("model"), MODELS["codex"]["main"]["model"], "Codex main model")
expect(codex.get("model_reasoning_effort"), MODELS["codex"]["main"]["effort"], "Codex main effort")
expect(
    codex.get("agents", {}).get("default_subagent_model"), MODELS["codex"]["subagent"]["model"], "Codex subagent model"
)
expect(
    codex.get("agents", {}).get("default_subagent_reasoning_effort"),
    MODELS["codex"]["subagent"]["effort"],
    "Codex subagent effort",
)

# Cursor main CLI config (subagents are generator-validated separately)
cursor = json.loads((REPO_ROOT / ".cursor-plugin/config/cli-config.json").read_text(encoding="utf-8"))
expect(cursor.get("model", {}).get("modelId"), MODELS["cursor"]["main"]["model"], "Cursor main model")

# OpenCode generated config
opencode = json.loads((REPO_ROOT / ".opencode-plugin/opencode.json").read_text(encoding="utf-8"))
expect(opencode.get("model"), MODELS["opencode"]["main"]["model"], "OpenCode main model")

# Per-agent pins are declared in models.json and emitted verbatim, so the two
# mappings must match key for key. The declared side is checked with the same
# coverage/reference rules the generator applies (every ycc/agents/*.md basename
# plus the built-ins, full provider/model strings); the emitted side is then
# diagnosed agent by agent so one run names every divergence.
try:
    declared_agents = validate_agent_models(MODELS["opencode"].get("agents"))
except SystemExit as exc:
    declared_agents = {}
    errors.append(f"OpenCode declared agents: {exc}")

emitted_agents = opencode.get("agents")
if not isinstance(emitted_agents, dict):
    errors.append(f"OpenCode agents: expected an object, got {type(emitted_agents).__name__}")
    emitted_agents = {}

for name in sorted(expected_agent_ids() | set(declared_agents) | set(emitted_agents)):
    label = f"OpenCode agents.{name}"
    entry = emitted_agents.get(name)
    if name not in emitted_agents:
        errors.append(f"{label}: missing from generated opencode.json")
    elif name not in declared_agents:
        errors.append(f"{label}: emitted but not declared in models.json")
    elif not isinstance(entry, dict) or not isinstance(entry.get("model"), str):
        errors.append(f"{label}: malformed entry {entry!r}, expected {{'model': 'provider/model'}}")
    else:
        expect(entry["model"], declared_agents[name], f"{label}.model")

if errors:
    for error in errors:
        print(f"  {error}", file=sys.stderr)
    raise SystemExit(1)

print("OK: runtime model/effort configs match ycc/settings/models.json declarations.")
