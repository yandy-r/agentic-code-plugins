#!/usr/bin/env bash
# generate-mcp-catalog.sh
# Lists the MCP servers bundled with this package (resources/mcp/mcp.json).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/../../../resources/mcp/select-mcp.py" --catalog
