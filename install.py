#!/usr/bin/env python3
"""Cài agent-kit vào một repo có sẵn mà không ghi đè file của bạn.

    python3 install.py /đường/dẫn/tới/repo

- File chưa có → chép vào.
- CLAUDE.md đã có → ghi CLAUDE.agent-kit.md để bạn tự gộp.
- .claude/settings.json đã có → tự gộp permissions + hooks (giữ nguyên của bạn).
- Thêm .agent-kit/, runner/config.env, __pycache__/ vào .gitignore.
"""
import json
import shutil
import stat
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "template"


def merge_settings(dst: Path, src: Path) -> None:
    mine, kit = json.loads(dst.read_text()), json.loads(src.read_text())
    perms = mine.setdefault("permissions", {})
    for k in ("allow", "deny"):
        cur = perms.setdefault(k, [])
        cur += [x for x in kit["permissions"].get(k, []) if x not in cur]
    hooks = mine.setdefault("hooks", {})
    for event, groups in kit["hooks"].items():
        cur = hooks.setdefault(event, [])
        for g in groups:
            if g not in cur:
                cur.append(g)
    dst.write_text(json.dumps(mine, indent=2, ensure_ascii=False) + "\n")


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    repo = Path(sys.argv[1]).expanduser().resolve()
    if not (repo / ".git").exists():
        sys.exit(f"{repo} không phải git repo.")

    notes = []
    for f in sorted(SRC.rglob("*")):
        if f.is_dir():
            continue
        rel = f.relative_to(SRC)
        dst = repo / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if rel.as_posix() == ".claude/settings.json" and dst.exists():
            merge_settings(dst, f)
            notes.append("đã gộp .claude/settings.json")
            continue
        if dst.exists():
            if rel.as_posix() == "CLAUDE.md":
                shutil.copy2(f, repo / "CLAUDE.agent-kit.md")
                notes.append("CLAUDE.md đã có → xem CLAUDE.agent-kit.md và gộp mục 5-6 vào")
            else:
                notes.append(f"giữ nguyên (đã có): {rel}")
            continue
        shutil.copy2(f, dst)
        if f.suffix in (".py", ".sh"):
            dst.chmod(dst.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)

    cfg = repo / "runner" / "config.env"
    if not cfg.exists():
        shutil.copy2(repo / "runner" / "config.env.example", cfg)

    gi = repo / ".gitignore"
    lines = gi.read_text().splitlines() if gi.exists() else []
    add = [x for x in (".agent-kit/", "runner/config.env", "__pycache__/") if x not in lines]
    if add:
        gi.write_text("\n".join(lines + ["", "# agent-kit"] + add) + "\n")

    print(f"✓ Đã cài agent-kit vào {repo}")
    for n in notes:
        print("  -", n)
    for tool, why in (("python3", ""), ("git", ""), ("gh", " (chỉ cần nếu GH_SYNC=1)"),
                      ("claude", " (không bắt buộc: không có thì dùng agent CLI khác qua AGENT_CMD, hoặc chế độ chat như Copilot Chat)")):
        if not shutil.which(tool):
            print(f"  ! thiếu `{tool}` trên máy này{why}")
    v = subprocess.run(["claude", "--version"], capture_output=True, text=True) if shutil.which("claude") else None
    if v:
        print(f"  claude: {v.stdout.strip()} (cần bản hỗ trợ hook onFailure và --permission-prompts)")
    print("\nTiếp theo: xem README.md, mục 'Bắt đầu'.")


if __name__ == "__main__":
    main()
