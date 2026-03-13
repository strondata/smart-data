"""Automated code hygiene workflows for dead code and unused import reduction."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
import ast
import os
import urllib.error
import urllib.request
from typing import Any


def _load_docs() -> str:
    """Read all documentation content into memory once."""
    docs_dir = Path("docs")
    if not docs_dir.exists():
        return ""
    docs_content = []
    for md_file in docs_dir.rglob("*.md"):
        try:
            docs_content.append(md_file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return "\n".join(docs_content)


def run_code_hygiene(
    target_dir: str = "aptdata/", dry_run: bool = False
) -> list[dict[str, Any]]:
    """Run Vulture and Ruff to identify and optionally remove unused code.

    This function analyzes the Abstract Syntax Tree (AST) using Ruff and Vulture.
    Ruff fixes unused imports natively. Vulture identifies dead code.

    Results are returned as structured JSON lines for lineage/observability.

    Parameters
    ----------
    target_dir : str
        The directory to run hygiene against.
    dry_run : bool
        If True, only reports findings and does not modify files.

    Returns
    -------
    list[dict[str, Any]]
        A list of structural changes and issues identified.
    """
    target_path = Path(target_dir).resolve()
    reports = []

    # 1. Ruff: Unused Imports (F401)
    ruff_cmd = ["ruff", "check", "--select", "F401", target_dir]
    if not dry_run:
        ruff_cmd.append("--fix")

    try:
        ruff_result = subprocess.run(
            ruff_cmd, capture_output=True, text=True, check=False
        )
        if ruff_result.stdout:
            for line in ruff_result.stdout.splitlines():
                if "F401" in line:
                    reports.append(
                        {
                            "tool": "ruff",
                            "rule": "F401",
                            "action": "fixed" if not dry_run else "identified",
                            "message": line.strip(),
                            "path": str(target_path),
                        }
                    )
    except Exception as exc:  # noqa: BLE001
        reports.append({"tool": "ruff", "error": str(exc), "status": "failed"})

    # 2. Vulture: Dead Code + LLM Semantic Analysis
    docs_content = _load_docs()
    vulture_cmd = ["vulture", target_dir]
    try:
        vulture_result = subprocess.run(
            vulture_cmd, capture_output=True, text=True, check=False
        )
        if vulture_result.stdout:
            findings = []
            for line in vulture_result.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                # Extract filepath and line number to sort findings descending
                import re
                match = re.match(r"^(.+?):(\d+):", line)
                if match:
                    findings.append((match.group(1), int(match.group(2)), line))
                else:
                    findings.append(("", 0, line))

            # Process findings in reverse line order per file to prevent line shifts
            # Sort by filepath, then by line number descending
            findings.sort(key=lambda x: (x[0], -x[1]))

            for _, _, finding_line in findings:
                # Cross-reference with docs using LLM Semantic Analysis
                is_documented = _check_with_llm_if_documented(finding_line, docs_content)

                if is_documented:
                    reports.append(
                        {
                            "tool": "vulture",
                            "action": "ignored (documented)",
                            "message": finding_line,
                            "path": str(target_path),
                        }
                    )
                else:
                    removed = False
                    if not dry_run:
                        removed = _remove_dead_code_ast(finding_line)

                    if removed or dry_run:
                        reports.append(
                            {
                                "tool": "vulture",
                                "action": "removed" if removed else "identified",
                                "message": finding_line,
                                "path": str(target_path),
                            }
                        )
    except Exception as exc:  # noqa: BLE001
        reports.append({"tool": "vulture", "error": str(exc), "status": "failed"})

    return reports


def _check_with_llm_if_documented(vulture_finding: str, docs_content: str) -> bool:
    """Perform semantic analysis via an LLM to check if the code is documented."""
    import re

    match = re.search(r"unused \w+ '([^']+)'", vulture_finding)
    if not match:
        return False

    component_name = match.group(1)

    # Optional LLM Analysis using OpenAI API if token is provided
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key and docs_content:
        try:
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps({
                    "model": "gpt-4o-mini",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a code hygiene agent. "
                            "Reply exactly 'true' if the given component name is "
                            "semantically documented in the provided markdown texts, "
                            "else reply 'false'."
                        },
                        {
                            "role": "user",
                            "content": f"Component Name: {component_name}\n\n"
                            f"Documentation Excerpts: {docs_content[:10000]}"
                        }
                    ],
                    "temperature": 0.0,
                }).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}"
                },
            )
            with urllib.request.urlopen(req, timeout=10) as response:  # noqa: S310
                result = json.loads(response.read().decode("utf-8"))
                reply = result["choices"][0]["message"]["content"].strip().lower()
                return reply == "true"
        except Exception:  # noqa: BLE001
            pass  # Fallback to local regex if LLM fails

    # Fallback simulated semantic analysis
    if component_name in docs_content:
        return True

    return False


def _remove_dead_code_ast(vulture_finding: str) -> bool:
    """Parse Vulture output and safely remove dead code using the ast module.

    To preserve comments and avoid line-shifting, we parse the file to find the end
    line of the dead code, and comment out the body of functions/classes while
    inserting `pass`. For variables, we just comment out the line.
    """
    import re

    match = re.match(r"^(.+?):(\d+):\s+unused (\w+) '([^']+)'", vulture_finding)
    if not match:
        return False

    filepath = match.group(1)
    line_number = int(match.group(2))
    element_type = match.group(3)
    element_name = match.group(4)

    target_file = Path(filepath)
    if not target_file.exists():
        return False

    try:
        source_code = target_file.read_text(encoding="utf-8")
        tree = ast.parse(source_code)

        # Find the node to delete
        target_node = None
        for node in ast.walk(tree):
            if hasattr(node, "lineno") and node.lineno == line_number:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if node.name == element_name:
                        target_node = node
                        break
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == element_name:
                            target_node = node
                            break

        if not target_node:
            return False

        lines = source_code.splitlines()

        # For variables, comment out the exact line(s)
        if isinstance(target_node, ast.Assign):
            end_lineno = getattr(target_node, "end_lineno", target_node.lineno)
            for i in range(target_node.lineno - 1, end_lineno):
                lines[i] = f"# Removed by Code Hygiene Agent: {lines[i]}"
        else:
            # For Functions/Classes: preserve signature, comment out body, add pass
            body_start_line = target_node.body[0].lineno
            body_end_line = getattr(target_node, "end_lineno", body_start_line)

            # Determine indentation
            indent_match = re.match(r"^(\s*)", lines[body_start_line - 1])
            indent = indent_match.group(1) if indent_match else "    "

            # Add a 'pass' before the commented-out body to keep syntax valid
            lines.insert(body_start_line - 1, f"{indent}pass  # Inserted by Code Hygiene Agent")

            # Comment out the old body lines
            # Adjust range due to insertion
            for i in range(body_start_line, body_end_line + 1):
                lines[i] = f"# {lines[i]}"

        # Write back
        target_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True

    except Exception:  # noqa: BLE001
        pass

    return False


if __name__ == "__main__":
    results = run_code_hygiene()
    for res in results:
        print(json.dumps(res))
