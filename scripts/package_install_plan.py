#!/usr/bin/env python3
"""Plan package installs over the validated model without changing catalogs or files."""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

from build_package_graph import package_sets
from generate_codex_common import PLUGIN_ROOT, VERBATIM_SKILL_FILES
from generate_codex_skills import plugin_output_path
from package_model import PackageModel, PackageModelError, load_package_model

TARGETS = ("claude", "cursor", "codex", "opencode", "agents", "omp")
STEP_ORDER = ("base", "dedupe", "agents", "commands", "settings", "rules", "mcp", "hooks")
CARRIERS: dict[str, dict[str, str]] = {
    "claude": {
        "skills": "base",
        "agents": "base",
        "shared": "base",
        "commands": "base",
        "settings": "settings",
        "statusline": "settings",
        "rules": "rules",
        "instructions": "rules",
        "mcp": "mcp",
        "hooks": "hooks",
    },
    "codex": {
        "skills": "base",
        "shared": "base",
        "agents": "agents",
        "settings": "settings",
        "instructions": "rules",
        "rules": "rules",
        "mcp": "mcp",
    },
    # Filesystem carriers do not activate native plugins or consult their caches.
    "cursor": {
        "skills": "base",
        "agents": "base",
        "shared": "base",
        "rules": "base",
        "commands": "commands",
        "hooks": "hooks",
        "settings": "settings",
        "mcp": "mcp",
    },
    # Each native OMP package is one `omp plugin install` (ycc-mcp ships its .mcp.json inside
    # the package, ycc-rules its flat rules/). Hooks never get an OMP carrier (ycc-hooks is
    # excluded on OMP: herdr ships its own integration). The installer-fallback payloads
    # (instructions, settings) are opt-in via --rules/--settings, so no package implies them.
    "omp": {
        "skills": "base",
        "agents": "base",
        "commands": "base",
        "shared": "base",
        "mcp": "base",
        "rules": "base",
    },
}


@dataclass(frozen=True)
class TargetPlan:
    """Complete installer steps, exact Cursor bundle units, and reported fallback gaps."""

    target: str
    steps: tuple[str, ...]
    cursor_units: tuple[str, ...] = ()
    skipped_components: tuple[str, ...] = ()


@dataclass(frozen=True)
class InstallPlan:
    """All targets validated before the shell performs any mutations."""

    targets: tuple[TargetPlan, ...]
    warnings: tuple[str, ...]


def parse_packages(csv: str) -> tuple[str, ...]:
    """Parse a strict CSV, rejecting empty tokens and preserving first occurrence."""
    values = csv.split(",")
    if any(not value.strip() for value in values):
        raise PackageModelError("--package contains an empty value")
    return tuple(dict.fromkeys(value.strip() for value in values))


def plan_install(
    model: PackageModel,
    packages: tuple[str, ...],
    targets: tuple[str, ...],
    *,
    skip_unsupported: bool = False,
) -> InstallPlan:
    """Expand model closures; a package's own components must all be deliverable.

    Explicit unsupported pairs fail before any write. Cursor fallback hooks
    are not inherited: only a package providing hooks owns that carrier. OMP
    inherits no fallback components at all (its --rules/--settings are opt-in).
    """
    known = {package.key: package for package in model.packages}
    for package in packages:
        if package not in known:
            raise PackageModelError(f"unknown package '{package}'")
        if package == "installer-fallback":
            raise PackageModelError("installer-fallback is an internal modeling key, not an installable package")
        if package == "ycc-all":
            raise PackageModelError("ycc-all is gated on automatic dependency installation proof")
        if not any(
            entry.status == "included" and entry.mechanism == "native" and not entry.opt_in
            for entry in known[package].runtimes
        ):
            raise PackageModelError(f"package '{package}' is deferred, excluded, opt-in, or not a native package")
    sets, errors = package_sets(model)
    if errors:
        raise PackageModelError("; ".join(errors))
    plans: list[TargetPlan] = []
    warnings: list[str] = []
    for target in targets:
        if target not in TARGETS:
            raise PackageModelError(f"unknown target '{target}'")
        carriers = CARRIERS.get(target, {})
        components: set[str] = set()
        problem = ""
        for package in packages:
            entry = model.lookup(package, target)
            if entry is None:
                problem = f"package '{package}' is not available for target '{target}'"
            elif entry.status != "included" or entry.opt_in or entry.mechanism != "native":
                problem = f"package '{package}' is {entry.status} or opt-in for target '{target}'"
            else:
                pair = sets[f"{package}@{target}"]
                missing = sorted(set(pair.provides) - carriers.keys())
                if missing:
                    problem = (
                        f"package '{package}' cannot be fully delivered on target '{target}': "
                        f"{', '.join(missing)} have no installer carrier"
                    )
                else:
                    selected = set(pair.install_set)
                    if target == "cursor" and "hooks" not in pair.provides:
                        selected.discard("hooks")
                    if target == "omp":
                        # OMP fallback payloads (instructions, settings) are opt-in via
                        # --rules/--settings, never package-implied.
                        selected &= set(pair.provides)
                    components.update(selected)
            if problem:
                break
        if problem:
            if not skip_unsupported:
                raise PackageModelError(problem)
            warnings.append(f"{problem} — skipping target '{target}'")
            continue
        steps = {carriers[component] for component in components if component in carriers}
        if target == "omp" and "skills" in components:
            # The default-on dedupe step hides the ycc skills OMP also loads from
            # other runtimes' dirs; only a package that ships skills can expose them.
            steps.add("dedupe")
        units = (
            tuple(unit for unit in ("skills", "agents", "rules") if unit in components) if target == "cursor" else ()
        )
        plans.append(
            TargetPlan(
                target,
                tuple(step for step in STEP_ORDER if step in steps),
                units,
                tuple(sorted(components - carriers.keys())),
            )
        )
    if not plans:
        raise PackageModelError("no selected target can install the requested packages")
    return InstallPlan(tuple(plans), tuple(warnings))


LEGACY_PLUGIN_ROOT = "~/.codex/plugins/ycc"


def _codex_payload_valid(root: Path) -> bool:
    """A ycc manifest, skill payload, and relocatable resource references.

    The checked-in legacy bundle rewrites shared references to the fixed
    ~/.codex/plugins/ycc symlink, which the installer creates only when it
    registers locally. A foreign cache holding that bundle cannot resolve those
    references, so only native exports (document-relative paths, per
    generate_codex_skills.rewrite_native_paths) count as working foreign installs.
    """
    try:
        payload = json.loads((root / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not (
        isinstance(payload, dict)
        and payload.get("name") == "ycc"
        and isinstance(payload.get("version"), str)
        and bool(payload["version"])
        and (root / "skills").is_dir()
        and (root / "shared").is_dir()
    ):
        return False
    skills = list((root / "skills").glob("*/SKILL.md"))
    if not skills:
        return False
    # Native generation puts this exact resource-resolution instruction in every
    # emitted SKILL.md. Unlike cache presence, it is evidence of the generator's
    # document-relative path policy (also checked by codex_native_smoke.py).
    native_guidance = "Bundled paths are relative to this SKILL.md's directory"
    for skill in skills:
        try:
            if native_guidance not in skill.read_text(encoding="utf-8"):
                return False
        except (OSError, UnicodeError):
            return False
    # These multi-runtime documents/scripts intentionally preserve install-layout
    # examples. Use the generator's source-to-output policy instead of treating
    # documentation of a legacy path as an actual resource dependency.
    verbatim_outputs = {plugin_output_path(Path(source)).relative_to(PLUGIN_ROOT) for source in VERBATIM_SKILL_FILES}
    for directory in (root / "skills", root / "shared"):
        for document in directory.rglob("*"):
            if not document.is_file() or document.suffix not in {".md", ".sh", ".py"}:
                continue
            if document.relative_to(root) in verbatim_outputs:
                continue
            try:
                if LEGACY_PLUGIN_ROOT in document.read_text(encoding="utf-8"):
                    return False
            except (OSError, UnicodeError):
                return False
    return True


def codex_native_marketplace(home: Path) -> str:
    """Return the marketplace owning a working ycc: enabled=true AND a valid installed payload."""
    try:
        config = tomllib.loads((home / ".codex/config.toml").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ""
    except (OSError, ValueError) as exc:
        raise PackageModelError(f"cannot inspect Codex config: {exc}") from exc
    plugins = config.get("plugins", {})
    names: set[str] = set()
    if isinstance(plugins, dict):
        for selector, entry in plugins.items():
            if not selector.startswith("ycc@") or not isinstance(entry, dict) or entry.get("enabled") is not True:
                continue
            marketplace = selector.removeprefix("ycc@")
            if not marketplace or Path(marketplace).name != marketplace or marketplace in {".", ".."}:
                continue
            cache = home / ".codex/plugins/cache" / marketplace / "ycc"
            if cache.is_dir() and any(_codex_payload_valid(root) for root in cache.iterdir() if root.is_dir()):
                names.add(marketplace)
    foreign = sorted(names - {"local-ycc-plugins"})
    return foreign[0] if foreign else "local-ycc-plugins" if names else ""


def main(argv: list[str] | None = None) -> int:
    """Emit JSON for tooling or tab-delimited records for the sourced shell helper."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packages")
    parser.add_argument("--targets")
    parser.add_argument("--skip-unsupported", action="store_true")
    parser.add_argument("--shell", action="store_true")
    parser.add_argument("--detect-codex-native", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.detect_codex_native is not None:
            print(codex_native_marketplace(args.detect_codex_native))
            return 0
        if args.packages is None or args.targets is None:
            parser.error("--packages and --targets are required")
        plan = plan_install(
            load_package_model(),
            parse_packages(args.packages),
            tuple(args.targets.split(",")),
            skip_unsupported=args.skip_unsupported,
        )
        if args.shell:
            for warning in plan.warnings:
                print(f"warning\t{warning}")
            for target in plan.targets:
                print(f"target\t{target.target}\t{','.join(target.steps)}")
                if target.target == "cursor":
                    print(f"cursor-units\t{' '.join(target.cursor_units)}")
                if target.skipped_components:
                    print(
                        f"warning\t{target.target}: package components "
                        f"{', '.join(target.skipped_components)} have no installer carrier — skipped"
                    )
        else:
            print(json.dumps(asdict(plan), indent=2))
    except PackageModelError as exc:
        print(f"package install: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
