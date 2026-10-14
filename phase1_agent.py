"""Phase 1: a single coding agent with a hand-written tool-calling loop.

Run:  python phase1_agent.py "Make the failing tests in tests/ pass"
Needs a .env file with GROQ_API_KEY and WORKSPACE (path to the sample target repo).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.environ["GROQ_API_KEY"],
    base_url="https://api.groq.com/openai/v1",
)
# Set MODEL in .env to override. Use a model from your own Groq model list.
MODEL = os.environ.get("MODEL", "openai/gpt-oss-120b")
WORKSPACE = Path(os.environ["WORKSPACE"]).resolve()
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", ".pytest_cache", "node_modules"}
MAX_OUTPUT_CHARS = 4000


# ---------- tools (the agent's "hands") ----------

def safe_path(rel: str) -> Path:
    """Resolve a path and refuse anything that escapes the workspace."""
    p = (WORKSPACE / rel).resolve()
    if not p.is_relative_to(WORKSPACE):
        raise ValueError("path escapes workspace")
    return p


def list_files(**_ignored) -> str:
    files = []
    for path in WORKSPACE.rglob("*"):
        if path.is_file() and not any(part in SKIP_DIRS for part in path.parts):
            files.append(str(path.relative_to(WORKSPACE)))
    return "\n".join(sorted(files)) or "(empty)"


def read_file(path: str) -> str:
    text = safe_path(path).read_text(encoding="utf-8")
    if not text.strip():
        return "(file is empty)"
    return text[:MAX_OUTPUT_CHARS]


def write_file(path: str, content: str) -> str:
    p = safe_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"wrote {len(content)} chars to {path}"


def run_tests() -> str:
    # NOTE: not a real sandbox yet. Docker isolation comes in a later phase.
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=short"],
        cwd=WORKSPACE, capture_output=True, text=True, timeout=60,
    )
    return (proc.stdout + proc.stderr)[-MAX_OUTPUT_CHARS:]


TOOL_FUNCS = {
    "list_files": list_files,
    "read_file": read_file,
    "write_file": write_file,
    "run_tests": run_tests,
}


def tool(name, description, properties=None, required=None):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
            },
        },
    }


TOOLS = [
    tool("list_files", "List all files in the repository. Takes no arguments."),
    tool("read_file", "Read a whole file. Takes only a path; there are no line ranges.",
         {"path": {"type": "string", "description": "relative path"}}, ["path"]),
    tool("write_file",
         "Overwrite a file with its COMPLETE new content. Both path and content are "
         "required; partial edits are not supported.",
         {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
    tool("run_tests", "Run the pytest suite and return the output."),
]

SYSTEM = (
    "You are a careful software engineer working inside a small Python repo. "
    "Always list and read the relevant files before editing. Make minimal changes. "
    "After editing, run the tests and fix any failures. "
    "When all tests pass, reply with a short summary of what you changed."
)


# ---------- the agent loop ----------

def run_agent(task: str, max_steps: int = 10) -> None:
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": task},
    ]
    total_tokens = 0

    for step in range(1, max_steps + 1):
        resp = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS)
        total_tokens += resp.usage.total_tokens
        msg = resp.choices[0].message

        # Send back only the fields the API needs (reasoning models add extras).
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

        if not msg.tool_calls:  # the model is done talking to tools
            print(f"\n=== DONE in {step} steps, {total_tokens} tokens ===\n{msg.content}")
            return {"steps": step, "tokens": total_tokens, "finished": True}

        for call in msg.tool_calls:
            name = call.function.name
            args = {}
            try:
                args = json.loads(call.function.arguments or "{}")
                result = TOOL_FUNCS[name](**args)
            except Exception as e:  # tell the model what went wrong so it can recover
                result = f"ERROR: {e}"
            print(f"[step {step}] {name}({list(args)}) -> {result[:80]!r}")
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})

    print(f"\n=== STOPPED: hit the {max_steps}-step limit, {total_tokens} tokens ===")
    return {"steps": max_steps, "tokens": total_tokens, "finished": False}

if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else "Make the failing tests pass."
    result = run_agent(task)
    print("RESULT_JSON " + json.dumps(result))