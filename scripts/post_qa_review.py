#!/usr/bin/env python3
"""Script to parse QAAgent JSON output and post a review on GitHub PR."""

import json
import os
import subprocess
import sys


def create_qa_fix_pr(report_data):
    """Automatically applies ruff fixes and creates a PR."""
    print("Attempting to auto-fix styling issues in a dedicated branch...")
    try:
        # We assume we are in a git repository
        branch_name = "qa-fixes"
        subprocess.run(["git", "checkout", "-b", branch_name], check=True, capture_output=True)
        subprocess.run(["poetry", "run", "ruff", "check", "--fix", "aptdata/", "tests/"], check=False, capture_output=True)

        # Check if there are changes
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if not status.stdout.strip():
            print("No auto-fixes could be applied.")
            subprocess.run(["git", "checkout", "-"], check=True, capture_output=True)
            return

        subprocess.run(["git", "add", "."], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "chore(qa): auto-fix formatting and styling (ruff)"], check=True, capture_output=True)

        # In a real scenario we would push to remote and open a PR:
        # subprocess.run(["git", "push", "origin", branch_name], check=True)
        # requests.post(f"https://api.github.com/repos/{owner}/{repo}/pulls", json={...})

        print(f"Created branch '{branch_name}' with auto-fixes. (Simulated push & PR creation).")

        # Switch back to the original branch
        subprocess.run(["git", "checkout", "-"], check=True, capture_output=True)

    except Exception as e:
        print(f"Failed to create auto-fix PR: {e}")


def main():
    if not os.environ.get("GITHUB_TOKEN"):
        print("No GITHUB_TOKEN set. Skipping actual PR comment via API.")

    pr_number = os.environ.get("PR_NUMBER")
    if not pr_number:
        print("No PR_NUMBER set. Mocking PR number.")
        pr_number = "1"

    report_path = "qa_report.json"
    if not os.path.exists(report_path):
        print(f"Report file {report_path} not found.")
        sys.exit(0)

    try:
        with open(report_path, encoding="utf-8") as f:
            # The agent might emit multiple JSON lines, we want the one with 'issues'
            report_data = None
            for line in f:
                data = json.loads(line)
                if "issues" in data:
                    report_data = data
                    break

        if not report_data:
            print("Could not find QA report data in JSON.")
            sys.exit(0)

        score = report_data.get("score", 0)
        passed = report_data.get("passed", False)
        issues = report_data.get("issues", [])

        status_icon = "✅" if passed else "❌"
        body = f"## {status_icon} QA/DX Agent Review\n\n"
        body += f"**Score:** {score}/100\n"
        body += f"**Status:** {'Passed' if passed else 'Failed'}\n\n"

        if not issues:
            body += "No issues found! Great job. 🎉\n"
        else:
            body += "### Issues Found\n"
            body += "| Rule | Severity | File | Message |\n"
            body += "|---|---|---|---|\n"
            for issue in issues:
                file_loc = issue.get('file', 'unknown')
                if issue.get('line'):
                    file_loc += f":{issue['line']}"
                body += f"| {issue.get('rule_id')} | {issue.get('severity')} | `{file_loc}` | {issue.get('message')} |\n"

        # Simulating GitHub API call
        print("--- POSTING TO GITHUB API ---")
        print(f"POST /repos/owner/repo/issues/{pr_number}/comments")
        print(body)
        print("-----------------------------")

        # Create auto-fix PR for formatting/docstrings
        has_ruff_issues = any(i.get("rule_id") == "QA-EXT-RUFF" for i in issues)
        if has_ruff_issues or not passed:
            create_qa_fix_pr(report_data)

        has_critical = any(i.get("severity") == "error" for i in issues)
        if has_critical:
            print("Critical architectural violations found. Failing the step.")
            sys.exit(1)

    except Exception as e:
        print(f"Error parsing QA report: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
