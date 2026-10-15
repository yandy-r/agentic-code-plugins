#!/usr/bin/env python3
"""Typed stdlib assertion helpers for the YAN-1121 namespace harness."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

BANNED_DIAGNOSTICS = re.compile(r"collision|conflict|duplicate", re.IGNORECASE)

EXPECTED_DUP_SKILL_COUNT = {"2.1.143": 2, "2.1.300": 1}


def check(label: str, expected: Any, actual: Any) -> None:
    """Fail closed with label/expected/actual; never return on mismatch."""
    if expected != actual:
        raise SystemExit(f"CHECK FAILED [{label}]: expected={expected!r} actual={actual!r}")


def present(text: str, markers: dict[str, str]) -> dict[str, bool]:
    """Report body-only marker presence in a text blob."""
    return {key: value in text for key, value in markers.items()}


def tool_descriptions(bodies: list[dict[str, Any]]) -> str:
    """Collect tool description/name text from request bodies."""
    chunks: list[str] = []
    for body in bodies:
        tools = body.get("tools", [])
        if isinstance(tools, list):
            for tool in tools:
                if isinstance(tool, dict):
                    for field in ("description", "name"):
                        value = tool.get(field)
                        if isinstance(value, str):
                            chunks.append(value)
    return "\n".join(chunks)


def select_result(results: list[dict[str, Any]], tool_use_id: str) -> dict[str, Any]:
    """Select the single tool_result for a tool_use id; fail closed otherwise."""
    matches = [r for r in results if r.get("tool_use_id") == tool_use_id]
    if len(matches) != 1:
        raise SystemExit(
            f"CHECK FAILED [tool_result {tool_use_id}]: " f"expected exactly 1 match, actual={len(matches)}"
        )
    result = matches[0]
    if not isinstance(result, dict):
        raise SystemExit(f"CHECK FAILED [tool_result {tool_use_id}]: not an object")
    return result


def assert_no_banned_diagnostics(label: str, texts: list[str]) -> None:
    """Fail if install/startup output reports a namespace collision."""
    for index, text in enumerate(texts):
        hit = BANNED_DIAGNOSTICS.search(text)
        if hit:
            raise SystemExit(f"CHECK FAILED [{label} collision diagnostics]: " f"block={index} match={hit.group(0)!r}")


def init_lists(init: dict[str, Any]) -> tuple[list[Any], list[str], list[str]]:
    """Extract plugins/skills/agents from a stream-json init event."""
    plugins = init.get("plugins", [])
    skills = init.get("skills", [])
    agents = init.get("agents", [])
    if not isinstance(plugins, list) or not isinstance(skills, list) or not isinstance(agents, list):
        raise SystemExit("CHECK FAILED [init shape]: plugins/skills/agents must be lists")
    return plugins, [str(s) for s in skills], [str(a) for a in agents]


def assert_shared_init(
    label: str,
    init: dict[str, Any],
    shared: str,
    expected_sources: set[str],
    version: str,
) -> None:
    """Check both same-named plugins load with expected sources and inventory."""
    plugins, skills, agents = init_lists(init)
    named = [p for p in plugins if isinstance(p, dict) and p.get("name") == shared]
    check(label + " plugin count", 2, len(named))
    check(label + " plugin sources", expected_sources, {str(p.get("source")) for p in named})
    expected_dup = EXPECTED_DUP_SKILL_COUNT.get(version)
    if expected_dup is None:
        raise SystemExit(f"CHECK FAILED [{label} dup skills]: unsupported version {version!r}")
    check(label + " dup skill count", expected_dup, skills.count(shared + ":probe"))
    check(label + " agent present", True, shared + ":worker" in agents)


def assert_distinct_init(
    label: str,
    init: dict[str, Any],
    caller: str,
    worker: str,
    market: str,
) -> None:
    """Check distinct manifests load with exact sources and full inventory."""
    plugins, skills, agents = init_lists(init)
    by_name = {}
    for plugin in plugins:
        if isinstance(plugin, dict):
            by_name[str(plugin.get("name"))] = str(plugin.get("source"))
    check(label + " caller source", caller + "@" + market, by_name.get(caller))
    check(label + " worker source", worker + "@" + market, by_name.get(worker))
    for skill in (caller + ":probe", worker + ":probe"):
        check(label + " skill " + skill, True, skill in skills)
    for agent in (caller + ":worker", worker + ":worker"):
        check(label + " agent " + agent, True, agent in agents)


def assert_cross_init(label: str, init: dict[str, Any], caller: str, worker: str) -> None:
    """Check caller exposes skills only and worker exposes the agent set."""
    _, skills, agents = init_lists(init)
    check(label + " caller skill", True, caller + ":probe" in skills)
    check(label + " worker skill", True, worker + ":probe" in skills)
    for agent in ("worker", "same", "qualified", "bare", "missing"):
        check(label + " worker agent " + agent, True, worker + ":" + agent in agents)
    check(label + " caller has no agents", False, any(s.startswith(caller + ":") for s in agents))


def result_text(result: dict[str, Any]) -> str:
    """Render tool_result content as searchable text."""
    return json.dumps(result.get("content", ""))


def true_keys(markers: dict[str, bool]) -> set[str]:
    """Return the marker map's positive keys."""
    return {key for key, value in markers.items() if value}


def verify_matrix(results: list[dict[str, Any]], version: str, prefix: str) -> None:
    """Check installs, inventory, diagnostics, tool outcomes and marker geography."""
    check("probe count", 15, len(results))
    by = {re.sub(r"-ns-[0-9a-f]+-", "-", r["label"]): r for r in results}
    caller, worker, shared = (prefix + "-" + n for n in ("caller", "worker", "shared"))
    for row in results:
        label = row["label"]
        check(label + " status", "observed", row["status"])
        check(label + " CLI exit", 0, row["exit"])
        check(label + " parent request exists", True, row["parent_requests"] > 0)
        expected = row["expected_plugins"]
        check(label + " installed count", 2, len(expected))
        listing = row["plugin_list"]
        check(label + " listed IDs", set(expected), {p.get("id") for p in listing})
        for plugin in listing:
            check(label + " user scope", "user", plugin.get("scope"))
            check(label + " enabled", True, plugin.get("enabled"))
        plugins, skills, agents = init_lists(row["init"])
        fixture_plugins = [p for p in plugins if p.get("name", "").startswith(prefix)]
        check(label + " init plugin count", 2, len(fixture_plugins))
        check(label + " init plugin sources/names", expected, {p.get("source"): p.get("name") for p in fixture_plugins})
        fixture_skills = [s for s in skills if s.startswith(prefix)]
        fixture_agents = [a for a in agents if a.startswith(prefix)]
        if label.startswith(("mismatched-", "shared-markets-")):
            assert_shared_init(label, row["init"], shared, set(expected), version)
            check(label + " exact skills", [shared + ":probe"] * EXPECTED_DUP_SKILL_COUNT[version], fixture_skills)
            check(label + " exact agents", [shared + ":worker"], fixture_agents)
        elif label.startswith("distinct-"):
            assert_distinct_init(label, row["init"], caller, worker, next(iter(expected)).split("@", 1)[1])
            check(label + " exact skills", sorted([caller + ":probe", worker + ":probe"]), sorted(fixture_skills))
            check(label + " exact agents", sorted([caller + ":worker", worker + ":worker"]), sorted(fixture_agents))
        else:
            assert_cross_init(label, row["init"], caller, worker)
            wanted_skills = [caller + ":" + s for s in ("probe", "cross-dispatch", "missing-dispatch", "cross-preload")]
            wanted_skills += [worker + ":" + s for s in ("probe", "same-dispatch", "local-preload")]
            check(label + " exact skills", sorted(wanted_skills), sorted(fixture_skills))
            check(
                label + " exact agents",
                sorted(worker + ":" + a for a in ("worker", "same", "qualified", "bare", "missing")),
                sorted(fixture_agents),
            )
        assert_no_banned_diagnostics(label, row["install_diagnostics"] + [row["startup_diagnostics"]])
        check(label + " first parent marker absence", set(), true_keys(row["first_parent_markers"]))
        check(label + " tool descriptions marker absence", set(), true_keys(row["tool_description_markers"]))
        agent_result = select_result(row["tool_results"], "toolu_ns_agent")
        if label == "missing-dispatch":
            check(label + " no subagent", 0, row["subagent_requests"])
            check(label + " agent result error", True, agent_result.get("is_error", False))
            text = result_text(agent_result)
            check(label + " error names target", True, row["absent_name"] in text)
            check(label + " error not found", True, "not found" in text)
        else:
            check(label + " agent result success", False, agent_result.get("is_error", False))
            check(label + " child request exists", True, row["subagent_requests"] > 0)
    expectations = {
        "mismatched-ab-shared": ({"a"}, {"b"}, set()),
        "mismatched-ba-shared": ({"b"}, {"a"}, set()),
        "shared-markets-ab-shared": ({"a"}, {"b"}, set()),
        "shared-markets-ba-shared": ({"b"}, {"a"}, set()),
        "distinct-ab-caller": ({"a"}, {"a"}, set()),
        "distinct-ab-worker": ({"b"}, {"b"}, set()),
        "distinct-ba-caller": ({"a"}, {"a"}, set()),
        "distinct-ba-worker": ({"b"}, {"b"}, set()),
        "cross-dispatch": ({"caller"}, {"worker"}, set()),
        "same-dispatch": ({"caller"}, {"worker"}, set()),
        "missing-dispatch": ({"caller"}, set(), set()),
        "preload-same": ({"worker"}, {"worker"}, {"local"}),
        "preload-qualified": ({"worker"}, {"worker"}, {"preload"}),
        "preload-bare": ({"worker"}, {"worker"}, {"preload"}),
        "preload-missing": ({"worker"}, {"worker"}, set()),
    }
    check("scenario labels", set(expectations), set(by))
    for label, (parent, system, messages) in expectations.items():
        row = by[label]
        check(label + " parent payload", parent, true_keys(row["markers_in_parent_messages"]))
        check(label + " child SYSTEM payload", system, true_keys(row["child_system_markers"]))
        check(label + " child MESSAGES payload", messages, true_keys(row["child_messages_markers"]))


def negative_self_test() -> None:
    """Prove check() fails closed on every normal run (no weakened-mode switch)."""
    try:
        check("negative-self-test", {"a"}, set())
    except SystemExit as exc:
        if "negative-self-test" in str(exc):
            return
    raise SystemExit("CHECK FAILED [negative-self-test]: check() did not fail closed")


def digest(path: Path) -> str:
    """Hash file bytes without including them in diagnostic output."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(paths: list[str]) -> dict[str, Any]:
    """Capture content/mtime identity, not secret contents; do not follow symlinks."""
    result = {}
    for raw in paths:
        root = Path(raw)
        items = [root]
        if not root.is_symlink() and root.is_dir():
            for directory, dirs, files in os.walk(root, followlinks=False):
                items.extend(Path(directory) / name for name in sorted(dirs + files))
        for item in items:
            if not item.exists() and not item.is_symlink():
                result[str(item)] = {"absent": True}
                continue
            stat = item.lstat()
            result[str(item)] = {
                "mtime_ns": stat.st_mtime_ns,
                "size": stat.st_size,
                "sha256": digest(item) if item.is_file() and not item.is_symlink() else None,
                "symlink": os.readlink(item) if item.is_symlink() else None,
            }
    return result
