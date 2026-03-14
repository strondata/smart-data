"""Code Hygiene Agent for removing dead code and unused imports.

This agent orchestrates native tools like ruff and vulture to find
dead code, cross-references findings with the docs/ directory via an LLM,
and removes the genuinely unused code using Regex to preserve formatting.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from aptdata.cli.rendering.console import SmartConsole

# Mock implementation or optional fallback if OpenAI is not present.
try:
    from openai import OpenAI

    _HAS_OPENAI = True
except ImportError:
    _HAS_OPENAI = False


def _get_markdown_docs(docs_dir: Path) -> str:
    """Read all markdown files in docs/ and return their concatenated content."""
    content = []
    if docs_dir.exists() and docs_dir.is_dir():
        for md_file in docs_dir.rglob("*.md"):
            try:
                text = md_file.read_text(encoding="utf-8")
                content.append(f"--- {md_file.name} ---\n{text}")
            except Exception:
                pass
    return "\n\n".join(content)


def _run_vulture(target_dir: str) -> list[dict[str, Any]]:
    """Run Vulture and return parsed findings."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "vulture", target_dir],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return []

    findings = []
    # Vulture output format: file:line: message
    pattern = re.compile(r"^(.*?):(\d+):\s+(.*)$")
    for line in result.stdout.splitlines():
        match = pattern.match(line)
        if match:
            findings.append(
                {
                    "file": match.group(1),
                    "line": int(match.group(2)),
                    "message": match.group(3),
                }
            )
    return findings


def _run_ruff_fix(target_dir: str) -> None:
    """Run Ruff to fix unused imports automatically."""
    try:
        subprocess.run(
            [sys.executable, "-m", "ruff", "check", "--fix", target_dir],
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        pass


def _cross_reference_with_llm(findings: list[dict[str, Any]], docs_content: str) -> list[dict[str, Any]]:
    """Use an LLM to cross-reference Vulture findings with the documentation."""
    if not _HAS_OPENAI or not docs_content.strip() or not os.environ.get("OPENAI_API_KEY"):
        # Fallback: simple text search if LLM or API key is unavailable.
        truly_unused = []
        for finding in findings:
            # Try to extract the name from message: e.g. "unused class 'BaseComponent'"
            name_match = re.search(r"'([^']+)'", finding["message"])
            if name_match:
                name = name_match.group(1)
                if name not in docs_content:
                    truly_unused.append(finding)
            else:
                truly_unused.append(finding)
        return truly_unused

    client = OpenAI()

    # Build prompt
    findings_text = json.dumps(findings, indent=2)
    prompt = (
        "You are a Tech Lead assisting with code hygiene.\n"
        "Below is a list of potential dead code findings reported by Vulture (in JSON format), "
        "and the content of our documentation files.\n"
        "Your task is to identify which findings are ACTUALLY safe to remove. "
        "If a class, function, or method is mentioned or documented in the documentation text, "
        "it is NOT safe to remove.\n\n"
        "Respond ONLY with a valid JSON array containing the subset of the findings that are "
        "SAFE to remove. Do not include any other text.\n\n"
        f"Findings:\n{findings_text}\n\n"
        f"Documentation:\n{docs_content[:15000]}"  # Truncate to avoid massive tokens
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        content = response.choices[0].message.content or "[]"
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]

        parsed = json.loads(content)
        if isinstance(parsed, list):
            return parsed
        return []
    except Exception:
        # Fallback to returning all findings on error
        return findings


import ast

def _find_node_bounds(source: str, line_no: int) -> tuple[int, int] | None:
    """Find the exact start and end line of the AST node containing line_no."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    class NodeVisitor(ast.NodeVisitor):
        def __init__(self, target_line: int) -> None:
            self.target_line = target_line
            self.bounds = None

        def generic_visit(self, node: ast.AST) -> None:
            if hasattr(node, "lineno") and hasattr(node, "end_lineno"):
                # If target_line falls exactly on the start of this node
                # For inner functions or variables, we want the most specific node,
                # so we allow overriding self.bounds if we drill down and find
                # a more precise node that starts on target_line.
                if node.lineno == self.target_line:
                    self.bounds = (node.lineno, node.end_lineno)
            super().generic_visit(node)

    visitor = NodeVisitor(line_no)
    visitor.visit(tree)
    return visitor.bounds


def _remove_dead_code(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove dead code from files using reverse-line-order string manipulation."""
    # Group by file
    from collections import defaultdict

    removals_by_file = defaultdict(list)
    for f in findings:
        removals_by_file[f["file"]].append(f)

    removed_items = []

    for file_path, items in removals_by_file.items():
        if not os.path.exists(file_path):
            continue

        with open(file_path, encoding="utf-8") as f:
            source = f.read()

        lines = source.splitlines(keepends=True)

        # Determine actual bounds for each finding using AST
        bounds_to_remove = []
        for item in items:
            bounds = _find_node_bounds(source, item["line"])
            if bounds:
                start_line, end_line = bounds
                bounds_to_remove.append((start_line, end_line, item))

        for start_line, end_line, item in bounds_to_remove:
            start_idx = start_line - 1
            end_idx = end_line

            if start_idx < 0 or start_idx >= len(lines):
                continue

            # Filter out lines that have already been marked for removal (set to None)
            current_block = [l for l in lines[start_idx:end_idx] if l is not None]
            removed_block = "".join(current_block).strip()

            if not removed_block:
                continue

            # Remove the lines by setting them to None to preserve indices for overlapping bounds
            for i in range(start_idx, end_idx):
                lines[i] = None

            removed_items.append(
                {
                    "file": file_path,
                    "line": item["line"],
                    "removed": removed_block,
                    "reason": item["message"],
                }
            )

        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines([l for l in lines if l is not None])

    return removed_items


def run_code_hygiene(deep: bool = False, json_mode: bool = False) -> dict[str, Any]:
    """Execute code hygiene tasks: unused imports and dead code removal.

    Parameters
    ----------
    deep : bool
        If True, run semantic cross-referencing with documentation.
    json_mode : bool
        If True, emit outputs as JSON.

    Returns
    -------
    dict
        A dictionary containing the report of removed items.
    """
    console = SmartConsole(json_mode=json_mode)
    target_dir = "aptdata/"
    docs_dir = Path("docs/")

    if not json_mode:
        console.info("Starting Code Hygiene Agent...")

    # 1. Auto-fix unused imports and formatting using Ruff
    _run_ruff_fix(target_dir)

    # 2. Run Vulture to find dead code
    if not json_mode:
        console.info("Running Vulture analysis...")
    findings = _run_vulture(target_dir)

    # 3. Cross-reference with docs
    if deep and findings:
        if not json_mode:
            console.info("Cross-referencing findings with documentation (Semantic Analysis)...")
        docs_content = _get_markdown_docs(docs_dir)
        findings = _cross_reference_with_llm(findings, docs_content)

    # 4. Programmatically remove dead code
    if not json_mode:
        console.info(f"Removing {len(findings)} unused items...")

    removed_items = _remove_dead_code(findings)

    report = {
        "event": "code_hygiene.completed",
        "deep": deep,
        "removed_items": removed_items,
        "count": len(removed_items),
    }

    if json_mode:
        print(json.dumps(report), flush=True)
    else:
        console.success(f"Code Hygiene complete. Removed {len(removed_items)} items.")

    return report
