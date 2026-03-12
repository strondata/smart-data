import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

from typer.testing import CliRunner

from aptdata.cli.app import app
from aptdata.core.hygiene import scan_codebase
from aptdata.mcp.server import run_code_hygiene


def test_code_hygiene_scanner(tmp_path: Path, monkeypatch: MagicMock) -> None:
    # Setup mock file structure
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "example.md").write_text("This mentions BaseComponent")

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "test.py").write_text("import os\n")

    # Mock subprocess.run for ruff output
    mock_ruff_output = json.dumps(
        [
            {
                "filename": str(tmp_path / "src" / "test.py"),
                "location": {"row": 1, "column": 1},
                "rule": {"code": "F401", "name": "unused-import"},
                "message": "'os' imported but unused",
            },
            {
                "filename": str(tmp_path / "src" / "obsolete.py"),
                "location": {"row": 5, "column": 1},
                "rule": {"code": "F841", "name": "unused-variable"},
                "message": "Local variable is assigned to but never used",
            },
        ]
    )

    class MockResult:
        stdout = mock_ruff_output
        returncode = 0

    def mock_run(*args, **kwargs):
        return MockResult()

    monkeypatch.setattr(subprocess, "run", mock_run)

    # Scan codebase
    findings = scan_codebase(tmp_path)

    assert len(findings) == 2

    finding1 = findings[0]
    assert "src/test.py" in finding1["file_path"].replace("\\", "/")
    assert finding1["rule_code"] == "ruff:F401"
    assert finding1["is_in_docs"] is False

    finding2 = findings[1]
    assert "src/obsolete.py" in finding2["file_path"].replace("\\", "/")
    assert finding2["rule_code"] == "ruff:F841"
    assert finding2["is_in_docs"] is False


def test_code_hygiene_no_issues(tmp_path: Path, monkeypatch: MagicMock) -> None:
    class MockResult:
        stdout = "[]"
        returncode = 0

    def mock_run(*args, **kwargs):
        return MockResult()

    monkeypatch.setattr(subprocess, "run", mock_run)

    findings = scan_codebase(tmp_path)
    assert len(findings) == 0


def test_code_hygiene_command(monkeypatch: MagicMock) -> None:
    # We'll mock scan_codebase to return some findings
    import aptdata.core.hygiene

    def mock_scan_codebase(directory):
        return [
            {
                "file_path": "foo.py",
                "line_number": 1,
                "rule_code": "F401",
                "message": "msg",
                "is_in_docs": False,
            }
        ]

    monkeypatch.setattr(aptdata.core.hygiene, "scan_codebase", mock_scan_codebase)

    runner = CliRunner()
    result = runner.invoke(app, ["mesh", "clean", "--json"])
    assert result.exit_code == 0
    assert "mesh.clean.started" in result.stdout
    assert "mesh.clean.completed" in result.stdout
    assert "foo.py" in result.stdout


def test_mcp_run_code_hygiene(monkeypatch: MagicMock) -> None:
    import aptdata.core.hygiene

    def mock_scan_codebase(directory):
        return [
            {
                "file_path": "foo.py",
                "line_number": 1,
                "rule_code": "F401",
                "message": "msg",
                "is_in_docs": False,
            }
        ]

    monkeypatch.setattr(aptdata.core.hygiene, "scan_codebase", mock_scan_codebase)

    result = run_code_hygiene(".")
    assert result["status"] == "success"
    assert result["count"] == 1
    assert result["findings"][0]["file_path"] == "foo.py"
