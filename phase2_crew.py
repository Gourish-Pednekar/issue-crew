"""Phase 2: Planner -> Coder -> Tester as a LangGraph, with a retry loop.

Run (from the issue-crew folder):  python phase2_crew.py "Add pagination ..."
"""
import json
import subprocess
import sys
import time
from typing import TypedDict

from langgraph.graph import END, StateGraph
from openai import BadRequestError, RateLimitError

# Reuse the client, model, tools and workspace from Phase 1.
from phase1_agent import MAX_OUTPUT_CHARS, MODEL, TOOL_FUNCS, TOOLS, WORKSPACE, client

MAX_ATTEMPTS = 3  # how many times the Coder may try before we give up


# ---------- shared state: everything the agents pass around ----------

class CrewState(TypedDict):
    task: str
    plan: str
    test_output: str
    tests_passed: bool
    attempts: int
    tokens: int
    steps: int


# ---------- guarded LLM call ----------

def call_llm(messages, tools, retries=3):
    """Call the model, surviving malformed tool calls and rate limits."""
    for attempt in range(retries):
        try:
            kwargs = {"tools": tools} if tools else {}
            return client.chat.completions.create(
                model=MODEL, messages=messages, **kwargs
            )
        except BadRequestError as e:
            if "tool_use_failed" in str(e):
                print("    [LLM] malformed tool call; nudging the model and retrying")
                messages.append({
                    "role": "user",
                    "content": (
                        "Your last tool call was malformed. Check the tool's required "
                        "parameters (write_file needs both path and content, "
                        "read_file takes only path) and try again."
                    ),
                })
                continue
            raise
        except RateLimitError:
            wait = 5 * (attempt + 1)
            print(f"    [LLM] rate limited; waiting {wait}s")
            time.sleep(wait)
    raise RuntimeError("LLM call failed after retries")


# ---------- a reusable "LLM agent with tools" runner ----------

def tools_named(*names):
    return [t for t in TOOLS if t["function"]["name"] in names]


def run_llm_agent(system, user, tool_names, max_steps=8):
    """Same tool loop as Phase 1. Returns (final_text, tokens_used, steps_used)."""
    tools = tools_named(*tool_names)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    tokens = 0
    for step in range(1, max_steps + 1):
        resp = call_llm(messages, tools)
        tokens += resp.usage.total_tokens
        msg = resp.choices[0].message

        assistant_msg = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.function.name, "arguments": c.function.arguments},
                }
                for c in msg.tool_calls
            ]
        messages.append(assistant_msg)

        if not msg.tool_calls:
            return msg.content or "", tokens, step

        for call in msg.tool_calls:
            name = call.function.name
            args = {}
            try:
                args = json.loads(call.function.arguments or "{}")
                if name not in tool_names:  # enforce this agent's tool permissions
                    raise ValueError(f"tool '{name}' is not allowed for this agent")
                result = TOOL_FUNCS[name](**args)
            except Exception as e:
                result = f"ERROR: {e}"
            print(f"    [{name}({list(args)})] -> {result[:60]!r}")
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})

    return "(step limit reached)", tokens, max_steps


def safe_run(label, system, user, tool_names):
    """Never let one agent crash the whole graph: a crash becomes a result."""
    try:
        return run_llm_agent(system, user, tool_names)
    except Exception as e:
        print(f"[{label}] crashed: {e}")
        return f"(crashed: {e})", 0, 0


# ---------- the agents (graph nodes) ----------

PLANNER_SYSTEM = (
    "You are a software planner. Explore the repo using list_files and read_file "
    "(read_file takes only a path and returns the whole file). "
    "Do NOT write code and do not include code snippets. "
    "Reply with a plan of at most 5 short numbered lines: which file to change, "
    "what to change, and edge cases to handle."
)

CODER_SYSTEM = (
    "You are a careful software engineer. Follow the plan and make minimal changes. "
    "Tools: list_files (no arguments), read_file (path only, returns the whole file), "
    "write_file (path AND the COMPLETE new file content; there is no partial editing). "
    "To change a file: read it, then write the full updated file. "
    "Make sure the Python you write is syntactically valid. "
    "You cannot run tests; a separate tester will run them. "
    "When done, reply with a one-line summary of what you changed."
)


def planner(state: CrewState):
    print("\n[PLANNER] exploring the repo...")
    text, tokens, steps = safe_run(
        "PLANNER", PLANNER_SYSTEM, state["task"], ["list_files", "read_file"]
    )
    print(f"[PLANNER] plan:\n{text}")
    return {
        "plan": text,
        "tokens": state["tokens"] + tokens,
        "steps": state["steps"] + steps,
    }


def coder(state: CrewState):
    attempt = state["attempts"] + 1
    print(f"\n[CODER] attempt {attempt}/{MAX_ATTEMPTS}")
    prompt = f"Task:\n{state['task']}\n\nPlan:\n{state['plan']}\n"
    if state["test_output"]:
        prompt += (
            "\nYour previous attempt failed the tests. Test output:\n"
            f"{state['test_output']}\nFix the code.\n"
        )
    text, tokens, steps = safe_run(
        "CODER", CODER_SYSTEM, prompt, ["list_files", "read_file", "write_file"]
    )
    print(f"[CODER] {text}")
    return {
        "attempts": attempt,
        "tokens": state["tokens"] + tokens,
        "steps": state["steps"] + steps,
    }


def tester(state: CrewState):
    """No LLM here: run pytest and trust the exit code."""
    print("\n[TESTER] running pytest...")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=short"],
        cwd=WORKSPACE, capture_output=True, text=True, timeout=60,
    )
    output = (proc.stdout + proc.stderr)[-MAX_OUTPUT_CHARS:]
    passed = proc.returncode == 0
    print(f"[TESTER] {'PASSED' if passed else 'FAILED'}")
    return {"tests_passed": passed, "test_output": "" if passed else output}


# ---------- routing: what happens after the tester ----------

def route_after_test(state: CrewState):
    if state["tests_passed"]:
        return "done"
    if state["attempts"] >= MAX_ATTEMPTS:
        return "give_up"
    return "retry"


# ---------- build the graph ----------

graph = StateGraph(CrewState)
graph.add_node("planner", planner)
graph.add_node("coder", coder)
graph.add_node("tester", tester)

graph.set_entry_point("planner")
graph.add_edge("planner", "coder")
graph.add_edge("coder", "tester")
graph.add_conditional_edges(
    "tester",
    route_after_test,
    {"done": END, "give_up": END, "retry": "coder"},
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
        }
    )
    status = "SUCCESS" if final["tests_passed"] else "FAILED"
    print(
        f"\n=== {status} | coder attempts: {final['attempts']} | "
        f"LLM steps: {final['steps']} | tokens: {final['tokens']} ==="
    )