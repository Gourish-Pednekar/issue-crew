"""Phase 3: Planner -> Coder -> Tester -> Reviewer, with a Supervisor (routing + budget).

Run (from the issue-crew folder):  python phase3_crew.py "<task>"
"""
import subprocess
import sys
import json
from langgraph.graph import END, StateGraph

from phase1_agent import WORKSPACE
from phase2_crew import (
    CODER_SYSTEM,
    MAX_ATTEMPTS,
    CrewState,
    call_llm,
    planner,
    safe_run,
    tester,
)

TOKEN_BUDGET = 40000  # Supervisor stops the crew when total tokens reach this


class ReviewState(CrewState):
    review_feedback: str
    approved: bool
    rejections: int
    last_review: str

# ---------- helpers ----------

def get_diff() -> str:
    """The Coder's changes, compared with the baseline commit (HEAD)."""
    proc = subprocess.run(
        ["git", "diff", "HEAD"],
        cwd=WORKSPACE, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30,
    )
    if proc.returncode != 0:
        # Fail loudly instead of pretending nothing changed.
        return f"(git diff FAILED: {proc.stderr.strip()[:200]})"
    return proc.stdout[-6000:] or "(no changes)"

def over_budget(state) -> bool:
    return state["tokens"] >= TOKEN_BUDGET


# ---------- agents ----------

REVIEWER_SYSTEM = (
    "You are a strict but fair code reviewer. You are given a task, a plan and a git diff. "
    "Answer in exactly this format:\n"
    "1. Task met: PASS or FAIL, with one short reason\n"
    "2. Valid, readable Python: PASS or FAIL, with one short reason\n"
    "3. Hacks (hardcoded values, special-casing test inputs): PASS or FAIL, with one short reason\n"
    "4. Validation and edge cases: PASS or FAIL, with one short reason\n"
    "Last line: exactly 'VERDICT: APPROVE' or 'VERDICT: REJECT'. "
    "Reject if any check fails, and name the concrete fix."
)

def coder(state: ReviewState):
    attempt = state["attempts"] + 1
    print(f"\n[CODER] attempt {attempt}/{MAX_ATTEMPTS}")
    prompt = f"Task:\n{state['task']}\n\nPlan:\n{state['plan']}\n"
    if state["test_output"]:
        prompt += (
            "\nYour previous attempt failed the tests. Test output:\n"
            f"{state['test_output']}\nFix the code.\n"
        )
    if state["review_feedback"]:
        prompt += (
            "\nA reviewer rejected your previous attempt. Feedback:\n"
            f"{state['review_feedback']}\nAddress it.\n"
        )
    text, tokens, steps = safe_run(
        "CODER", CODER_SYSTEM, prompt, ["list_files", "read_file", "write_file"]
    )
    print(f"[CODER] {text}")
    return {
        "attempts": attempt,
        "tokens": state["tokens"] + tokens,
        "steps": state["steps"] + steps,
        "review_feedback": "",  # feedback has been consumed
    }


def reviewer(state: ReviewState):
    print("\n[REVIEWER] reading the diff...")
    user = (
        f"Task:\n{state['task']}\n\nPlan:\n{state['plan']}\n\n"
        f"Diff:\n{get_diff()}"
    )
    try:
        resp = call_llm(
            [
                {"role": "system", "content": REVIEWER_SYSTEM},
                {"role": "user", "content": user},
            ],
            [],  # the reviewer has no tools
        )
        text = resp.choices[0].message.content or ""
        tokens = resp.usage.total_tokens
    except Exception as e:
        print(f"[REVIEWER] crashed: {e}")
        text, tokens = "VERDICT: REJECT\nReviewer was unavailable; re-check your work.", 0

    verdict_lines = [l for l in text.upper().splitlines() if l.strip().startswith("VERDICT:")]
    approved = bool(verdict_lines) and "APPROVE" in verdict_lines[-1]
    print(f"[REVIEWER] {'APPROVED' if approved else 'REJECTED'}\n{text}")
    return {
        "approved": approved,
        "review_feedback": "" if approved else text,
        "tokens": state["tokens"] + tokens,
        "rejections": state["rejections"] + (0 if approved else 1),
        "last_review": text[:600],
    }


# ---------- the Supervisor: routing and limits ----------

def route_after_test(state: ReviewState):
    if state["tests_passed"]:
        return "review"
    if state["attempts"] >= MAX_ATTEMPTS or over_budget(state):
        return "give_up"
    return "retry"


def route_after_review(state: ReviewState):
    if state["approved"]:
        return "done"
    if state["attempts"] >= MAX_ATTEMPTS or over_budget(state):
        return "give_up"
    return "retry"


# ---------- build the graph ----------

graph = StateGraph(ReviewState)
graph.add_node("planner", planner)
graph.add_node("coder", coder)
graph.add_node("tester", tester)
graph.add_node("reviewer", reviewer)

graph.set_entry_point("planner")
graph.add_edge("planner", "coder")
graph.add_edge("coder", "tester")
graph.add_conditional_edges(
    "tester",
    route_after_test,
    {"review": "reviewer", "retry": "coder", "give_up": END},
)
graph.add_conditional_edges(
    "reviewer",
    route_after_review,
    {"done": END, "retry": "coder", "give_up": END},
)

crew = graph.compile()


if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else "Make the failing tests pass."
    final = crew.invoke(
        {
            "task": task,
            "plan": "",
            "test_output": "",
            "tests_passed": False,
            "attempts": 0,
            "tokens": 0,
            "steps": 0,
            "review_feedback": "",
            "approved": False,
            "rejections": 0,
            "last_review": "",
        }
    )
    ok = final["tests_passed"] and final["approved"]
    if ok:
        status = "SUCCESS (tests pass, reviewer approved)"
    elif final["tests_passed"]:
        status = "TESTS PASS but reviewer did NOT approve"
    else:
        status = "FAILED"
    print(
        f"\n=== {status} | coder attempts: {final['attempts']} | "
        f"LLM steps: {final['steps']} | tokens: {final['tokens']} / {TOKEN_BUDGET} ==="
    )
    print("RESULT_JSON " + json.dumps({
        "tests_passed": final["tests_passed"],
        "approved": final["approved"],
        "attempts": final["attempts"],
        "steps": final["steps"],
        "tokens": final["tokens"],
        "rejections": final["rejections"],
        "last_review": final["last_review"],
    }))