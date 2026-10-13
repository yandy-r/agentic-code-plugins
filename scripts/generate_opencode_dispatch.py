#!/usr/bin/env python3
"""Project Claude dispatch prose onto OpenCode V2's native child-session API."""

from __future__ import annotations

import re
from pathlib import Path

from generate_opencode_common import apply_opencode_text_transforms, load_agent_aliases
from generate_opencode_dispatch_markdown import (
    _project_standalone_only_terms,
    _remove_empty_fenced_blocks,
    _remove_team_operations,
    _strip_embedded_team_communication_sections,
    _strip_team_sections,
    _translate_native_vocabulary,
)
from generate_opencode_dispatch_markdown import (
    project_opencode_dispatch_description as project_opencode_dispatch_description,
)
from generate_opencode_dispatch_special import (
    _project_implementor,
    _project_plan,
    _project_prp_implement,
    _project_prp_plan,
    _project_review_checklist,
)
from generate_opencode_dispatch_workflows import (
    _project_foreground_result_contracts,
    _project_implement_plan,
    _project_operational_team_clauses,
    _project_required_workflow_surfaces,
    _project_research_workflow_contracts,
)

SCRIPT_DIR = Path(__file__).resolve().parent
STANDALONE_DISPATCH_SOURCE = "_shared/references/standalone-dispatch.md"
STANDALONE_DISPATCH_TEMPLATE = SCRIPT_DIR / "opencode_templates" / "standalone-dispatch.md"


def render_standalone_dispatch_reference() -> str:
    """Return the maintained OpenCode-only standalone dispatch contract.

    Sections 1-7 come from the hand-maintained native template. Sections 8-10
    (worktree/branch preparation, dependency batching, confirmed-plan execution)
    are mode-independent, so they are selected whole from the canonical source
    and given the plain OpenCode path/vocabulary rewrite, keeping the commands
    and prompt lines consumers point at. The template's team-mode note is
    section 11.
    """
    try:
        template = STANDALONE_DISPATCH_TEMPLATE.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"OpenCode dispatch template is unavailable: {STANDALONE_DISPATCH_TEMPLATE}") from exc
    source_path = SCRIPT_DIR.parent / "ycc" / "skills" / STANDALONE_DISPATCH_SOURCE
    try:
        source = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Standalone dispatch source is unavailable: {source_path}") from exc
    marker = "## 8. Unsupported team mode"
    if marker not in template:
        raise RuntimeError("OpenCode dispatch template lost its team-mode section")
    head, unsupported = template.split(marker, 1)
    workflow = _project_standalone_workflow_sections(source)
    unsupported = "## 11. Unsupported team mode" + unsupported
    return _ensure_trailing_newline(f"{head.rstrip()}\n\n{workflow.rstrip()}\n\n{unsupported.strip()}")


def _project_standalone_workflow_sections(text: str) -> str:
    """Select canonical sections 8-10 and rewrite paths/vocabulary for OpenCode."""
    sections = _split_numbered_sections(text)
    body = "\n\n".join(sections[number] for number in (8, 9, 10))
    body = body.replace("Applies to standalone and `--team` runs.", "Applies to standalone runs.")
    body = apply_opencode_text_transforms(body, load_agent_aliases())
    body = _translate_native_vocabulary(body)
    return _ensure_trailing_newline(body)


def _split_numbered_sections(text: str) -> dict[int, str]:
    """Split the canonical dispatch source into `## <n>. ...` sections by number."""
    matches = list(re.finditer(r"^## (\d+)\.\s", text, flags=re.MULTILINE))
    sections: dict[int, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[int(match.group(1))] = text[match.start() : end].rstrip().removesuffix("---").rstrip()
    missing = [number for number in (8, 9, 10) if number not in sections]
    if missing:
        raise RuntimeError(f"Standalone dispatch source is missing sections {missing}")
    return sections


def _ensure_trailing_newline(text: str) -> str:
    return text.rstrip("\n") + "\n" if text else ""


def project_opencode_dispatch(text: str, source_path: str | Path) -> str:
    """Return OpenCode-native dispatch prose for one generated source file."""
    normalized_path = Path(source_path).as_posix()
    if normalized_path.endswith(STANDALONE_DISPATCH_SOURCE):
        return render_standalone_dispatch_reference()

    projected = _strip_team_sections(text)
    projected = _strip_embedded_team_communication_sections(projected)
    projected = _project_foreground_result_contracts(projected)
    projected = _project_research_workflow_contracts(projected, normalized_path)
    is_entrypoint = normalized_path.endswith("SKILL.md") or normalized_path.startswith("commands/")
    projected = _remove_team_operations(projected, add_compatibility_note=is_entrypoint)
    projected = _project_standalone_only_terms(projected)
    projected = _translate_native_vocabulary(projected)
    projected = _project_research_workflow_contracts(projected, normalized_path)
    if normalized_path.endswith("implement-plan/SKILL.md"):
        projected = _project_implement_plan(projected)
    if normalized_path.endswith("agents/implementor.md"):
        projected = _project_implementor(projected)
    if normalized_path.endswith("_shared/references/review-checklist.md"):
        projected = _project_review_checklist(projected)
    if normalized_path.endswith("prp-implement/SKILL.md"):
        projected = _project_prp_implement(projected)
    if normalized_path.endswith("prp-plan/SKILL.md"):
        projected = _project_prp_plan(projected)
    if normalized_path.endswith("plan/SKILL.md"):
        projected = _project_plan(projected)
    projected = _project_operational_team_clauses(projected, normalized_path)
    projected = _project_required_workflow_surfaces(projected, normalized_path)
    projected = _remove_empty_fenced_blocks(projected)
    return _ensure_trailing_newline(projected)
