#!/usr/bin/env python3
"""Tests for the YAN-1174 OMP hook policies in scripts/validate_omp_native.py.

hook_surface_errors keeps every OMP package root free of code surfaces (ycc ships no OMP hooks or
extensions; herdr reporting is herdr's own integration); hook_verdict_errors keeps the hook
inventory, HOOK_VERDICTS, the spike §3 matrix and the OMP docs in agreement.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate_omp_packages as gen  # noqa: E402
import validate_omp_native as policy  # noqa: E402
from package_model import PackageModel, load_package_model  # noqa: E402

REPO_ROOT = gen.REPO_ROOT
HOOKS_ROOT = gen.OUTPUT_ROOT / "ycc-hooks"


def with_omp(model: PackageModel, key: str, **changes: Any) -> PackageModel:
    packages = tuple(
        (
            replace(
                package,
                runtimes=tuple(replace(row, **changes) if row.runtime == "omp" else row for row in package.runtimes),
            )
            if package.key == key
            else package
        )
        for package in model.packages
    )
    return replace(model, packages=packages)


class OmpHookPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.model = load_package_model()

    def write(self, rel: Path | str, content: Any = "x\n") -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
        return path

    def assert_has(self, errors: list[str], expected: str) -> None:
        self.assertTrue(any(expected in error for error in errors), f"expected {expected!r} in {errors!r}")

    def surface(self, model: PackageModel | None = None) -> list[str]:
        return policy.hook_surface_errors(self.root, model or self.model)

    # --- code-surface guard (D2-D5) ---------------------------------------------------

    def test_package_json_extensions_rejected(self) -> None:
        for payload, key in (
            ({"omp": {"extensions": ["./x.ts"]}}, "omp.extensions"),
            ({"pi": {"extensions": ["./x.ts"]}}, "pi.extensions"),
            ({"hooks": "./hooks"}, "hooks"),
            ({"tools": ["./t.ts"]}, "tools"),
        ):
            with self.subTest(key=key):
                path = self.write(gen.COMPONENT_ROOT / gen.PACKAGE_JSON, {"name": "ycc", **payload})
                errors = self.surface()
                self.assert_has(
                    errors, f"{gen.COMPONENT_ROOT / gen.PACKAGE_JSON}#{key}: ycc OMP packages ship no hooks"
                )
                self.assert_has(errors, "herdr reporting is herdr's own integration")
                path.unlink()
        self.assertEqual(self.surface(), [])

    def test_manifest_hooks_key_rejected(self) -> None:
        self.write(gen.COMPONENT_ROOT / gen.OMP_MANIFEST, {"name": "ycc", "hooks": "./h"})
        self.assert_has(
            self.surface(), f"{gen.COMPONENT_ROOT / gen.OMP_MANIFEST}#hooks: ycc OMP packages ship no hooks"
        )

    def test_hook_dirs_and_hooks_json_rejected(self) -> None:
        mcp = gen.OUTPUT_ROOT / "ycc-mcp"
        for rel, expected in (
            (gen.COMPONENT_ROOT / "hooks/pre/x.ts", gen.COMPONENT_ROOT / "hooks"),
            (mcp / "extensions/herdr.md", mcp / "extensions"),
            (gen.COMPONENT_ROOT / "tools/t.md", gen.COMPONENT_ROOT / "tools"),
            (gen.COMPONENT_ROOT / "skills/a/hooks.json", gen.COMPONENT_ROOT / "skills/a/hooks.json"),
        ):
            with self.subTest(rel=str(rel)):
                path = self.write(rel)
                self.assert_has(self.surface(), f"{expected}: ycc OMP packages ship no hooks")
                shutil.rmtree(self.root / gen.OUTPUT_ROOT)
                self.assertFalse(path.exists())

    def test_js_module_outside_skills_rejected_but_skill_helpers_allowed(self) -> None:
        for suffix in gen_suffixes():
            with self.subTest(suffix=suffix):
                self.write(gen.COMPONENT_ROOT / f"skills/a/scripts/helper{suffix}")
                self.assertEqual(self.surface(), [])
                self.write(gen.COMPONENT_ROOT / f"agents/loader{suffix}")
                self.assert_has(
                    self.surface(), f"{gen.COMPONENT_ROOT}/agents/loader{suffix}: ycc OMP packages ship no hooks"
                )
                shutil.rmtree(self.root / gen.OUTPUT_ROOT)

    def test_current_repository_has_no_omp_code_surface(self) -> None:
        self.assertEqual(policy.hook_surface_errors(REPO_ROOT, load_package_model()), [])

    def test_reintroducing_a_ycc_herdr_extension_fails(self) -> None:
        self.write(
            HOOKS_ROOT / gen.PACKAGE_JSON, {"name": "ycc-hooks", "omp": {"extensions": ["./extensions/herdr.ts"]}}
        )
        self.write(HOOKS_ROOT / gen.OMP_MANIFEST, {"name": "ycc-hooks"})
        self.write(HOOKS_ROOT / "extensions/herdr.ts", "export default function () {}\n")
        included = with_omp(self.model, "ycc-hooks", status="included")
        errors = self.surface(included)
        self.assert_has(errors, f"{HOOKS_ROOT / gen.PACKAGE_JSON}#omp.extensions: ycc OMP packages ship no hooks")
        self.assert_has(errors, f"{HOOKS_ROOT / 'extensions'}: ycc OMP packages ship no hooks")
        inactive = policy.inactive_root_errors(self.root, self.model, gen.native_packages(self.model.packages))
        self.assert_has(inactive, f"{HOOKS_ROOT / gen.PACKAGE_JSON}: manifest for a row that is not included")
        self.assert_has(inactive, f"{HOOKS_ROOT}: root for a row that is not included")

    # --- hook-verdict drift check (D6) -------------------------------------------------

    def copy_verdict_sources(self) -> None:
        sources = [
            *(path.relative_to(REPO_ROOT) for path in (REPO_ROOT / policy.HOOK_SOURCE_DIR).iterdir()),
            *policy.HOOK_SOURCE_FILES,
            *policy.HOOK_REGISTRATIONS,
            *policy.HOOK_DOCS,
            policy.SPIKE_DOSSIER,
        ]
        for rel in sources:
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO_ROOT / rel, target)

    def edit(self, rel: Path, old: str, new: str) -> None:
        path = self.root / rel
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new), encoding="utf-8")

    def test_verdict_table_matches_sources(self) -> None:
        self.copy_verdict_sources()
        self.assertEqual(policy.hook_verdict_errors(self.root), [])

        new_hook = self.write(policy.HOOK_SOURCE_DIR / "new.sh", "#!/bin/sh\n")
        self.assert_has(policy.hook_verdict_errors(self.root), "ycc/settings/hooks/new.sh: ycc hook has no OMP verdict")
        new_hook.unlink()

        cursor = policy.HOOK_REGISTRATIONS[0]
        original = (self.root / cursor).read_text(encoding="utf-8")
        hooks = json.loads(original)
        hooks["hooks"]["Stop"] = [{"command": "./stop.sh"}]
        self.write(cursor, hooks)
        self.assert_has(policy.hook_verdict_errors(self.root), f"{cursor}#Stop: ycc hook has no OMP verdict")
        self.write(cursor, original)

        (self.root / policy.HOOK_SOURCE_FILES[0]).unlink()
        self.assert_has(
            policy.hook_verdict_errors(self.root), f"{policy.HOOK_SOURCE_FILES[0]}: stale HOOK_VERDICTS entry"
        )
        shutil.copy2(REPO_ROOT / policy.HOOK_SOURCE_FILES[0], self.root / policy.HOOK_SOURCE_FILES[0])

        dossier = self.root / policy.SPIKE_DOSSIER
        text = dossier.read_text(encoding="utf-8")
        anchor = "`ycc/settings/hooks/herdr-agent-state.sh`"
        dossier.write_text(
            "\n".join(line for line in text.splitlines() if not (line.startswith("|") and anchor in line)) + "\n",
            encoding="utf-8",
        )
        self.assert_has(
            policy.hook_verdict_errors(self.root), "no §3 matrix row for ycc/settings/hooks/herdr-agent-state.sh"
        )
        dossier.write_text(text, encoding="utf-8")

        herdr_row = next(line for line in text.splitlines() if line.startswith("| herdr session reporting"))
        dossier.write_text(text.replace(herdr_row, herdr_row.replace("**native**", "**adapter**")), encoding="utf-8")
        self.assert_has(policy.hook_verdict_errors(self.root), "'herdr session reporting' verdict must hold **native**")
        dossier.write_text(text, encoding="utf-8")

        self.edit(Path("docs/install/omp.md"), "\n", "\nA herdr session_start shim ships later.\n")
        self.assert_has(policy.hook_verdict_errors(self.root), "docs/install/omp.md: promises a ycc OMP herdr reporter")

    def test_repository_hook_verdicts_hold(self) -> None:
        self.assertEqual(policy.hook_verdict_errors(REPO_ROOT), [])


def gen_suffixes() -> tuple[str, ...]:
    return policy.CODE_SUFFIXES


if __name__ == "__main__":
    unittest.main()
