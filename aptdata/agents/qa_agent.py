from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

class QAAgent:
    """Autonomous agent for QA and DX in aptdata.

    Orchestrates static analysis tools and performs semantic checks.
    """

    def __init__(self, directory: str | Path = ".") -> None:
        self.directory = Path(directory).resolve()
        self.findings: list[dict[str, Any]] = []

    def run_static_analysis(self) -> None:
        """Run standard fast static analysis tools."""
        tools = ["ruff", "mypy", "pydocstyle"]
        for tool in tools:
            try:
                result = subprocess.run(
                    [tool, str(self.directory)],
                    check=False,
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    self.findings.append({
                        "event": "lint.error",
                        "type": tool,
                        "message": result.stdout.strip() or result.stderr.strip(),
                        "file": str(self.directory),
                        "critical": False,
                    })
            except FileNotFoundError:
                pass

    def check_makefile_commands(self) -> None:
        """Check for orphaned Makefile commands not in docs."""
        makefile = self.directory / "Makefile"
        if not makefile.exists():
            return

        import re
        targets = []
        for line in makefile.read_text().splitlines():
            m = re.match(r"^([a-zA-Z0-9_-]+):", line)
            if m:
                targets.append(m.group(1))

        # For each target, ensure it's documented.
        docs_dir = self.directory / "docs"
        if docs_dir.exists():
            all_doc_content = ""
            for md_file in docs_dir.rglob("*.md"):
                all_doc_content += md_file.read_text(errors='ignore')

            for target in targets:
                if target not in all_doc_content:
                    self.findings.append({
                        "event": "lint.error",
                        "type": "makefile",
                        "message": f"Makefile target '{target}' is orphaned (not found in docs/).",
                        "file": "Makefile",
                        "critical": False,
                    })

    def evaluate_semantics(self) -> None:
        """Use LLM (mocked here) for complex semantic checks like docstrings."""
        # Check core abstractions for missing/poor docstrings (mock implementation)
        core_files = [
            self.directory / "aptdata" / "core" / "system.py",
            self.directory / "aptdata" / "core" / "base.py"
        ]
        for f in core_files:
            if f.exists():
                content = f.read_text()
                if 'def ' in content and '"""' not in content:
                    self.findings.append({
                        "event": "lint.error",
                        "type": "docstring",
                        "message": f"Missing docstrings in core abstraction: {f.name}",
                        "file": str(f),
                        "critical": False,
                    })

    def check_test_coverage(self, changed_files: list[str]) -> None:
        """Check that new code has corresponding tests."""
        for file in changed_files:
            if file.startswith("aptdata/") and file.endswith(".py"):
                # Basic check: is there a test file?
                test_file = self.directory / "tests" / f"test_{Path(file).name}"
                if not test_file.exists():
                    self.findings.append({
                        "event": "lint.error",
                        "type": "coverage",
                        "message": f"Missing unit test for {file}",
                        "file": file,
                        "critical": True,
                    })

    def check_architectural_rules(self) -> None:
        """Check for critical architectural violations like Pandas in Core."""
        core_dir = self.directory / "aptdata" / "core"
        if core_dir.exists():
            for py_file in core_dir.rglob("*.py"):
                if "import pandas" in py_file.read_text() or "from pandas" in py_file.read_text():
                    self.findings.append({
                        "event": "lint.error",
                        "type": "architecture",
                        "message": f"Critical architectural violation: Pandas coupled in Core file {py_file.name}",
                        "file": str(py_file),
                        "critical": True,
                    })

    def run_all(self) -> list[dict[str, Any]]:
        self.check_makefile_commands()
        self.evaluate_semantics()
        self.check_architectural_rules()
        return self.findings
