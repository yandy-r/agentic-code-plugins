#!/usr/bin/env python3
"""Behaviour tests for the generated ycc sensitive-file guard (OpenCode V2 plugin).

The generated plugin is imported under node and driven with a fake V2 context
whose `tool.hook` records the registered callbacks, so each case exercises the
same `execute.before` / `execute.after` events OpenCode v2.0.32 triggers
(packages/plugin/src/effect/tool.ts ToolHooks).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO_ROOT = Path(__file__).resolve().parent.parent
GUARD_DIR = REPO_ROOT / ".opencode-plugin" / "ycc-sensitive-guard"
NODE = shutil.which("node")
RESTRICTED = "pr-comment-fixer"
OPEN_AGENT = "code-finder"

# Reads cases as JSON on stdin and prints one JSON outcome per case. The setup
# location (`setupDir`, like a server started elsewhere) differs from the
# session location that ctx.session.get reports for each case's sessionID.
DRIVER = r"""
import { pathToFileURL } from "node:url";
import { readFileSync } from "node:fs";
const [guardDir, setupDir] = process.argv.slice(2);
const { sessions, setupLocation, cases } = JSON.parse(readFileSync(0, "utf8"));
const plugin = (await import(pathToFileURL(guardDir + "/index.js").href)).default;
const hooks = {};
const ctx = {
  location: setupLocation === false
    ? undefined
    : { directory: setupDir, project: { directory: setupDir, canonical: setupDir } },
  tool: { hook: async (name, cb) => { (hooks[name] ??= []).push(cb); } },
  session: {
    get: async ({ sessionID }) => {
      if (!(sessionID in sessions)) throw new Error(`session not found: ${sessionID}`);
      return { data: { id: sessionID, location: { directory: sessions[sessionID] } } };
    },
  },
};
await plugin.setup(ctx);
const results = [];
for (const item of cases) {
  const event = { sessionID: item.sessionID ?? "ses", messageID: "msg", id: "call",
    agent: item.agent, tool: item.tool, input: item.input };
  try {
    if (item.result) {
      Object.assign(event, { status: "completed", result: item.result });
      for (const cb of hooks["execute.after"] ?? []) await cb(event);
      results.push({ ok: true, result: event.result });
    } else {
      for (const cb of hooks["execute.before"] ?? []) await cb(event);
      results.push({ ok: true });
    }
  } catch (error) {
    results.push({ ok: false, message: String(error?.message ?? error) });
  }
}
console.log(JSON.stringify({ id: plugin.id, hooks: Object.keys(hooks).sort(), results }));
"""


@unittest.skipIf(NODE is None, "node is required")
class SensitiveGuardTestCase(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.tmp = Path(temp.name)
        self.work = self.tmp / "work"
        (self.work / "src").mkdir(parents=True)
        (self.work / "src" / "app.ts").write_text("export const value = 1;\n", encoding="utf-8")
        (self.work / ".env").write_text("TOKEN=synthetic\n", encoding="utf-8")
        (self.work / ".env.example").write_text("TOKEN=\n", encoding="utf-8")
        (self.work / "config").mkdir()
        (self.work / "config" / ".env.production").write_text("TOKEN=synthetic\n", encoding="utf-8")
        (self.work / "notes.txt").symlink_to(self.work / ".env")
        (self.work / "linked").symlink_to(self.work / "config")
        # Dangling link to a sensitive path that does not exist yet.
        (self.work / "pending.txt").symlink_to(self.work / "config" / ".env.local")
        # Curly-quote name that the read tool's look-alike fallback would pick.
        (self.work / "it\u2019s.txt").symlink_to(self.work / ".env")

    def run_cases(
        self,
        cases: list[dict[str, Any]],
        sessions: dict[str, str] | None = None,
        setup_dir: Path | None = None,
        setup_location: bool = True,
    ) -> list[dict[str, Any]]:
        """Drive the hooks; session "ses" lives in self.work unless overridden.

        The plugin's setup location defaults to a separate server directory, so
        every case also proves paths resolve against the session location.
        """
        assert NODE is not None
        script = self.tmp / "driver.mjs"
        script.write_text(DRIVER, encoding="utf-8")
        server = setup_dir or self.tmp / "server"
        server.mkdir(exist_ok=True)
        payload = {
            "sessions": {"ses": str(self.work)} if sessions is None else sessions,
            "setupLocation": setup_location,
            "cases": cases,
        }
        result = subprocess.run(
            [NODE, str(script), str(GUARD_DIR), str(server)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=60,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(self.tmp / "home")},
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        observed = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(observed["id"], "yandy-r.ycc-sensitive-guard")
        self.assertEqual(observed["hooks"], ["execute.after", "execute.before"])
        results: list[dict[str, Any]] = observed["results"]
        return results

    def assert_blocked(self, tool: str, input_: dict[str, Any], agent: str = RESTRICTED) -> None:
        (outcome,) = self.run_cases([{"agent": agent, "tool": tool, "input": input_}])
        self.assertFalse(outcome["ok"], f"{tool} {input_} was not blocked")
        self.assertIn("ycc sensitive-file guard", outcome["message"])

    def assert_allowed(self, tool: str, input_: dict[str, Any], agent: str = RESTRICTED) -> None:
        (outcome,) = self.run_cases([{"agent": agent, "tool": tool, "input": input_}])
        self.assertTrue(outcome["ok"], outcome)

    def test_blocks_sensitive_targets_for_restricted_agents(self) -> None:
        blocked = [
            ("read", {"path": ".env"}),
            ("read", {"path": "./config/../.env"}),
            ("read", {"path": str(self.work / "config" / ".env.production")}),
            ("read", {"path": ".ENV"}),
            ("read", {"path": "notes.txt"}),
            ("read", {"path": "linked/.env.production"}),
            ("read", {"path": "~/.aws/credentials"}),
            ("read", {"path": "deploy/server.pem"}),
            ("read", {"path": ".ssh"}),
            ("edit", {"path": ".env", "oldString": "a", "newString": "b"}),
            ("write", {"path": "config/.envrc", "content": "x"}),
            ("patch", {"patchText": "*** Begin Patch\n*** Update File: notes.txt\n@@\n-a\n+b\n*** End Patch"}),
            ("patch", {"patchText": "*** Begin Patch\n*** Add File: keys/id_rsa\n+x\n*** End Patch"}),
            ("grep", {"pattern": "TOKEN", "path": ".env"}),
            ("grep", {"pattern": "TOKEN", "path": "notes.txt"}),
            ("grep", {"pattern": "TOKEN", "include": ".env"}),
            ("grep", {"pattern": "TOKEN", "include": "**/.env.production"}),
            ("glob", {"pattern": "*", "path": ".ssh"}),
            ("shell", {"command": "npm run x -- .env"}),
            ("shell", {"command": "python3 -c \"print(open('config/.env.production').read())\""}),
            ("shell", {"command": "make show FILE=notes.txt"}),
            ("shell", {"command": "ls .e*"}),
            ("shell", {"command": "ls", "workdir": ".ssh"}),
            ("shell", {"command": "git show HEAD:.env"}),
            ("shell", {"command": "git show HEAD~1:.env"}),
            ("shell", {"command": "git show 'main:config/.env.production'"}),
            ("shell", {"command": "git show :0:.env"}),
            ("shell", {"command": "git cat-file -p v1.2.0:deploy/server.pem"}),
            ("shell", {"command": "git log -p -- HEAD:.ENV"}),
            ("shell", {"command": "git diff --no-index . /tmp/empty"}),
            ("shell", {"command": "git diff --stat --no-index -- .. /tmp/empty"}),
            ("shell", {"command": "cat .{e,x}nv"}),
            ("shell", {"command": "cat .{'e'nv,'a b'}"}),
            ("shell", {"command": "git diff /tmp/empty ."}),
            ("shell", {"command": "git diff . ~/empty"}),
            ("shell", {"command": "git diff -- ../outside ."}),
            ("shell", {"command": "git -C /tmp/elsewhere diff"}),
            ("shell", {"command": "git --git-dir=/tmp/x/.git log -p"}),
            ("shell", {"command": "git --work-tree /tmp/x diff"}),
            ("shell", {"command": "git diff", "workdir": "/tmp"}),
            ("shell", {"command": "cd src && git diff ../../outside ."}),
            ("shell", {"command": "git diff $HOME ."}),
            ("shell", {"command": 'git diff "${TMPDIR}" .'}),
            ("shell", {"command": "git diff $(dirname $PWD) ."}),
            ("shell", {"command": "git diff `echo /tmp` ."}),
            ("shell", {"command": "cat $OLDPWD/.env"}),
            ("shell", {"command": "git diff ~root ."}),
            ("shell", {"command": "git diff ~someone/project ."}),
            ("shell", {"command": "git diff ~- ."}),
            ("shell", {"command": "git diff ~+/../sibling ."}),
            ("shell", {"command": "git diff --output=x ~+/.. ."}),
            ("shell", {"command": "make show DIR=~-"}),
            ("shell", {"command": "cat .e{n..n}v"}),
            ("shell", {"command": "cat $'\\x2eenv'"}),
            ("write", {"path": "pending.txt", "content": "x"}),
            ("edit", {"path": "pending.txt", "oldString": "a", "newString": "b"}),
            ("patch", {"patchText": "*** Begin Patch\n  *** Update File: notes.txt\n@@\n-a\n+b\n*** End Patch"}),
            ("patch", {"patchText": "*** Begin Patch\n\t*** Add File:   pending.txt  \n+x\n*** End Patch"}),
            ("read", {"path": "it's.txt"}),
            ("read", {"path": "keys/id_rsa.env.example"}),
            ("read", {"path": "id_ed25519.prod.env.example"}),
            ("read", {"path": "prod.env"}),
            ("read", {"path": "config/app.env"}),
            ("read", {"path": "app.env.local"}),
            ("edit", {"path": "config/app.env", "oldString": "a", "newString": "b"}),
            ("grep", {"pattern": "TOKEN", "path": "prod.env"}),
            ("shell", {"command": "ls; head prod.env"}),
        ]
        cases = [{"agent": RESTRICTED, "tool": tool, "input": input_} for tool, input_ in blocked]
        for (tool, input_), outcome in zip(blocked, self.run_cases(cases), strict=True):
            with self.subTest(tool=tool, input=input_):
                self.assertFalse(outcome["ok"], outcome)
                self.assertIn("ycc sensitive-file guard", outcome["message"])

    def test_allows_ordinary_work_and_documented_exceptions(self) -> None:
        allowed = [
            ("read", {"path": "src/app.ts"}),
            ("read", {"path": ".env.example"}),
            ("read", {"path": "app.env.example"}),
            ("read", {"path": "config/app.env.example"}),
            ("read", {"path": "."}),
            ("edit", {"path": "src/app.ts", "oldString": "1", "newString": "2"}),
            ("grep", {"pattern": "value", "path": "src"}),
            ("grep", {"pattern": "value"}),
            ("grep", {"pattern": "value", "include": "*.ts"}),
            ("glob", {"pattern": "**/*.ts"}),
            ("shell", {"command": "ls"}),
            ("shell", {"command": "ls src/*"}),
            ("shell", {"command": "npm test -- src/app.ts"}),
            ("shell", {"command": "pytest -k env"}),
            ("shell", {"command": "git show HEAD:src/app.ts"}),
            ("shell", {"command": "git show HEAD~1:.env.example"}),
            ("shell", {"command": "git log --oneline HEAD~3..HEAD"}),
            ("shell", {"command": "git diff origin/main:src/app.ts HEAD:src/app.ts"}),
            ("shell", {"command": "git diff HEAD~1 -- src"}),
            ("shell", {"command": "git status --short && git log --oneline -- src/app.ts"}),
            ("shell", {"command": "git diff", "workdir": "src"}),
            ("shell", {"command": "git blame -C src/app.ts"}),
            ("shell", {"command": "git log -c -p HEAD~2..HEAD -- src"}),
            ("shell", {"command": "npm test -- --grep '{value}'"}),
            ("read", {"path": "src/missing.ts"}),
            ("write", {"path": "src/new.ts", "content": "x"}),
            ("patch", {"patchText": "*** Begin Patch\n  *** Update File: src/app.ts\n@@\n-1\n+2\n*** End Patch"}),
        ]
        cases = [{"agent": RESTRICTED, "tool": tool, "input": input_} for tool, input_ in allowed]
        for (tool, input_), outcome in zip(allowed, self.run_cases(cases), strict=True):
            with self.subTest(tool=tool, input=input_):
                self.assertTrue(outcome["ok"], outcome)

    def test_unrestricted_agents_are_untouched(self) -> None:
        self.assert_allowed("read", {"path": ".env"}, agent=OPEN_AGENT)
        self.assert_allowed("shell", {"command": "cat .env"}, agent=OPEN_AGENT)

    def test_grep_results_drop_sensitive_files_and_recount(self) -> None:
        output = [
            {"entry": {"path": ".env"}, "line": 1, "offset": 0, "text": "TOKEN=synthetic", "submatches": []},
            {"entry": {"path": "src/app.ts"}, "line": 1, "offset": 0, "text": "export const value", "submatches": []},
            {"entry": {"path": "notes.txt"}, "line": 1, "offset": 0, "text": "TOKEN=synthetic", "submatches": []},
        ]
        result = {
            "output": output,
            "content": "Found 3 matches\n.env:\n  Line 1: TOKEN=synthetic",
            "metadata": {"matches": 3, "truncated": False},
        }
        cases = [{"agent": RESTRICTED, "tool": "grep", "input": {"pattern": "."}, "result": result}]
        (outcome,) = self.run_cases(cases)
        filtered = outcome["result"]
        self.assertEqual([m["entry"]["path"] for m in filtered["output"]], ["src/app.ts"])
        self.assertEqual(filtered["metadata"]["matches"], 1)
        self.assertNotIn("synthetic", json.dumps(filtered))
        self.assertIn("Found 1 matches", filtered["content"])
        self.assertIn(str(self.work / "src" / "app.ts"), filtered["content"])

        cases = [{"agent": OPEN_AGENT, "tool": "grep", "input": {"pattern": "."}, "result": result}]
        (untouched,) = self.run_cases(cases)
        self.assertEqual(untouched["result"], result)

    def test_glob_results_drop_sensitive_names(self) -> None:
        result = {
            "output": [{"path": ".env"}, {"path": ".env.example"}, {"path": "src/app.ts"}, {"path": "linked"}],
            "content": "x",
            "metadata": {"count": 4, "truncated": False},
        }
        (outcome,) = self.run_cases(
            [{"agent": RESTRICTED, "tool": "glob", "input": {"pattern": "*", "hidden": True}, "result": result}]
        )
        filtered = outcome["result"]
        self.assertEqual([e["path"] for e in filtered["output"]], [".env.example", "src/app.ts", "linked"])
        self.assertEqual(filtered["metadata"]["count"], 3)
        self.assertNotIn(str(self.work / ".env") + "\n", filtered["content"] + "\n")

        empty = {"output": [{"path": ".env"}], "content": "x", "metadata": {"count": 1, "truncated": False}}
        cases = [{"agent": RESTRICTED, "tool": "glob", "input": {"pattern": ".env"}, "result": empty}]
        (outcome,) = self.run_cases(cases)
        self.assertEqual(outcome["result"]["content"], "No files found")

    def test_error_results_pass_through(self) -> None:
        cases = [{"agent": RESTRICTED, "tool": "read", "input": {"path": "src/app.ts"}, "result": {"content": "ok"}}]
        (outcome,) = self.run_cases(cases)
        self.assertEqual(outcome["result"], {"content": "ok"})

    def test_paths_resolve_against_each_sessions_location(self) -> None:
        other = self.tmp / "other"
        (other / "src").mkdir(parents=True)
        (other / "src" / "main.ts").write_text("x\n", encoding="utf-8")
        sessions = {"ses": str(self.work), "ses-other": str(other)}
        cases = [
            # Relative `.env` names the session's file, not the server's.
            {"agent": RESTRICTED, "tool": "read", "input": {"path": "notes.txt"}},
            {"agent": RESTRICTED, "tool": "read", "input": {"path": "notes.txt"}, "sessionID": "ses-other"},
            # git arguments are confined to the calling session's directory.
            {"agent": RESTRICTED, "tool": "shell", "input": {"command": "git diff src ."}, "sessionID": "ses-other"},
            {
                "agent": RESTRICTED,
                "tool": "shell",
                "input": {"command": f"git diff {self.work} ."},
                "sessionID": "ses-other",
            },
        ]
        outcomes = self.run_cases(cases, sessions=sessions)
        self.assertEqual([outcome["ok"] for outcome in outcomes], [False, True, True, False])

        grep = {
            "output": [{"entry": {"path": "src/main.ts"}, "line": 1, "offset": 0, "text": "x", "submatches": []}],
            "content": "x",
            "metadata": {"matches": 1, "truncated": False},
        }
        (filtered,) = self.run_cases(
            [
                {
                    "agent": RESTRICTED,
                    "tool": "grep",
                    "input": {"pattern": "x"},
                    "result": grep,
                    "sessionID": "ses-other",
                }
            ],
            sessions=sessions,
        )
        self.assertIn(str(other / "src" / "main.ts"), filtered["result"]["content"])

    def test_falls_back_to_setup_location_then_fails_closed(self) -> None:
        # session.get fails: the plugin's setup location is the root.
        (outcome,) = self.run_cases(
            [{"agent": RESTRICTED, "tool": "read", "input": {"path": ".env"}, "sessionID": "gone"}],
            setup_dir=self.work,
        )
        self.assertFalse(outcome["ok"])
        (outcome,) = self.run_cases(
            [{"agent": RESTRICTED, "tool": "read", "input": {"path": "src/app.ts"}, "sessionID": "gone"}],
            setup_dir=self.work,
        )
        self.assertTrue(outcome["ok"], outcome)

        # Neither: restricted agents are denied, results withheld, others untouched.
        grep = {"output": [{"entry": {"path": "src/app.ts"}}], "content": "x", "metadata": {}}
        outcomes = self.run_cases(
            [
                {"agent": RESTRICTED, "tool": "read", "input": {"path": "src/app.ts"}, "sessionID": "gone"},
                {"agent": RESTRICTED, "tool": "grep", "input": {"pattern": "x"}, "result": grep, "sessionID": "gone"},
                {"agent": OPEN_AGENT, "tool": "read", "input": {"path": ".env"}, "sessionID": "gone"},
            ],
            setup_location=False,
        )
        self.assertFalse(outcomes[0]["ok"])
        self.assertIn("ycc sensitive-file guard", outcomes[0]["message"])
        self.assertEqual(outcomes[1]["result"]["output"], [])
        self.assertIn("withheld", outcomes[1]["result"]["content"])
        self.assertTrue(outcomes[2]["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
