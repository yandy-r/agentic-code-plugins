#!/usr/bin/env python3
"""Helpers and assertions for scripts/test-omp-herdr-hooks.sh (opt-in live herdr harness).

herdr's own OMP integration (`herdr integration install omp`) reports session identity; ycc
ships no OMP hook code. These subcommands prove that against real `omp --mode rpc` runs.

  recorder SOCKET MODE OUT          fake herdr socket: MODE ok replies {"result":{"type":"ok"}},
                                    stall accepts and never replies; each request is one JSONL
                                    record {"n", "t", "request"} in OUT, where n is the accept
                                    order (fixed before the per-connection thread starts). Writes
                                    OUT.ready once bound
  session [--new] [--hold S] OUT -- OMP_ARGV...
                                    run `omp --mode rpc`: get_state, then (--new) new_session and
                                    get_state, wait S seconds, close stdin, wait for exit. OUT is
                                    JSON: frames, sessions, start/ready/close/exit times, rc
  assert-trigger REC SESSION               L1 one startup and one new report_agent_session
  assert-payload REC SESSION SCHEMA PANE   L2 herdr:omp payload, seq, session path, schema keys
  assert-silent REC SESSION                L3 no connection, session ready
  assert-isolated SESSION                  L4 no extension_error, get_state answered
  assert-stall REC SESSION HOLD            L5 stalled socket: ready, bounded exit
  assert-cancel REC SESSION                L6 stdin close with a stalled socket: exit within 3 s
  assert-single-source REC SESSION         L7 only herdr:omp, one session+state pair per event
  assert-no-extensions LIST_JSON           L7 no ycc package in `plugin list --json` ships
                                           manifest.extensions
  herdr-pane SOCKET PANE OUT               L8 real herdr: pane reports herdr:omp; a ycc:omp
                                           report_agent_session leaves agent_session unchanged
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import signal
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

SOURCE = "herdr:omp"
AGENT = "omp"
YCC_SOURCE = "ycc:omp"
SESSION_METHOD = "pane.report_agent_session"
STATE_METHOD = "pane.report_agent"
RESPONSE_TIMEOUT = 30.0
EXIT_TIMEOUT = 20.0
STALL_READY_BUDGET = 5.0
EXIT_BUDGET = 3.0


class SmokeError(Exception):
    """A recorded omp/herdr result that contradicts the expected integration behavior."""


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SmokeError(f"{path}: unreadable JSON: {exc}") from exc


def records(path: Path) -> list[dict[str, Any]]:
    """Recorder entries in accept order (the integration's send order), not write order."""
    out: list[dict[str, Any]] = []
    if not path.exists():
        raise SmokeError(f"{path}: recorder log missing")
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except ValueError as exc:
            raise SmokeError(f"{path}:{number}: not JSONL: {exc}") from exc
        if not isinstance(item, dict):
            raise SmokeError(f"{path}:{number}: record is not an object")
        if not isinstance(item.get("n"), int):
            raise SmokeError(f"{path}:{number}: record has no accept counter")
        out.append(item)
    return sorted(out, key=lambda item: int(item["n"]))


def request_of(record: dict[str, Any]) -> dict[str, Any]:
    request = record.get("request")
    if not isinstance(request, dict):
        raise SmokeError(f"unparseable request on the herdr socket: {record.get('raw')!r}")
    return request


def params_of(record: dict[str, Any]) -> dict[str, Any]:
    params = request_of(record).get("params")
    if not isinstance(params, dict):
        raise SmokeError(f"request without params: {record}")
    return params


# --- recorder -------------------------------------------------------------------------------


def recorder(sock_path: Path, mode: str, out: Path) -> str:
    if mode not in {"ok", "stall"}:
        raise SmokeError(f"unknown recorder mode {mode!r} (ok|stall; refuse means no recorder)")
    lock = threading.Lock()
    held: list[socket.socket] = []
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(sock_path))
    server.listen(16)

    def on_term(_signum: int, _frame: object) -> None:
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, on_term)
    signal.signal(signal.SIGINT, on_term)

    def write(entry: dict[str, Any]) -> None:
        with lock, out.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

    def serve(conn: socket.socket, accepted: int) -> None:
        buffer = b""
        conn.settimeout(10)
        try:
            while b"\n" not in buffer:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                buffer += chunk
        except OSError:
            pass
        line = buffer.split(b"\n", 1)[0].decode("utf-8", "replace")
        entry: dict[str, Any] = {"n": accepted, "t": time.time(), "mode": mode}
        try:
            entry["request"] = json.loads(line)
        except ValueError:
            entry["raw"] = line
        write(entry)
        if mode == "stall":
            held.append(conn)
            return
        request_id = entry.get("request", {}).get("id") if isinstance(entry.get("request"), dict) else None
        try:
            conn.sendall((json.dumps({"id": request_id, "result": {"type": "ok"}}) + "\n").encode())
        except OSError:
            pass
        conn.close()

    out.touch()
    Path(f"{out}.ready").write_text(str(os.getpid()), encoding="utf-8")
    try:
        accepted = 0
        while True:
            conn, _ = server.accept()
            # The accept order is the integration's send order (one request per connection,
            # serialized queue); threads may write their records in any order.
            threading.Thread(target=serve, args=(conn, accepted), daemon=True).start()
            accepted += 1
    finally:
        for conn in held:
            conn.close()
        server.close()


# --- session --------------------------------------------------------------------------------


def session(out: Path, new: bool, hold: float, argv: list[str]) -> str:
    if not argv:
        raise SmokeError("session: missing omp argv after --")
    start = time.time()
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=out.with_suffix(".stderr").open("wb"),
    )
    assert proc.stdin is not None and proc.stdout is not None
    stdin, stdout = proc.stdin, proc.stdout
    frames: list[dict[str, Any]] = []
    inbox: queue.Queue[tuple[float, dict[str, Any]] | None] = queue.Queue()

    def pump() -> None:
        for raw in stdout:
            now = time.time()
            try:
                frame = json.loads(raw)
            except ValueError:
                frame = {"type": "<non-json>", "raw": raw.decode("utf-8", "replace")}
            if isinstance(frame, dict):
                frame["_t"] = now
                inbox.put((now, frame))
        inbox.put(None)

    threading.Thread(target=pump, daemon=True).start()
    result: dict[str, Any] = {"argv": argv, "start_t": start, "hold": hold, "new": new}
    sessions: list[dict[str, Any]] = []
    responses: dict[str, float] = {}

    def send(payload: dict[str, Any]) -> None:
        stdin.write((json.dumps(payload) + "\n").encode())
        stdin.flush()

    def await_response(request_id: str) -> dict[str, Any]:
        deadline = time.time() + RESPONSE_TIMEOUT
        while time.time() < deadline:
            try:
                item = inbox.get(timeout=max(0.0, deadline - time.time()))
            except queue.Empty:
                break
            if item is None:
                raise SmokeError(f"omp exited before answering {request_id}")
            when, frame = item
            frames.append(frame)
            if frame.get("type") == "ready":
                result.setdefault("ready_t", when)
            if frame.get("type") == "response" and frame.get("id") == request_id:
                responses[request_id] = when
                return frame
        raise SmokeError(f"no response to {request_id} within {RESPONSE_TIMEOUT}s")

    def record_state(request_id: str) -> None:
        send({"id": request_id, "type": "get_state"})
        frame = await_response(request_id)
        if frame.get("success") is not True:
            raise SmokeError(f"get_state failed: {frame}")
        data = frame.get("data", {})
        sessions.append({"sessionId": data.get("sessionId"), "sessionFile": data.get("sessionFile")})

    error: str | None = None
    try:
        record_state("state-1")
        if new:
            send({"id": "new", "type": "new_session"})
            frame = await_response("new")
            if frame.get("success") is not True:
                raise SmokeError(f"new_session failed: {frame}")
            record_state("state-2")
        result["last_response_t"] = time.time()
        time.sleep(hold)
    except SmokeError as exc:
        error = str(exc)
    finally:
        result["close_t"] = time.time()
        try:
            stdin.close()
        except OSError:
            pass
    try:
        result["rc"] = proc.wait(timeout=EXIT_TIMEOUT)
    except subprocess.TimeoutExpired:
        proc.kill()
        result["rc"] = None
        proc.wait()
    result["exit_t"] = time.time()
    while True:
        try:
            item = inbox.get(timeout=2)
        except queue.Empty:
            break
        if item is None:
            break
        frames.append(item[1])
        if item[1].get("type") == "ready":
            result.setdefault("ready_t", item[0])
    result.update(frames=frames, sessions=sessions, responses=responses, error=error)
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    if error:
        raise SmokeError(error)
    return (
        f"session rc={result['rc']} sessions={[s['sessionId'] for s in sessions]} "
        f"exit {result['exit_t'] - result['close_t']:.2f}s after stdin close"
    )


def load_session(path: Path) -> dict[str, Any]:
    data = load_json(path)
    if not isinstance(data, dict):
        raise SmokeError(f"{path}: not a session record")
    if data.get("error"):
        raise SmokeError(f"{path}: session failed: {data['error']}")
    return data


def require_answered(data: dict[str, Any], label: str) -> None:
    if not data.get("sessions") or not data["sessions"][0].get("sessionId"):
        raise SmokeError(f"{label}: get_state was not answered with a sessionId")
    if "ready_t" not in data:
        raise SmokeError(f"{label}: no rpc ready frame")
    if data.get("rc") != 0:
        raise SmokeError(f"{label}: omp exited {data.get('rc')} (see the .stderr file beside the session JSON)")


def extension_errors(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [frame for frame in data.get("frames", []) if frame.get("type") == "extension_error"]


# --- assertions -----------------------------------------------------------------------------


Records = list[dict[str, Any]]


def session_reports(rec: Path, session_json: Path) -> tuple[Records, Records, Records]:
    data = load_session(session_json)
    require_answered(data, "L1")
    sessions: list[dict[str, Any]] = data["sessions"]
    if len(sessions) != 2:
        raise SmokeError(f"L1: expected 2 RPC sessions (startup + new), got {sessions}")
    items = records(rec)
    reports = [r for r in items if request_of(r).get("method") == SESSION_METHOD]
    return items, reports, sessions


def assert_trigger(rec: Path, session_json: Path) -> str:
    _, reports, sessions = session_reports(rec, session_json)
    starts = [params_of(r).get("session_start_source") for r in reports]
    if starts != ["startup", "new"]:
        raise SmokeError(f"L1: expected one startup then one new report_agent_session, got {starts}")
    return f"L1 ok: one startup and one new report_agent_session for sessions {[s['sessionId'] for s in sessions]}"


def assert_payload(rec: Path, session_json: Path, schema_json: Path, pane: str) -> str:
    items, reports, sessions = session_reports(rec, session_json)
    if len(reports) != len(sessions):
        raise SmokeError(f"L2: {len(reports)} report_agent_session requests for {len(sessions)} sessions")
    schema = load_json(schema_json)
    required = schema["schemas"]["request"]["$defs"]["PaneReportAgentSessionParams"]["required"]
    previous = -1
    # records() returns accept (send) order, not thread-completion order.
    for item in items:
        params = params_of(item)
        seq = params.get("seq")
        if not isinstance(seq, int) or isinstance(seq, bool) or seq <= previous:
            raise SmokeError(
                f"L2: seq {seq!r} (connection {item.get('n')}) is not an integer strictly above {previous}"
            )
        previous = seq
    for item, expected in zip(reports, sessions, strict=True):
        params = params_of(item)
        missing = [key for key in required if key not in params]
        if missing:
            raise SmokeError(f"L2: report misses schema-required {missing}: {params}")
        if params.get("pane_id") != pane or params.get("source") != SOURCE or params.get("agent") != AGENT:
            raise SmokeError(f"L2: expected pane_id={pane} source={SOURCE} agent={AGENT}, got {params}")
        session_path = params.get("agent_session_path")
        session_id = expected["sessionId"]
        if not isinstance(session_path, str) or not os.path.isabs(session_path):
            raise SmokeError(f"L2: agent_session_path {session_path!r} is not an absolute path")
        if session_id not in Path(session_path).name:
            raise SmokeError(f"L2: {session_path} does not name RPC sessionId {session_id}")
        if expected.get("sessionFile") and expected["sessionFile"] != session_path:
            raise SmokeError(f"L2: report path {session_path} != RPC sessionFile {expected['sessionFile']}")
    return (
        f"L2 ok: {SOURCE} agent={AGENT} pane {pane}; seq strictly increasing over {len(items)} requests; "
        f"schema-required {required} present; absolute paths name RPC sessionIds"
    )


def assert_silent(rec: Path, session_json: Path) -> str:
    data = load_session(session_json)
    require_answered(data, "L3")
    items = records(rec)
    if items:
        raise SmokeError(f"L3: expected 0 herdr connections, got {len(items)}: {items[:2]}")
    return f"L3 ok: 0 connections; session {data['sessions'][0]['sessionId']} ready"


def assert_isolated(session_json: Path) -> str:
    data = load_session(session_json)
    require_answered(data, "L4")
    errors = extension_errors(data)
    if errors:
        raise SmokeError(f"L4: extension_error frames: {errors}")
    return f"L4 ok: refused socket, no extension_error, get_state answered ({len(data['sessions'])} sessions)"


def assert_stall(rec: Path, session_json: Path, hold: float) -> str:
    data = load_session(session_json)
    require_answered(data, "L5")
    if not records(rec):
        raise SmokeError("L5: the stalled socket saw no connection, so the stall was not exercised")
    errors = extension_errors(data)
    if errors:
        raise SmokeError(f"L5: extension_error frames: {errors}")
    first_state = data["responses"]["state-1"]
    ready_gap = first_state - data["ready_t"]
    if ready_gap > STALL_READY_BUDGET:
        raise SmokeError(f"L5: get_state answered {ready_gap:.2f}s after ready (budget {STALL_READY_BUDGET}s)")
    run = data["exit_t"] - data["last_response_t"]
    if run > hold + EXIT_BUDGET:
        raise SmokeError(f"L5: exit {run:.2f}s after the last response (budget {hold}+{EXIT_BUDGET}s)")
    return f"L5 ok: get_state {ready_gap:.2f}s after ready; exit {run:.2f}s after the last response (hold {hold}s)"


def assert_cancel(rec: Path, session_json: Path) -> str:
    data = load_session(session_json)
    require_answered(data, "L6")
    if not records(rec):
        raise SmokeError("L6: the stalled socket saw no connection, so cancellation was not exercised")
    gap = data["exit_t"] - data["close_t"]
    if gap > EXIT_BUDGET:
        raise SmokeError(f"L6: exit {gap:.2f}s after stdin close (budget {EXIT_BUDGET}s)")
    if extension_errors(data):
        raise SmokeError(f"L6: extension_error frames: {extension_errors(data)}")
    return f"L6 ok: exit {gap:.2f}s after stdin close with a stalled socket"


def assert_single_source(rec: Path, session_json: Path) -> str:
    data = load_session(session_json)
    require_answered(data, "L7")
    items = records(rec)
    sources = sorted({str(params_of(r).get("source")) for r in items})
    if sources != [SOURCE]:
        raise SmokeError(f"L7: expected only {SOURCE} reports, got sources {sources}")
    events = len(data["sessions"])
    methods = [request_of(r).get("method") for r in items]
    expected = [SESSION_METHOD, STATE_METHOD] * events
    if sorted(map(str, methods)) != sorted(expected):
        raise SmokeError(f"L7: expected one session+state pair per event ({events} events), got {methods}")
    return f"L7 ok: {len(items)} requests, all {SOURCE}, exactly one session+state pair for each of {events} events"


def walk(node: Any) -> Iterator[tuple[str, Any]]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield key, value
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def assert_no_extensions(list_json: Path) -> str:
    listing = load_json(list_json)
    if not isinstance(listing, dict):
        raise SmokeError(f"{list_json}: not a plugin listing")
    seen: list[str] = []
    for group in ("npm", "marketplace"):
        for item in listing.get(group) or []:
            name = str(item.get("id") or item.get("name") or "")
            if not name.split("@", 1)[0].startswith("ycc"):
                continue
            seen.append(name)
            hits = [value for key, value in walk(item) if key == "extensions" and value]
            for entry in item.get("entries") or []:
                install = entry.get("installPath")
                manifest = Path(str(install)) / "package.json" if install else None
                if manifest is None or not manifest.is_file():
                    raise SmokeError(f"L7: {name} entry has no installed package.json: {entry}")
                omp_field = load_json(manifest).get("omp")
                if isinstance(omp_field, dict) and omp_field.get("extensions"):
                    hits.append(omp_field["extensions"])
            if hits:
                raise SmokeError(f"L7: {name} ships manifest.extensions {hits}")
    if not any(name.split("@", 1)[0] == "ycc" for name in seen):
        raise SmokeError(f"L7: ycc@ycc is not installed in {list_json} (saw {seen})")
    return f"L7 ok: installed {seen}; no listing or installed package.json carries omp.extensions"


# --- herdr pane -----------------------------------------------------------------------------


def herdr_call(sock_path: Path, method: str, params: dict[str, Any]) -> dict[str, Any]:
    request = {"id": f"ycc-smoke:{method}:{time.time_ns()}", "method": method, "params": params}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(10)
        conn.connect(str(sock_path))
        conn.sendall((json.dumps(request) + "\n").encode())
        buffer = b""
        while b"\n" not in buffer:
            chunk = conn.recv(65536)
            if not chunk:
                break
            buffer += chunk
    reply = json.loads(buffer.split(b"\n", 1)[0])
    if not isinstance(reply, dict) or "error" in reply:
        raise SmokeError(f"herdr {method} failed: {reply}")
    return reply


def pane_info(sock_path: Path, pane: str) -> dict[str, Any]:
    info = herdr_call(sock_path, "pane.get", {"pane_id": pane})["result"]["pane"]
    if not isinstance(info, dict):
        raise SmokeError(f"pane.get {pane}: no pane object")
    return info


def herdr_pane(sock_path: Path, pane: str, out: Path) -> str:
    deadline = time.time() + 30
    info = pane_info(sock_path, pane)
    while not info.get("agent_session") and time.time() < deadline:
        time.sleep(0.5)
        info = pane_info(sock_path, pane)
    trace: dict[str, Any] = {"before": info}
    out.write_text(json.dumps(trace, indent=1), encoding="utf-8")
    before = info.get("agent_session")
    if info.get("agent") != AGENT or not isinstance(before, dict) or before.get("source") != SOURCE:
        raise SmokeError(f"L8: pane {pane} did not report agent={AGENT} with a {SOURCE} session: {info}")
    seq = time.time_ns() // 1000 + 10**9
    reply = herdr_call(
        sock_path,
        SESSION_METHOD,
        {
            "pane_id": pane,
            "source": YCC_SOURCE,
            "agent": AGENT,
            "seq": seq,
            "agent_session_id": "ycc-smoke-inert",
            "session_start_source": "startup",
        },
    )
    after = pane_info(sock_path, pane)
    trace.update(ycc_reply=reply, after=after)
    out.write_text(json.dumps(trace, indent=1), encoding="utf-8")
    if after.get("agent_session") != before:
        raise SmokeError(f"L8: a {YCC_SOURCE} report changed agent_session {before} -> {after.get('agent_session')}")
    return (
        f"L8 ok: pane {pane} agent={AGENT} session {before.get('kind')}={before.get('value')} from {SOURCE}; "
        f"{YCC_SOURCE} report_agent_session ({reply.get('result')}) left it unchanged"
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="omp_herdr_smoke", description=__doc__.split("\n", 1)[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("recorder")
    p.add_argument("socket", type=Path)
    p.add_argument("mode")
    p.add_argument("out", type=Path)
    p = sub.add_parser("session")
    p.add_argument("out", type=Path)
    p.add_argument("--new", action="store_true")
    p.add_argument("--hold", type=float, default=1.0)
    p.add_argument("argv", nargs=argparse.REMAINDER)
    for name, args in (
        ("assert-trigger", ("rec", "session")),
        ("assert-payload", ("rec", "session", "schema", "pane")),
        ("assert-silent", ("rec", "session")),
        ("assert-isolated", ("session",)),
        ("assert-stall", ("rec", "session", "hold")),
        ("assert-cancel", ("rec", "session")),
        ("assert-single-source", ("rec", "session")),
        ("assert-no-extensions", ("list_json",)),
        ("herdr-pane", ("socket", "pane", "out")),
    ):
        p = sub.add_parser(name)
        for arg in args:
            p.add_argument(arg)
    ns = parser.parse_args(argv[1:])
    try:
        command: str = ns.command
        if command == "recorder":
            message = recorder(ns.socket, ns.mode, ns.out)
        elif command == "session":
            omp_argv = ns.argv[1:] if ns.argv[:1] == ["--"] else ns.argv
            message = session(ns.out, ns.new, ns.hold, omp_argv)
        elif command == "assert-trigger":
            message = assert_trigger(Path(ns.rec), Path(ns.session))
        elif command == "assert-payload":
            message = assert_payload(Path(ns.rec), Path(ns.session), Path(ns.schema), ns.pane)
        elif command == "assert-silent":
            message = assert_silent(Path(ns.rec), Path(ns.session))
        elif command == "assert-isolated":
            message = assert_isolated(Path(ns.session))
        elif command == "assert-stall":
            message = assert_stall(Path(ns.rec), Path(ns.session), float(ns.hold))
        elif command == "assert-cancel":
            message = assert_cancel(Path(ns.rec), Path(ns.session))
        elif command == "assert-single-source":
            message = assert_single_source(Path(ns.rec), Path(ns.session))
        elif command == "assert-no-extensions":
            message = assert_no_extensions(Path(ns.list_json))
        else:
            message = herdr_pane(Path(ns.socket), ns.pane, Path(ns.out))
    except (SmokeError, OSError, ValueError, KeyError) as exc:
        print(f"omp_herdr_smoke {ns.command}: {exc}", file=sys.stderr)
        return 1
    print(message)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
