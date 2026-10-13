"""Shared helpers for agent-kit hooks. Standard library only."""
import json
import os
import sys
from pathlib import Path

PROJECT = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())).resolve()

# Who is running: worker (default), planner, test-writer, reviewer. Set by runner/kit.py.
ROLE = os.environ.get("AGENT_KIT_ROLE", "worker")

# Roles that may ONLY write inside these prefixes. Everything else is denied.
ROLE_WRITE_ONLY = {
    "planner": ["tasks/"],
    "test-writer": [".agent-kit/holdout-staging/"],
    "reviewer": [],
}

# Paths a worker must never change. The human edits these, not the AI.
PROTECTED = [
    "eval/",
    ".claude/",
    "tasks/",
    "runner/",
    "design/",
    "docs/",
    "CLAUDE.md",
    ".env",
    ".git/",
]


def unlocked() -> bool:
    """Human override: launch with AGENT_KIT_UNLOCK=1 to let Claude edit protected files."""
    return os.environ.get("AGENT_KIT_UNLOCK") == "1"


def read_input() -> dict:
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def rel(path: str) -> str:
    """Path relative to project root, or the absolute path if outside it."""
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = PROJECT / p
    p = p.resolve()
    try:
        return p.relative_to(PROJECT).as_posix()
    except ValueError:
        return p.as_posix()


def under(relpath: str, prefix: str) -> bool:
    if prefix.endswith("/"):
        return relpath == prefix[:-1] or relpath.startswith(prefix)
    return relpath == prefix or relpath.startswith(prefix + ".")


def is_protected(relpath: str) -> bool:
    return any(under(relpath, item) for item in PROTECTED)


def deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def log(event: str, detail: str) -> None:
    """Append guard events so the morning report can show what was blocked."""
    d = PROJECT / ".agent-kit" / "logs"
    try:
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "guard.log", "a") as f:
            f.write(f"{ROLE}\t{event}\t{detail}\n")
    except Exception:
        pass
