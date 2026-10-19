#!/usr/bin/env python3
"""Checked-in capability-matrix test plus self-contained negative fixtures and CLI coverage."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from validate_capability_matrix import (  # noqa: E402
    CANONICAL_CAPABILITIES,
    CANONICAL_TARGETS,
    DEFAULT_MATRIX_PATH,
    DEFAULT_SCHEMA_PATH,
    validate,
)

RUNTIMES = ["claude", "cursor", "codex", "opencode", "omp", "agents"]
HEADER = "| capability | " + " | ".join(CANONICAL_TARGETS) + " |"
SEPARATOR = "| --- | " + " | ".join("---" for _ in CANONICAL_TARGETS) + " |"
# Every capability is supported except INSTALL_PATH:omp, which needs a note.
NOTE_KEY = "INSTALL_PATH:omp"


def row(capability: str, last: str = "supported") -> str:
    cells = ["supported"] * (len(CANONICAL_TARGETS) - 1) + [last]
    return f"| {capability} | " + " | ".join(cells) + " |"


def fixture_rows() -> list[str]:
    return [row(cap, "unsupported" if cap == "INSTALL_PATH" else "supported") for cap in CANONICAL_CAPABILITIES]


def fixture_matrix(
    *,
    header: str = HEADER,
    separator: str = SEPARATOR,
    rows: list[str] | None = None,
    notes: list[str] | None = None,
) -> str:
    table = [header, separator, *(fixture_rows() if rows is None else rows)]
    note_lines = [f"**{NOTE_KEY}**", "Not installable yet."] if notes is None else notes
    return "\n".join(
        [
            "# Matrix",
            "",
            "## Capability Matrix",
            "",
            *table,
            "",
            "## Notes",
            "",
            *note_lines,
            "",
        ]
    )


def fixture_schema(runtimes: list[str] | None = None) -> dict[str, object]:
    enum = RUNTIMES if runtimes is None else runtimes
    return {"$defs": {"Package": {"properties": {"runtimes": {"propertyNames": {"enum": list(enum)}}}}}}


class MatrixFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def write(self, matrix: str, schema: dict[str, object] | None = None) -> tuple[Path, Path]:
        matrix_path = self.root / "target-capability-matrix.md"
        schema_path = self.root / "packages.schema.json"
        matrix_path.write_text(matrix, encoding="utf-8")
        schema_path.write_text(json.dumps(schema or fixture_schema()), encoding="utf-8")
        return matrix_path, schema_path

    def errors(self, matrix: str, schema: dict[str, object] | None = None) -> list[str]:
        return validate(*self.write(matrix, schema))

    def assert_error(self, errors: list[str], needle: str) -> None:
        self.assertTrue(any(needle in error for error in errors), f"{needle!r} not in {errors}")


class CheckedInMatrixTests(MatrixFixture):
    def test_checked_in_matrix_passes(self) -> None:
        self.assertEqual(validate(DEFAULT_MATRIX_PATH, DEFAULT_SCHEMA_PATH), [])

    def test_fixture_passes(self) -> None:
        self.assertEqual(self.errors(fixture_matrix()), [])


class NegativeTests(MatrixFixture):
    def test_unknown_target_column_fails(self) -> None:
        header = HEADER.replace("| omp |", "| pi |")
        errors = self.errors(fixture_matrix(header=header))
        self.assert_error(errors, "must be exactly")
        self.assert_error(errors, "target 'pi' is not a runtime")

    def test_reordered_targets_fail(self) -> None:
        header = HEADER.replace("| cursor | codex |", "| codex | cursor |")
        self.assert_error(self.errors(fixture_matrix(header=header)), "must be exactly")

    def test_stale_target_not_in_schema_fails(self) -> None:
        schema = fixture_schema([r for r in RUNTIMES if r != "omp"])
        self.assert_error(self.errors(fixture_matrix(), schema), "target 'omp' is not a runtime")

    def test_missing_note_fails(self) -> None:
        errors = self.errors(fixture_matrix(notes=[]))
        self.assert_error(errors, f"{NOTE_KEY} has no **{NOTE_KEY}** note")

    def test_stale_note_target_fails(self) -> None:
        notes = [f"**{NOTE_KEY}**", "x", "", "**SKILLS:pi**", "Stale."]
        self.assert_error(self.errors(fixture_matrix(notes=notes)), "unknown target 'pi'")

    def test_stale_note_capability_fails(self) -> None:
        notes = [f"**{NOTE_KEY}**", "x", "", "**PLUGINS:omp**", "Stale."]
        self.assert_error(self.errors(fixture_matrix(notes=notes)), "unknown capability 'PLUGINS'")

    def test_bad_vocab_fails(self) -> None:
        rows = fixture_rows()
        rows[0] = row("SKILLS", "planned")
        self.assert_error(self.errors(fixture_matrix(rows=rows)), "'planned' is not one of")

    def test_duplicate_capability_fails(self) -> None:
        rows = fixture_rows()
        rows.insert(1, rows[0])
        self.assert_error(self.errors(fixture_matrix(rows=rows)), "duplicate capability row 'SKILLS'")

    def test_deleted_capability_row_fails(self) -> None:
        rows = [r for r in fixture_rows() if not r.startswith("| MODS |")]
        self.assert_error(self.errors(fixture_matrix(rows=rows)), "missing ['MODS']")

    def test_unknown_capability_row_fails(self) -> None:
        rows = [*fixture_rows(), row("PLUGINS")]
        self.assert_error(self.errors(fixture_matrix(rows=rows)), "unknown ['PLUGINS']")

    def test_reordered_capability_rows_fail(self) -> None:
        rows = fixture_rows()
        rows[0], rows[1] = rows[1], rows[0]
        self.assert_error(self.errors(fixture_matrix(rows=rows)), "out of order")

    def test_empty_capability_name_fails(self) -> None:
        rows = fixture_rows()
        rows[0] = row("")
        errors = self.errors(fixture_matrix(rows=rows))
        self.assert_error(errors, "capability row has an empty name")
        self.assert_error(errors, "missing ['SKILLS']")

    def test_alignment_colon_separator_fails(self) -> None:
        # The audit parser treats a colon separator as a data row, so the validator must too.
        separator = "| :-- | " + " | ".join(":-:" for _ in CANONICAL_TARGETS) + " |"
        self.assertNotEqual(self.errors(fixture_matrix(separator=separator)), [])

    def test_colonless_note_is_allowed(self) -> None:
        notes = [f"**{NOTE_KEY}**", "x", "", "**FREE FORM**", "Prose."]
        self.assertEqual(self.errors(fixture_matrix(notes=notes)), [])


class CliTests(MatrixFixture):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "validate_capability_matrix.py"), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_cli_default_passes(self) -> None:
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")

    def test_cli_override_fails_to_stderr(self) -> None:
        matrix_path, schema_path = self.write(fixture_matrix(notes=[]))
        result = self.run_cli("--matrix", str(matrix_path), "--schema", str(schema_path))
        self.assertEqual(result.returncode, 1)
        self.assertIn(NOTE_KEY, result.stderr)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
