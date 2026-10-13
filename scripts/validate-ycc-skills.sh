#!/usr/bin/env bash
# Validate ycc skill frontmatter now that skills are the only invocation surface
# (wrapper commands are retired):
#   - every ycc/skills/<name>/SKILL.md has YAML frontmatter
#   - `name` is present and equals the directory name
#   - `description` is present and non-empty
#   - `user-invocable` / `disable-model-invocation` (when set) are booleans
#   - no legacy `command` key (the old `command: false` opt-out is gone)
#   - ycc/commands/ must not exist
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SKILLS_DIR="${REPO_ROOT}/ycc/skills"
COMMANDS_DIR="${REPO_ROOT}/ycc/commands"

[[ -d "${SKILLS_DIR}" ]] || { echo "validate-ycc-skills.sh: missing ${SKILLS_DIR}" >&2; exit 1; }

python3 - "${SKILLS_DIR}" "${COMMANDS_DIR}" <<'PY'
import re
import sys
from pathlib import Path

import yaml

FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
BOOLEAN_KEYS = ("user-invocable", "disable-model-invocation")


def load_frontmatter(text: str):
    """Return (dict, error). dict is None when frontmatter is absent/invalid."""
    m = FM_RE.match(text)
    if not m:
        return None, "missing YAML frontmatter"
    raw = m.group(1)
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        return None, f"invalid YAML frontmatter: {exc}"
    if not isinstance(data, dict):
        return None, "frontmatter is not a mapping"
    return data, None


skills_dir = Path(sys.argv[1])
commands_dir = Path(sys.argv[2])
errors: list[str] = []

if commands_dir.exists():
    errors.append(
        "ycc/commands/ must not exist (wrapper commands are retired; "
        "invoke skills directly)"
    )

count = 0
for skill_dir in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
    if skill_dir.name.startswith("_"):
        continue
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        errors.append(f"skill '{skill_dir.name}' has no SKILL.md")
        continue
    count += 1
    fm, err = load_frontmatter(skill_md.read_text(encoding="utf-8"))
    if err:
        errors.append(f"skill '{skill_dir.name}': {err}")
        continue
    name = fm.get("name")
    if not name:
        errors.append(f"skill '{skill_dir.name}': missing 'name'")
    elif name != skill_dir.name:
        errors.append(
            f"skill '{skill_dir.name}': name '{name}' does not match directory"
        )
    if not str(fm.get("description") or "").strip():
        errors.append(f"skill '{skill_dir.name}': missing or empty 'description'")
    for key in BOOLEAN_KEYS:
        if key in fm and not isinstance(fm[key], bool):
            errors.append(
                f"skill '{skill_dir.name}': '{key}' must be a boolean, "
                f"got {fm[key]!r}"
            )
    if "command" in fm:
        errors.append(
            f"skill '{skill_dir.name}': legacy 'command' key is not allowed "
            f"(use 'user-invocable: false' for non-slash skills)"
        )

if errors:
    print("validate-ycc-skills.sh: skill validation failed:", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    sys.exit(1)

print(f"OK: {count} skills validated; no ycc/commands directory.")
PY
