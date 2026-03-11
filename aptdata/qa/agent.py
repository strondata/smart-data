"""QA/DX Agent module for code governance and quality."""

import ast
import logging
import re
import subprocess
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

class QAIssue(BaseModel):
    """Represents a code quality issue found by the agent."""
    model_config = ConfigDict(extra="allow")

    rule_id: str
    file: str
    line: int | None = None
    message: str
    severity: str = "warning"


class QAReport(BaseModel):
    """The final QA report."""
    model_config = ConfigDict(extra="allow")

    issues: list[QAIssue] = Field(default_factory=list)
    score: int = 100
    scanned_files: int = 0
    passed: bool = True


class QAAgent:
    """Agent responsible for auditing codebase QA and DX standards."""

    def __init__(self, root_dir: str | Path = ".") -> None:
        self.root_dir = Path(root_dir).resolve()

    def run_all_checks(self, deep: bool = False) -> QAReport:
        """Run all QA/DX checks and return a unified report."""
        report = QAReport()

        self._check_cli_makefile_consistency(report)
        self._check_cli_commands(report)
        self._check_docstrings(report)
        self._check_contract_first_violations(report)
        self._check_missing_tests(report)

        if deep:
            self._run_external_tools(report)
            self._check_cyclomatic_complexity(report)

        # Basic scoring
        report.score = max(0, 100 - len(report.issues) * 5)
        report.passed = report.score >= 80 and not any(
            i.severity == "error" for i in report.issues
        )
        return report

    def _check_cli_makefile_consistency(self, report: QAReport) -> None:
        """Check if Makefile targets have corresponding documentation."""
        makefile_path = self.root_dir / "Makefile"
        if not makefile_path.exists():
            return

        content = makefile_path.read_text(encoding="utf-8")

        targets = []
        for line in content.splitlines():
            match = re.match(r"^([a-zA-Z0-9_-]+):", line)
            if match and match.group(1) not in (".PHONY",):
                targets.append(match.group(1))

        docs_dir = self.root_dir / "docs"
        docs_content = ""
        if docs_dir.exists():
            for doc_file in docs_dir.rglob("*.md"):
                docs_content += doc_file.read_text(encoding="utf-8")

        readme_path = self.root_dir / "README.md"
        if readme_path.exists():
            docs_content += readme_path.read_text(encoding="utf-8")

        for target in targets:
            if target not in docs_content:
                report.issues.append(
                    QAIssue(
                        rule_id="QA-MAKE-001",
                        file="Makefile",
                        message=f"Makefile target '{target}' is not documented in docs/.",
                        severity="warning"
                    )
                )

    def _check_cli_commands(self, report: QAReport) -> None:
        """Inspect aptdata.cli for Typer/Click commands missing help text."""
        cli_dir = self.root_dir / "aptdata/cli"
        if not cli_dir.exists():
            return

        for py_file in cli_dir.rglob("*.py"):
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        # Check if it has a typer/click decorator
                        is_command = any(
                            isinstance(d, ast.Call) and
                            isinstance(d.func, ast.Attribute) and
                            d.func.attr == "command"
                            for d in node.decorator_list
                        )
                        if is_command:
                            docstring = ast.get_docstring(node)
                            if not docstring:
                                report.issues.append(
                                    QAIssue(
                                        rule_id="QA-CLI-001",
                                        file=str(py_file.relative_to(self.root_dir)),
                                        line=node.lineno,
                                        message=f"CLI command '{node.name}' is missing a docstring (--help).",
                                        severity="warning"
                                    )
                                )
            except SyntaxError:
                pass

    def _check_docstrings(self, report: QAReport) -> None:
        """Audit presence and quality of docstrings in core/plugins."""
        dirs_to_check = ["aptdata/core", "aptdata/plugins"]
        for d in dirs_to_check:
            dir_path = self.root_dir / d
            if not dir_path.exists():
                continue
            for py_file in dir_path.rglob("*.py"):
                if py_file.name == "__init__.py":
                    continue
                report.scanned_files += 1
                try:
                    tree = ast.parse(py_file.read_text(encoding="utf-8"))
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                            docstring = ast.get_docstring(node)
                            if not docstring and not node.name.startswith("_"):
                                report.issues.append(
                                    QAIssue(
                                        rule_id="QA-DOC-001",
                                        file=str(py_file.relative_to(self.root_dir)),
                                        line=node.lineno,
                                        message=f"Missing docstring in public '{node.name}'.",
                                        severity="warning"
                                    )
                                )
                except SyntaxError:
                    pass

    def _check_contract_first_violations(self, report: QAReport) -> None:
        """Check for structural contract-first violations (e.g. Pandas coupling in core)."""
        core_dir = self.root_dir / "aptdata/core"
        if not core_dir.exists():
            return

        for py_file in core_dir.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            if "import pandas" in content or "from pandas import" in content:
                report.issues.append(
                    QAIssue(
                        rule_id="QA-ARCH-001",
                        file=str(py_file.relative_to(self.root_dir)),
                        message="Architectural violation: Pandas coupled in framework core.",
                        severity="error"  # Blocks PR
                    )
                )

    def _check_missing_tests(self, report: QAReport) -> None:
        """Ensure core/plugins files have corresponding unit tests."""
        tests_dir = self.root_dir / "tests"
        if not tests_dir.exists():
            return

        dirs_to_check = ["aptdata/core", "aptdata/plugins"]
        for d in dirs_to_check:
            dir_path = self.root_dir / d
            if not dir_path.exists():
                continue
            for py_file in dir_path.rglob("*.py"):
                if py_file.name == "__init__.py":
                    continue

                # Exclude purely abstract interfaces
                if py_file.name in ("interfaces.py", "base.py"):
                    continue

                test_file_name = f"test_{py_file.name}"
                test_exists = False
                for t in tests_dir.rglob(test_file_name):
                    test_exists = True
                    break

                if not test_exists:
                    report.issues.append(
                        QAIssue(
                            rule_id="QA-TEST-001",
                            file=str(py_file.relative_to(self.root_dir)),
                            message=f"Missing unit test file '{test_file_name}' for '{py_file.name}'.",
                            severity="warning"
                        )
                    )

    def _check_cyclomatic_complexity(self, report: QAReport) -> None:
        """Check cyclomatic complexity using radon."""
        try:
            res = subprocess.run(
                ["radon", "cc", "-a", "-s", "--min", "C", "aptdata/"],
                cwd=self.root_dir,
                capture_output=True,
                text=True,
                check=False
            )
            if res.returncode == 0 and res.stdout.strip():
                # Any output means complexity > B (which means C, D, E, F)
                lines = [l for l in res.stdout.splitlines() if "-" in l]
                for line in lines:
                    report.issues.append(
                        QAIssue(
                            rule_id="QA-CC-001",
                            file=".",
                            message=f"High Cyclomatic Complexity: {line.strip()}",
                            severity="warning"
                        )
                    )
        except FileNotFoundError:
            pass

    def _run_external_tools(self, report: QAReport) -> None:
        """Run external tools like ruff, mypy for deep analysis."""
        try:
            res = subprocess.run(
                ["ruff", "check", "aptdata/"],
                cwd=self.root_dir,
                capture_output=True,
                text=True,
                check=False
            )
            if res.returncode != 0:
                report.issues.append(
                    QAIssue(
                        rule_id="QA-EXT-RUFF",
                        file=".",
                        message="Ruff found linting issues.",
                        severity="warning"
                    )
                )
        except FileNotFoundError:
            pass
