"""Continuous Code Hygiene Scanner.

This module provides the core logic for identifying dead code, unused imports,
and obsolete components by combining static analysis (via ruff and vulture)
and semantic analysis (via LLM heuristics) against the documentation.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass
class HygieneFinding:
    """A single finding from the hygiene scanner."""

    file_path: str
    line_number: int
    rule_code: str
    message: str
    is_in_docs: bool

    def to_dict(self) -> dict:
        """Convert finding to dictionary."""
        return {
            "file_path": self.file_path,
            "line_number": self.line_number,
            "rule_code": self.rule_code,
            "message": self.message,
            "is_in_docs": self.is_in_docs,
        }


class SemanticAnalyzer:
    """Uses LLM to cross-reference dead code with documentation."""

    def __init__(self, docs_dir: Path) -> None:
        """Initialize the semantic analyzer."""
        self.docs_dir = docs_dir
        self._doc_texts: list[str] = []
        self._load_docs()
        self.api_key = os.getenv("OPENAI_API_KEY")

    def _load_docs(self) -> None:
        """Load all documentation text into memory."""
        if not self.docs_dir.exists():
            return
        for md_file in self.docs_dir.rglob("*.md"):
            try:
                self._doc_texts.append(md_file.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue

    def analyze(self, symbol: str, context: str) -> bool:
        """Analyze if the symbol is mentioned in docs using LLM or fallback."""
        if not self._doc_texts:
            return False

        if self.api_key:
            return self._analyze_llm(symbol, context)
        return self._analyze_fallback(symbol)

    def _analyze_fallback(self, symbol: str) -> bool:
        """Basic heuristic fallback when LLM is unavailable."""
        words = symbol.replace("'", " ").replace('"', " ").split()
        for word in words:
            if len(word) > 3 and any(word in text for text in self._doc_texts):
                return True
        return False

    def _analyze_llm(self, symbol: str, context: str) -> bool:
        """Use an LLM to perform semantic analysis."""
        prompt = (
            "Analyze the following code symbol that was flagged as dead code. "
            "Check if it's conceptually mentioned or documented in the "
            "following documentation fragments. Answer 'true' or 'false' only.\n\n"
            f"Symbol: {symbol}\nContext: {context}\nDocs: "
        )
        # To avoid blowing up tokens, we just send a truncated version
        # of docs or a few relevant snippets.
        docs_sample = "\\n".join(self._doc_texts)[:2000]
        prompt += docs_sample

        try:
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps(
                    {
                        "model": "gpt-4o-mini",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.0,
                    }
                ).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as response:  # noqa: S310
                result = json.loads(response.read().decode("utf-8"))
                content = result["choices"][0]["message"]["content"].strip().lower()
                return "true" in content
        except Exception:  # noqa: BLE001
            return self._analyze_fallback(symbol)


class CodeHygieneScanner:
    """Scanner that combines static analysis and doc heuristics."""

    def __init__(self, root_dir: Path | str = ".") -> None:
        """Initialize the scanner."""
        self.root_dir = Path(root_dir).resolve()
        self.docs_dir = self.root_dir / "docs"
        self.analyzer = SemanticAnalyzer(self.docs_dir)

    def _run_ruff(self) -> list[HygieneFinding]:
        """Run ruff to find unused imports and variables."""
        findings: list[HygieneFinding] = []
        cmd = [
            "ruff",
            "check",
            "--format=json",
            "--select=F401,F841",
            str(self.root_dir),
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=False
            )
            if not result.stdout.strip():
                return []

            data = json.loads(result.stdout)
            for item in data:
                file_path = item.get("filename", "")
                try:
                    rel_path = str(Path(file_path).relative_to(self.root_dir))
                except ValueError:
                    rel_path = file_path

                line_num = item.get("location", {}).get("row", 0)
                rule = item.get("rule", {}).get("code", "UNKNOWN")
                message = item.get("message", "")

                # For simple unused variables/imports, we use the message as symbol
                is_in_docs = self.analyzer.analyze(message, "ruff finding")

                findings.append(
                    HygieneFinding(
                        file_path=rel_path,
                        line_number=line_num,
                        rule_code=f"ruff:{rule}",
                        message=message,
                        is_in_docs=is_in_docs,
                    )
                )
        except (subprocess.SubprocessError, FileNotFoundError, json.JSONDecodeError):
            pass

        return findings

    def _run_vulture(self) -> list[HygieneFinding]:
        """Run vulture to find dead classes and methods."""
        findings: list[HygieneFinding] = []
        # Target the aptdata source and tests directory for vulture
        cmd = ["vulture", "aptdata/", "tests/"]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, cwd=self.root_dir, check=False
            )
            # Vulture outputs lines like:
            # path/to/file.py:123: unused function 'my_func' (60% confidence)
            pattern = re.compile(
                r"^(?P<file>.+):(?P<line>\d+): "
                r"(?P<msg>unused (?P<type>\w+) '(?P<name>[^']+)' "
                r"\(\d+% confidence\))$"
            )

            for line in result.stdout.splitlines():
                match = pattern.match(line.strip())
                if match:
                    file_path = match.group("file")
                    line_num = int(match.group("line"))
                    msg = match.group("msg")
                    symbol_name = match.group("name")

                    is_in_docs = self.analyzer.analyze(
                        symbol_name, f"vulture finding: {msg}"
                    )

                    findings.append(
                        HygieneFinding(
                            file_path=file_path,
                            line_number=line_num,
                            rule_code="vulture:dead_code",
                            message=msg,
                            is_in_docs=is_in_docs,
                        )
                    )
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

        return findings

    def scan(self) -> list[HygieneFinding]:
        """Run static analysis and semantic cross-referencing."""
        findings = self._run_ruff()
        findings.extend(self._run_vulture())
        return findings


def scan_codebase(root_dir: str | Path = ".") -> list[dict]:
    """Execute the hygiene scan and return dictionary records."""
    scanner = CodeHygieneScanner(root_dir)
    return [finding.to_dict() for finding in scanner.scan()]
