#!/usr/bin/env python3
"""Kiểm tra nhanh agent-kit (chỉ dùng thư viện chuẩn, không gọi AI, không cần mạng).

    python3 tests/smoke.py

Chạy trước khi commit thay đổi ở install.py, template/ hoặc kit.py. Không thuộc bản cài (không nằm trong template/).
Không thay cho thử end-to-end với agent giả (work PASS/FAIL, 3 chế độ): xem CLAUDE.md, mục "Kiểm tra trước khi commit".
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
PY = sys.executable or "python3"


def run(cmd, cwd, env=None, **kw):
    if "input" not in kw:
        kw["stdin"] = subprocess.DEVNULL
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, env=env, **kw)


def new_repo(parent: Path, name: str, claude_md: bool = True) -> Path:
    d = parent / name
    d.mkdir()
    run(["git", "init", "-q", "-b", "main"], d)
    (d / "README.md").write_text("# Company README\n")
    if claude_md:
        (d / "CLAUDE.md").write_text("# Công ty\nđừng đụng prod\n")
    return d


def copy_kit(dst: Path) -> Path:
    shutil.copytree(KIT, dst, ignore=shutil.ignore_patterns(".git", "__pycache__", "tests", "*.pyc"))
    return dst


def tree(d: Path) -> dict:
    return {p.relative_to(d).as_posix(): p.read_bytes() for p in sorted(d.rglob("*"))
            if p.is_file() and ".git/" not in p.as_posix() and "__pycache__" not in p.as_posix()}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="agent-kit-smoke-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def install(self, repo, kit=KIT, *args):
        return run([PY, str(kit / "install.py"), str(repo), *args], self.tmp)


class TestInstall(Base):
    def test_user_files_untouched_and_rules_installed(self):
        d = new_repo(self.tmp, "p")
        r = self.install(d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((d / "README.md").read_text(), "# Company README\n")
        self.assertEqual((d / "CLAUDE.md").read_text(), "# Công ty\nđừng đụng prod\n")
        self.assertTrue((d / ".claude/rules/agent-kit.md").exists())
        self.assertTrue((d / ".github/instructions/agent-kit.instructions.md").exists())
        self.assertFalse((d / "CLAUDE.agent-kit.md").exists())
        self.assertTrue((d / ".agent-kit-manifest.json").exists())

    def test_starter_claude_md_only_when_missing(self):
        d = new_repo(self.tmp, "p", claude_md=False)
        self.install(d)
        self.assertIn("Bản đồ dự án", (d / "CLAUDE.md").read_text())

    def test_reinstall_is_noop_for_existing(self):
        d = new_repo(self.tmp, "p")
        self.install(d)
        before = tree(d)
        self.install(d)
        self.assertEqual(before, tree(d))

    def test_no_pycache_installed(self):
        d = new_repo(self.tmp, "p")
        (KIT / "template/.claude/hooks/__pycache__").mkdir(exist_ok=True)
        (KIT / "template/.claude/hooks/__pycache__/x.pyc").write_bytes(b"x")
        try:
            self.install(d)
        finally:
            shutil.rmtree(KIT / "template/.claude/hooks/__pycache__", ignore_errors=True)
        self.assertFalse((d / ".claude/hooks/__pycache__").exists())


class TestUpgrade(Base):
    def setUp(self):
        super().setUp()
        self.d = new_repo(self.tmp, "p")
        self.install(self.d)
        self.kit2 = copy_kit(self.tmp / "kit2")
        (self.kit2 / "template/runner/VERSION").write_text("9.9.9\n")
        with open(self.kit2 / "template/.claude/agents/reviewer.md", "a") as f:
            f.write("\n<!-- v9 -->\n")
        with open(self.kit2 / "template/eval/checks.sh", "a") as f:
            f.write("\n# v9 (file của người dùng)\n")

    def up(self, *args):
        return self.install(self.d, self.kit2, "--upgrade", *args)

    def test_unmodified_kit_file_is_updated_user_file_is_not(self):
        r = self.up()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("v9", (self.d / ".claude/agents/reviewer.md").read_text())
        self.assertNotIn("v9", (self.d / "eval/checks.sh").read_text())
        self.assertEqual(json.loads((self.d / ".agent-kit-manifest.json").read_text())["version"], "9.9.9")

    def test_modified_kit_file_is_held_not_overwritten(self):
        p = self.d / ".claude/agents/reviewer.md"
        p.write_text(p.read_text() + "\nsửa tay\n")
        r = self.up()
        self.assertIn("sửa tay", p.read_text())
        self.assertNotIn("v9", p.read_text())
        self.assertIn("v9", (self.d / ".agent-kit/upgrade/.claude/agents/reviewer.md").read_text())
        self.assertIn("KHÔNG ghi đè", r.stdout)

    def test_force_overwrites_with_backup_but_never_user_files(self):
        p = self.d / ".claude/agents/reviewer.md"
        p.write_text(p.read_text() + "\nsửa tay\n")
        (self.d / "eval/checks.sh").write_text("mine\n")
        self.up("--force")
        self.assertIn("v9", p.read_text())
        self.assertNotIn("sửa tay", p.read_text())
        backups = list((self.d / ".agent-kit/backup").glob("*/.claude/agents/reviewer.md"))
        self.assertEqual(len(backups), 1)
        self.assertIn("sửa tay", backups[0].read_text())
        self.assertEqual((self.d / "eval/checks.sh").read_text(), "mine\n")
        self.assertEqual((self.d / "CLAUDE.md").read_text(), "# Công ty\nđừng đụng prod\n")

    def test_dry_run_writes_nothing(self):
        before = tree(self.d)
        r = self.up("--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(before, tree(self.d))
        self.assertIn("chưa ghi gì", r.stdout)

    def test_legacy_install_without_manifest_needs_force(self):
        (self.d / ".agent-kit-manifest.json").unlink()
        r = self.up()
        self.assertIn("Chưa có .agent-kit-manifest.json", r.stdout)
        self.assertNotIn("v9", (self.d / ".claude/agents/reviewer.md").read_text())
        self.up("--force")
        self.assertIn("v9", (self.d / ".claude/agents/reviewer.md").read_text())

    def test_upgrade_requires_existing_install(self):
        e = new_repo(self.tmp, "empty")
        r = self.install(e, KIT, "--upgrade")
        self.assertNotEqual(r.returncode, 0)


class TestInstalledKit(Base):
    def setUp(self):
        super().setUp()
        self.d = new_repo(self.tmp, "p")
        self.install(self.d)

    def kit(self, *args):
        return run([PY, "runner/kit.py", *args], self.d)

    def test_version_and_doctor_manifest_check(self):
        self.assertIn("agent-kit 0.", self.kit("--version").stdout)
        self.assertIn("khớp manifest", self.kit("doctor").stdout)
        hook = self.d / ".claude/hooks/guard_bash.py"
        hook.write_text(hook.read_text() + "\n# sửa\n")
        self.assertIn("bị sửa", self.kit("doctor").stdout)

    def test_menu_without_tty_prints_and_exits(self):
        r = self.kit()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("0. Thoát", r.stdout)

    def test_menu_json(self):
        m = json.loads(self.kit("menu", "--json").stdout)
        self.assertTrue(m["options"])
        for o in m["options"]:
            self.assertTrue({"command", "available", "ai", "key", "label"} <= set(o))

    def fake_run(self, name, tid, **kw):
        d = self.d / ".agent-kit/runs" / name / tid
        d.mkdir(parents=True)
        res = dict(id=tid, passed=True, reasons=[], attempt=1, host="m", agent="claude", cost=0.0,
                   seconds=60, finished=name)
        res.update(kw)
        (d / "result.json").write_text(json.dumps(res))

    def test_report_by_task(self):
        self.fake_run("2026-10-01_000001_m", "A-1", passed=False, cost=0.75,
                      reasons=["- sửa vùng bảo vệ: eval/checks.sh"], costs={"worker": 0.5, "reviewer": 0.25})
        self.fake_run("2026-10-02_000001_m", "A-1", cost=0.5, costs={"worker": 0.5})
        self.fake_run("2026-10-02_000001_m", "B-1")
        out = self.kit("report", "--by-task").stdout
        self.assertIn("A-1", out)
        self.assertLess(out.index("A-1"), out.index("B-1"), "task tốn nhất phải đứng đầu")
        self.assertIn("$1.25", out)
        self.assertIn("3 lượt chạy (2 PASS, 1 FAIL", out)
        self.assertIn("sửa vùng bảo vệ ×1", out)

    def test_report_by_task_empty(self):
        self.assertIn("Chưa có", self.kit("report", "--by-task").stdout)

    def test_spend_accumulates_per_role(self):
        code = ("import sys; sys.path.insert(0,'runner'); import kit; "
                "kit.spend('T','worker',0.5); kit.spend('T','reviewer',0.25); kit.spend('T','worker',0.25); kit.spend('T','x',0); "
                "print(kit.SPEND)")
        out = run([PY, "-c", code], self.d).stdout
        self.assertIn("'worker': 0.75", out)
        self.assertIn("'reviewer': 0.25", out)
        self.assertNotIn("'x'", out)

    def test_hooks_deny(self):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.d))
        r = run([PY, ".claude/hooks/guard_bash.py"], self.d, env, input='{"tool_input":{"command":"git push"}}')
        self.assertIn("deny", r.stdout)
        r = run([PY, ".claude/hooks/guard_files.py"], self.d, env,
                input='{"agent_type":"planner","tool_input":{"file_path":"src/a.py"}}')
        self.assertIn("deny", r.stdout)
        r = run([PY, ".claude/hooks/guard_files.py"], self.d, env,
                input=json.dumps({"tool_input": {"file_path": str(self.d / ".claude/rules/agent-kit.md")}}))
        self.assertIn("deny", r.stdout)


class TestSources(unittest.TestCase):
    def test_compile(self):
        files = [KIT / "install.py", KIT / "template/runner/kit.py", *sorted((KIT / "template/.claude/hooks").glob("*.py"))]
        for f in files:
            src = f.read_text()
            compile(src, str(f), "exec")

    def test_version_file_matches_changelog(self):
        v = (KIT / "template/runner/VERSION").read_text().strip()
        self.assertIn(f"## {v} ", (KIT / "CHANGELOG.md").read_text(), "VERSION chưa có mục trong CHANGELOG.md")


if __name__ == "__main__":
    unittest.main(verbosity=2)
