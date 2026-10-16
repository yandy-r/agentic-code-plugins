#!/bin/sh
# Cursor sessionStart integration for herdr. No worktree creation or Claude events.
# Reports session identity only when running inside an explicitly configured pane.
[ "${1:-}" = "session" ] || exit 0
[ "${HERDR_ENV:-}" = "1" ] || exit 0
[ -n "${HERDR_SOCKET_PATH:-}" ] || exit 0
[ -n "${HERDR_PANE_ID:-}" ] || exit 0
command -v python3 >/dev/null 2>&1 || exit 0

python3 -c '
import json
import os
import socket
import sys
import time

try:
    payload = json.load(sys.stdin)
except (ValueError, OSError):
    raise SystemExit(0)
if not isinstance(payload, dict) or payload.get("hook_event_name") != "sessionStart":
    raise SystemExit(0)
session_id = payload.get("session_id") or payload.get("conversation_id")
if not isinstance(session_id, str) or not session_id:
    raise SystemExit(0)
seq = time.time_ns()
request = {
    "id": f"herdr:cursor:{seq}",
    "method": "pane.report_agent_session",
    "params": {
        "pane_id": os.environ["HERDR_PANE_ID"],
        "source": "herdr:cursor",
        "agent": "cursor",
        "seq": seq,
        "agent_session_id": session_id,
    },
}
try:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(0.5)
        client.connect(os.environ["HERDR_SOCKET_PATH"])
        client.sendall((json.dumps(request) + "\n").encode())
        client.recv(4096)
except OSError:
    pass
' 2>/dev/null || true
