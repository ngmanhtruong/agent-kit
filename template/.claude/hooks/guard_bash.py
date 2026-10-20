#!/usr/bin/env python3
"""Hard guard: block dangerous shell commands. Add a rule here whenever an
error happens twice — that is how a reminder becomes a regulation."""
import os
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # no __pycache__ inside .claude/hooks
sys.path.insert(0, str(Path(__file__).parent))
from _common import PROJECT, PROTECTED, deny, log, read_input, unlocked  # noqa: E402

data = read_input()
cmd = (data.get("tool_input", {}) or {}).get("command", "")
if not cmd:
    sys.exit(0)

# (pattern, reason). Patterns are case-insensitive.
RULES = [
    (r"\brm\s+(-[a-z]*r[a-z]*f|-[a-z]*f[a-z]*r)\b\s+(/|~|\$home|\.\.|\*)", "rm -rf trên thư mục gốc/home/cha"),
    (r"\bsudo\b", "sudo"),
    (r"\bgit\s+push\b", "git push (runner sẽ push)"),
    (r"\bgit\s+reset\s+--hard\b", "git reset --hard"),
    (r"\bgit\s+clean\s+-[a-z]*f", "git clean -f"),
    (r"\bgit\s+(checkout|switch)\s+(main|master)\b", "chuyển sang nhánh gốc"),
    (r"--no-verify\b", "bỏ qua pre-commit hook"),
    (r"\b(curl|wget)\b[^|]*\|\s*(ba|z)?sh\b", "tải và chạy script từ mạng"),
    (r"\bchmod\s+(-R\s+)?777\b", "chmod 777"),
    (r"\b(cat|less|more|head|tail|cp|grep|source|\.)\s[^;&|]*\.env\b", "đọc file .env"),
    (r"\b(printenv|env)\s*($|[;&|])", "in toàn bộ biến môi trường"),
    (r"\bdisableAllHooks\b|AGENT_KIT_UNLOCK|AGENT_KIT_ROLE", "tắt/đổi rào chắn"),
    (r"--dangerously-skip-permissions", "bỏ qua permission"),
    (r"agent-holdout", "đọc bài kiểm tra ẩn"),
    (r"\bgh\s+(pr|issue|release|repo)\b", "thao tác GitHub (runner sẽ làm)"),
]

holdout = os.environ.get("AGENT_KIT_HOLDOUT_DIR", "").strip()
if holdout:
    RULES.append((re.escape(holdout), "đọc bài kiểm tra ẩn"))

for pattern, reason in RULES:
    if re.search(pattern, cmd, re.IGNORECASE):
        log("BLOCK_BASH", f"{reason}\t{cmd[:200]}")
        deny(f"Lệnh bị chặn bởi rào cứng: {reason}.")

# Shell writes into protected paths (redirects, sed -i, mv/cp/rm targets).
if not unlocked():
    write_ops = r"(>>?|\btee\b|\bsed\s+-i|\bmv\b|\bcp\b|\brm\b|\btouch\b|\btruncate\b)"
    for item in PROTECTED:
        target = re.escape(item.rstrip("/"))
        if re.search(write_ops + r"[^;&|]*(^|[\s/'\"])" + target + r"(/|\b)", cmd):
            log("BLOCK_BASH_PROTECTED", cmd[:200])
            deny(f"Không được ghi/xoá vùng bảo vệ '{item}' bằng shell.")

# Optional semantic check (Jev, TypeSafe). Off unless JEV_ENABLED=1 and a key is set. The regex rules above
# stay the hard barrier: if Jev is slow/unreachable we fall back to them (JEV_ON_ERROR=allow, the default).
if not unlocked():
    try:
        sys.path.insert(0, str(PROJECT / "runner"))
        import jev  # noqa: E402
        if jev.enabled() and jev.setting("JEV_GUARD") == "1":
            task = ""
            tf = os.environ.get("AGENT_KIT_TASK_FILE", "")
            if tf and Path(tf).is_file():
                task = Path(tf).read_text()[:2000]
            questions = {"dangerous": "Running this command would destroy data, leak secrets or credentials, "
                                      "change system or security settings, or act outside the project, "
                                      "beyond what ordinary software development needs."}
            if task:
                questions["off_task"] = "This command has nothing to do with accomplishing the task in `task`."
            p = jev.ask({"command": cmd[:1500], "task": task or "(interactive session, no task file)"}, questions)
            limit = float(jev.setting("JEV_BLOCK_AT"))
            if p is None:
                log("JEV_ERROR", f"{jev.last_error}\t{cmd[:120]}")
                if jev.setting("JEV_ON_ERROR") == "block":
                    deny(f"Jev không trả lời được ({jev.last_error}) và JEV_ON_ERROR=block.")
            else:
                hit = [k for k, v in p.items() if v >= limit]
                if hit:
                    log("BLOCK_BASH_JEV", f"{hit}\t{p}\t{cmd[:200]}")
                    why = "nguy hiểm" if "dangerous" in hit else "không liên quan task"
                    deny(f"Jev đánh giá lệnh này {why} (xác suất {max(p.values()):.2f} ≥ {limit}). "
                         "Nếu đúng ý bạn, hãy chạy lệnh đó bằng tay.")
    except SystemExit:
        raise
    except Exception as e:  # Jev không bao giờ làm hỏng hook
        log("JEV_ERROR", f"{type(e).__name__}: {e}"[:200])

sys.exit(0)
