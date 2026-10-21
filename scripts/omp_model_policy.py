#!/usr/bin/env python3
"""OMP model policy: `targets.omp` in ycc/settings/models.json and the managed snippet.

`targets.omp` declares ycc's OMP model intent: `main`/`subagent`/`fallback` models, the
OMP roles ycc manages (`roles`) and the Claude agent-model aliases (`agentModels`).
generate_omp_agents.py reads `agentModels`; validate-model-settings.py checks the whole
entry plus ycc/settings/omp/config.yml, the snippet `install.sh --settings` merges into
the user `config.yml`.

Pinned against oh-my-pi v18.12.5 (`src/config/model-roles.ts` `MODEL_ROLES` and the
thinking levels it accepts). Re-check both when the OMP floor moves.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_PATH = REPO_ROOT / "ycc/settings/models.json"
MODELS_LABEL = "ycc/settings/models.json: targets.omp"

# oh-my-pi v18.12.5 src/config/model-roles.ts MODEL_ROLES.
BUILTIN_ROLES = ("default", "smol", "slow", "vision", "plan", "commit", "tiny", "memory", "task", "advisor", "widget")
# Thinking levels a `provider/model:<level>` selector accepts.
THINKING = ("off", "minimal", "low", "medium", "high", "xhigh", "max")
# A full `provider/model` reference; bare ids and empty halves are rejected.
SELECTOR = re.compile(r"^[a-z0-9][a-z0-9-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
# Leaves ycc may own in the user config.yml.
SNIPPET_KEYS = frozenset({("modelRoles",), ("tools", "approvalMode")})
APPROVAL_MODE = "write"
# `roles` values: which declared model a managed role resolves to.
ROLE_TARGETS = ("main", "subagent")
REQUIRED_KEYS = ("config", "main", "subagent", "fallback", "roles", "agentModels")


def load_omp(models_path: Path = MODELS_PATH) -> dict[str, Any]:
    """Return `targets.omp` from models.json; fail if it is absent or not an object."""
    payload = json.loads(models_path.read_text(encoding="utf-8"))
    omp = payload.get("targets", {}).get("omp") if isinstance(payload, dict) else None
    if not isinstance(omp, dict):
        raise ValueError(f"{MODELS_LABEL} is missing or not an object")
    return omp


def role_selector(omp: Mapping[str, Any], ref: str) -> str:
    """Managed selector for a `roles` target: `<model>:<effort>, <fallback.model>:<fallback.effort>`."""
    primary = omp[ref]
    fallback = omp["fallback"]
    return f"{primary['model']}:{primary['effort']}, {fallback['model']}:{fallback['effort']}"


def expected_snippet(omp: Mapping[str, Any]) -> dict[str, Any]:
    """The managed config.yml content `targets.omp` implies."""
    return {
        "modelRoles": {role: role_selector(omp, ref) for role, ref in omp["roles"].items()},
        "tools": {"approvalMode": APPROVAL_MODE},
    }


def agent_model_map(models_path: Path = MODELS_PATH) -> dict[str, str | None]:
    """Claude agent `model:` alias -> OMP `@role` (None: emit no model key)."""
    agent_models = load_omp(models_path).get("agentModels")
    if not isinstance(agent_models, dict):
        raise ValueError(f"{MODELS_LABEL}.agentModels must be an object")
    mapping: dict[str, str | None] = {}
    for alias, value in agent_models.items():
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{MODELS_LABEL}.agentModels.{alias} must be null or an '@<role>' string")
        mapping[str(alias)] = value
    return mapping


def _model_errors(omp: Mapping[str, Any], name: str) -> list[str]:
    entry = omp.get(name)
    label = f"{MODELS_LABEL}.{name}"
    if not isinstance(entry, dict):
        return [f"{label} must be an object with 'model' and 'effort'"]
    errors: list[str] = []
    model = entry.get("model")
    if not isinstance(model, str) or not SELECTOR.match(model):
        errors.append(f"{label}.model: expected a full 'provider/model' id, got {model!r}")
    effort = entry.get("effort")
    if effort not in THINKING:
        errors.append(f"{label}.effort: {effort!r} is not an OMP thinking level ({', '.join(THINKING)})")
    return errors


def _roles_errors(roles: object) -> list[str]:
    label = f"{MODELS_LABEL}.roles"
    if not isinstance(roles, dict):
        return [f"{label} must be an object"]
    errors: list[str] = []
    for role, ref in roles.items():
        if role not in BUILTIN_ROLES:
            errors.append(f"{label}.{role}: unknown OMP role (built-in roles: {', '.join(BUILTIN_ROLES)})")
        if ref not in ROLE_TARGETS:
            errors.append(f"{label}.{role}: expected one of {', '.join(ROLE_TARGETS)}, got {ref!r}")
    return errors


def _agent_models_errors(agent_models: object, roles: object, used_agent_models: set[str]) -> list[str]:
    label = f"{MODELS_LABEL}.agentModels"
    if not isinstance(agent_models, dict):
        return [f"{label} must be an object"]
    managed = set(roles) if isinstance(roles, dict) else set()
    errors: list[str] = []
    missing = sorted(used_agent_models - set(agent_models))
    if missing:
        errors.append(f"{label}: no mapping for agent model(s) used in ycc/agents: {', '.join(missing)}")
    for alias, value in agent_models.items():
        where = f"{label}.{alias}"
        if value is None:
            continue
        if not isinstance(value, str):
            errors.append(f"{where}: expected null or '@<role>', got {value!r}")
        elif value.startswith("pi/"):
            errors.append(f"{where}: legacy 'pi/' alias {value!r} is not valid on OMP; use '@<role>'")
        elif not value.startswith("@"):
            errors.append(f"{where}: expected null or '@<role>', got {value!r} (bare model ids are not allowed)")
        elif value[1:] not in managed:
            errors.append(
                f"{where}: {value!r} names a role ycc does not manage; add it to {MODELS_LABEL}.roles "
                f"(managed: {', '.join(sorted(managed)) or 'none'})"
            )
    return errors


def _snippet_errors(snippet: object, expected: Mapping[str, Any] | None, config_label: str) -> list[str]:
    if not isinstance(snippet, dict):
        return [f"{config_label}: expected a mapping, got {type(snippet).__name__}"]
    errors: list[str] = []
    for key, value in snippet.items():
        if (key,) in SNIPPET_KEYS:
            continue
        nested = {path[1] for path in SNIPPET_KEYS if path[0] == key and len(path) == 2}
        if not nested:
            errors.append(f"{config_label}: '{key}' is not a ycc-managed OMP key")
        elif not isinstance(value, dict):
            errors.append(f"{config_label}: '{key}' must be a mapping")
        else:
            errors.extend(
                f"{config_label}: '{key}.{child}' is not a ycc-managed OMP key"
                for child in value
                if child not in nested
            )
    if expected is None or errors:
        return errors
    for key in sorted(set(expected) | set(snippet)):
        want = expected.get(key)
        got = snippet.get(key)
        if isinstance(want, dict) and isinstance(got, dict):
            for child in sorted(set(want) | set(got)):
                if got.get(child) != want.get(child):
                    errors.append(
                        f"{config_label}: {key}.{child}: got {got.get(child)!r}, "
                        f"expected {want.get(child)!r} (from {MODELS_LABEL})"
                    )
        elif got != want:
            errors.append(f"{config_label}: {key}: got {got!r}, expected {want!r} (from {MODELS_LABEL})")
    return errors


def omp_model_errors(omp: object, snippet: object, used_agent_models: set[str]) -> list[str]:
    """Every policy violation in `targets.omp` and the managed snippet, one message each."""
    if not isinstance(omp, dict):
        return [f"{MODELS_LABEL} must be an object"]
    missing = [key for key in REQUIRED_KEYS if key not in omp]
    if missing:
        return [f"{MODELS_LABEL}: missing required key(s): {', '.join(missing)}"]
    errors: list[str] = []
    for name in ("main", "subagent", "fallback"):
        errors.extend(_model_errors(omp, name))
    errors.extend(_roles_errors(omp["roles"]))
    errors.extend(_agent_models_errors(omp["agentModels"], omp["roles"], used_agent_models))
    # Only derive the expected snippet from a valid entry; otherwise the drift report is noise.
    expected = None if errors else expected_snippet(omp)
    errors.extend(_snippet_errors(snippet, expected, str(omp["config"])))
    return errors
