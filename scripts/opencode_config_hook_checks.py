#!/usr/bin/env python3
"""Stdlib fixtures and fail-closed checks for the opt-in YAN-1125 lab."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import socket
import stat
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

PASSWORD = "yan1125-private-lab-only"


def check(label: str, expected: Any, actual: Any) -> None:
    """Mismatch terminates the harness, including when Python runs with -O."""
    if expected != actual:
        raise SystemExit(f"FAIL {label}: expected {expected!r}, actual {actual!r}")
    print(f"ok: {label}", flush=True)


def free_port() -> int:
    """Return a loopback TCP port available at bind time."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def snapshot(home: Path) -> dict[str, Any]:
    """Inspect metadata/hash only, never copy config or service contents."""
    config = home / ".config/opencode"
    targets = [config, home / ".local/state/opencode/service.json"]
    if config.is_dir():
        targets.extend(sorted(config.iterdir()))
    result: dict[str, Any] = {}
    for path in targets:
        if not path.exists() and not path.is_symlink():
            result[str(path)] = None
            continue
        info = path.lstat()
        result[str(path)] = [info.st_mode, info.st_size, info.st_mtime_ns, info.st_ino]
        if path.name in ("opencode.json", "service.json") and stat.S_ISREG(info.st_mode):
            result[str(path) + "#sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def track(lab: Path, pid: int, add: bool) -> None:
    """Add or remove a server process-group ID in the lab cleanup registry."""
    path = lab / "process-groups"
    pids = path.read_text().splitlines() if path.exists() else []
    pids = [p for p in pids if p != str(pid)]
    if add:
        pids.append(str(pid))
    path.write_text("".join(p + "\n" for p in pids))


def stop(lab: Path, process: subprocess.Popen[bytes]) -> None:
    """Terminate the whole group, even if the group leader already exited."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=3)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=3)
    track(lab, process.pid, False)


def fixtures(lab: Path, marker: str) -> dict[str, Path]:
    """Write disposable V2/V1 plugin, skill, catalog, and MCP stub fixtures."""
    root = lab / "fixtures"
    skill = root / "skills/dir-skill/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(f"---\nname: Dir Skill\ndescription: {marker} directory\n---\nRead support.md.\n")
    (skill.parent / "support.md").write_text(f"{marker} relative support\n")
    mcp = root / "mcp.py"
    mcp.write_text(
        "import json,sys\n"
        "for line in sys.stdin:\n"
        " r=json.loads(line)\n"
        " if 'id' not in r: continue\n"
        " result={}\n"
        " if r.get('method')=='initialize':\n"
        "  result={'protocolVersion':r['params']['protocolVersion'],'capabilities':{},"
        "'serverInfo':{'name':'spike','version':'0'}}\n"
        " print(json.dumps({'jsonrpc':'2.0','id':r['id'],'result':result}),flush=True)\n"
    )
    plugin = root / "v2-plugin"
    plugin.mkdir()
    (plugin / "package.json").write_text('{"type":"module","main":"index.js"}')
    # All registration methods return Promises. Await each before setup finishes.
    (plugin / "index.js").write_text(
        'export default { id: "yan1125.probe", async setup(ctx) {\n'
        ' await ctx.agent.transform(e => e.update("yan1125-agent", a => {\n'
        f'  a.name="Yan1125 Agent"; a.description={json.dumps(marker + " agent")};\n'
        '  a.mode="subagent";\n'
        " }));\n"
        ' await ctx.command.transform(e => e.add({name:"yan1125-cmd",\n'
        f"  description:{json.dumps(marker + ' command')}, execute:async () => {{}} }}));\n"
        ' await ctx.skill.transform(e => e.add({id:"yan1125-skill",name:"Yan1125 Skill",\n'
        f"  description:{json.dumps(marker + ' skill')},path:{json.dumps(str(skill))},\n"
        f"  content:{json.dumps(marker + ' inline; Read support.md relative to the skill base.')} }}));\n"
        f" await ctx.mcp.transform(e => e.set({json.dumps(marker + '-mcp')},\n"
        f'  {{type:"local",command:["python3",{json.dumps(str(mcp))}],timeout:{{startup:2000}}}}));\n'
        ' await ctx.session.hook("context", e => {\n'
        '  e.system.push({type:"text",text:' + json.dumps(marker + " hook-instruction") + "});\n"
        " });\n"
        "} };\n"
    )
    v1 = root / "v1-plugin"
    v1.mkdir()
    (v1 / "package.json").write_text('{"type":"module","main":"index.js"}')
    (v1 / "index.js").write_text(
        "export const P=async()=>({config(cfg){\n"
        ' cfg.agents={"yan1125-v1":{"description":' + json.dumps(marker + " v1") + "}};\n"
        "}});\nexport default P;\n"
    )
    catalog = root / "catalog"
    (catalog / "yan1125-url").mkdir(parents=True)
    (catalog / "yan1125-url/yan1125-url.md").write_text(
        f"---\nname: URL Skill\ndescription: {marker} catalog\n---\nRead support.md.\n"
    )
    (catalog / "yan1125-url/support.md").write_text(f"{marker} cached support\n")
    (catalog / "index.json").write_text(
        json.dumps(
            {
                "skills": [
                    {
                        "name": "yan1125-url",
                        "version": "1",
                        "files": ["yan1125-url.md", "support.md"],
                    }
                ]
            }
        )
    )
    return {"plugin": plugin, "v1": v1, "skill": skill, "catalog": catalog}


class Loopback(threading.Thread):
    """Catalog GETs and fake OpenAI POSTs, bound only to loopback; no headers logged."""

    def __init__(self, catalog: Path) -> None:
        """Bind an ephemeral loopback server serving the skill catalog and fake OpenAI API."""
        super().__init__(daemon=True)
        self.bodies: list[dict[str, Any]] = []
        self.gets: list[str] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            """HTTP handler for skill catalog files and OpenAI chat completions."""

            def do_GET(self) -> None:  # noqa: N802
                """Serve relative skill catalog files from the fixture directory."""
                outer.gets.append(self.path)
                path = (catalog / self.path.lstrip("/")).resolve()
                if not path.is_relative_to(catalog) or not path.is_file():
                    self.send_error(404)
                    return
                self.send_response(200)
                self.end_headers()
                self.wfile.write(path.read_bytes())

            def do_POST(self) -> None:  # noqa: N802
                """Record the JSON request body and return a minimal OpenAI completion."""
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                outer.bodies.append(body)
                self.send_response(200)
                # Both streaming and non-streaming clients can finish without retries.
                if body.get("stream"):
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    chunk = {
                        "id": "spike",
                        "object": "chat.completion.chunk",
                        "created": 0,
                        "model": "spike",
                        "choices": [
                            {"index": 0, "delta": {"role": "assistant", "content": "OK"}, "finish_reason": None}
                        ],
                    }
                    self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
                    chunk["choices"] = [{"index": 0, "delta": {}, "finish_reason": "stop"}]
                    self.wfile.write(("data: " + json.dumps(chunk) + "\n\ndata: [DONE]\n\n").encode())
                else:
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(
                        json.dumps(
                            {
                                "id": "spike",
                                "object": "chat.completion",
                                "created": 0,
                                "model": "spike",
                                "choices": [
                                    {
                                        "index": 0,
                                        "message": {"role": "assistant", "content": "OK"},
                                        "finish_reason": "stop",
                                    }
                                ],
                            }
                        ).encode()
                    )

            def log_message(self, *_args: Any) -> None:
                """Suppress standard HTTP access logs to avoid leaking request metadata."""
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def run(self) -> None:
        """Serve loopback requests until shut down."""
        self.server.serve_forever(poll_interval=0.1)

    def close(self) -> None:
        """Stop the loopback HTTP server and join its thread."""
        self.server.shutdown()
        self.server.server_close()
        self.join(timeout=2)
