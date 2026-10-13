#!/usr/bin/env python3
"""agent-kit runner: design → tasks → agents → graded PRs. Chạy với mọi agent.

Agent (đặt AGENT trong runner/config.env, mặc định auto):
  claude  Claude Code CLI — có rào cứng (hooks), chạy tự động trọn task
  cli     agent CLI khác qua AGENT_CMD (Copilot CLI, Codex, Gemini...) — chạy tự động
  chat    không có CLI (Copilot Chat trong VS Code...) — agent trong chat tự chạy
          `kit.py work`, làm bước nó in ra, rồi chạy lại cho tới khi xong
  auto    claude nếu có → cli nếu có AGENT_CMD → chat

Kiểm tra (chỉ đọc — an toàn chạy trên bất kỳ máy nào, bất kỳ lúc nào):
  python3 runner/kit.py status [--offline]       bảng trạng thái mọi task, gộp từ mọi máy
  python3 runner/kit.py report [--last N]        tóm tắt các phiên gần nhất (mọi máy)
  python3 runner/kit.py report --task <id>       chi tiết một task: lý do, log, báo cáo, nhánh
  python3 runner/kit.py doctor                   kiểm tra toàn bộ: cài đặt, agent, tasks, đồng bộ

Làm việc:
  python3 runner/kit.py plan design/<feature>    planner chia design thành tasks nháp
  python3 runner/kit.py approve <id|epic|all>    duyệt nháp → GitHub Issue (không gọi AI)
  python3 runner/kit.py work [--max N] [--task ID]   phiên làm việc: làm các task sẵn sàng
  python3 runner/kit.py work --abort             (chế độ chat) huỷ task đang làm, không tính lượt
  python3 runner/kit.py sync                     PR merged → done; cập nhật và chia sẻ trạng thái
  python3 runner/kit.py import                   GitHub Issue nhãn 'agent-ready' → task nháp
  python3 runner/kit.py set <id> <status>        đổi trạng thái tay (vd: failed → queued)
  python3 runner/kit.py doctor --fix             sửa các lỗi an toàn (task kẹt 'running', sync)

Dữ liệu dùng chung giữa các máy nằm trên nhánh git riêng `agent-kit/log`
(không bao giờ đụng nhánh code): mỗi máy chỉ ghi file của chính nó, nên không
xung đột; đọc thì gộp theo bản ghi mới nhất. Spec (tasks/*.md) chỉ người sửa.
Chỉ dùng thư viện chuẩn của Python 3.8+.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
TASKS = ROOT / "tasks"
STATE_DIR = ROOT / ".agent-kit"
STATE_FILE = STATE_DIR / "state.json"
STATUSES = ["draft", "queued", "running", "review", "done", "failed"]
LIMIT_RE = re.compile(r"usage limit|rate.?limit|limit reached|quota", re.I)


# ───────────────────────── config ─────────────────────────
def load_config() -> dict:
    cfg = {
        "BASE_BRANCH": "main", "MAX_TASKS": "3", "TASK_TIMEOUT_MIN": "60",
        "MAX_ATTEMPTS": "2", "MAX_BUDGET_USD": "", "CLAUDE_BIN": "claude",
        "HOLDOUT_DIR": "", "HOLDOUT_CMD": "", "REVIEW": "1",
        "GH_SYNC": "0", "GIT_PULL": "1", "PUBLISH": "1",
        "LOG_BRANCH": "agent-kit/log", "MACHINE_NAME": "", "LOCK_HOURS": "12",
        "STALE_RUN_HOURS": "",
        "TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": "",
        "WORKTREE_ROOT": str(ROOT.parent / f".agent-worktrees-{ROOT.name}"),
    }
    f = ROOT / "runner" / "config.env"
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = os.path.expanduser(os.path.expandvars(v.strip().strip('"').strip("'")))
    return cfg


CFG = load_config()
HOST = re.sub(r"[^A-Za-z0-9_.-]", "-", CFG.get("MACHINE_NAME") or socket.gethostname().split(".")[0]) or "host"
LOG_BRANCH = CFG["LOG_BRANCH"]
LOG_REF = f"refs/remotes/origin/{LOG_BRANCH}"


def flag(name: str) -> bool:
    return CFG.get(name, "0") == "1"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def age_hours(iso: str) -> float:
    try:
        t = dt.datetime.fromisoformat(iso)
        if t.tzinfo is None:
            t = t.replace(tzinfo=dt.timezone.utc)
        return (dt.datetime.now(dt.timezone.utc) - t).total_seconds() / 3600
    except Exception:
        return float("inf")


def local_time(iso: str) -> str:
    try:
        return dt.datetime.fromisoformat(iso).astimezone().strftime("%m-%d %H:%M")
    except Exception:
        return "-"


# ───────────────────────── shell helpers ─────────────────────────
def run(cmd, cwd=ROOT, timeout=None, env=None, check=False, shell=False):
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                       timeout=timeout, env=env, shell=shell)
    if check and r.returncode != 0:
        raise RuntimeError(f"{cmd} failed:\n{r.stdout}\n{r.stderr}")
    return r


def git(args, cwd=ROOT, check=True):
    return run(["git", *args], cwd=cwd, check=check)


def gh(args, check=True):
    return run(["gh", *args], check=check)


def has_origin() -> bool:
    return "origin" in git(["remote"], check=False).stdout.split()


# ───────────────────────── tasks (markdown) ─────────────────────────
def parse_task(path: Path):
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        return None
    meta = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        v = re.sub(r"\s+#.*$", "", v).strip()
        if v.startswith("[") and v.endswith("]"):
            v = [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
        elif v.lower() in ("true", "false"):
            v = v.lower() == "true"
        elif re.fullmatch(r"-?\d+", v):
            v = int(v)
        else:
            v = v.strip("'\"")
        meta[k.strip()] = v
    meta.setdefault("depends_on", [])
    meta.setdefault("priority", 9)
    meta.setdefault("type", "task")
    meta["_path"] = path
    meta["_body"] = m.group(2)
    meta["_sha"] = hashlib.sha1(text.encode()).hexdigest()[:10]
    return meta


def set_front(path: Path, key: str, value) -> None:
    """Update one frontmatter key in place (used only by approve/import, on the human's machine)."""
    text = path.read_text()
    line = f"{key}: {value}"
    pat = re.compile(rf"^{re.escape(key)}:.*$", re.M)
    head, sep, body = text.partition("\n---")
    head = pat.sub(line, head) if pat.search(head) else head + "\n" + line
    path.write_text(head + sep + body)


def load_tasks(problems: list = None) -> dict:
    out = {}
    for p in sorted(TASKS.rglob("*.md")) if TASKS.exists() else []:
        if p.name.startswith("_") or p.name == "README.md":
            continue
        t = parse_task(p)
        if not t or not t.get("id"):
            if problems is not None:
                problems.append(f"{p.relative_to(ROOT)}: thiếu frontmatter hoặc id")
            continue
        tid = str(t["id"])
        if tid in out and problems is not None:
            problems.append(f"id trùng '{tid}': {out[tid]['_path'].relative_to(ROOT)} và {p.relative_to(ROOT)}")
        out[tid] = t
    return out


def acceptance_ok(t: dict) -> bool:
    sec = re.search(r"# Acceptance.*?\n(.*?)(\n# |\Z)", t["_body"], re.S)
    if not sec:
        return False
    items = [l for l in sec.group(1).splitlines()
             if re.match(r"\s*- \[.\]", l) and "<!--" not in l and "checks.sh" not in l]
    return len(items) > 0


# ───────────────────────── shared log branch ─────────────────────────
def fetch_log() -> bool:
    """Update the remote-tracking ref of the log branch. Never touches the working tree."""
    if not has_origin():
        return False
    return git(["fetch", "-q", "origin", f"+refs/heads/{LOG_BRANCH}:{LOG_REF}"],
               check=False).returncode == 0


def log_ref_exists() -> bool:
    return git(["rev-parse", "-q", "--verify", LOG_REF], check=False).returncode == 0


def log_ls(prefix: str) -> list:
    if not log_ref_exists():
        return []
    r = git(["ls-tree", "-r", "--name-only", LOG_REF, "--", prefix], check=False)
    return [x for x in r.stdout.splitlines() if x]


def log_read(path: str) -> str:
    r = git(["show", f"{LOG_REF}:{path}"], check=False)
    return r.stdout if r.returncode == 0 else ""


def remote_hosts() -> dict:
    """host → {"meta": {...}, "tasks": {...}} as published on the log branch."""
    out = {}
    for p in log_ls("state/"):
        try:
            out[Path(p).stem] = json.loads(log_read(p))
        except Exception:
            pass
    return out


def remote_lock() -> dict:
    try:
        return json.loads(log_read("lock.json")) if log_ref_exists() else {}
    except Exception:
        return {}


class LockHeld(Exception):
    pass


class LogBranch:
    """Write side of the log branch. Each host writes only its own files,
    so concurrent pushes from different machines never conflict; a rejected
    push is simply retried on top of the new remote tip."""

    def __init__(self):
        self.dir = Path(CFG["WORKTREE_ROOT"]) / "_agent-kit-log"
        self.tmp_branch = f"agent-kit-log-tmp-{HOST}"

    def enabled(self) -> bool:
        return flag("PUBLISH") and has_origin()

    def _cleanup(self):
        if self.dir.exists():
            git(["worktree", "remove", "--force", str(self.dir)], check=False)
        git(["worktree", "prune"], check=False)
        git(["branch", "-D", self.tmp_branch], check=False)

    def _prepare(self):
        self._cleanup()
        self.dir.parent.mkdir(parents=True, exist_ok=True)
        if fetch_log():
            git(["worktree", "add", "-q", "--detach", str(self.dir), LOG_REF])
        else:  # first publish ever: start an orphan branch with no code in it
            git(["worktree", "add", "-q", "--detach", str(self.dir), "HEAD"])
            git(["checkout", "-q", "--orphan", self.tmp_branch], cwd=self.dir)
            git(["rm", "-rfq", "."], cwd=self.dir, check=False)

    def commit(self, msg: str, mutate) -> bool:
        if not self.enabled():
            return False
        try:
            for attempt in range(4):
                self._prepare()
                mutate(self.dir)  # may raise LockHeld
                git(["add", "-A"], cwd=self.dir)
                if not git(["status", "--porcelain"], cwd=self.dir).stdout.strip():
                    return True
                git(["-c", "core.hooksPath=/dev/null", "-c", "user.name=agent-kit",
                     "-c", "user.email=agent-kit@localhost", "commit", "-qm", f"[{HOST}] {msg}"],
                    cwd=self.dir)
                if git(["push", "-q", "origin", f"HEAD:refs/heads/{LOG_BRANCH}"],
                       cwd=self.dir, check=False).returncode == 0:
                    return True
                time.sleep(2 + attempt * 3)
            print(f"! không push được nhánh {LOG_BRANCH} sau 4 lần thử")
            return False
        finally:
            self._cleanup()


LOG = LogBranch()


# ───────────────────────── runtime state ─────────────────────────
def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def save_state(st: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(st, indent=2, ensure_ascii=False))


def merge_states(local: dict, hosts: dict) -> dict:
    """Last-writer-wins per task, by the 'updated' UTC timestamp."""
    out = {k: dict(v) for k, v in local.items()}
    for data in hosts.values():
        for tid, rec in (data.get("tasks") or {}).items():
            cur = out.get(tid)
            if not cur or str(rec.get("updated", "")) > str(cur.get("updated", "")):
                out[tid] = dict(rec)
    return out


def view_state(fetch: bool = True):
    """Merged view of local + every machine's published state. Read-only."""
    fetched = fetch_log() if fetch else False
    hosts = remote_hosts()
    return merge_states(load_state(), hosts), hosts, fetched


def status_of(t: dict, st: dict) -> str:
    s = st.get(str(t["id"]), {}).get("status")
    if s:
        return s
    return "queued" if t.get("status") == "approved" else "draft"


def set_status(t: dict, st: dict, status: str, **extra) -> None:
    rec = st.setdefault(str(t["id"]), {})
    old = rec.get("status")
    rec.update(status=status, updated=now(), host=HOST, **extra)
    save_state(st)
    if flag("GH_SYNC") and t.get("issue") and old != status:
        gh(["issue", "edit", str(t["issue"]), "--add-label", f"status:{status}"]
           + (["--remove-label", f"status:{old}"] if old else []), check=False)


def publish(st: dict, run_dir: Path = None, meta: dict = None, msg: str = "state") -> bool:
    """Share this machine's state (and a run's logs) on the log branch."""
    def mutate(d: Path):
        sf = d / "state" / f"{HOST}.json"
        sf.parent.mkdir(parents=True, exist_ok=True)
        try:
            old_meta = json.loads(sf.read_text()).get("meta", {})
        except Exception:
            old_meta = {}
        m = dict(old_meta, host=HOST, last_seen=now(), **(meta or {}))
        sf.write_text(json.dumps({"meta": m, "tasks": st}, indent=2, ensure_ascii=False))
        if run_dir and run_dir.exists():
            dest = d / "runs" / HOST / run_dir.name
            shutil.copytree(str(run_dir), str(dest), dirs_exist_ok=True)
    return LOG.commit(msg, mutate)


def acquire_lock() -> None:
    def mutate(d: Path):
        p = d / "lock.json"
        if p.exists():
            try:
                cur = json.loads(p.read_text())
            except Exception:
                cur = {}
            if cur.get("host") != HOST and age_hours(cur.get("started", "")) < float(CFG["LOCK_HOURS"]):
                raise LockHeld(f"{cur.get('host')} đang chạy từ {local_time(cur.get('started', ''))}")
        p.write_text(json.dumps({"host": HOST, "pid": os.getpid(), "started": now()}))
    LOG.commit("lock", mutate)


def release_lock() -> None:
    def mutate(d: Path):
        p = d / "lock.json"
        if p.exists():
            try:
                if json.loads(p.read_text()).get("host") == HOST:
                    p.unlink()
            except Exception:
                p.unlink()
    LOG.commit("unlock", mutate)


# ───────────────────────── agent drivers ─────────────────────────
# kit.py works with any agent:
#   claude — Claude Code CLI (hooks = hard guardrails, subagents by name)
#   cli    — any other agent CLI via AGENT_CMD (e.g. Copilot CLI, Codex, Gemini)
#   chat   — no CLI at all (e.g. Copilot Chat in VS Code): `kit.py work` runs one
#            step at a time and prints what the chat agent must do next.
class NeedsChat(Exception):
    pass


class LimitHit(Exception):
    pass


def claude_available() -> bool:
    b = CFG["CLAUDE_BIN"]
    return bool(shutil.which(b)) or Path(b).expanduser().is_file()


def agent_mode() -> str:
    m = (CFG.get("AGENT") or "auto").strip().lower()
    if m == "auto":
        return "claude" if claude_available() else ("cli" if CFG.get("AGENT_CMD") else "chat")
    return m if m in ("claude", "cli", "chat") else "chat"


def role_guide(role: str) -> str:
    """The role's instructions from .claude/agents/<role>.md, without frontmatter."""
    p = ROOT / ".claude" / "agents" / f"{role}.md"
    text = p.read_text() if p.exists() else ""
    return re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S).strip()


def _claude(prompt: str, role: str, cwd: Path, agent: str, timeout_min: int) -> dict:
    cmd = [CFG["CLAUDE_BIN"], "-p", prompt, "--output-format", "json",
           "--permission-mode", "acceptEdits", "--permission-prompts", "none"]
    if agent:
        cmd += ["--agent", agent]
    if CFG.get("MAX_BUDGET_USD"):
        cmd += ["--max-budget-usd", CFG["MAX_BUDGET_USD"]]
    return _exec(cmd, cwd, role, timeout_min, parse_json=True)


def _cli(prompt: str, role: str, cwd: Path, agent: str, timeout_min: int) -> dict:
    tmpl = CFG.get("AGENT_CMD", "").strip()
    if not tmpl:
        raise SystemExit("AGENT=cli nhưng AGENT_CMD trống trong runner/config.env")
    full = (role_guide(agent) + "\n\n---\n\n" + prompt) if agent else prompt
    parts = shlex.split(tmpl)
    if any("{prompt}" in x for x in parts):
        return _exec([x.replace("{prompt}", full) for x in parts], cwd, role, timeout_min)
    return _exec(parts, cwd, role, timeout_min, stdin=full)


def _exec(cmd, cwd, role, timeout_min, parse_json=False, stdin=None) -> dict:
    env = dict(os.environ, AGENT_KIT_ROLE=role, AGENT_KIT_BASE=CFG["BASE_BRANCH"],
               AGENT_KIT_HOLDOUT_DIR=CFG.get("HOLDOUT_DIR", ""))
    try:
        r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, env=env,
                           input=stdin, timeout=timeout_min * 60)
    except subprocess.TimeoutExpired:
        return {"ok": False, "limit": False, "result": "timeout", "cost": 0}
    except FileNotFoundError:
        raise SystemExit(f"Không chạy được agent: không tìm thấy `{cmd[0]}`")
    raw = r.stdout + "\n" + r.stderr
    j = {}
    if parse_json:
        try:
            j = json.loads(r.stdout)
        except Exception:
            j = {}
    failed = r.returncode != 0 or bool(j.get("is_error"))
    return {"ok": not failed, "limit": failed and bool(LIMIT_RE.search(raw)),
            "result": str(j.get("result", r.stdout.strip() or raw)), "cost": j.get("total_cost_usd", 0) or 0}


def call_agent(prompt: str, role: str, cwd: Path, agent: str = "", timeout_min: int = 60) -> dict:
    mode = agent_mode()
    if mode == "claude":
        return _claude(prompt, role, cwd, agent, timeout_min)
    if mode == "cli":
        return _cli(prompt, role, cwd, agent, timeout_min)
    raise NeedsChat()


# ───────────────────────── read-only commands ─────────────────────────
def table(rows):
    w = [max(len(str(r[i])) for r in rows) for i in range(len(rows[0]))]
    for r in rows:
        print("  ".join(str(c).ljust(w[i]) for i, c in enumerate(r)).rstrip())


def stale_running(rec: dict, lock: dict) -> bool:
    if rec.get("status") != "running":
        return False
    held = lock.get("host") == rec.get("host") and age_hours(lock.get("started", "")) < float(CFG["LOCK_HOURS"])
    if rec.get("host") == HOST and ((STATE_DIR / "work.lock").exists() or SESSION.exists()):
        held = True  # this machine is running it right now
    return not held and age_hours(rec.get("updated", "")) > 1


def cmd_status(args):
    st, hosts, fetched = view_state(fetch=not getattr(args, "offline", False))
    tasks, lock = load_tasks(), remote_lock()
    rows = [("ID", "TYPE", "STATUS", "TRY", "DEPENDS", "MÁY", "CẬP NHẬT", "PR / NHÁNH")]
    counts = {}
    for t in sorted(tasks.values(), key=lambda x: (str(x.get("epic", "")), x["priority"], str(x["id"]))):
        rec = st.get(str(t["id"]), {})
        s = status_of(t, st)
        if stale_running(rec, lock):
            s = "running?"
        counts[s] = counts.get(s, 0) + 1
        rows.append((t["id"], t["type"], s, rec.get("attempts", 0), ",".join(t["depends_on"]) or "-",
                     rec.get("host", "-"), local_time(rec.get("updated", "")),
                     rec.get("pr") or rec.get("branch") or "-"))
    if len(rows) == 1:
        print("Chưa có task nào trong tasks/.")
    else:
        table(rows)
    print("\nTổng: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) if counts else "")
    for h, d in sorted(hosts.items()):
        m = d.get("meta", {})
        last = local_time(m["last_run"]) if m.get("last_run") else "chưa chạy phiên nào"
        print(f"Máy {h}: phiên cuối {last} · cập nhật {local_time(m.get('last_seen', ''))}")
    if lock:
        print(f"🔒 Đang chạy: {lock.get('host')} từ {local_time(lock.get('started', ''))}")
    sess = load_session()
    if sess:
        print(f"▶ Phiên chat đang mở trên máy này: task {sess.get('task')}, bước '{sess.get('stage')}'. "
              f"Tiếp tục: python3 runner/kit.py work · Huỷ: python3 runner/kit.py work --abort")
    if not fetched and not getattr(args, "offline", False):
        print("(!) Không đọc được nhánh log từ origin — chỉ hiển thị dữ liệu trên máy này.")
    if counts.get("running?"):
        print("(!) 'running?' = task kẹt (lượt chạy đã chết). Chạy: python3 runner/kit.py doctor --fix")


def run_dirs() -> list:
    """[(name, host, source)] newest first; source 'remote' (log branch) or 'local'."""
    seen, out = set(), []
    for p in log_ls("runs/"):
        parts = p.split("/")
        if len(parts) >= 4 and (parts[1], parts[2]) not in seen:
            seen.add((parts[1], parts[2]))
            out.append((parts[2], parts[1], "remote"))
    for d in (STATE_DIR / "runs").glob("*") if (STATE_DIR / "runs").exists() else []:
        if d.is_dir() and (HOST, d.name) not in seen:
            out.append((d.name, HOST, "local"))
    return sorted(out, reverse=True)


def run_file(host: str, name: str, source: str, rel: str) -> str:
    if source == "remote":
        return log_read(f"runs/{host}/{name}/{rel}")
    p = STATE_DIR / "runs" / name / rel
    return p.read_text() if p.exists() else ""


def tail(text: str, n: int = 25) -> str:
    lines = text.rstrip().splitlines()
    return "\n".join(("    " + l) for l in lines[-n:]) if lines else "    (trống)"


def cmd_report(args):
    fetch_log()
    runs = run_dirs()
    if not runs:
        print("Chưa có lượt chạy nào.")
        return
    if args.task:
        tid = args.task
        hits = [(n, h, s) for n, h, s in runs if run_file(h, n, s, f"{tid}/review.json")]
        if not hits:
            print(f"Không tìm thấy lượt chạy nào của {tid}.")
            return
        st, _, _ = view_state(fetch=False)
        rec = st.get(tid, {})
        print(f"══ {tid} · trạng thái hiện tại: {rec.get('status', '-')} · thử {rec.get('attempts', 0)} lần")
        if rec.get("pr"):
            print(f"PR: {rec['pr']}")
        for n, h, s in hits[: args.last or 3]:
            meta = {}
            try:
                meta = json.loads(run_file(h, n, s, f"{tid}/result.json") or "{}")
            except Exception:
                pass
            print(f"\n── Lượt {n} trên {h} · {'PASS' if meta.get('passed') else 'FAIL'}"
                  f" · nhánh {meta.get('branch', '-')} · base {meta.get('base_sha', '-')}"
                  f" · spec {meta.get('spec_sha', '-')}")
            for r in meta.get("reasons", []):
                print(f"  ✗ {r}")
            review = run_file(h, n, s, f"{tid}/review.json")
            print("  Reviewer:\n" + tail(review, 20))
            for f, label in [(f"{tid}.md", "Báo cáo worker"), ("checks.log", "checks.sh"),
                             ("holdout.log", "Test ẩn"), ("worker.txt", "Worker (cuối)")]:
                txt = run_file(h, n, s, f"{tid}/{f}")
                if txt:
                    print(f"  {label}:\n" + tail(txt, 30 if f.endswith(".md") else 15))
        return
    for n, h, s in runs[: args.last or 3]:
        print(f"══ {n} · máy {h}{' (chỉ có trên máy này)' if s == 'local' else ''}")
        print(run_file(h, n, s, "SUMMARY.md").strip() or "  (không có SUMMARY.md — lượt chạy bị ngắt?)")
        print()
    print("Chi tiết một task: python3 runner/kit.py report --task <id>")


def claude_version_ok():
    if not shutil.which(CFG["CLAUDE_BIN"]) and not Path(CFG["CLAUDE_BIN"]).exists():
        return None, "không tìm thấy"
    r = run([CFG["CLAUDE_BIN"], "--version"], check=False)
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", r.stdout)
    if not m:
        return None, r.stdout.strip() or "không đọc được phiên bản"
    v = tuple(int(x) for x in m.groups())
    return v >= (2, 1, 295), ".".join(m.groups())


def find_cycle(tasks: dict):
    color = {}

    def visit(n, path):
        color[n] = 1
        for d in tasks[n]["depends_on"]:
            if d not in tasks:
                continue
            if color.get(d) == 1:
                return path + [d]
            if not color.get(d):
                c = visit(d, path + [d])
                if c:
                    return c
        color[n] = 2
        return None

    for n in tasks:
        if not color.get(n):
            c = visit(n, [n])
            if c:
                return c
    return None


def cmd_doctor(args):
    out = {"✗": 0, "!": 0}

    def say(mark, msg):
        if mark in out:
            out[mark] += 1
        print(f"  {mark} {msg}")

    print("Cài đặt")
    if (ROOT / "runner" / "config.env").exists():
        say("✓", "runner/config.env có")
    else:
        say("✗", "thiếu runner/config.env → cp runner/config.env.example runner/config.env")
    mode = agent_mode()
    if mode == "claude":
        ok, v = claude_version_ok()
        say("✓" if ok else ("✗" if ok is None else "!"), f"agent: Claude Code {v}" + ("" if ok else " (cần ≥ 2.1.295)"))
    elif mode == "cli":
        exe = (shlex.split(CFG.get("AGENT_CMD", "")) or [""])[0]
        say("✓" if exe and shutil.which(exe) else "✗", f"agent: CLI `{exe or '(AGENT_CMD trống)'}`"
            + ("" if exe and shutil.which(exe) else " không tìm thấy") + " — không có rào cứng (hooks), kit.py vẫn chấm và chặn sửa vùng bảo vệ")
    else:
        say("✓", "agent: chế độ chat (Copilot Chat, ...) — chạy `python3 runner/kit.py work` trong chat, làm theo từng bước nó in ra")
    if flag("GH_SYNC"):
        r = run(["gh", "auth", "status"], check=False) if shutil.which("gh") else None
        say("✓" if r and r.returncode == 0 else "✗", "gh đã đăng nhập" if r and r.returncode == 0 else "gh chưa cài/chưa đăng nhập (GH_SYNC=1)")
    tracked = git(["ls-files", ".claude/settings.json", "eval/checks.sh", "runner/kit.py"], check=False).stdout.split()
    say("✓" if len(tracked) == 3 else "✗", "khung agent-kit đã commit" if len(tracked) == 3
        else "khung agent-kit chưa commit đủ (.claude/, eval/, runner/) → worker sẽ chạy không rào chắn")
    chk = ROOT / "eval" / "checks.sh"
    if chk.exists() and re.search(r"^\s*step ", chk.read_text(), re.M):
        say("✓", "eval/checks.sh đã cấu hình")
    else:
        say("✗", "eval/checks.sh chưa có bước nào → mọi task sẽ FAIL")
    if has_origin():
        say("✓", "có remote origin")
    else:
        say("!", "không có remote origin → các máy không chia sẻ được trạng thái")

    print("\nĐồng bộ giữa các máy")
    fetched = fetch_log()
    if fetched:
        say("✓", f"đọc được nhánh {LOG_BRANCH}")
    elif has_origin():
        say("!", f"chưa có nhánh {LOG_BRANCH} trên origin (sẽ được tạo ở phiên `work` đầu tiên)")
    base = CFG["BASE_BRANCH"]
    if has_origin() and git(["fetch", "-q", "origin", base], check=False).returncode == 0:
        behind = git(["rev-list", "--count", f"HEAD..origin/{base}"], check=False).stdout.strip()
        ahead = git(["rev-list", "--count", f"origin/{base}..HEAD"], check=False).stdout.strip()
        if behind not in ("", "0"):
            say("!", f"máy này chậm {behind} commit so với origin/{base} → git pull")
        elif ahead not in ("", "0"):
            say("!", f"máy này có {ahead} commit chưa push → git push (máy khác chạy `work` sẽ không thấy)")
        else:
            say("✓", f"khớp với origin/{base}")
    dirty = git(["status", "--porcelain", "--", "tasks"], check=False).stdout.strip()
    if dirty:
        say("!", "tasks/ có thay đổi chưa commit → máy khác chạy `work` sẽ không thấy")
    hosts = remote_hosts()
    for h, d in sorted(hosts.items()):
        last = d.get("meta", {}).get("last_run", "")
        if last and CFG.get("STALE_RUN_HOURS") and age_hours(last) > float(CFG["STALE_RUN_HOURS"]):
            say("!", f"máy {h}: phiên cuối {local_time(last)}, quá {CFG['STALE_RUN_HOURS']} giờ — lịch chạy tự động có còn hoạt động?")
        elif last:
            say("✓", f"máy {h}: phiên cuối {local_time(last)}")
    lock = remote_lock()
    if lock:
        if age_hours(lock.get("started", "")) < float(CFG["LOCK_HOURS"]):
            say("✓", f"đang chạy trên {lock.get('host')} từ {local_time(lock.get('started', ''))}")
        else:
            say("!", f"khoá cũ của {lock.get('host')} ({local_time(lock.get('started', ''))}) — lượt đó đã chết; sẽ tự hết hạn")

    print("\nTasks")
    problems = []
    tasks = load_tasks(problems)
    for p in problems:
        say("✗", p)
    for t in tasks.values():
        for d in t["depends_on"]:
            if d not in tasks:
                say("✗", f"{t['id']}: depends_on '{d}' không tồn tại")
    cyc = find_cycle(tasks)
    if cyc:
        say("✗", "vòng phụ thuộc: " + " → ".join(cyc))
    for t in tasks.values():
        if t.get("status") == "approved" and t["type"] != "epic":
            if not acceptance_ok(t):
                say("✗", f"{t['id']}: đã duyệt nhưng Acceptance trống")
            if flag("GH_SYNC") and not t.get("issue"):
                say("!", f"{t['id']}: đã duyệt nhưng chưa có GitHub Issue")
    if not problems and tasks:
        say("✓", f"{len(tasks)} task đọc được")

    print("\nTrạng thái chạy")
    st = merge_states(load_state(), hosts)
    stale, remote_heads = [], None
    if has_origin():
        r = git(["ls-remote", "--heads", "origin", "agent/*"], check=False)
        remote_heads = {l.split("refs/heads/")[-1] for l in r.stdout.splitlines()}
    for t in tasks.values():
        tid, rec = str(t["id"]), st.get(str(t["id"]), {})
        s = rec.get("status")
        if stale_running(rec, lock):
            stale.append(t)
            say("✗", f"{tid}: kẹt 'running' từ {local_time(rec.get('updated', ''))} trên {rec.get('host')} → doctor --fix")
        if s in ("review", "failed") and rec.get("spec_sha") and rec["spec_sha"] != t["_sha"]:
            say("!", f"{tid}: spec đã sửa SAU khi agent chạy → kết quả có thể không còn đúng ý (approve/set lại)")
        if s == "failed":
            say("!", f"{tid}: failed sau {rec.get('attempts', 0)} lần → xem: kit.py report --task {tid}")
        if remote_heads is not None and rec.get("branch") and s in ("review", "failed") \
                and rec["branch"] not in remote_heads and flag("PUBLISH"):
            say("!", f"{tid}: nhánh {rec['branch']} không có trên origin")
        if s == "review" and rec.get("pr") and flag("GH_SYNC"):
            r = gh(["pr", "view", rec["pr"], "--json", "state", "-q", ".state"], check=False)
            if r.stdout.strip() in ("MERGED", "CLOSED"):
                say("!", f"{tid}: PR đã {r.stdout.strip().lower()} nhưng chưa sync → kit.py sync")
    if not stale and st:
        say("✓", "không có task kẹt")
    blocks = STATE_DIR / "logs" / "guard.log"
    if blocks.exists():
        n = len(blocks.read_text().splitlines())
        say("✓", f"hook đã chặn {n} hành động trên máy này (.agent-kit/logs/guard.log)")

    if args.fix:
        print("\nSửa")
        local = load_state()
        for t in stale:
            local[str(t["id"])] = dict(st.get(str(t["id"]), {}))
            set_status(t, local, "queued", last_fail="- lượt chạy trước bị ngắt giữa chừng")
            print(f"  ↺ {t['id']} → queued")
        cmd_sync(None, quiet=True)
        print("  ↺ đã sync")

    print(f"\nKết quả: {out['✗']} lỗi, {out['!']} cảnh báo")
    sys.exit(1 if out["✗"] else 0)


# ───────────────────────── write commands ─────────────────────────
def cmd_plan(args):
    d = (ROOT / args.design_dir).resolve()
    if not d.is_dir():
        sys.exit(f"Không thấy thư mục design: {d}")
    feature = d.name
    files = "\n".join(f"- {p.relative_to(ROOT)}" for p in sorted(d.rglob("*")) if p.is_file())
    prompt = (f"Chia design trong `{d.relative_to(ROOT)}` thành epic + tasks.\n"
              f"Các file design:\n{files}\n\n"
              f"Ghi vào `tasks/{feature}/`. Theo đúng hướng dẫn của bạn và `tasks/_TEMPLATE.md`. "
              f"Trường `design:` của mỗi task = `{d.relative_to(ROOT)}`.")
    if agent_mode() == "chat":
        print("Chế độ chat: làm bước này trong Copilot Chat (chế độ Agent) hoặc trợ lý AI đang mở repo này.\n"
              "Prompt cho agent:\n")
        print("─" * 60)
        print("Đọc và làm đúng theo `.claude/agents/planner.md` (bạn đóng vai planner).\n" + prompt +
              "\nChỉ được tạo/sửa file trong `tasks/`. Mọi task để `status: draft`.")
        print("─" * 60)
        print(f"\nXong thì xem lại tasks/{feature}/ rồi chạy: python3 runner/kit.py approve {feature.upper()}")
        return
    print(f"Planner đang đọc {d.relative_to(ROOT)} ...")
    r = call_agent(prompt, role="planner", cwd=ROOT, agent="planner", timeout_min=30)
    print(r["result"])
    print("\nXem lại tasks/%s/ rồi chạy: python3 runner/kit.py approve %s" % (feature, feature.upper()))


def ensure_labels():
    for name, color in [("agent-kit", "5319e7"), ("epic", "3e4b9e"), ("task", "0e8a16"),
                        ("bug", "d73a4a"), ("needs-human", "fbca04")] + \
                       [(f"status:{s}", "c5def5") for s in STATUSES]:
        gh(["label", "create", name, "--color", color, "--force"], check=False)


def cmd_approve(args):
    tasks = load_tasks()
    st, _, _ = view_state()
    key = args.target
    picked = [t for t in tasks.values()
              if t.get("status") == "draft" and
              (key == "all" or str(t["id"]) == key or str(t.get("epic", "")) == key)]
    if not picked:
        sys.exit("Không có task nháp nào khớp.")
    if flag("GH_SYNC"):
        ensure_labels()
    for t in picked:
        if t["type"] != "epic" and not acceptance_ok(t):
            print(f"✗ {t['id']}: Acceptance trống hoặc còn placeholder → bỏ qua")
            continue
        set_front(t["_path"], "status", "approved")
        t["status"] = "approved"
        if flag("GH_SYNC") and not t.get("issue"):
            title = re.search(r"# Mục tiêu\s*\n+(.+)", t["_body"])
            title = (title.group(1).strip() if title else "")[:80]
            body = t["_body"] + f"\n\n---\nSpec: `{t['_path'].relative_to(ROOT)}`"
            r = gh(["issue", "create", "--title", f"[{t['id']}] {title}", "--body", body,
                    "--label", f"agent-kit,{t['type']},status:queued"], check=False)
            m = re.search(r"/issues/(\d+)", r.stdout)
            if m:
                set_front(t["_path"], "issue", m.group(1))
                t["issue"] = m.group(1)
            else:
                print(f"  ! không tạo được issue: {r.stderr.strip()[:200]}")
        if t["type"] != "epic":
            set_status(t, st, "queued", attempts=0, last_fail=None)
        print(f"✓ {t['id']} approved" + (f" (#{t['issue']})" if t.get("issue") else ""))
    publish(st, msg="approve")
    if any(t.get("holdout") is True for t in picked):
        print("\nTask có holdout: true → bài test ẩn sẽ được viết trong `kit.py work`, ngay trước khi làm task đó.")
    print("\nNhớ commit + push thư mục tasks/ để máy khác chạy `work` thấy được.")


def holdout_prompt(t: dict) -> str:
    tid = str(t["id"])
    return (f"Viết bài kiểm tra ẩn cho task `{t['_path'].relative_to(ROOT)}` "
            f"(design: `{t.get('design', '')}`). Ghi vào `.agent-kit/holdout-staging/{tid}/` "
            f"với đường dẫn tương đối giống nơi test thật nằm trong repo. Không sửa file nào khác.")


def collect_holdout(tid: str) -> bool:
    """Move tests from staging (inside the repo) to HOLDOUT_DIR (outside it)."""
    staging = STATE_DIR / "holdout-staging" / tid
    if not staging.exists() or not any(p.is_file() for p in staging.rglob("*")):
        return False
    dest = Path(CFG["HOLDOUT_DIR"]) / tid
    shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(staging), str(dest))
    print(f"  bài test ẩn → {dest}")
    return True


def write_holdout(t: dict) -> bool:
    tid = str(t["id"])
    shutil.rmtree(STATE_DIR / "holdout-staging" / tid, ignore_errors=True)
    r = call_agent(holdout_prompt(t), role="test-writer", cwd=ROOT, agent="test-writer", timeout_min=20)
    if r["limit"]:
        raise LimitHit(r["result"][-300:])
    if not collect_holdout(tid):
        print(f"  ! test-writer không tạo file cho {tid}: {r['result'][:200]}")
        return False
    return True


def needs_holdout(t: dict) -> bool:
    return t.get("holdout") is True and bool(CFG.get("HOLDOUT_DIR")) and \
        not (Path(CFG["HOLDOUT_DIR"]) / str(t["id"])).exists()


class SkipTask(Exception):
    """Task can't be worked on now for a reason that is not the agent's fault (no attempt used)."""


def gh_snapshot() -> dict:
    """issue number → {labels, state, updatedAt} for every agent-kit issue (one API call)."""
    r = gh(["issue", "list", "--label", "agent-kit", "--state", "all", "--limit", "1000",
            "--json", "number,labels,state,updatedAt"], check=False)
    try:
        return {str(i["number"]): i for i in json.loads(r.stdout or "[]")}
    except Exception:
        return {}


def cmd_sync(_args=None, quiet=False):
    tasks = load_tasks()
    st, _, _ = view_state()
    save_state(st)
    snap = gh_snapshot() if flag("GH_SYNC") else {}
    for t in tasks.values():
        tid = str(t["id"])
        rec = st.get(tid, {})
        # 1) a label changed on GitHub after our last record (e.g. edited by hand) wins
        issue = snap.get(str(t.get("issue") or ""))
        if issue:
            gh_status = next((l["name"][7:] for l in issue["labels"]
                              if l["name"].startswith("status:")), None)
            if gh_status in STATUSES and gh_status != rec.get("status") \
                    and str(issue.get("updatedAt", "")).replace("Z", "+00:00") > str(rec.get("updated", "")):
                set_status(t, st, gh_status, note="đổi từ nhãn GitHub")
        # 2) review → done when PR merged; closed without merge → failed
        rec = st.get(tid, {})
        if rec.get("status") == "review" and rec.get("pr") and flag("GH_SYNC"):
            state = gh(["pr", "view", rec["pr"], "--json", "state", "-q", ".state"], check=False).stdout.strip()
            if state == "MERGED":
                set_status(t, st, "done")
            elif state == "CLOSED":
                set_status(t, st, "failed", note="PR bị đóng không merge")
    # 3) epic done when all its tasks are done
    for e in [t for t in tasks.values() if t["type"] == "epic"]:
        kids = [t for t in tasks.values() if t.get("epic") == e.get("epic", e["id"]) and t["type"] != "epic"]
        if kids and all(status_of(k, st) == "done" for k in kids) and status_of(e, st) != "done":
            set_status(e, st, "done")
    save_state(st)
    publish(st, msg="sync")
    if not quiet:
        cmd_status(argparse.Namespace(offline=True))


def cmd_set(args):
    tasks = load_tasks()
    t = tasks.get(args.id)
    if not t:
        sys.exit(f"Không có task '{args.id}'.")
    if args.status not in STATUSES:
        sys.exit(f"Trạng thái phải là một trong: {', '.join(STATUSES)}")
    st, _, _ = view_state()
    extra = {"note": f"đặt tay bởi {HOST}"}
    if args.status == "queued":
        extra.update(attempts=0, last_fail=None)
    set_status(t, st, args.status, **extra)
    publish(st, msg=f"set {args.id}={args.status}")
    print(f"{args.id} → {args.status}")


def cmd_import(_args):
    if not flag("GH_SYNC"):
        sys.exit("Cần GH_SYNC=1 trong runner/config.env")
    tasks = load_tasks()
    known = {str(t.get("issue")) for t in tasks.values()}
    r = gh(["issue", "list", "--label", "agent-ready", "--state", "open", "--limit", "200",
            "--json", "number,title,body,labels"])
    for i in json.loads(r.stdout or "[]"):
        if str(i["number"]) in known:
            continue
        kind = "bug" if any(l["name"] == "bug" for l in i["labels"]) else "task"
        tid = f"GH-{i['number']}"
        p = TASKS / "imported" / f"{tid}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"---\nid: {tid}\ntype: {kind}\nepic: imported\nstatus: draft\n"
                     f"depends_on: []\npriority: {1 if kind == 'bug' else 3}\nholdout: false\n"
                     f"design:\nissue: {i['number']}\n---\n\n# Mục tiêu\n{i['title']}\n\n{i['body']}\n")
        gh(["issue", "edit", str(i["number"]), "--add-label", "agent-kit"], check=False)
        print(f"+ {p.relative_to(ROOT)}  (cần có mục '# Acceptance' rồi mới approve được)")


# ───────────────────────── work ─────────────────────────
# Paths an implementer must never change. Checked here on the final diff, so the
# rule holds for every agent — not only for Claude Code, whose hooks also block it.
PROTECTED = ["eval/", ".claude/", "tasks/", "runner/", "design/", "docs/", "CLAUDE.md",
             ".github/copilot-instructions.md", ".env"]


def is_protected(path: str) -> bool:
    return any(path == p.rstrip("/") or path.startswith(p if p.endswith("/") else p + ".") or
               (p.endswith("/") and path.startswith(p)) or path == p for p in PROTECTED)


def ready_tasks(tasks, st):
    out = []
    for t in tasks.values():
        if t["type"] == "epic" or t.get("status") != "approved" or status_of(t, st) != "queued":
            continue
        if st.get(str(t["id"]), {}).get("attempts", 0) >= int(CFG["MAX_ATTEMPTS"]):
            continue
        deps = [tasks.get(d) for d in t["depends_on"]]
        if all(d is not None and status_of(d, st) == "done" for d in deps):
            out.append(t)
    return sorted(out, key=lambda t: (t["priority"], str(t["id"])))


def run_holdout(t, wd: Path, log: Path):
    src = Path(CFG["HOLDOUT_DIR"]) / str(t["id"]) if CFG.get("HOLDOUT_DIR") else None
    if not src or not src.exists() or not CFG.get("HOLDOUT_CMD"):
        return None
    copied = []
    for f in src.rglob("*"):
        if f.is_file():
            dst = wd / f.relative_to(src)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)
            copied.append(dst)
    try:
        r = run(CFG["HOLDOUT_CMD"], cwd=wd, timeout=900, shell=True)
        log.write_text(r.stdout + "\n" + r.stderr)
        return r.returncode == 0
    finally:
        for f in copied:
            f.unlink(missing_ok=True)
        git(["checkout", "--", "."], cwd=wd, check=False)  # restore anything overwritten


def implementer_prompt(t: dict, branch: str, prev: str) -> str:
    tid = str(t["id"])
    return (f"Bạn đang làm task `{tid}` trên nhánh `{branch}`. Đọc `CLAUDE.md` trước.\n\n"
            f"=== TASK ===\n{t['_path'].read_text()}\n=== HẾT TASK ===\n\n"
            + (f"Lần thử trước bị chấm FAIL vì:\n{prev}\nĐừng lặp lại.\n\n" if prev else "")
            + f"Khi xong, làm theo skill `finish-task` (`.claude/skills/finish-task/SKILL.md`). "
              f"Báo cáo ghi vào `.agent-kit/reports/{tid}.md`.")


def reviewer_prompt(t: dict, g: dict) -> str:
    tid, base = str(t["id"]), CFG["BASE_BRANCH"]
    hold = g["hold_ok"]
    return (f"Chấm task `{tid}`. Spec: `{t['_path'].relative_to(ROOT)}` (nội dung bên dưới). "
            f"So sánh với nhánh gốc bằng `git diff {base}...HEAD`. "
            f"Kết quả checks: `.agent-kit/checks.log` ({'PASS' if g['checks_ok'] else 'FAIL'}). "
            f"Bộ test bổ sung: {'không có' if hold is None else ('PASS' if hold else 'FAIL')}. "
            f"Báo cáo của worker: `.agent-kit/reports/{tid}.md` (đừng tin, tự kiểm tra).\n\n"
            f"=== TASK ===\n{t['_path'].read_text()}")


def parse_review(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        rv = json.loads(m.group(0)) if m else None
    except Exception:
        rv = None
    if not isinstance(rv, dict) or rv.get("verdict") not in ("PASS", "FAIL"):
        return {"verdict": "FAIL", "reasons": ["reviewer không trả về JSON hợp lệ: " + (text or "")[:300]]}
    return rv


def grade(t: dict, wd: Path) -> dict:
    """Mechanical grading, identical for every agent: diff, protected paths, checks, hidden tests."""
    tid, base = str(t["id"]), CFG["BASE_BRANCH"]
    (wd / ".agent-kit").mkdir(exist_ok=True)
    if git(["status", "--porcelain"], cwd=wd).stdout.strip():
        git(["add", "-A"], cwd=wd, check=False)
        git(["commit", "-qm", f"{tid}: uncommitted changes from agent", "--no-verify"], cwd=wd, check=False)
    changed = git(["diff", "--name-only", f"{base}...HEAD"], cwd=wd, check=False).stdout.split()
    touched = [p for p in changed if is_protected(p)]
    chk = run(["bash", "eval/checks.sh"], cwd=wd, timeout=900)
    (wd / ".agent-kit" / "checks.log").write_text(chk.stdout + "\n" + chk.stderr)
    hold_ok = run_holdout(t, wd, wd / ".agent-kit" / "holdout.log")
    g = {"has_diff": bool(changed), "protected": touched, "checks_ok": chk.returncode == 0,
         "hold_ok": hold_ok, "checks_tail": (chk.stdout + chk.stderr)[-2500:]}
    g["ok"] = g["has_diff"] and not touched and g["checks_ok"] and hold_ok is not False
    g["reasons"] = (([] if g["has_diff"] else ["không có thay đổi nào"]) +
                    ([f"sửa vùng bảo vệ: {', '.join(touched)}"] if touched else []) +
                    ([] if g["checks_ok"] else ["eval/checks.sh FAIL"]) +
                    ([] if hold_ok is not False else ["bài test ẩn FAIL"]))
    return g


def finalize(t: dict, st: dict, wd: Path, branch: str, attempt: int, base_sha: str,
             g: dict, review: dict, out: Path, cost=0) -> dict:
    """Record the verdict, push the branch, open a PR on PASS — same for every agent."""
    tid, base = str(t["id"]), CFG["BASE_BRANCH"]
    out.mkdir(parents=True, exist_ok=True)
    for f in ["checks.log", "holdout.log", f"reports/{tid}.md"]:
        p = wd / ".agent-kit" / f
        if p.exists():
            shutil.copy2(p, out / Path(f).name)
    (out / "review.json").write_text(json.dumps(review, indent=2, ensure_ascii=False))
    passed = g["ok"] and review.get("verdict") in ("PASS", "SKIPPED")
    reasons = [] if passed else g["reasons"] + list(review.get("reasons", []))
    pushed = has_origin() and flag("PUBLISH") and \
        git(["push", "-q", "-u", "origin", branch, "--force"], cwd=wd, check=False).returncode == 0
    result = {"id": tid, "passed": passed, "reasons": reasons, "branch": branch, "pushed": pushed,
              "base_sha": base_sha, "spec_sha": t["_sha"], "attempt": attempt, "host": HOST,
              "agent": agent_mode(), "cost": cost, "risks": review.get("risks", []), "pr": "",
              "finished": now()}
    if passed:
        pr = ""
        if flag("GH_SYNC") and pushed:
            report = (out / f"{tid}.md").read_text() if (out / f"{tid}.md").exists() else ""
            body = (f"{report}\n\n---\n**Chấm tự động**: checks PASS · test ẩn "
                    f"{'PASS' if g['hold_ok'] else 'không có'} · reviewer {review.get('verdict')}\n"
                    f"**Rủi ro**: {'; '.join(review.get('risks', [])) or '-'}\n"
                    f"**Nên xem kỹ**: {'; '.join(review.get('human_should_check', [])) or '-'}\n"
                    f"**Chạy trên**: {HOST} · agent {agent_mode()} · base `{base_sha}` · spec `{t['_sha']}`\n\n"
                    + (f"Closes #{t['issue']}" if t.get("issue") else ""))
            r = gh(["pr", "create", "--base", base, "--head", branch,
                    "--title", f"[{tid}] agent", "--body", body], check=False)
            m = re.search(r"https://\S+/pull/\d+", r.stdout)
            pr = m.group(0) if m else ""
        result["pr"] = pr
        set_status(t, st, "review", pr=pr, branch=branch, last_fail=None)
    else:
        note = "\n".join(f"- {x}" for x in reasons)
        give_up = attempt >= int(CFG["MAX_ATTEMPTS"])
        set_status(t, st, "failed" if give_up else "queued", last_fail=note, branch=branch)
        if give_up and flag("GH_SYNC") and t.get("issue"):
            gh(["issue", "comment", str(t["issue"]), "--body",
                f"Agent thử {attempt} lần vẫn FAIL. Nhánh `{branch}`.\n{note}\n\n"
                f"Chi tiết: `python3 runner/kit.py report --task {tid}`"], check=False)
            gh(["issue", "edit", str(t["issue"]), "--add-label", "needs-human"], check=False)
    (out / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    return result


def begin_attempt(t: dict, st: dict, run_name: str):
    tid, base = str(t["id"]), CFG["BASE_BRANCH"]
    attempt = st.get(tid, {}).get("attempts", 0) + 1
    base_sha = git(["rev-parse", "--short", base]).stdout.strip()
    set_status(t, st, "running", attempts=attempt, spec_sha=t["_sha"], base_sha=base_sha, run=run_name)
    publish(st, msg=f"start {tid}")
    return attempt, base_sha, f"agent/{tid}-a{attempt}"


def run_task(t, st, run_dir: Path) -> dict:
    """Batch mode (claude / cli): the whole task in an isolated worktree, no human in the loop."""
    tid, base = str(t["id"]), CFG["BASE_BRANCH"]
    if needs_holdout(t):
        print(f"  viết bài test ẩn cho {tid} ...")
        if not write_holdout(t):
            raise SkipTask("test-writer không viết được bài test ẩn")
    prev = st.get(tid, {}).get("last_fail")
    attempt, base_sha, branch = begin_attempt(t, st, run_dir.name)
    wt = Path(CFG["WORKTREE_ROOT"]) / tid
    if wt.exists():
        git(["worktree", "remove", "--force", str(wt)], check=False)
    git(["branch", "-D", branch], check=False)
    wt.parent.mkdir(parents=True, exist_ok=True)
    git(["worktree", "add", "-q", "-b", branch, str(wt), base])
    out = run_dir / tid
    out.mkdir(parents=True, exist_ok=True)
    try:
        w = call_agent(implementer_prompt(t, branch, prev), role="worker", cwd=wt, agent="implementer",
                       timeout_min=int(CFG["TASK_TIMEOUT_MIN"]))
        (out / "worker.txt").write_text(w["result"])
        if w["limit"]:
            set_status(t, st, "queued", attempts=attempt - 1)
            raise LimitHit(w["result"][-300:])
        g = grade(t, wt)
        review = {"verdict": "SKIPPED", "reasons": [], "risks": [], "human_should_check": []}
        if flag("REVIEW") and g["has_diff"]:
            rv = call_agent(reviewer_prompt(t, g), role="reviewer", cwd=wt, agent="reviewer", timeout_min=20)
            if rv["limit"]:
                set_status(t, st, "queued", attempts=attempt - 1)
                raise LimitHit(rv["result"][-300:])
            review = parse_review(rv["result"])
        return finalize(t, st, wt, branch, attempt, base_sha, g, review, out, w["cost"])
    finally:
        git(["worktree", "remove", "--force", str(wt)], check=False)


def notify(text: str):
    tok, chat = CFG.get("TELEGRAM_BOT_TOKEN"), CFG.get("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        return
    data = urllib.parse.urlencode({"chat_id": chat, "text": text[:4000]}).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage", data, timeout=20)
    except Exception as e:
        print(f"telegram: {e}")


def preflight(require_clean: bool = True) -> bool:
    """Shared checks before a work session. Returns True if the remote lock was taken."""
    if not git(["ls-files", ".claude/settings.json", "eval/checks.sh"], check=False).stdout.strip():
        sys.exit("agent-kit chưa được commit lên repo. Commit + push trước.")
    if flag("GIT_PULL") and has_origin():
        if require_clean and git(["status", "--porcelain", "--untracked-files=no"]).stdout.strip():
            msg = "Dừng: repo trên máy này có thay đổi chưa commit → không pull được spec mới. Commit/push hoặc dọn sạch rồi chạy lại."
            notify(f"agent-kit · {ROOT.name} · {HOST}\n{msg}")
            sys.exit(msg)
        cur = git(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
        if cur != CFG["BASE_BRANCH"]:
            sys.exit(f"Dừng: đang ở nhánh `{cur}`. Chuyển về `{CFG['BASE_BRANCH']}` rồi chạy lại.")
        r = git(["pull", "-q", "--ff-only"], check=False)
        if r.returncode != 0:
            msg = f"Dừng: git pull --ff-only thất bại ({r.stderr.strip()[:200]}). Push commit của máy này lên trước rồi chạy lại."
            notify(f"agent-kit · {ROOT.name} · {HOST}\n{msg}")
            sys.exit(msg)
    try:
        acquire_lock()
    except LockHeld as e:
        sys.exit(f"Máy khác đang làm việc: {e}")
    return LOG.enabled()


def summarize(results, todo, stopped, run_dir: Path, started: str, st: dict) -> str:
    lines = [f"agent-kit · {ROOT.name} · {HOST} · {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}"]
    for r in results:
        lines.append(f"{'✅' if r['passed'] else '❌'} {r['id']} {r.get('pr') or r.get('branch') or ''}".rstrip())
        if not r["passed"]:
            lines += [f"   · {x}" for x in r["reasons"][:3]]
    if not todo:
        lines.append("Không có task nào sẵn sàng.")
    if stopped:
        lines.append(stopped)
    lines.append("Chi tiết: python3 runner/kit.py report")
    summary = "\n".join(lines)
    (run_dir / "SUMMARY.md").write_text(summary + "\n")
    (run_dir / "meta.json").write_text(json.dumps(
        {"host": HOST, "agent": agent_mode(), "started": started, "finished": now(),
         "tasks": [r["id"] for r in results], "stopped": stopped}, indent=2, ensure_ascii=False))
    if not publish(st, run_dir, meta={"last_run": started}, msg="work summary") and LOG.enabled():
        summary += f"\n(!) Không chia sẻ được kết quả lên nhánh {LOG_BRANCH}"
    print(summary)
    notify(summary)
    return summary


def new_run_dir() -> Path:
    d = STATE_DIR / "runs" / (dt.datetime.now().strftime("%Y-%m-%d_%H%M%S") + f"_{HOST}")
    d.mkdir(parents=True, exist_ok=True)
    return d


def work_batch(args):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock = STATE_DIR / "work.lock"
    if lock.exists() and age_hours(dt.datetime.fromtimestamp(lock.stat().st_mtime, dt.timezone.utc).isoformat()) < float(CFG["LOCK_HOURS"]):
        sys.exit("Đang có một phiên work khác trên máy này (.agent-kit/work.lock).")
    lock.write_text(str(os.getpid()))
    remote_locked = False
    try:
        remote_locked = preflight()
        cmd_sync(quiet=True)
        tasks = load_tasks()
        st, _, _ = view_state(fetch=False)
        todo = [t for t in ready_tasks(tasks, st) if not args.task or str(t["id"]) == args.task]
        todo = todo[: args.max or int(CFG["MAX_TASKS"])]
        started, run_dir = now(), new_run_dir()
        results, stopped = [], ""
        for t in todo:
            print(f"▶ {t['id']}")
            try:
                results.append(run_task(t, st, run_dir))
            except LimitHit as e:
                stopped = f"Dừng sớm: chạm giới hạn gói ({e})"
                break
            except SkipTask as e:
                set_status(t, st, "queued", note=f"bỏ qua phiên này: {e}")
                results.append({"id": str(t["id"]), "passed": False, "reasons": [f"bỏ qua (không tính lượt thử): {e}"]})
            except Exception as e:
                set_status(t, st, "queued", last_fail=f"- lỗi runner: {e}")
                results.append({"id": str(t["id"]), "passed": False, "reasons": [f"lỗi runner: {e}"]})
            publish(st, run_dir, msg=f"done {t['id']}")
        summarize(results, todo, stopped, run_dir, started, st)
    finally:
        if remote_locked:
            release_lock()
        lock.unlink(missing_ok=True)


# ── chat mode: one step per call; the chat agent runs `kit.py work` again after each step ──
SESSION = STATE_DIR / "session.json"


def load_session() -> dict:
    try:
        return json.loads(SESSION.read_text())
    except Exception:
        return {}


def save_session(s: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SESSION.write_text(json.dumps(s, indent=2, ensure_ascii=False))


def say_step(title: str, body: str, next_cmd: str = "python3 runner/kit.py work"):
    bar = "─" * 64
    print(f"\n{bar}\n▶ BƯỚC TIẾP THEO: {title}\n{bar}\n{body.strip()}\n{bar}")
    if next_cmd:
        print(f"Xong bước này thì chạy: {next_cmd}")


def chat_start_implement(t: dict, st: dict, s: dict):
    tid = str(t["id"])
    prev = st.get(tid, {}).get("last_fail")
    attempt, base_sha, branch = begin_attempt(t, st, s["run_dir"])
    git(["branch", "-D", branch], check=False)
    git(["checkout", "-q", "-b", branch, CFG["BASE_BRANCH"]])
    s.update(stage="implement", attempt=attempt, base_sha=base_sha, branch=branch, fixes=0)
    save_session(s)
    say_step(f"LÀM TASK {tid} (vai implementer)",
             "Đọc và làm đúng theo `.claude/agents/implementer.md`.\n"
             "Bạn đang ở nhánh `" + branch + "` (kit.py đã tạo). Commit trên nhánh này, không push.\n\n"
             + implementer_prompt(t, branch, prev))


def chat_finish(t, st, s, g, review):
    out = STATE_DIR / "runs" / s["run_dir"] / str(t["id"])
    r = finalize(t, st, ROOT, s["branch"], s["attempt"], s["base_sha"], g, review, out)
    git(["checkout", "-q", CFG["BASE_BRANCH"]], check=False)
    SESSION.unlink(missing_ok=True)
    summarize([r], [t], "", STATE_DIR / "runs" / s["run_dir"], s["started"], st)
    release_lock()
    print(f"\nĐã trở về nhánh `{CFG['BASE_BRANCH']}`. Bài làm nằm ở nhánh `{s['branch']}`"
          + (f", PR: {r['pr']}" if r.get("pr") else "") + ".")
    print("Còn task khác? Chạy lại: python3 runner/kit.py work")


def work_chat(args):
    s = load_session()
    tasks = load_tasks()
    if args.abort:
        if not s:
            sys.exit("Không có phiên nào đang mở.")
        st, _, _ = view_state(fetch=False)
        t = tasks.get(s["task"])
        if t and s.get("attempt"):
            set_status(t, st, "queued", attempts=s["attempt"] - 1, note="phiên chat bị huỷ")
            publish(st, msg=f"abort {s['task']}")
        git(["checkout", "-q", CFG["BASE_BRANCH"]], check=False)
        SESSION.unlink(missing_ok=True)
        release_lock()
        print(f"Đã huỷ phiên của {s['task']} (không tính lượt thử). Nhánh làm dở vẫn giữ lại: {s.get('branch', '-')}")
        return

    st, _, _ = view_state(fetch=False)
    if not s:
        if args.task and args.task not in tasks:
            sys.exit(f"Không có task '{args.task}'.")
        preflight()
        cmd_sync(quiet=True)
        st, _, _ = view_state(fetch=False)
        ready = [t for t in ready_tasks(tasks, st) if not args.task or str(t["id"]) == args.task]
        if not ready:
            release_lock()
            print("Không có task nào sẵn sàng. Xem: python3 runner/kit.py status")
            return
        t = ready[0]
        s = {"task": str(t["id"]), "stage": "", "started": now(), "host": HOST,
             "run_dir": new_run_dir().name}
        save_session(s)
        print(f"Bắt đầu task {t['id']}.")
        if needs_holdout(t):
            shutil.rmtree(STATE_DIR / "holdout-staging" / str(t["id"]), ignore_errors=True)
            s["stage"] = "holdout"
            save_session(s)
            say_step(f"VIẾT BÀI TEST ẨN cho {t['id']} (vai test-writer)",
                     "Nên làm trong MỘT CUỘC CHAT MỚI, để agent làm bài sau không nhớ nội dung test.\n"
                     "Đọc và làm đúng theo `.claude/agents/test-writer.md`.\n\n" + holdout_prompt(t))
            return
        chat_start_implement(t, st, s)
        return

    t = tasks.get(s["task"])
    if not t:
        sys.exit(f"Task {s['task']} của phiên đang mở không còn trong tasks/. Huỷ: python3 runner/kit.py work --abort")

    if s["stage"] == "holdout":
        if not collect_holdout(str(t["id"])):
            say_step(f"VIẾT BÀI TEST ẨN cho {t['id']} (chưa thấy file nào)",
                     f"Chưa có file nào trong `.agent-kit/holdout-staging/{t['id']}/`.\n\n" + holdout_prompt(t))
            return
        chat_start_implement(t, st, s)
        return

    if s["stage"] == "implement":
        g = grade(t, ROOT)
        if not g["ok"]:
            s["fixes"] = s.get("fixes", 0) + 1
            save_session(s)
            limit = int(os.environ.get("AGENT_KIT_MAX_FIX_ATTEMPTS", "3"))
            if s["fixes"] <= limit:
                detail = "\n".join(f"- {x}" for x in g["reasons"])
                if not g["checks_ok"]:
                    detail += "\n\nĐuôi log eval/checks.sh:\n" + g["checks_tail"]
                if g["hold_ok"] is False:
                    detail += "\n\nBài test ẩn FAIL (nội dung test được giữ kín). Đối chiếu lại Interface và Acceptance."
                say_step(f"SỬA TASK {t['id']} (lần {s['fixes']}/{limit})",
                         "Chấm tự động chưa đạt:\n" + detail +
                         "\n\nSửa code (không sửa test, eval/, tasks/...), commit, rồi chạy lại.")
                return
            chat_finish(t, st, s, g, {"verdict": "SKIPPED", "reasons": [f"hết {limit} lần sửa"]})
            return
        if flag("REVIEW"):
            s.update(stage="review", grade=g)
            save_session(s)
            (STATE_DIR / "reviews").mkdir(parents=True, exist_ok=True)
            say_step(f"CHẤM ĐỘC LẬP task {t['id']} (vai reviewer)",
                     "Làm trong MỘT CUỘC CHAT MỚI (reviewer không được là agent vừa làm bài).\n"
                     "Đọc và làm đúng theo `.claude/agents/reviewer.md`. Không sửa code.\n"
                     f"Ghi đúng một khối JSON kết quả vào `.agent-kit/reviews/{t['id']}.json`.\n\n"
                     + reviewer_prompt(t, g))
            return
        chat_finish(t, st, s, g, {"verdict": "SKIPPED", "reasons": [], "risks": []})
        return

    if s["stage"] == "review":
        f = STATE_DIR / "reviews" / f"{t['id']}.json"
        if not f.exists():
            say_step(f"CHẤM ĐỘC LẬP task {t['id']} (chưa thấy kết quả)",
                     f"Chưa có `.agent-kit/reviews/{t['id']}.json`.\n\n" + reviewer_prompt(t, s["grade"]))
            return
        review = parse_review(f.read_text())
        f.unlink()
        chat_finish(t, st, s, s["grade"], review)
        return


def cmd_work(args):
    mode = agent_mode()
    if mode == "chat" or load_session():
        return work_chat(args)
    if args.abort:
        sys.exit("Không có phiên chat nào đang mở.")
    return work_batch(args)


def main():
    if hasattr(__import__("signal"), "SIGPIPE"):  # quiet exit when piped into head/less
        import signal
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("status"); p.add_argument("--offline", action="store_true"); p.set_defaults(fn=cmd_status)
    p = sub.add_parser("report"); p.add_argument("--last", type=int, default=0)
    p.add_argument("--task"); p.set_defaults(fn=cmd_report)
    p = sub.add_parser("doctor"); p.add_argument("--fix", action="store_true"); p.set_defaults(fn=cmd_doctor)
    p = sub.add_parser("plan"); p.add_argument("design_dir"); p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("approve"); p.add_argument("target"); p.set_defaults(fn=cmd_approve)
    p = sub.add_parser("work"); p.add_argument("--max", type=int, default=0)
    p.add_argument("--task"); p.add_argument("--abort", action="store_true"); p.set_defaults(fn=cmd_work)
    sub.add_parser("sync").set_defaults(fn=cmd_sync)
    sub.add_parser("import").set_defaults(fn=cmd_import)
    p = sub.add_parser("set"); p.add_argument("id"); p.add_argument("status"); p.set_defaults(fn=cmd_set)
    a = ap.parse_args()
    try:
        a.fn(a)
    except NeedsChat:
        sys.exit("Lệnh này cần agent CLI; máy này đang ở chế độ chat (AGENT=chat hoặc không có CLI).")


if __name__ == "__main__":
    main()
