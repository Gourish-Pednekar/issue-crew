"""Evaluation harness: run agents on tasks, verify the result, log to a CSV.

Usage (from the issue-crew folder, venv active):
  python eval/run_eval.py --agents crew2 --tasks 01-validation --runs 1
"""
import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from sandbox import run_pytest  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
MODEL = os.environ.get("MODEL", "openai/gpt-oss-120b")
EVAL_DIR = ROOT / "eval"
TASKS_DIR = EVAL_DIR / "tasks"
WORK_DIR = EVAL_DIR / "work"
RESULTS_CSV = EVAL_DIR / "results.csv"
AGENT_TIMEOUT = 900  # seconds per run

AGENTS = {
    "single": "phase1_agent.py",
    "crew1": "phase2_crew.py",
    "crew2": "phase3_crew.py",
}

FIELDS = [
    "timestamp", "task", "agent", "model", "run", "resolved", "tests_modified",
    "agent_tests_passed", "approved", "rejections", "attempts", "steps", "tokens",
    "seconds", "last_review", "error",
]


def snapshot_tests(root: Path) -> dict:
    """Map of test file path -> contents, used to detect tampering."""
    tests = root / "tests"
    out = {}
    if tests.exists():
        for p in sorted(tests.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                out[str(p.relative_to(tests))] = p.read_bytes()
    return out


def run_one(task: dict, agent: str, run_idx: int) -> dict:
    src = TASKS_DIR / task["id"]
    work = WORK_DIR / f"{task['id']}-{agent}-{run_idx}-{int(time.time())}"
    shutil.copytree(src, work)
        # The Reviewer reads `git diff HEAD`, so each work copy needs a baseline commit.
    for git_args in (
        ["init", "-q"],
        ["add", "-A"],
        ["-c", "user.name=eval", "-c", "user.email=eval@example.com",
         "commit", "-q", "-m", "baseline"],
    ):
        subprocess.run(["git", *git_args], cwd=work, capture_output=True, check=True)

    row = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "task": task["id"], "agent": agent, "model": MODEL, "run": run_idx,
        "resolved": False, "tests_modified": None, "agent_tests_passed": None,
        "approved": None, "rejections": None, "attempts": None, "steps": None,
        "tokens": None, "seconds": None, "last_review": "", "error": "",
    }
    env = dict(os.environ, WORKSPACE=str(work), PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    start = time.time()
    try:
        try:
            proc = subprocess.run(
                [sys.executable, AGENTS[agent], task["prompt"]],
                cwd=ROOT, env=env, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=AGENT_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            row["error"] = f"agent timed out after {AGENT_TIMEOUT}s"
            return row

        result = None
        for line in proc.stdout.splitlines():
            if line.startswith("RESULT_JSON "):
                result = json.loads(line[len("RESULT_JSON "):])
        if "DAILY_TOKEN_LIMIT" in proc.stdout:
            row["error"] = "DAILY_TOKEN_LIMIT"
            return row
        if result is None:
            tail = (proc.stderr or proc.stdout)[-200:].replace("\n", " | ")
            row["error"] = f"no RESULT_JSON (exit {proc.returncode}): {tail}"
            return row

        row["agent_tests_passed"] = result.get("tests_passed")
        row["approved"] = result.get("approved")
        row["attempts"] = result.get("attempts")
        row["steps"] = result.get("steps")
        row["tokens"] = result.get("tokens")
        row["rejections"] = result.get("rejections")
        row["last_review"] = (result.get("last_review") or "").replace("\n", " | ")[:400]

        # Independent verification: restore the original tests, then run them.
        row["tests_modified"] = snapshot_tests(work) != snapshot_tests(src)
        shutil.rmtree(work / "tests", ignore_errors=True)
        shutil.copytree(src / "tests", work / "tests")
        passed, _ = run_pytest(work)
        row["resolved"] = passed
        return row
    finally:
        row["seconds"] = round(time.time() - start, 1)
        shutil.rmtree(work, ignore_errors=True)


def append_row(row: dict) -> None:
    new_file = not RESULTS_CSV.exists()
    with open(RESULTS_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agents", nargs="+", choices=list(AGENTS), required=True)
    parser.add_argument("--tasks", nargs="*", help="task ids; default is all tasks")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--sleep", type=float, default=5, help="seconds between runs")
    args = parser.parse_args()

    tasks = json.loads((EVAL_DIR / "tasks.json").read_text(encoding="utf-8"))
    if args.tasks:
        tasks = [t for t in tasks if t["id"] in args.tasks]
    if not tasks:
        sys.exit("no matching tasks")

    WORK_DIR.mkdir(exist_ok=True)
    total = len(tasks) * len(args.agents) * args.runs
    done = 0
    for task in tasks:
        for run_idx in range(1, args.runs + 1):
            for agent in args.agents:
                done += 1
                print(f"[{done}/{total}] task={task['id']} agent={agent} run={run_idx} ...", flush=True)
                row = run_one(task, agent, run_idx)
                if row["error"] == "DAILY_TOKEN_LIMIT":
                    print("\nDaily token limit reached. This run was NOT logged. "
                          "Stop here and resume tomorrow.")
                    sys.exit(0)
                append_row(row)
                print(
                    f"resolved={row['resolved']} approved={row['approved']} "
                    f"rejections={row['rejections']} attempts={row['attempts']} "
                    f"steps={row['steps']} tokens={row['tokens']} "
                    f"seconds={row['seconds']} tests_modified={row['tests_modified']}"
                    + (f" ERROR: {row['error']}" if row["error"] else ""),
                    flush=True,
                )
                time.sleep(args.sleep)
    print(f"\nDone. Results are in {RESULTS_CSV}")


if __name__ == "__main__":
    main()