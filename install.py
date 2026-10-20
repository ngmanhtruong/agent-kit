#!/usr/bin/env python3
"""Cài / nâng cấp agent-kit trong một repo có sẵn mà không ghi đè file của bạn.

    python3 install.py /đường/dẫn/tới/repo                    cài lần đầu (hoặc bổ sung file còn thiếu)
    python3 install.py /đường/dẫn/tới/repo --upgrade          nâng cấp các file của kit lên bản mới
    python3 install.py /đường/dẫn/tới/repo --upgrade --dry-run   chỉ in kế hoạch, không ghi gì
    python3 install.py /đường/dẫn/tới/repo --upgrade --force  ghi đè cả file của kit đã bị sửa (có sao lưu)
    python3 install.py /đường/dẫn/tới/repo --with-jev         (cài hoặc nâng cấp) chọn dùng Jev/TypeSafe: bật JEV_ENABLED=1

Cài lần đầu:
- File chưa có → chép vào. File đã có → giữ nguyên.
- CLAUDE.md của bạn không bao giờ bị đụng. Quy tắc của kit nằm ở .claude/rules/agent-kit.md (tự được nạp).
  Chưa có CLAUDE.md → tạo bản khởi đầu từ starter/CLAUDE.md.
- .claude/settings.json đã có → tự gộp permissions + hooks (giữ nguyên của bạn).
- Thêm .agent-kit/, runner/config.env, __pycache__/ vào .gitignore.
- Ghi .agent-kit-manifest.json (phiên bản + dấu vân tay các file của kit; nên commit).

Nâng cấp chỉ chạm "file của kit" (OWNED bên dưới: kit.py, hooks, agents, skills, quy tắc, mẫu).
File của bạn (eval/checks.sh, docs/architecture.md, CLAUDE.md, ...) không bao giờ bị ghi đè.
- File của kit chưa bị sửa → thay bằng bản mới.
- File của kit bạn đã sửa (hoặc cài từ bản cũ chưa có manifest) → KHÔNG ghi đè; bản mới được đặt ở
  .agent-kit/upgrade/<đường dẫn> để bạn diff và gộp. Dùng --force để ghi đè (bản cũ lưu ở .agent-kit/backup/).
"""
import argparse
import datetime as dt
import hashlib
import json
import shutil
import stat
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "template"
STARTER = Path(__file__).resolve().parent / "starter"
MANIFEST = ".agent-kit-manifest.json"
SETTINGS = ".claude/settings.json"

# File của kit: nâng cấp được. Mọi file khác trong template/ là của người dùng (chỉ chép khi chưa có).
OWNED = (
    "runner/kit.py", "runner/jev.py", "runner/VERSION", "runner/config.env.example",
    ".claude/hooks/", ".claude/agents/", ".claude/skills/", ".claude/rules/agent-kit.md",
    ".github/instructions/agent-kit.instructions.md",
    "docs/orchestration.md", "tasks/_TEMPLATE.md",
    "design/README.md", "design/_IDEA_TEMPLATE.md", "design/_PRD_TEMPLATE.md",
)


def is_owned(rel: str) -> bool:
    return any(rel == o or (o.endswith("/") and rel.startswith(o)) for o in OWNED)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def kit_version() -> str:
    v = SRC / "runner" / "VERSION"
    return v.read_text().strip() if v.exists() else "0"


def load_manifest(repo: Path) -> dict:
    try:
        return json.loads((repo / MANIFEST).read_text())
    except (OSError, ValueError):
        return {}


def template_files():
    for f in sorted(SRC.rglob("*")):
        if f.is_dir() or "__pycache__" in f.parts or f.suffix == ".pyc":
            continue
        yield f, f.relative_to(SRC).as_posix()


def put(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    if src.suffix in (".py", ".sh"):
        dst.chmod(dst.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)


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


def ensure_context_files(repo: Path, notes: list, dry: bool) -> None:
    if (repo / "CLAUDE.md").exists():
        notes.append("CLAUDE.md của bạn giữ nguyên; điền bối cảnh còn thiếu (phạm vi được/cấm đụng) vào đó")
    else:
        notes.append("tạo CLAUDE.md khởi đầu — điền mục 1-4 (hoặc nhờ agent con context-writer đề xuất)")
        if not dry:
            shutil.copy2(STARTER / "CLAUDE.md", repo / "CLAUDE.md")


def ensure_config_and_gitignore(repo: Path) -> None:
    cfg = repo / "runner" / "config.env"
    if not cfg.exists():
        shutil.copy2(repo / "runner" / "config.env.example", cfg)
    gi = repo / ".gitignore"
    lines = gi.read_text().splitlines() if gi.exists() else []
    add = [x for x in (".agent-kit/", "runner/config.env", "__pycache__/") if x not in lines]
    if add:
        gi.write_text("\n".join(lines + ["", "# agent-kit"] + add) + "\n")


def enable_jev(repo: Path) -> None:
    """Người dùng chọn dùng Jev: đặt JEV_ENABLED=1 trong runner/config.env (của máy này) và in các bước còn lại.
    Không tự cài skill hay đặt khoá: skill nằm ở cấu hình agent của bạn, khoá là bí mật của bạn."""
    cfg = repo / "runner" / "config.env"
    lines = cfg.read_text().splitlines() if cfg.exists() else []
    if any(l.strip().startswith("JEV_ENABLED=") for l in lines):
        lines = ["JEV_ENABLED=1" if l.strip().startswith("JEV_ENABLED=") else l for l in lines]
    else:
        lines += ["", "# Jev (TypeSafe) — bật bởi install.py --with-jev", "JEV_ENABLED=1"]
    cfg.write_text("\n".join(lines) + "\n")
    print("\n✓ Jev: đã đặt JEV_ENABLED=1 trong runner/config.env (chỉ máy này; máy khác tự chạy lại với --with-jev).")
    print("  Còn lại, tự làm:")
    print("  1. Tạo khoá ở https://console.typesafe.ai/keys, rồi export TYPESAFE_API_KEY trong shell (hoặc điền vào runner/config.env).")
    print("  2. (Tuỳ chọn) cài skill TypeSafe cho agent, giúp agent viết đúng code dùng API TypeSafe:")
    print("       Claude Code:  claude plugin marketplace add typesafe-ai/skills && claude plugin install typesafe@typesafe-ai")
    print("       Agent khác:   npx skills add typesafe-ai/skills --skill typesafe-ai")
    print("     (kit.py tự gọi API nên không cần skill để Jev chạy.)")
    print("  3. python3 runner/kit.py doctor   # kiểm tra kết nối Jev")
    hook = repo / ".claude" / "hooks" / "guard_bash.py"
    if not hook.exists() or "import jev" not in hook.read_text():
        print("\n  ! Project này chưa có phần nối Jev (cài từ bản cũ, hoặc hook đã bị sửa): JEV_ENABLED=1 CHƯA có tác dụng.")
        print(f"    Chạy: python3 {Path(__file__).resolve()} {repo} --upgrade --with-jev")
    print("  Lưu ý riêng tư: lệnh shell của agent và nội dung task/Acceptance sẽ được gửi tới api.typesafe.ai.")


def install(repo: Path, dry: bool) -> None:
    old = load_manifest(repo)
    files = dict(old.get("files", {}))
    notes = []
    for f, rel in template_files():
        dst = repo / rel
        if rel == SETTINGS and dst.exists():
            if not dry:
                merge_settings(dst, f)
            notes.append("đã gộp .claude/settings.json")
            continue
        if dst.exists():
            notes.append(f"giữ nguyên (đã có): {rel}")
            if is_owned(rel) and sha(dst) == sha(f):
                files[rel] = sha(f)
            continue
        if not dry:
            put(f, dst)
        if is_owned(rel):
            files[rel] = sha(f)
    ensure_context_files(repo, notes, dry)
    if not dry:
        ensure_config_and_gitignore(repo)
        write_manifest(repo, files)
    report(repo, notes, f"✓ Đã cài agent-kit {kit_version()} vào {repo}")
    if old.get("version") and old["version"] != kit_version():
        print(f"  ! repo này đang ở agent-kit {old['version']}, kit hiện là {kit_version()} → chạy lại với --upgrade")


def write_manifest(repo: Path, files: dict) -> None:
    data = {"version": kit_version(), "files": dict(sorted(files.items()))}
    (repo / MANIFEST).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def upgrade(repo: Path, force: bool, dry: bool) -> None:
    old = load_manifest(repo)
    files = dict(old.get("files", {}))
    if not old:
        print("! Chưa có " + MANIFEST + " (cài từ bản cũ): không biết file nào bạn đã sửa, nên mọi file khác bản mới "
              "sẽ được coi là đã sửa.\n  Nếu bạn chưa sửa file nào của kit: thêm --force (có sao lưu).")
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    updated, same, held, added, forced = [], 0, [], [], []
    for f, rel in template_files():
        dst = repo / rel
        if rel == SETTINGS:
            if dst.exists():
                if not dry:
                    merge_settings(dst, f)
            elif not dry:
                put(f, dst)
            continue
        if not is_owned(rel):
            if not dst.exists():
                added.append(rel)
                if not dry:
                    put(f, dst)
            continue
        new = sha(f)
        if not dst.exists():
            added.append(rel)
            if not dry:
                put(f, dst)
            files[rel] = new
        elif sha(dst) == new:
            same += 1
            files[rel] = new
        elif old.get("files", {}).get(rel) == sha(dst):
            updated.append(rel)
            if not dry:
                put(f, dst)
            files[rel] = new
        elif force:
            forced.append(rel)
            if not dry:
                bk = repo / ".agent-kit" / "backup" / stamp / rel
                bk.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dst, bk)
                put(f, dst)
            files[rel] = new
        else:
            held.append(rel)
            if not dry:
                hold = repo / ".agent-kit" / "upgrade" / rel
                hold.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, hold)
    gone = sorted(r for r in files if r not in {rel for _, rel in template_files()})
    for r in gone:
        files.pop(r, None)
    if not dry:
        ensure_config_and_gitignore(repo)
        write_manifest(repo, files)
    tag = " (chạy thử, chưa ghi gì)" if dry else ""
    print(f"✓ Nâng cấp agent-kit {old.get('version', '?')} → {kit_version()} trong {repo}{tag}")
    print(f"  - đã cập nhật: {len(updated)} · không đổi: {same} · thêm mới: {len(added)}")
    for r in updated:
        print(f"    ↻ {r}")
    for r in added:
        print(f"    + {r}")
    for r in forced:
        print(f"    ⚠ ghi đè (đã sao lưu ở .agent-kit/backup/{stamp}/): {r}")
    if held:
        print(f"  ! {len(held)} file của kit đã bị sửa nên KHÔNG ghi đè (bản mới ở .agent-kit/upgrade/):")
        for r in held:
            print(f"    ✗ {r}   → diff -u {r} .agent-kit/upgrade/{r}")
        print("    Gộp tay, hoặc chạy lại với --force nếu muốn lấy bản mới của kit.")
    for r in gone:
        print(f"  ? kit không còn dùng {r}; xoá nếu bạn không cần.")
    if not dry:
        print(f"\nNhớ commit: git add {MANIFEST} .claude runner docs design tasks .github")


def report(repo: Path, notes: list, head: str) -> None:
    print(head)
    for n in notes:
        print("  -", n)
    for tool, why in (("python3", ""), ("git", ""), ("gh", " (chỉ cần nếu GH_SYNC=1)"),
                      ("claude", " (không bắt buộc: không có thì dùng agent CLI khác qua AGENT_CMD, hoặc chế độ chat như Copilot Chat)")):
        if not shutil.which(tool):
            print(f"  ! thiếu `{tool}` trên máy này{why}")
    v = subprocess.run(["claude", "--version"], capture_output=True, text=True) if shutil.which("claude") else None
    if v:
        print(f"  claude: {v.stdout.strip()} (cần bản hỗ trợ hook onFailure và --permission-prompts)")
    print("\nTiếp theo: chạy `python3 runner/kit.py` (menu) hoặc `kit.py doctor`; hướng dẫn đầy đủ: README.md của repo agent-kit.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Cài / nâng cấp agent-kit", usage="install.py REPO [--upgrade [--force] [--dry-run]] [--with-jev]")
    ap.add_argument("repo")
    ap.add_argument("--upgrade", action="store_true", help="nâng cấp các file của kit")
    ap.add_argument("--force", action="store_true", help="(với --upgrade) ghi đè cả file của kit đã bị sửa, có sao lưu")
    ap.add_argument("--dry-run", action="store_true", help="chỉ in kế hoạch")
    ap.add_argument("--with-jev", action="store_true", help="chọn dùng Jev (TypeSafe): đặt JEV_ENABLED=1 trong runner/config.env")
    a = ap.parse_args()
    if (a.force or a.dry_run) and not a.upgrade:
        ap.error("--force và --dry-run chỉ dùng cùng --upgrade")
    repo = Path(a.repo).expanduser().resolve()
    if not (repo / ".git").exists():
        sys.exit(f"{repo} không phải git repo.")
    if a.upgrade:
        if not (repo / "runner" / "kit.py").exists():
            sys.exit("Repo này chưa cài agent-kit. Chạy không có --upgrade trước.")
        upgrade(repo, a.force, a.dry_run)
    else:
        install(repo, False)
    if a.with_jev and not a.dry_run:
        enable_jev(repo)


if __name__ == "__main__":
    main()
