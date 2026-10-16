#!/usr/bin/env python3
"""Consumer-boundary tests for the opencode npm package generator (YAN-1143).

Generates once, then exercises the package the way a consumer does: the
manifest npm reads, a relocated copy, and the V2 plugin adapter driven with a
fake context under node.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate_opencode_package as generator  # noqa: E402
from package_model import REPO_ROOT, PackageModel, load_package_model  # noqa: E402

PACKAGE = Path("packages/opencode/ycc-opencode")
NODE = shutil.which("node")

# Drives the real adapter with a fake V2 context, then prints JSON observations.
DRIVER = r"""
import { pathToFileURL } from "node:url";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { spawnSync } from "node:child_process";
const [root, preSkill, preAgent, preMcp, systemText] = process.argv.slice(2);
const plugin = (await import(pathToFileURL(root + "/index.js").href)).default;
const skills = new Map(), agents = new Map(), mcp = new Map(), commands = new Map(), prompts = [], hooks = [];
if (preSkill) skills.set(preSkill, { id: preSkill, preexisting: true });
if (preAgent) agents.set(preAgent, { id: preAgent, preexisting: true });
if (preMcp) mcp.set(preMcp, { preexisting: true });
const ctx = {
  skill: { transform: async (cb) => cb({ get: (id) => skills.get(id), add: (s) => skills.set(s.id, s) }) },
  agent: { transform: async (cb) => cb({
    get: (id) => agents.get(id),
    update: (id, fn) => { const record = agents.get(id) ?? { id }; fn(record); agents.set(id, record); } }) },
  command: { transform: async (cb) => cb({ add: (c) => commands.set(c.name, c) }) },
  mcp: { transform: async (cb) => cb({ get: (n) => mcp.get(n), set: (n, c) => mcp.set(n, c) }) },
  session: {
    hook: async (name, cb) => hooks.push({ name, cb }),
    get: async () => ({ agent: "build" }),
    switchAgent: async () => {}, switchModel: async () => {},
    prompt: async (input) => { prompts.push(input); },
  },
};
const cleanup = await plugin.setup(ctx);
const command = commands.get("ycc:plan");
await command.execute({ sessionID: "ses_test", prompt: { text: "alpha beta" }, delivery: "immediate" });
const event = { system: systemText ? [{ type: "text", text: systemText }] : [] };
for (const hook of hooks) await hook.cb(event);
const renderedRoot = dirname(dirname(dirname([...skills.values()].find((s) => !s.preexisting).path)));
const forgeText = readFileSync(join(renderedRoot, "shared/references/forge-detection.md"), "utf8");
const sourceLine = forgeText.split("\n").map((line) => line.trim())
  .find((line) => line.startsWith("source ") && line.includes("shared/scripts/lib/forge.sh"));
const shell = spawnSync("bash", ["-c", sourceLine + '\nforge_host_from_url https://example.test/owner/repo.git'], {
  cwd: "/tmp", encoding: "utf8",
});
console.log(JSON.stringify({
  id: plugin.id,
  skills: [...skills.values()],
  agents: [...agents.values()],
  mcp: Object.fromEntries(mcp),
  commandNames: [...commands.keys()],
  hooks: hooks.map((h) => h.name),
  prompts,
  system: event.system,
  renderedRoot, shell: { status: shell.status, stdout: shell.stdout, stderr: shell.stderr },
}));
await cleanup();
"""


def run_driver(root: Path, *extra: str, env: dict[str, str] | None = None) -> dict:
    assert NODE is not None
    script = root.parent / f"driver-{abs(hash(extra))}.mjs"
    script.write_text(DRIVER, encoding="utf-8")
    result = subprocess.run(
        [NODE, str(script), str(root), *(extra + ("",) * (4 - len(extra)))],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return json.loads(result.stdout.strip().splitlines()[-1])


class OpencodeNpmPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temp = tempfile.TemporaryDirectory()
        cls.dest = Path(cls._temp.name) / "repo"
        cls.model = load_package_model()
        cls.inventory = generator.write_all(cls.dest)
        cls.root = cls.dest / PACKAGE
        cls.manifest = json.loads((cls.root / "package.json").read_text(encoding="utf-8"))
        cls.registration = json.loads((cls.root / "registration.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temp.cleanup()

    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.tmp = Path(temp.name)

    # -- manifest npm consumes ------------------------------------------------

    def test_manifest_matches_canonical_version_and_engine_floor(self) -> None:
        canonical = json.loads((REPO_ROOT / self.model.version_source).read_text(encoding="utf-8"))
        self.assertEqual(self.manifest["name"], "@yandy-r/ycc-opencode")
        self.assertEqual(self.manifest["version"], canonical["version"])
        self.assertEqual(self.manifest["engines"], {"opencode": ">=2.0.30"})
        self.assertEqual(self.manifest["type"], "module")
        self.assertEqual(self.manifest["main"], "./index.js")
        self.assertEqual(self.manifest["exports"], {".": "./index.js"})
        self.assertEqual(
            self.manifest["repository"],
            {
                "type": "git",
                "url": "git+https://github.com/yandy-r/claude-plugins.git",
                "directory": "packages/opencode/ycc-opencode",
            },
        )

    def test_every_published_file_exists_and_nothing_private_ships(self) -> None:
        for entry in self.manifest["files"]:
            self.assertTrue((self.root / entry).exists(), entry)
        self.assertNotIn("private", self.manifest)
        self.assertNotIn("scripts", self.manifest)

    @unittest.skipIf(NODE is None, "node is required")
    def test_npm_pack_is_self_contained(self) -> None:
        npm = shutil.which("npm")
        if npm is None:
            self.skipTest("npm is required")
        result = subprocess.run(
            [npm, "pack", "--dry-run", "--json", "--ignore-scripts"],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        start = min(index for char in "[{" if (index := result.stdout.find(char)) >= 0)
        payload = json.loads(result.stdout[start:])
        if isinstance(payload, list):
            entry = payload[0]
        else:
            entry = payload if "files" in payload else next(iter(payload.values()))
        paths = {item["path"] for item in entry["files"]}
        self.assertLessEqual({"index.js", "registration.json", "package.json", "AGENTS.md"}, paths)
        self.assertTrue(any(path.startswith("shared/scripts/") for path in paths))

    # -- component classes and relocatable assets -----------------------------

    def test_registration_covers_every_component_class(self) -> None:
        source_skills = {p.parent.name for p in (REPO_ROOT / "ycc/skills").glob("*/SKILL.md")}
        source_agents = {p.stem for p in (REPO_ROOT / "ycc/agents").glob("*.md")}
        self.assertEqual({s["id"] for s in self.registration["skills"]}, source_skills)
        self.assertEqual({a["id"] for a in self.registration["agents"]}, source_agents)
        self.assertEqual({c["name"] for c in self.registration["commands"]}, {f"ycc:{name}" for name in source_skills})
        self.assertEqual(self.registration["context"], "AGENTS.md")
        mcp_source = json.loads((REPO_ROOT / "mcp-configs/mcp.json").read_text(encoding="utf-8"))["mcpServers"]
        self.assertEqual(set(self.registration["mcp"]), set(mcp_source))
        for agent in self.registration["agents"]:
            self.assertRegex(agent["model"], r"^[^/]+/.+")
            self.assertEqual(agent["mode"], "subagent")

    def test_no_install_root_or_home_path_is_baked_for_shipped_units(self) -> None:
        baked = re.compile(r"(~|\$\{HOME\}|\$HOME)/\.config/opencode/(skills|shared|agents|commands)/")
        offenders = [
            str(path.relative_to(self.root))
            for path in self.root.rglob("*")
            if path.is_file() and baked.search(path.read_text(encoding="utf-8", errors="ignore"))
        ]
        # Verbatim target-matrix documents every deployment target literally.
        self.assertEqual(
            [o for o in offenders if o != "shared/references/target-capability-matrix.md"],
            [],
        )
        self.assertNotIn(str(REPO_ROOT), (self.root / "index.js").read_text(encoding="utf-8"))
        self.assertNotIn(str(REPO_ROOT), (self.root / "registration.json").read_text(encoding="utf-8"))

    def test_relative_shared_references_resolve_to_real_files_after_relocation(self) -> None:
        moved = self.tmp / "elsewhere" / "node_modules" / "@yandy-r" / "ycc-opencode"
        shutil.copytree(self.root, moved)
        pattern = re.compile(r"(?<![\w./-])((?:\.\./)+(?:shared|skills|agents)/[\w./-]+)")
        checked = 0
        for path in moved.rglob("*.md"):
            if path.name == "README.md":
                continue
            for match in pattern.finditer(path.read_text(encoding="utf-8")):
                ref = match.group(1).split("#")[0].rstrip(".,)`")
                self.assertTrue((path.parent / ref).exists(), f"{path.relative_to(moved)}: {ref}")
                checked += 1
        self.assertGreater(checked, 0)
        script = (moved / "skills/git-workflow/scripts/create-pr.sh").read_text(encoding="utf-8")
        self.assertIn('FORGE_LIB="${SCRIPT_DIR}/../../../shared/scripts/lib/forge.sh"', script)

    def test_concrete_legacy_bundle_references_are_relocated(self) -> None:
        cases = (
            ("agents/implementor.md", "{{package-root}}/shared/references/worktree-strategy.md"),
            ("agents/planner.md", "{{package-root}}/shared/references/worktree-strategy.md"),
            ("agents/pr-comment-fixer.md", "{{package-root}}/skills/pr-autofix/references/prompt-injection-safety.md"),
            ("agents/releaser.md", "{{package-root}}/skills/releaser/references/ci-optimization-checklist.md"),
            (
                "shared/references/forge-detection.md",
                "{{package-root}}/skills/git-cleanup/references/host-detection.md",
            ),
            ("skills/backport/SKILL.md", "{{package-root}}/agents/backport-conflict-resolver.md"),
            ("skills/prp-plan/SKILL.md", "{{package-root}}/shared/references/worktree-strategy.md"),
            ("skills/blueprint/references/bootstrap-mapping.md", "{{package-root}}/skills/init/SKILL.md"),
        )
        for rel, expected in cases:
            with self.subTest(rel=rel):
                self.assertIn(expected, (self.root / rel).read_text(encoding="utf-8"))
        legacy = re.compile(r"\.opencode-plugin/(?:skills|agents)/")
        preserved = generator.verbatim_outputs(__import__("generate_opencode_skills")) | {
            "skills/bundle-author/SKILL.md",
            "skills/bundle-author/references/surface-map.md",
            "skills/bundle-author/references/when-not-to-scaffold.md",
            "skills/bundle-author/references/templates/agent-template.md",
            "skills/bundle-author/references/templates/skill-template.md",
            "skills/bundle-author/scripts/scaffold-skill.sh",
        }
        offenders = [
            str(path.relative_to(self.root))
            for path in self.root.rglob("*")
            if path.is_file()
            and str(path.relative_to(self.root)) not in preserved
            and legacy.search(path.read_text(encoding="utf-8", errors="ignore"))
        ]
        self.assertEqual(offenders, [])

    # -- the adapter, driven as opencode drives it ----------------------------

    @unittest.skipIf(NODE is None, "node is required")
    def test_relocated_package_registers_all_component_classes_and_runs_commands(self) -> None:
        moved = self.tmp / "moved" / "ycc-opencode"
        shutil.copytree(self.root, moved)
        observed = run_driver(moved)
        self.assertEqual(len(observed["skills"]), len(self.registration["skills"]))
        self.assertEqual(len(observed["agents"]), len(self.registration["agents"]))
        self.assertEqual(len(observed["commandNames"]), len(self.registration["commands"]))
        self.assertEqual(set(observed["mcp"]), set(self.registration["mcp"]))
        self.assertEqual(observed["hooks"], ["context"])
        for skill in observed["skills"]:
            self.assertEqual(Path(skill["path"]), Path(observed["renderedRoot"]) / "skills" / skill["id"] / "SKILL.md")
            self.assertNotIn("{{package-root}}", skill["content"])
            self.assertFalse(skill["content"].startswith("---"))
        self.assertEqual(observed["shell"]["status"], 0, observed["shell"]["stderr"])
        self.assertEqual(observed["shell"]["stdout"].strip(), "example.test")
        self.assertIn("ycc:init", observed["commandNames"])
        self.assertNotIn("init", observed["commandNames"])
        agent = next(a for a in observed["agents"] if a["id"] == "architect")
        self.assertEqual(agent["mode"], "subagent")
        self.assertIn("permissions", agent)
        self.assertEqual(set(agent["model"]), {"id", "providerID"})
        self.assertNotIn("{{package-root}}", agent["system"])
        # The command forwards the template with the invocation text expanded.
        (prompt,) = observed["prompts"]
        self.assertEqual(prompt["sessionID"], "ses_test")
        self.assertIn("load the `plan` skill", prompt["text"])
        self.assertTrue(prompt["text"].rstrip().endswith("alpha beta"))
        self.assertNotIn("$ARGUMENTS", prompt["text"])
        # Instructions arrive as a typed SystemPart, never a bare string.
        self.assertEqual([part["type"] for part in observed["system"]], ["text"])
        self.assertEqual(observed["system"][0]["text"], (moved / "AGENTS.md").read_text(encoding="utf-8"))

    @unittest.skipIf(NODE is None, "node is required")
    def test_existing_registrations_win_and_instructions_are_not_duplicated(self) -> None:
        moved = self.tmp / "coexist" / "ycc-opencode"
        shutil.copytree(self.root, moved)
        instructions = (moved / "AGENTS.md").read_text(encoding="utf-8")
        observed = run_driver(moved, "plan", "architect", "github", instructions)
        plan = next(s for s in observed["skills"] if s["id"] == "plan")
        architect = next(a for a in observed["agents"] if a["id"] == "architect")
        self.assertTrue(plan.get("preexisting"))
        self.assertTrue(architect.get("preexisting"))
        self.assertTrue(observed["mcp"]["github"].get("preexisting"))
        self.assertEqual(len(observed["skills"]), len(self.registration["skills"]))
        # Same text already present: the hook pushes nothing.
        self.assertEqual(len(observed["system"]), 1)

    @unittest.skipIf(NODE is None, "node is required")
    def test_mcp_environment_placeholders_resolve_at_setup_not_generation(self) -> None:
        stored = json.dumps(self.registration["mcp"])
        self.assertIn("{env:", stored)
        self.assertNotIn("sk-", stored)
        moved = self.tmp / "env" / "ycc-opencode"
        shutil.copytree(self.root, moved)
        env = {"PATH": "/usr/bin:/bin", "XERO_CLIENT_ID": "id-from-env", "XERO_CLIENT_SECRET": "secret-from-env"}
        observed = run_driver(moved, env=env)
        self.assertEqual(observed["mcp"]["xero"]["environment"]["XERO_CLIENT_ID"], "id-from-env")

    @unittest.skipIf(NODE is None, "node is required")
    def test_asset_paths_cannot_escape_the_package(self) -> None:
        moved = self.tmp / "escape" / "ycc-opencode"
        shutil.copytree(self.root, moved)
        registration = json.loads((moved / "registration.json").read_text(encoding="utf-8"))
        registration["skills"][0]["path"] = "../outside/SKILL.md"
        (moved / "registration.json").write_text(json.dumps(registration), encoding="utf-8")
        with self.assertRaisesRegex(AssertionError, "escapes the package root"):
            run_driver(moved)

    # -- generator ownership and safety ---------------------------------------

    def test_check_passes_clean_and_detects_drift_and_orphans(self) -> None:
        dest = self.tmp / "repo"
        generator.write_all(dest)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(generator.run_check(dest), 0)
            (dest / PACKAGE / "AGENTS.md").write_text("drift\n", encoding="utf-8")
            (dest / PACKAGE / "stray.txt").write_text("orphan\n", encoding="utf-8")
            self.assertEqual(generator.run_check(dest), 1)

    def test_write_prunes_orphans_but_never_touches_sibling_packages(self) -> None:
        dest = self.tmp / "repo"
        generator.write_all(dest)
        sibling = dest / "packages/opencode/not-ours/keep.txt"
        sibling.parent.mkdir(parents=True)
        sibling.write_text("keep\n", encoding="utf-8")
        orphan = dest / PACKAGE / "skills/removed-skill/SKILL.md"
        orphan.parent.mkdir(parents=True)
        orphan.write_text("stale\n", encoding="utf-8")
        generator.write_all(dest)
        self.assertFalse(orphan.exists())
        self.assertFalse(orphan.parent.exists())
        self.assertTrue(sibling.is_file())

    def test_dry_run_mutates_nothing(self) -> None:
        dest = self.tmp / "repo"
        with contextlib.redirect_stdout(io.StringIO()):
            generator.write_all(dest, dry_run=True)
        self.assertFalse((dest / PACKAGE).exists())

    def test_managed_symlinks_are_rejected_in_every_mode(self) -> None:
        dest = self.tmp / "repo"
        target = self.tmp / "elsewhere"
        target.mkdir()
        (dest / "packages/opencode").mkdir(parents=True)
        (dest / PACKAGE).symlink_to(target, target_is_directory=True)
        for action in (
            lambda: generator.write_all(dest),
            lambda: generator.write_all(dest, dry_run=True),
            lambda: generator.run_check(dest),
        ):
            with self.assertRaises(ValueError):
                action()
        self.assertEqual(list(target.iterdir()), [])

    def test_selection_follows_the_model_not_catalog_visibility(self) -> None:
        def with_runtime(**changes: object) -> PackageModel:
            packages = tuple(
                (
                    replace(
                        package,
                        runtimes=tuple(
                            replace(entry, **changes) if entry.runtime == "opencode" else entry
                            for entry in package.runtimes
                        ),
                    )
                    if package.key == "@yandy-r/ycc-opencode"
                    else package
                )
                for package in self.model.packages
            )
            return PackageModel(self.model.schema_version, self.model.version_source, packages)

        listed = with_runtime(listed=True)
        self.assertEqual([p.key for p in generator.npm_packages(listed.packages)], ["@yandy-r/ycc-opencode"])
        deferred = with_runtime(status="deferred")
        self.assertEqual(generator.npm_packages(deferred.packages), ())
        self.assertEqual(generator.npm_package_roots(deferred.packages), (PACKAGE,))
        unsupported = with_runtime(components=("skills", "hooks"))
        with self.assertRaisesRegex(ValueError, "unsupported opencode npm components"):
            generator.npm_packages(unsupported.packages)

    def test_missing_canonical_version_fails_before_any_write(self) -> None:
        dest = self.tmp / "repo"
        with patch.object(generator, "native_version", side_effect=ValueError("missing nonempty version")):
            with self.assertRaisesRegex(ValueError, "missing nonempty version"):
                generator.write_all(dest)
        self.assertFalse(dest.exists())

    def test_cli_check_exit_codes(self) -> None:
        script = REPO_ROOT / "scripts/generate_opencode_package.py"
        result = subprocess.run(
            [sys.executable, str(script), "--bogus"], capture_output=True, text=True, timeout=60, check=False
        )
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
