"""Turn a GitHub issue on the target repo into a pull request using the crew.

Usage:
    python issue_to_pr.py 1 --dry-run   # run the crew locally, no push, no PR
    python issue_to_pr.py 1             # run the crew, push a branch, open a PR
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import github_client as gh

ROOT = Path(__file__).resolve().parent
AGENT_SCRIPT = ROOT / "phase3_crew.py"
CLONE_URL = f"https://github.com/{gh.REPO_NAME}.git"
AGENT_TIMEOUT = 1800


def git(*args, cwd):
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )


def run_crew(workspace: Path, task: str) -> dict:
    env = dict(
        os.environ,
        WORKSPACE=str(workspace),
        PYTHONIOENCODING="utf-8",
        PYTHONUTF8="1",
    )
    proc = subprocess.run(
        [sys.executable, str(AGENT_SCRIPT), task],
        cwd=ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=AGENT_TIMEOUT,
    )
    if "DAILY_TOKEN_LIMIT" in proc.stdout:
        raise SystemExit("Daily token limit reached. Try again tomorrow.")
    for line in proc.stdout.splitlines():
        if line.startswith("RESULT_JSON "):
            return json.loads(line[len("RESULT_JSON "):])
    tail = (proc.stderr or proc.stdout)[-300:]
    raise SystemExit(f"Crew produced no result (exit {proc.returncode}): {tail}")


def push(workspace: Path, branch: str) -> None:
    token = os.environ["GITHUB_TOKEN"]
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    proc = subprocess.run(
        ["git", "-c", f"http.extraheader=Authorization: Basic {basic}",
         "push", "-q", "origin", branch],
        cwd=workspace, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        msg = proc.stderr.replace(token, "***").replace(basic, "***")
        raise SystemExit("git push failed:\n" + msg)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("issue", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    issue = gh.get_issue(args.issue)
    print(f"Issue #{issue['number']}: {issue['title']}")

    workspace = Path(tempfile.mkdtemp(prefix=f"issue-crew-{args.issue}-"))
    git("clone", "-q", CLONE_URL, str(workspace), cwd=ROOT)
    branch = f"crew/issue-{args.issue}-{int(time.time())}"
    git("checkout", "-q", "-b", branch, cwd=workspace)
    print(f"Workspace: {workspace}")

    task = f"GitHub issue #{issue['number']}: {issue['title']}\n\n{issue['body']}"
    result = run_crew(workspace, task)
    print(
        f"Crew: tests_passed={result['tests_passed']} approved={result['approved']} "
        f"attempts={result['attempts']} steps={result['steps']} tokens={result['tokens']}"
    )

    if git("status", "--porcelain", "--", "tests", cwd=workspace).stdout.strip():
        raise SystemExit("The crew changed files under tests/. Not opening a PR.")
    if not result["tests_passed"]:
        raise SystemExit("Tests did not pass. Not opening a PR.")
    if not git("status", "--porcelain", cwd=workspace).stdout.strip():
        raise SystemExit("The crew made no changes.")

    git("add", "-A", cwd=workspace)
    print(git("diff", "--cached", "--stat", cwd=workspace).stdout)

    if args.dry_run:
        print("Dry run: nothing committed or pushed.")
        return

    git(
        "-c", "user.name=issue-crew",
        "-c", "user.email=issue-crew@users.noreply.github.com",
        "commit", "-q", "-m", f"Fix #{issue['number']}: {issue['title']}",
        cwd=workspace,
    )
    push(workspace, branch)

    body = (
        f"Closes #{issue['number']}\n\n"
        "Opened by issue-crew (Planner, Coder, Tester, Reviewer).\n\n"
        f"- Tests passed: {result['tests_passed']}\n"
        f"- Reviewer approved: {result['approved']}\n"
        f"- Coder attempts: {result['attempts']}\n"
        f"- LLM steps: {result['steps']}\n"
        f"- Tokens: {result['tokens']}\n"
    )
    url = gh.create_pull_request(
        title=f"Fix #{issue['number']}: {issue['title']}",
        body=body, head=branch, base="main",
    )
    print("Pull request:", url)

    comment = (
        "issue-crew opened a pull request for this issue.\n\n"
        f"- Pull request: {url}\n"
        f"- Tests passed: {result['tests_passed']}\n"
        f"- Reviewer approved: {result['approved']}\n"
        f"- Coder attempts: {result['attempts']}\n"
        f"- LLM steps: {result['steps']}\n"
        f"- Tokens: {result['tokens']}\n"
    )
    try:
        print("Issue comment:", gh.comment_on_issue(issue["number"], comment))
    except Exception as exc:
        print(f"PR was opened, but commenting failed: {exc}")


if __name__ == "__main__":
    main()