"""Run the target repo's tests inside a locked-down Docker container."""
import subprocess
import uuid

IMAGE = "issue-crew-sandbox"
TIMEOUT_SECONDS = 90


def run_pytest(workspace, max_chars=4000):
    """Return (passed, output). No network, capped memory/CPU/processes."""
    name = f"issue-crew-test-{uuid.uuid4().hex[:8]}"
    cmd = [
        "docker", "run", "--rm", "--name", name,
        "--network", "none",
        "--memory", "512m",
        "--cpus", "1",
        "--pids-limit", "128",
        "-v", f"{workspace}:/workspace",
        IMAGE,
        "python", "-m", "pytest", "-q", "--tb=short", "-p", "no:cacheprovider",
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        # Killing the docker CLI does not stop the container, so stop it explicitly.
        subprocess.run(["docker", "kill", name], capture_output=True)
        return False, f"Tests timed out after {TIMEOUT_SECONDS}s and were killed."

    output = (proc.stdout + proc.stderr)[-max_chars:]
    if proc.returncode in (125, 126, 127):
        return False, f"SANDBOX ERROR (is Docker Desktop running?):\n{output}"
    if proc.returncode == 137:
        return False, "Tests were killed (out of memory or resource limit exceeded)."
    return proc.returncode == 0, output