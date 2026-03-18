"""Agent for QA and DX analysis.

Analyzes the codebase for stylistic, typing, and architectural rule
violations using standard tools and custom AST inspection.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


class QAAgent:
    """Agent orchestrating QA and Developer Experience (DX) analysis.

    Uses native tools (ruff, mypy, pydocstyle) for static analysis, and AST
    parsing for architectural constraints (e.g. Contract-First violations,
    Pandas imports in core).
    """

    def __init__(self, root_dir: Path | str = ".") -> None:
        self.root_dir = Path(root_dir).resolve()

    def run_ruff(self, files: list[str]) -> list[dict[str, Any]]:
        """Run ruff and return findings."""
        if not files:
            return []
        try:
            cmd = ["ruff", "check", "--output-format", "json"] + files
            result = subprocess.run(
                cmd,
                cwd=self.root_dir,
                capture_output=True,
                text=True,
                check=False,
            )
            if not result.stdout.strip():
                return []
            findings = json.loads(result.stdout)
            return [
                {
                    "tool": "ruff",
                    "file": f.get("filename", ""),
                    "line": f.get("location", {}).get("row", 0),
                    "code": f.get("code", "E"),
                    "message": f.get("message", ""),
                    "severity": "warning",
                    "critical": False,
                }
                for f in findings
            ]
        except Exception as exc:  # noqa: BLE001
            return [
                {
                    "tool": "ruff",
                    "file": "",
                    "line": 0,
                    "code": "ERROR",
                    "message": f"Failed to run ruff: {exc}",
                    "severity": "error",
                    "critical": False,
                }
            ]

    def run_mypy(self, files: list[str]) -> list[dict[str, Any]]:
        """Run mypy and return findings."""
        if not files:
            return []
        try:
            # Note: without --output-json (which requires a plugin or parsing stdout),
            # we do a very basic parse, or just run it with --show-error-codes
            cmd = ["mypy", "--show-error-codes"] + files
            result = subprocess.run(
                cmd,
                cwd=self.root_dir,
                capture_output=True,
                text=True,
                check=False,
            )
            findings = []
            for line in result.stdout.splitlines():
                if ": error:" in line:
                    parts = line.split(":")
                    if len(parts) >= 4:
                        file_path = parts[0].strip()
                        line_num = int(parts[1].strip()) if parts[1].strip().isdigit() else 0
                        message = ":".join(parts[3:]).strip()
                        code = "type-error"
                        if "[" in message and "]" in message:
                            code = message.split("[")[-1].split("]")[0]
                            message = message[: message.rfind("[")].strip()
                        findings.append(
                            {
                                "tool": "mypy",
                                "file": file_path,
                                "line": line_num,
                                "code": code,
                                "message": message,
                                "severity": "error",
                                "critical": False,
                            }
                        )
            return findings
        except Exception as exc:  # noqa: BLE001
            return [
                {
                    "tool": "mypy",
                    "file": "",
                    "line": 0,
                    "code": "ERROR",
                    "message": f"Failed to run mypy: {exc}",
                    "severity": "error",
                    "critical": False,
                }
            ]

    def check_architectural_rules(self, files: list[str]) -> list[dict[str, Any]]:
        """Use AST parsing to enforce architectural invariants."""
        findings = []

        for file_path in files:
            full_path = self.root_dir / file_path
            if not full_path.exists() or not full_path.is_file():
                continue
            if not file_path.endswith(".py"):
                continue

            try:
                content = full_path.read_text(encoding="utf-8")
                tree = ast.parse(content, filename=str(full_path))
            except Exception:  # noqa: BLE001
                continue

            # Rule: No pandas imports in core (aptdata/core/...)
            is_core = "aptdata/core/" in file_path.replace("\\", "/")
            if is_core:
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name.split(".")[0] == "pandas":
                                findings.append(
                                    {
                                        "tool": "ast",
                                        "file": file_path,
                                        "line": node.lineno,
                                        "code": "ARCH001",
                                        "message": "Pandas import in core module violates architecture.",
                                        "severity": "error",
                                        "critical": True,
                                    }
                                )
                    elif isinstance(node, ast.ImportFrom):
                        if node.module and node.module.split(".")[0] == "pandas":
                            findings.append(
                                {
                                    "tool": "ast",
                                    "file": file_path,
                                    "line": node.lineno,
                                    "code": "ARCH001",
                                    "message": "Pandas import in core module violates architecture.",
                                    "severity": "error",
                                    "critical": True,
                                }
                            )

            # Rule: Contract-First violations (e.g. returning dict in BaseComponent subclasses)
            # This is a basic heuristic check for type hints
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # Check if it's a method that returns dict or list instead of a Model/Dataset
                    if node.returns and isinstance(node.returns, ast.Name):
                        if node.returns.id in ("dict", "list", "Dict", "List"):
                            findings.append(
                                {
                                    "tool": "ast",
                                    "file": file_path,
                                    "line": node.lineno,
                                    "code": "ARCH002",
                                    "message": f"Method '{node.name}' uses pure '{node.returns.id}' type hint instead of Contract-First Pydantic/Dataset.",
                                    "severity": "warning",
                                    "critical": False,
                                }
                            )

        return findings

    def check_docstrings(self, files: list[str]) -> list[dict[str, Any]]:
        """Run pydocstyle/AST heuristic to check docstring presence."""
        findings = []
        for file_path in files:
            full_path = self.root_dir / file_path
            if not full_path.exists() or not full_path.is_file() or not file_path.endswith(".py"):
                continue

            try:
                content = full_path.read_text(encoding="utf-8")
                tree = ast.parse(content, filename=str(full_path))
            except Exception:  # noqa: BLE001
                continue

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    docstring = ast.get_docstring(node)
                    if not docstring:
                        # Skip private and dunder methods
                        if node.name.startswith("_") and not node.name.startswith("__"):
                            continue
                        findings.append(
                            {
                                "tool": "docstring",
                                "file": file_path,
                                "line": node.lineno,
                                "code": "DOC001",
                                "message": f"Missing docstring in public {'class' if isinstance(node, ast.ClassDef) else 'function'} '{node.name}'.",
                                "severity": "warning",
                                "critical": False,
                            }
                        )
                    elif isinstance(node, ast.FunctionDef):
                        # Simple heuristic to check if docstring matches signature
                        for arg in node.args.args:
                            if arg.arg != "self" and arg.arg not in docstring:
                                findings.append(
                                    {
                                        "tool": "docstring",
                                        "file": file_path,
                                        "line": node.lineno,
                                        "code": "DOC002",
                                        "message": f"Argument '{arg.arg}' in function '{node.name}' is not documented in the docstring.",
                                        "severity": "warning",
                                        "critical": False,
                                    }
                                )
        return findings

    def check_complexity(self, files: list[str]) -> list[dict[str, Any]]:
        """Run radon to check cyclomatic complexity."""
        if not files:
            return []
        try:
            cmd = ["radon", "cc", "-j"] + files
            result = subprocess.run(
                cmd,
                cwd=self.root_dir,
                capture_output=True,
                text=True,
                check=False,
            )
            findings = []
            if result.stdout.strip():
                data = json.loads(result.stdout)
                for file_path, blocks in data.items():
                    for block in blocks:
                        if block.get("complexity", 0) > 10:  # Threshold for warning
                            findings.append(
                                {
                                    "tool": "complexity",
                                    "file": file_path,
                                    "line": block.get("lineno", 0),
                                    "code": "C901",
                                    "message": f"Cyclomatic complexity of {block.get('name')} is {block.get('complexity')} (threshold: 10)",
                                    "severity": "warning",
                                    "critical": False,
                                }
                            )
            return findings
        except Exception as exc:  # noqa: BLE001
            return [
                {
                    "tool": "complexity",
                    "file": "",
                    "line": 0,
                    "code": "ERROR",
                    "message": f"Failed to run radon: {exc}",
                    "severity": "warning",
                    "critical": False,
                }
            ]

    def evaluate_docstring_semantics(self, docstring: str, code: str) -> Optional[str]:
        """Use an LLM to evaluate if the docstring accurately describes the code.

        This is a placeholder for actual LLM integration (e.g., calling OpenAI API).
        """
        # Placeholder logic: if docstring is too short, warn about semantic quality.
        if len(docstring.split()) < 3:
            return "Docstring appears semantically weak or too brief."
        return None

    def check_missing_tests(self, changed_files: list[str] | None) -> list[dict[str, Any]]:
        """Check if new/modified code has corresponding tests."""
        findings = []
        if changed_files is None:
            return findings

        for file_path in changed_files:
            # We only care about application python code, not tests themselves
            if not file_path.endswith(".py") or file_path.startswith("tests/"):
                continue

            # Heuristic: file `aptdata/core/system.py` should have `tests/test_system.py` or similar
            filename = Path(file_path).name
            expected_test_name = f"test_{filename}"

            # Simple recursive search for the test file in tests/ dir
            test_dir = self.root_dir / "tests"
            if test_dir.exists():
                test_files = list(test_dir.rglob(expected_test_name))
                if not test_files:
                    findings.append(
                        {
                            "tool": "qa",
                            "file": file_path,
                            "line": 0,
                            "code": "TEST001",
                            "message": f"Missing unit test for {file_path}. Expected {expected_test_name}.",
                            "severity": "warning",
                            "critical": False,
                        }
                    )
        return findings

    def check_cli_and_makefile(self) -> list[dict[str, Any]]:
        """Verify CLI commands and Makefile targets are documented."""
        findings = []

        # Check Makefile
        makefile_path = self.root_dir / "Makefile"
        if makefile_path.exists():
            content = makefile_path.read_text(encoding="utf-8")
            # A simple heuristic: check if targets are mentioned in docs/ (e.g. index.md or diys.md)
            # Or if they have comments above them. Let's just do a basic parsing.
            targets = re.findall(r'^([a-zA-Z0-9_-]+):', content, re.MULTILINE)

            docs_content = ""
            docs_dir = self.root_dir / "docs"
            if docs_dir.exists():
                for doc_file in docs_dir.rglob("*.md"):
                    docs_content += doc_file.read_text(encoding="utf-8")
            readme_path = self.root_dir / "README.md"
            if readme_path.exists():
                docs_content += readme_path.read_text(encoding="utf-8")

            for target in targets:
                if target not in ["install", "test", "test-cov", "test-unit", "test-integration", "test-e2e", "lint", "clean", "docs", "docs-serve", "lint-fix"]:
                    # If target not documented in docs/ or README.md
                    if f"make {target}" not in docs_content:
                        findings.append(
                            {
                                "tool": "qa",
                                "file": "Makefile",
                                "line": 0,
                                "code": "MK001",
                                "message": f"Makefile target '{target}' is orphaned (not documented).",
                                "severity": "warning",
                                "critical": False,
                            }
                        )

        # Check CLI Commands for --help/docstrings
        cli_dir = self.root_dir / "aptdata" / "cli"
        if cli_dir.exists():
            for file_path in cli_dir.rglob("*.py"):
                try:
                    content = file_path.read_text(encoding="utf-8")
                    tree = ast.parse(content, filename=str(file_path))
                    for node in ast.walk(tree):
                        if isinstance(node, ast.FunctionDef):
                            # Check if decorated with @app.command or similar
                            is_command = False
                            for dec in node.decorator_list:
                                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                                    if dec.func.attr == "command":
                                        is_command = True
                            if is_command:
                                docstring = ast.get_docstring(node)
                                if not docstring:
                                    findings.append(
                                        {
                                            "tool": "qa",
                                            "file": str(file_path.relative_to(self.root_dir)),
                                            "line": node.lineno,
                                            "code": "CLI001",
                                            "message": f"CLI command '{node.name}' lacks a docstring (used for --help).",
                                            "severity": "warning",
                                            "critical": False,
                                        }
                                    )
                except Exception:  # noqa: BLE001
                    continue

        return findings

    def lint(
        self,
        deep: bool = False,
        changed_files: list[str] | None = None,
    ) -> dict[str, Any]:
        """Perform QA/DX analysis and return a structured report.

        Parameters
        ----------
        deep:
            If true, run deeper static analysis like mypy and architectural rules.
        changed_files:
            List of modified file paths to restrict the check.

        Returns
        -------
        dict
            Structured JSON report with keys ``status``, ``findings``, etc.
        """
        if changed_files is not None:
            files_to_check = changed_files
        else:
            files_to_check = [
                str(p.relative_to(self.root_dir))
                for p in self.root_dir.rglob("*.py")
                if "venv" not in p.parts and ".venv" not in p.parts
            ]

        findings = []

        findings.extend(self.run_ruff(files_to_check))
        findings.extend(self.check_docstrings(files_to_check))

        if deep:
            findings.extend(self.run_mypy(files_to_check))
            findings.extend(self.check_architectural_rules(files_to_check))
            findings.extend(self.check_complexity(files_to_check))
            findings.extend(self.check_missing_tests(changed_files))
            findings.extend(self.check_cli_and_makefile())

        has_critical = any(f.get("critical", False) for f in findings)
        status = "failed" if has_critical else "passed"

        report = {
            "status": status,
            "checked_files_count": len(files_to_check),
            "findings": findings,
            "metrics": {
                "total_issues": len(findings),
                "critical_issues": sum(1 for f in findings if f.get("critical", False)),
                "warnings": sum(1 for f in findings if not f.get("critical", False)),
            },
        }

        return report

__all__ = ["QAAgent"]
