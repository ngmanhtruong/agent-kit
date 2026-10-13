#!/usr/bin/env python3
"""Hard guard: block Edit/Write on protected paths, outside the project,
or outside the write area of the current role (env role or subagent type)."""
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # no __pycache__ inside .claude/hooks
sys.path.insert(0, str(Path(__file__).parent))
from _common import (ROLE_WRITE_ONLY, deny, is_protected, log, read_input,  # noqa: E402
                     rel, role_of, under, unlocked)

data = read_input()
role = role_of(data)
ti = data.get("tool_input", {}) or {}
path = ti.get("file_path") or ti.get("notebook_path") or ""

if not path or unlocked():
    sys.exit(0)

r = rel(path)

if r.startswith("/"):
    log("BLOCK_FILE_OUTSIDE", r, role)
    deny(f"Không được ghi file ngoài project: {r}")

if role in ROLE_WRITE_ONLY:
    allowed = ROLE_WRITE_ONLY[role]
    if not any(under(r, p) for p in allowed):
        log("BLOCK_FILE_ROLE", r, role)
        deny(f"Vai trò '{role}' chỉ được ghi vào: {', '.join(allowed) or '(không gì cả)'}.")
    sys.exit(0)

if is_protected(r):
    log("BLOCK_FILE_PROTECTED", r, role)
    deny(
        f"'{r}' là vùng được bảo vệ (bài chấm, rào chắn, bối cảnh, spec). "
        "Không sửa. Nếu thật sự cần, ghi đề xuất vào báo cáo cho người duyệt."
    )

sys.exit(0)
