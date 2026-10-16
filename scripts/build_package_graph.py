#!/usr/bin/env python3
"""Build the ycc package component graph and validate per-runtime install closures."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from package_graph_extract import Graph, extract_graph  # noqa: E402
from package_model import DEFAULT_MANIFEST_PATH, PackageModel, PackageModelError, load_package_model  # noqa: E402

COMPONENT_OF_KIND = {"skill": "skills", "agent": "agents", "shared": "shared"}
# `mention` edges record prose/navigational `ycc:` cross-references, not runtime dispatch or
# file reach-ins; keep them out of closure so docs mentions do not force the v7 `ycc-agents` split.
CLOSURE_EDGE_KINDS = frozenset({"dispatch", "catalog", "shared", "script", "file", "preload", "handoff"})
# Public packages only: `installer-fallback` (file-copy) is "not a public installable package id"
# (packages.json). Its overlaps with ycc-hooks@cursor and the opt-in opencode npm package are
# native-vs-copy dedupe, owned by `install.sh --package` (YAN-1136), not a package-definition error.
DUPLICATE_MECHANISMS = frozenset({"native", "npm"})
# AGENTS.md: "The `agents` target is skills-only"; packages.json models installer-fallback@agents the same way.
RUNTIME_GAPS = frozenset({("agents", "agents")})


@dataclass(frozen=True)
class PackageSets:
    """Component sets for one package on one runtime."""

    own: tuple[str, ...]
    provides: tuple[str, ...]
    install_set: tuple[str, ...]


def _component(node_id: str) -> str:
    return COMPONENT_OF_KIND[node_id.split(":", 1)[0]]


def package_sets(model: PackageModel) -> tuple[dict[str, PackageSets], list[str]]:
    """Compute `pkg@runtime` own, transitive Claude provides, and install sets, plus cycle errors."""
    entries = {(p.key, r.runtime): r for p in model.packages for r in p.runtimes}
    errors: list[str] = []

    def provides(key: str, runtime: str, chain: tuple[str, ...]) -> set[str]:
        entry = entries[(key, runtime)]
        components = set(entry.components)
        for required in entry.requires:
            if required in chain:
                errors.append(f"requires cycle on {runtime}: {' -> '.join((*chain, required))}")
            elif (required, runtime) in entries:
                components |= provides(required, runtime, (*chain, required))
        return components

    result: dict[str, PackageSets] = {}
    for (key, runtime), entry in sorted(entries.items()):
        own = provides(key, runtime, (key,))
        fallback = entries.get(("installer-fallback", runtime))
        install = own | set(fallback.components if fallback and fallback.status == "included" else ())
        result[f"{key}@{runtime}"] = PackageSets(
            tuple(sorted(entry.components)), tuple(sorted(own)), tuple(sorted(install))
        )
    return result, sorted(set(errors))


def check_closures(
    graph: Graph, model: PackageModel, sets: dict[str, PackageSets] | None = None
) -> tuple[list[str], list[str]]:
    """Return (errors, gaps); callers supplying computed sets must also retain their cycle errors."""
    errors: list[str] = []
    if sets is None:
        sets, errors = package_sets(model)
    gap_edges: dict[tuple[str, str], list[str]] = {}
    edges = [
        e for e in sorted(graph.edges.values(), key=lambda e: (e.src, e.dst, e.kind)) if e.kind in CLOSURE_EDGE_KINDS
    ]
    for package in model.packages:
        for entry in package.runtimes:
            if entry.status != "included":
                continue
            key = f"{package.key}@{entry.runtime}"
            for edge in edges:
                if _component(edge.src) not in sets[key].own or _component(edge.dst) in sets[key].install_set:
                    continue
                message = f"closure unsatisfied: {key} ships {edge.src} needing {edge.dst} ({edge.evidence})"
                if (entry.runtime, _component(edge.dst)) in RUNTIME_GAPS:
                    gap_edges.setdefault((key, _component(edge.dst)), []).append(
                        f"{edge.src}->{edge.dst} ({edge.evidence})"
                    )
                else:
                    errors.append(message)
    gaps = [
        f"runtime gap: {key} has no '{component}' component; {len(items)} edge(s) unmet, first: {items[0]}"
        for (key, component), items in sorted(gap_edges.items())
    ]
    return sorted(set(errors)), gaps


def check_duplicates(model: PackageModel) -> list[str]:
    """Report components shipped by two included native/npm packages on the same runtime."""
    owners: dict[tuple[str, str], list[str]] = {}
    for package in model.packages:
        for entry in package.runtimes:
            if entry.status == "included" and entry.mechanism in DUPLICATE_MECHANISMS:
                for component in entry.components:
                    owners.setdefault((entry.runtime, component), []).append(package.key)
    return sorted(
        f"duplicate component '{component}' on {runtime}: {', '.join(sorted(keys))}"
        for (runtime, component), keys in owners.items()
        if len(keys) > 1
    )


def to_json(
    graph: Graph,
    model: PackageModel,
    errors: list[str],
    gaps: list[str],
    sets: dict[str, PackageSets] | None = None,
) -> str:
    """Serialize deterministically (sorted keys, sorted lists); computes `sets` when omitted."""
    if sets is None:
        sets, _ = package_sets(model)
    payload = {
        "schema_version": 1,
        "source_root": graph.source_root,
        "nodes": {
            n.id: {"kind": n.kind, "path": n.path, **({"stem": n.stem} if n.stem else {})} for n in graph.nodes.values()
        },
        "edges": [
            {"from": e.src, "to": e.dst, "kind": e.kind, "evidence": e.evidence, "count": e.count}
            for e in sorted(graph.edges.values(), key=lambda e: (e.src, e.dst, e.kind))
        ],
        "packages": {
            k: {"own": list(v.own), "provides": list(v.provides), "install_set": list(v.install_set)}
            for k, v in sets.items()
        },
        "gaps": sorted(gaps),
        "errors": sorted(errors),
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Validate graph closures; `--output` additionally writes the graph JSON (`-` is stdout)."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--source-root", type=Path, default=REPO_ROOT / "ycc")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--output", help="Write graph JSON to PATH, or '-' for stdout.")
    group.add_argument("--check", action="store_true", help="Validate only; write nothing (the default).")
    args = parser.parse_args(argv)
    try:
        model = load_package_model(args.manifest)
    except PackageModelError as exc:
        print(f"build_package_graph: {exc}", file=sys.stderr)
        return 1
    graph, extraction_errors = extract_graph(args.source_root)
    sets, cycle_errors = package_sets(model)
    closure_errors, gaps = check_closures(graph, model, sets)
    errors = sorted({*extraction_errors, *cycle_errors, *closure_errors, *check_duplicates(model)})
    if args.output:
        payload = to_json(graph, model, errors, gaps, sets)
        if args.output == "-":
            sys.stdout.write(payload)
        else:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(payload, encoding="utf-8")
    for gap in gaps:
        print(f"build_package_graph: gap: {gap}", file=sys.stderr)
    for error in errors:
        print(f"build_package_graph: {error}", file=sys.stderr)
    if errors:
        return 1
    print(
        f"OK: {len(graph.nodes)} nodes, {len(graph.edges)} edges, {len(gaps)} gaps, 0 errors",
        file=sys.stderr if args.output == "-" else sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
