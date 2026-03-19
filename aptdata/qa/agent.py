import ast
import json
import logging
import os  # noqa: F401
import re
import subprocess
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(message)s")


class QAAgent:
    """Agent for automated code quality, formatting, interfaces, and architecture."""

    def __init__(self, root_dir: str = ".") -> None:
        self.root_dir = Path(root_dir)
        self.findings: list[dict[str, Any]] = []

    def run_all_checks(
        self, changed_files: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Run all quality and architecture checks."""
        self.findings.clear()

        target_dir = self.root_dir / "aptdata"
        if changed_files:
            targets = [
                f for f in changed_files if Path(f).exists() and f.endswith(".py")
            ]
        else:
            targets = [str(target_dir)]

        if targets:
            self._run_ruff(targets)
            self._run_mypy(targets)
            self._run_pydocstyle(targets)
            self._run_radon(targets)

            for t in targets:
                if Path(t).is_file():
                    self.detect_architectural_violations(Path(t))
                else:
                    for py_file in Path(t).rglob("*.py"):
                        self.detect_architectural_violations(py_file)

        self.validate_makefile_targets()
        self.validate_cli_commands()
        self.validate_missing_unit_tests(targets)

        return self.findings

    def emit_json_lines(self) -> None:
        """Emit findings as JSON lines."""
        for finding in self.findings:
            print(json.dumps(finding), flush=True)

    def _run_ruff(self, targets: list[str]) -> None:
        """Run ruff for static analysis and formatting checks."""
        try:
            cmd = ["ruff", "check", "--output-format=json", *targets]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.stdout:
                try:
                    ruff_findings = json.loads(result.stdout)
                    for r in ruff_findings:
                        self.findings.append(
                            {
                                "tool": "ruff",
                                "file": r.get("filename"),
                                "line": r.get("location", {}).get("row"),
                                "message": r.get("message"),
                                "severity": "warning",
                            }
                        )
                except json.JSONDecodeError:
                    pass
        except FileNotFoundError:
            self.findings.append(
                {"tool": "ruff", "message": "Ruff not found", "severity": "error"}
            )

    def _run_mypy(self, targets: list[str]) -> None:
        """Run mypy for static typing checks."""
        try:
            cmd = ["mypy", "--show-error-context", "--show-column-numbers", *targets]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                for line in result.stdout.splitlines():
                    if ".py:" in line:
                        self.findings.append(
                            {
                                "tool": "mypy",
                                "message": line.strip(),
                                "severity": "warning",
                            }
                        )
        except FileNotFoundError:
            self.findings.append(
                {"tool": "mypy", "message": "Mypy not found", "severity": "error"}
            )

    def _run_pydocstyle(self, targets: list[str]) -> None:
        """Run pydocstyle to audit docstrings."""
        try:
            cmd = ["pydocstyle", *targets]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                current_file = None
                for line in result.stdout.splitlines():
                    if line.startswith(str(self.root_dir)):
                        current_file = line.split(":")[0]
                    elif line.strip().startswith("D") and current_file:
                        self.findings.append(
                            {
                                "tool": "pydocstyle",
                                "file": current_file,
                                "message": line.strip(),
                                "severity": "warning",
                            }
                        )
        except FileNotFoundError:
            self.findings.append(
                {
                    "tool": "pydocstyle",
                    "message": "Pydocstyle not found",
                    "severity": "error",
                }
            )

    def _run_radon(self, targets: list[str]) -> None:
        """Run radon for cyclomatic complexity analysis."""
        try:
            cmd = ["radon", "cc", "-s", "-j", *targets]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.stdout:
                try:
                    radon_data = json.loads(result.stdout)
                    for file_path, blocks in radon_data.items():
                        for block in blocks:
                            if block.get("complexity", 0) > 10:
                                self.findings.append(
                                    {
                                        "tool": "radon",
                                        "file": file_path,
                                        "line": block.get("lineno"),
                                        "message": "High complexity "
                                        f"({block.get('complexity')}) "
                                        f"in {block.get('name')}",
                                        "severity": "warning",
                                    }
                                )
                except json.JSONDecodeError:
                    pass
        except FileNotFoundError:
            self.findings.append(
                {"tool": "radon", "message": "Radon not found", "severity": "error"}
            )

    def detect_architectural_violations(self, file_path: Path) -> None:
        """Detect architectural violations using AST/Regex."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception:
            return

        if "aptdata/core" in str(file_path) and re.search(
            r"import\s+pandas|from\s+pandas\s+import", content
        ):
            self.findings.append(
                {
                    "tool": "architecture",
                    "file": str(file_path),
                    "message": "Pandas import detected in core "
                    "framework (Coupling violation)",
                    "severity": "critical",
                }
            )

        try:
            tree = ast.parse(content, filename=str(file_path))
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    for arg in node.args.args:
                        if (
                            arg.annotation
                            and isinstance(arg.annotation, ast.Name)
                            and arg.annotation.id == "dict"
                            and (
                                "Component" in node.name
                                or "Flow" in node.name
                                or "execute" in node.name
                            )
                        ):
                            self.findings.append(
                                {
                                    "tool": "architecture",
                                    "file": str(file_path),
                                    "line": node.lineno,
                                    "message": "Pure dict used instead of Pydantic "
                                    f"model in {node.name} "
                                    "(Contract-First violation)",
                                    "severity": "critical",
                                }
                            )
        except SyntaxError:
            pass

    def validate_makefile_targets(self) -> None:
        """Ensure Makefile targets are documented."""
        makefile_path = self.root_dir / "Makefile"
        docs_dir = self.root_dir / "docs"

        if not makefile_path.exists():
            return

        content = makefile_path.read_text()
        targets = re.findall(r"^([a-zA-Z0-9_-]+):", content, re.MULTILINE)

        documented_targets = set()
        if docs_dir.exists():
            for md_file in docs_dir.rglob("*.md"):
                md_content = md_file.read_text(encoding="utf-8")
                for target in targets:
                    if target in md_content:
                        documented_targets.add(target)

        ignored = [
            "clean",
            "lint",
            "lint-fix",
            "test-cov",
            "test-unit",
            "test-integration",
            "test-e2e",
        ]
        for target in targets:
            if target not in documented_targets and target not in ignored:
                self.findings.append(
                    {
                        "tool": "makefile_audit",
                        "file": "Makefile",
                        "message": f"Makefile target '{target}' lacks "
                        "corresponding documentation in docs/",
                        "severity": "warning",
                    }
                )

    def validate_cli_commands(self) -> None:
        """Ensure CLI commands have --help and docs."""
        cli_dir = self.root_dir / "aptdata" / "cli"
        if not cli_dir.exists():
            return

        for py_file in cli_dir.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        is_command = any(
                            isinstance(d, ast.Call)
                            and isinstance(d.func, ast.Attribute)
                            and d.func.attr == "command"
                            for d in node.decorator_list
                        )
                        if is_command and not ast.get_docstring(node):
                            self.findings.append(
                                {
                                    "tool": "cli_audit",
                                    "file": str(py_file),
                                    "line": node.lineno,
                                    "message": f"CLI command '{node.name}' "
                                    "lacks a docstring for --help",
                                    "severity": "warning",
                                }
                            )
            except SyntaxError:
                pass

    def validate_missing_unit_tests(self, targets: list[str]) -> None:
        """Detect absence of unit tests for new/modified code."""
        tests_dir = self.root_dir / "tests"
        for t in targets:
            py_path = Path(t)
            if not py_path.is_file() or not str(py_path).endswith(".py"):
                continue

            # Heuristic for test detection
            if "aptdata" not in str(py_path):
                continue

            # e.g., aptdata/core/xyz.py -> tests/test_xyz.py or tests/core/test_xyz.py
            # Simple check if there's any file in tests/ with 'test_' + py_path.name
            test_name = f"test_{py_path.name}"
            test_exists = False
            if tests_dir.exists():
                for test_file in tests_dir.rglob("*.py"):
                    if test_file.name == test_name:
                        test_exists = True
                        break

            if (
                not test_exists
                and py_path.name != "__init__.py"
                and py_path.name != "app.py"
                and py_path.name != "scaffold.py"
            ):
                self.findings.append(
                    {
                        "tool": "test_audit",
                        "file": str(py_path),
                        "message": f"Missing unit tests for '{py_path.name}'. "
                        f"Expected to find '{test_name}' in tests/ directory.",
                        "severity": "warning",
                    }
                )
