#!/usr/bin/env python3
"""Regression tests for model-derived package install plans."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from generate_codex_skills import write_tree
from package_install_plan import codex_native_marketplace, parse_packages, plan_install
from package_model import PackageModelError, load_package_model

MODEL = load_package_model()
ROOT = Path(__file__).resolve().parent


def expect_error(packages: tuple[str, ...], target: str, needle: str) -> None:
    try:
        plan_install(MODEL, packages, (target,))
    except PackageModelError as exc:
        assert needle in str(exc), str(exc)
        return
    raise AssertionError("expected package rejection")


def test_closures() -> None:
    for package, target, expected in (
        ("ycc", "claude", ("base", "settings", "rules")),
        ("ycc", "codex", ("base", "agents", "settings", "rules")),
        ("ycc-mcp", "claude", ("settings", "rules", "mcp")),
        ("ycc-mcp", "codex", ("agents", "settings", "rules", "mcp")),
        ("ycc-mcp", "cursor", ("settings", "mcp")),
        ("ycc", "cursor", ("base", "commands", "settings")),
        ("ycc-hooks", "cursor", ("settings", "hooks")),
        ("ycc-hooks", "claude", ("settings", "rules", "hooks")),
        ("ycc", "omp", ("base", "dedupe")),
        ("ycc-mcp", "omp", ("base",)),
        ("ycc-rules", "omp", ("base",)),
    ):
        assert plan_install(MODEL, (package,), (target,)).targets[0].steps == expected
    rules = plan_install(MODEL, ("ycc-rules",), ("cursor",)).targets[0]
    assert rules.cursor_units == ("rules",)
    assert rules.skipped_components == ()
    main = plan_install(MODEL, ("ycc",), ("cursor",)).targets[0]
    assert main.cursor_units == ("skills", "agents")
    hooks = plan_install(MODEL, ("ycc-hooks",), ("cursor",)).targets[0]
    assert hooks.cursor_units == ()
    assert "hooks" not in plan_install(MODEL, ("ycc-mcp",), ("cursor",)).targets[0].steps
    assert parse_packages("ycc,ycc-mcp,ycc") == ("ycc", "ycc-mcp")
    both = plan_install(MODEL, ("ycc", "ycc-mcp", "ycc-rules"), ("omp",)).targets[0]
    assert (both.steps, both.skipped_components) == (("base", "dedupe"), ())


def test_rejections() -> None:
    for package, target, needle in (
        ("unknown", "claude", "unknown package"),
        ("installer-fallback", "claude", "internal modeling key"),
        ("ycc-all", "claude", "dependency installation proof"),
        ("ycc-agents", "claude", "deferred"),
        ("@yandy-r/ycc-opencode", "opencode", "opt-in"),
        ("ycc", "opencode", "not available"),
        ("ycc", "agents", "not available"),
        ("ycc-hooks", "codex", "excluded"),
        ("ycc-mcp", "agents", "not available"),
        ("ycc-hooks", "omp", "is excluded or opt-in for target 'omp'"),
        ("ycc-all", "omp", "dependency installation proof"),
        ("installer-fallback", "omp", "internal modeling key"),
    ):
        expect_error((package,), target, needle)
    all_plan = plan_install(MODEL, ("ycc",), ("claude", "cursor", "codex", "opencode", "agents"), skip_unsupported=True)
    assert tuple(t.target for t in all_plan.targets) == ("claude", "cursor", "codex")
    assert not any("commands" in warning for warning in all_plan.warnings)
    assert not any("shared" in warning for warning in all_plan.warnings)


def test_parse_rejects_empty() -> None:
    for bad in ("", "ycc,", ",ycc", "ycc,,ycc-mcp"):
        try:
            parse_packages(bad)
        except PackageModelError:
            continue
        raise AssertionError(f"expected rejection of {bad!r}")


def test_positive_native_detection() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        (home / ".codex").mkdir()
        config = home / ".codex/config.toml"
        config.write_text('[plugins."ycc@foreign"]\nenabled = true\n', encoding="utf-8")
        assert codex_native_marketplace(home) == "", "enabled config alone is stale, not delivered"
        payload = home / ".codex/plugins/cache/foreign/ycc/1.0.0"
        (payload / ".codex-plugin").mkdir(parents=True)
        manifest = payload / ".codex-plugin/plugin.json"
        manifest.write_text('{"name":"ycc","version":"1.0.0"}', encoding="utf-8")
        assert codex_native_marketplace(home) == "", "manifest without payload is insufficient"
        (payload / "skills/example").mkdir(parents=True)
        (payload / "shared/scripts").mkdir(parents=True)
        (payload / "shared/scripts/helper.sh").write_text("echo helper", encoding="utf-8")
        legacy = payload / "skills/example/SKILL.md"
        legacy.write_text("Bundled resources use ~/.codex/plugins/ycc/shared/scripts/helper.sh", encoding="utf-8")
        assert codex_native_marketplace(home) == "", "legacy fixed-path payload is not relocatable"
        legacy.write_text(
            "Bundled paths are relative to this SKILL.md's directory.\n"
            "Run ../../shared/scripts/helper.sh by absolute path.",
            encoding="utf-8",
        )
        assert codex_native_marketplace(home) == "foreign"
        manifest.write_text(json.dumps({"name": "not-ycc", "version": "1.0.0"}), encoding="utf-8")
        assert codex_native_marketplace(home) == ""
        manifest.write_text('{"name":"ycc","version":"1.0.0"}', encoding="utf-8")
        config.write_text('[plugins."ycc@foreign"]\nenabled = false\n', encoding="utf-8")
        assert codex_native_marketplace(home) == "", "cached but disabled is not active"
        # Documentation of the legacy layout is preserved by the generator's
        # intentional verbatim COPY policy. It is not a resource dependency.
        config.write_text('[plugins."ycc@foreign"]\nenabled = true\n', encoding="utf-8")
        matrix = payload / "shared/references/target-capability-matrix.md"
        matrix.parent.mkdir(parents=True, exist_ok=True)
        matrix.write_text("See ~/.codex/plugins/ycc for the legacy layout.", encoding="utf-8")
        assert codex_native_marketplace(home) == "foreign"
        # Move that doc's path onto the dependency: the executable chain from a
        # non-verbatim skill to shared/scripts counts, and must reject.
        (payload / "shared/scripts/helper.sh").write_text(
            "exec ~/.codex/plugins/ycc/shared/scripts/helper.sh", encoding="utf-8"
        )
        assert codex_native_marketplace(home) == ""


def test_cli() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "package_install_plan.py"), "--packages", "ycc", "--targets", "claude", "--shell"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0 and result.stdout.strip() == "target\tclaude\tbase,settings,rules"


def test_real_native_export() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        (home / ".codex").mkdir()
        payload = home / ".codex/plugins/cache/foreign/ycc/9.9.9"
        payload.mkdir(parents=True)
        write_tree(payload, False, native_paths=True)
        (payload / ".codex-plugin").mkdir(exist_ok=True)
        version = json.loads((ROOT.parent / "ycc/.claude-plugin/plugin.json").read_text(encoding="utf-8"))
        (payload / ".codex-plugin/plugin.json").write_text(
            json.dumps({"name": version["name"], "version": version["version"]}), encoding="utf-8"
        )
        (home / ".codex/config.toml").write_text('[plugins."ycc@foreign"]\nenabled = true\n', encoding="utf-8")
        text = (payload / "shared/references/target-capability-matrix.md").read_text(encoding="utf-8")
        assert "~/.codex/plugins/ycc" in text
        assert codex_native_marketplace(home) == "foreign"


if __name__ == "__main__":
    test_closures()
    test_rejections()
    test_parse_rejects_empty()
    test_positive_native_detection()
    test_real_native_export()
    test_cli()
    print("test_package_install_plan: 6 tests passed")
