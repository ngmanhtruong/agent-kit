#!/usr/bin/env python3
"""Kiểm tra nhanh agent-kit (chỉ dùng thư viện chuẩn, không gọi AI, không cần mạng).

    python3 tests/smoke.py

Chạy trước khi commit thay đổi ở install.py, template/ hoặc kit.py. Không thuộc bản cài (không nằm trong template/).
Không thay cho thử end-to-end với agent giả (work PASS/FAIL, 3 chế độ): xem CLAUDE.md, mục "Kiểm tra trước khi commit".
"""
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
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


class FakeJev(http.server.BaseHTTPRequestHandler):
    """Giả lập api.typesafe.ai: trả xác suất cố định theo tên câu hỏi."""
    probs = {"dangerous": 0.0, "off_task": 0.0, "c": 1.0}
    status = 200
    hits = 0

    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        FakeJev.hits += 1
        self._send(FakeJev.status, {"models": ["jev-latest"]})

    def do_POST(self):
        FakeJev.hits += 1
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert self.headers["Authorization"] == "Bearer test-key", self.headers["Authorization"]
        assert req["model"] and all(q["type"] == "noul" for q in req["questions"].values())
        answers = {k: {"type": "noul", "noul": FakeJev.probs.get(k, FakeJev.probs["c"] if k.startswith("c") else 0.0)}
                   for k in req["questions"]}
        self._send(FakeJev.status, {"model": "jev-1", "answers": answers, "usage": {"input_tokens": 1, "output_tokens": 1}})


class TestJev(Base):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeJev)
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        super().setUp()
        FakeJev.probs = {"dangerous": 0.0, "off_task": 0.0, "c": 1.0}
        FakeJev.status, FakeJev.hits = 200, 0
        self.d = new_repo(self.tmp, "p")
        self.install(self.d)
        cfg = self.d / "runner/config.env"
        cfg.write_text(cfg.read_text().replace("GH_SYNC=1", "GH_SYNC=0"))

    def env(self, **kw):
        e = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.d), JEV_ENABLED="1", TYPESAFE_API_KEY="test-key",
                 JEV_BASE_URL=self.url, JEV_TIMEOUT_S="2")
        e.update(kw)
        return e

    def hook(self, cmd="ls -la", **kw):
        return run([PY, ".claude/hooks/guard_bash.py"], self.d, self.env(**kw),
                   input=json.dumps({"tool_input": {"command": cmd}})).stdout

    def test_client_returns_probabilities_and_none_on_error(self):
        code = "import sys; sys.path.insert(0,'runner'); import jev; print(jev.ask('x', {'dangerous':'q'}), jev.last_error)"
        FakeJev.probs["dangerous"] = 0.4
        self.assertIn("{'dangerous': 0.4}", run([PY, "-c", code], self.d, self.env()).stdout)
        FakeJev.status = 500
        out = run([PY, "-c", code], self.d, self.env()).stdout
        self.assertIn("None", out)
        self.assertIn("HTTP 500", out)

    def test_hook_blocks_dangerous_and_allows_safe(self):
        FakeJev.probs["dangerous"] = 0.95
        self.assertIn("deny", self.hook())
        FakeJev.probs["dangerous"] = 0.1
        self.assertEqual(self.hook().strip(), "")

    def test_hook_blocks_off_task_only_with_a_task_file(self):
        FakeJev.probs["off_task"] = 0.95
        self.assertEqual(self.hook().strip(), "", "không có task thì không hỏi off_task")
        task = self.d / "t.md"
        task.write_text("# Mục tiêu\nlàm X\n")
        self.assertIn("deny", self.hook(AGENT_KIT_TASK_FILE=str(task)))

    def test_hook_falls_back_when_jev_is_down_unless_block(self):
        FakeJev.status = 500
        self.assertEqual(self.hook().strip(), "")
        self.assertIn("deny", self.hook(JEV_ON_ERROR="block"))
        self.assertIn("HTTP 500", (self.d / ".agent-kit/logs/guard.log").read_text())

    def test_disabled_makes_no_network_call_and_regex_still_blocks(self):
        self.assertEqual(self.hook(JEV_ENABLED="0").strip(), "")
        self.assertEqual(FakeJev.hits, 0)
        FakeJev.probs["dangerous"] = 0.0
        self.assertIn("deny", self.hook("git push", JEV_ENABLED="0"))

    def test_no_key_means_disabled(self):
        self.assertEqual(self.hook(TYPESAFE_API_KEY="").strip(), "")
        self.assertEqual(FakeJev.hits, 0)

    def test_with_jev_flag_sets_config_and_is_idempotent(self):
        r = self.install(self.d, KIT, "--with-jev")
        self.assertIn("TYPESAFE_API_KEY", r.stdout)
        self.install(self.d, KIT, "--with-jev")
        text = (self.d / "runner/config.env").read_text()
        self.assertEqual(text.count("JEV_ENABLED=1"), 1)
        self.assertNotIn("JEV_ENABLED=0", text)

    def kit(self, *args, **env):
        return run([PY, "runner/kit.py", *args], self.d, self.env(**env))

    def test_kit_jev_status_is_read_only(self):
        cfg = self.d / "runner/config.env"
        before = cfg.read_text()
        out = self.kit("jev", JEV_ENABLED="0").stdout
        self.assertIn("TẮT", out)
        self.assertIn("đã nối Jev", out)
        self.assertEqual(before, cfg.read_text())

    def test_kit_jev_on_needs_confirmation_without_tty_then_off(self):
        cfg = self.d / "runner/config.env"
        r = self.kit("jev", "on")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--yes", r.stdout + r.stderr)
        self.assertIn("JEV_ENABLED=0", cfg.read_text(), "chưa xác nhận thì không đổi gì")
        r = self.kit("jev", "on", "--yes")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(cfg.read_text().count("JEV_ENABLED=1"), 1)
        self.assertIn("BẬT", r.stdout)
        self.kit("jev", "off")
        text = cfg.read_text()
        self.assertEqual(text.count("JEV_ENABLED="), 1)
        self.assertIn("JEV_ENABLED=0", text)

    def test_kit_jev_on_warns_when_key_missing(self):
        r = self.kit("jev", "on", "--yes", TYPESAFE_API_KEY="", JEV_API_KEY="")
        self.assertIn("thiếu khoá", r.stdout)

    def test_doctor_hints_how_to_enable_when_off(self):
        out = self.kit("doctor", JEV_ENABLED="0").stdout
        self.assertIn("kit.py jev on", out)

    def test_menu_lists_jev_option(self):
        m = json.loads(self.kit("menu", "--json").stdout)
        self.assertIn("j", [o["key"] for o in m["options"] if o["available"]])

    def test_with_jev_warns_when_project_is_not_wired(self):
        (self.d / ".claude/hooks/guard_bash.py").write_text("# old hook without the Jev bridge\n")
        r = self.install(self.d, KIT, "--with-jev")
        self.assertIn("CHƯA có tác dụng", r.stdout)
        self.assertIn("--upgrade --with-jev", r.stdout)
        ok = new_repo(self.tmp, "ok")
        self.install(ok)
        self.assertNotIn("CHƯA có tác dụng", self.install(ok, KIT, "--with-jev").stdout)

    def test_doctor_reports_jev(self):
        out = run([PY, "runner/kit.py", "doctor"], self.d, self.env()).stdout
        self.assertIn("Jev bật", out)
        self.assertGreater(FakeJev.hits, 0)
        out = run([PY, "runner/kit.py", "doctor"], self.d, self.env(TYPESAFE_API_KEY="")).stdout
        self.assertIn("thiếu khoá", out)

    def test_approve_warns_about_unverifiable_acceptance(self):
        (self.d / "tasks/x").mkdir(parents=True, exist_ok=True)
        (self.d / "tasks/x/T-1.md").write_text(
            "---\nid: T-1\ntype: task\nepic: X\nstatus: draft\nholdout: false\ndesign: design/x\n---\n"
            "# Mục tiêu\nlàm X\n# Acceptance\n- [ ] trả về 200 khi gọi /ping\n- [ ] code đẹp\n")
        FakeJev.probs["c"] = 0.2
        r = run([PY, "runner/kit.py", "approve", "T-1"], self.d, self.env())
        self.assertIn("khó kiểm chứng", r.stdout)
        self.assertIn("T-1 approved", r.stdout, "chỉ cảnh báo, không chặn")
        self.assertIn("status: approved", (self.d / "tasks/x/T-1.md").read_text())


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
