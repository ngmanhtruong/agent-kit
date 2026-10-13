#!/usr/bin/env python3
"""Self-grading gate (Stop and SubagentStop): when a worker/implementer tries to stop after changing code, run
eval/checks.sh. If it fails, block the stop and feed the errors back.
Gives up after MAX_ATTEMPTS so a stuck agent doesn't burn the whole quota."""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import PROJECT, is_protected, log, read_input, role_of  # noqa: E402

MAX_ATTEMPTS = int(os.environ.get("AGENT_KIT_MAX_FIX_ATTEMPTS", "3"))
CHECKS = PROJECT / "eval" / "checks.sh"

data = read_input()
session = data.get("session_id", "unknown")

if role_of(data) != "worker" or os.environ.get("AGENT_KIT_SKIP_STOP_CHECK") == "1" or not CHECKS.exists():
    sys.exit(0)


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=PROJECT, capture_output=True,
                              text=True, timeout=30).stdout.strip()
    except Exception:
        return ""


# Only grade when CODE changed: uncommitted edits, or commits ahead of base.
# Changes limited to protected/spec areas (tasks/, docs/, design/, ...) — e.g. after
# a planner or bug-triager subagent ran — don't trigger grading.
base = os.environ.get("AGENT_KIT_BASE", "")
paths = (git("diff", "--name-only", "HEAD").splitlines()
         + git("ls-files", "--others", "--exclude-standard").splitlines())
if base:
    paths += git("diff", "--name-only", f"{base}...HEAD").splitlines()
code_changed = [p for p in paths if p and not is_protected(p) and not p.startswith(".agent-kit/")]
if not code_changed:
    sys.exit(0)

state = PROJECT / ".agent-kit" / "state"
state.mkdir(parents=True, exist_ok=True)
counter = state / f"stop_attempts_{session}"
attempts = int(counter.read_text()) if counter.exists() else 0

res = subprocess.run(["bash", str(CHECKS)], cwd=PROJECT,
                     capture_output=True, text=True, timeout=850)
if res.returncode == 0:
    counter.unlink(missing_ok=True)
    log("CHECKS_PASS", session)
    sys.exit(0)

attempts += 1
counter.write_text(str(attempts))
log("CHECKS_FAIL", f"{session}\tattempt {attempts}")

if attempts > MAX_ATTEMPTS:
    sys.exit(0)  # let it stop; the runner marks the task failed

tail = (res.stdout + "\n" + res.stderr)[-3000:]
print(json.dumps({
    "decision": "block",
    "reason": (
        f"eval/checks.sh chưa pass (lần {attempts}/{MAX_ATTEMPTS}). "
        "Sửa lỗi rồi mới được dừng. Không sửa eval/ hay test để cho pass.\n\n" + tail
    ),
}))
sys.exit(0)
