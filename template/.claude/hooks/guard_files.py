#!/usr/bin/env python3
"""Hard guard: block Edit/Write on protected paths, outside the project,
or outside the write area of the current role."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import (ROLE, ROLE_WRITE_ONLY, deny, is_protected, log,  # noqa: E402
                     read_input, rel, under, unlocked)

data = read_input()
ti = data.get("tool_input", {}) or {}
path = ti.get("file_path") or ti.get("notebook_path") or ""

if not path or unlocked():
    sys.exit(0)

r = rel(path)

if r.startswith("/"):
    log("BLOCK_FILE_OUTSIDE", r)
    deny(f"Không được ghi file ngoài project: {r}")

if ROLE in ROLE_WRITE_ONLY:
    allowed = ROLE_WRITE_ONLY[ROLE]
    if not any(under(r, p) for p in allowed):
        log("BLOCK_FILE_ROLE", r)
        deny(f"Vai trò '{ROLE}' chỉ được ghi vào: {', '.join(allowed) or '(không gì cả)'}.")
    sys.exit(0)

if is_protected(r):
    log("BLOCK_FILE_PROTECTED", r)
    deny(
        f"'{r}' là vùng được bảo vệ (bài chấm, rào chắn, bối cảnh, spec). "
        "Không sửa. Nếu thật sự cần, ghi đề xuất vào báo cáo cho người duyệt."
    )

sys.exit(0)
