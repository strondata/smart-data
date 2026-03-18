import ast
import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Any, List, Dict

logger = logging.getLogger(__name__)

class DeadCodeVisitor(ast.NodeVisitor):
    def __init__(self, target_names: List[str]):
        self.target_names = target_names
        self.to_remove: List[tuple[int, int]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name in self.target_names:
            self.to_remove.append((node.lineno, node.end_lineno))
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if node.name in self.target_names:
            self.to_remove.append((node.lineno, node.end_lineno))
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name in self.target_names:
                self.to_remove.append((node.lineno, node.end_lineno))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name in self.target_names:
                self.to_remove.append((node.lineno, node.end_lineno))
        self.generic_visit(node)

class QAAgent:
    """QA/DX Agent for continuous code hygiene and structural validation."""

    def __init__(self, root_dir: Path | None = None) -> None:
        self.root_dir = root_dir or Path.cwd()

    def _cross_reference_docs(self, name: str) -> bool:
        """Simulate LLM semantic cross-referencing with docs/.
        Returns True if the component is documented (should NOT be removed).
        """
        docs_dir = self.root_dir / "docs"
        if not docs_dir.exists():
            return False

        for md_file in docs_dir.rglob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
                if name in content:
                    return True
            except Exception:
                pass
        return False

    def _remove_dead_code(self, filepath: Path, targets: List[str]) -> bool:
        """Removes dead code using AST traversal and precise line nullification."""
        try:
            source = filepath.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(filepath))
        except SyntaxError:
            return False

        visitor = DeadCodeVisitor(targets)
        visitor.visit(tree)

        if not visitor.to_remove:
            return False

        lines = source.splitlines()
        # Replace the target lines with None to preserve indices
        for start_line, end_line in visitor.to_remove:
            # AST lineno is 1-indexed
            if end_line is None:
                end_line = start_line
            for i in range(start_line - 1, end_line):
                if 0 <= i < len(lines):
                    lines[i] = None  # type: ignore

        new_source = "\n".join(line for line in lines if line is not None) + "\n"
        filepath.write_text(new_source, encoding="utf-8")
        return True

    def run_clean(self, json_mode: bool = False) -> List[Dict[str, Any]]:
        """Run dead code detection and clean up using Vulture."""
        reports = []
        try:
            # Run vulture to detect dead code
            result = subprocess.run(
                ["vulture", "aptdata", "examples", "--min-confidence", "80"],
                capture_output=True,
                text=True,
                cwd=self.root_dir
            )

            # Vulture output format: path/to/file.py:line: unused function 'name' (confidence)
            pattern = re.compile(r"^(.*?):(\d+): unused (.*?) '(.*?)' \(\d+%\)$")
            findings_by_file: Dict[Path, List[str]] = {}

            for line in result.stdout.splitlines() + result.stderr.splitlines():
                match = pattern.match(line)
                if match:
                    filepath = self.root_dir / match.group(1)
                    name = match.group(4)
                    if not self._cross_reference_docs(name):
                        if filepath not in findings_by_file:
                            findings_by_file[filepath] = []
                        findings_by_file[filepath].append(name)
                        reports.append({
                            "event": "qa.clean.finding",
                            "file": str(filepath),
                            "target": name,
                            "action": "removed"
                        })

            # Apply removals
            for filepath, targets in findings_by_file.items():
                if filepath.exists():
                    self._remove_dead_code(filepath, targets)

        except FileNotFoundError:
            # Vulture not installed, fallback or skip
            reports.append({
                "event": "qa.clean.error",
                "error": "Vulture is not installed."
            })

        if json_mode:
            for report in reports:
                print(json.dumps(report), flush=True)

        return reports

    def run_lint(self, deep: bool = False, json_mode: bool = False, changed_files: List[str] | None = None) -> List[Dict[str, Any]]:
        """Run linting (ruff, mypy, pydocstyle, radon) and architectural validation."""
        reports = []
        tools = ["ruff", "mypy", "pydocstyle", "radon"]

        for tool in tools:
            try:
                # Basic mock/stub for linting execution
                result = subprocess.run(
                    [tool, "check", "."] if tool == "ruff" else [tool, "."],
                    capture_output=True,
                    text=True,
                    cwd=self.root_dir,
                    check=False
                )
                if result.returncode != 0:
                    reports.append({
                        "event": "qa.lint.failure",
                        "tool": tool,
                        "output": result.stdout or result.stderr
                    })
            except FileNotFoundError:
                pass

        if json_mode:
            for report in reports:
                print(json.dumps(report), flush=True)

        return reports
