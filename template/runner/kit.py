#!/usr/bin/env python3
"""agent-kit runner: design → tasks → agents → graded PRs.

  python3 runner/kit.py status                 bảng trạng thái
  python3 runner/kit.py plan design/<feature>  planner chia design thành tasks nháp
  python3 runner/kit.py approve <id|epic|all>  duyệt nháp → tạo GitHub Issue + bài test ẩn
  python3 runner/kit.py night                  chạy các task sẵn sàng (dùng cho cron)
  python3 runner/kit.py sync                   cập nhật trạng thái từ GitHub (PR merged → done)
  python3 runner/kit.py import                 kéo GitHub Issue gắn nhãn 'agent-ready' thành task

Spec (do người duyệt) nằm trong tasks/*.md. Trạng thái chạy nằm trong
.agent-kit/state.json và được phản chiếu lên nhãn GitHub Issue 'status:*',
nên MacBook và mini PC không sửa đè file của nhau.
Chỉ dùng thư viện chuẩn của Python 3.8+.
"""
import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

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
        "GH_SYNC": "0", "GIT_PULL": "1",
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


def flag(name: str) -> bool:
    return CFG.get(name, "0") == "1"


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
    return meta


def set_front(path: Path, key: str, value) -> None:
    """Update one frontmatter key in place (used only by approve/import, on the human's machine)."""
    text = path.read_text()
    line = f"{key}: {value}"
    pat = re.compile(rf"^{re.escape(key)}:.*$", re.M)
    head, sep, body = text.partition("\n---")
    head = pat.sub(line, head) if pat.search(head) else head + "\n" + line
    path.write_text(head + sep + body)


def load_tasks() -> dict:
    out = {}
    for p in sorted(TASKS.rglob("*.md")):
        if p.name.startswith("_"):
            continue
        t = parse_task(p)
        if t and t.get("id"):
            out[str(t["id"])] = t
    return out


def acceptance_ok(t: dict) -> bool:
    sec = re.search(r"# Acceptance.*?\n(.*?)(\n# |\Z)", t["_body"], re.S)
    if not sec:
        return False
    items = [l for l in sec.group(1).splitlines()
             if re.match(r"\s*- \[.\]", l) and "<!--" not in l and "checks.sh" not in l]
    return len(items) > 0


# ───────────────────────── runtime state ─────────────────────────
def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def save_state(st: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(st, indent=2, ensure_ascii=False))


def status_of(t: dict, st: dict) -> str:
    s = st.get(str(t["id"]), {}).get("status")
    if s:
        return s
    return "queued" if t.get("status") == "approved" else "draft"


def set_status(t: dict, st: dict, status: str, **extra) -> None:
    rec = st.setdefault(str(t["id"]), {})
    old = rec.get("status")
    rec.update(status=status, updated=dt.datetime.now().isoformat(timespec="seconds"), **extra)
    save_state(st)
    if flag("GH_SYNC") and t.get("issue") and old != status:
        gh(["issue", "edit", str(t["issue"]), "--add-label", f"status:{status}"]
           + (["--remove-label", f"status:{old}"] if old else []), check=False)


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


def claude(prompt: str, role: str, cwd: Path, agent: str = "", timeout_min: int = 60,
           extra_env: dict = None) -> dict:
    cmd = [CFG["CLAUDE_BIN"], "-p", prompt, "--output-format", "json",
           "--permission-mode", "acceptEdits", "--permission-prompts", "none"]
    if agent:
        cmd += ["--agent", agent]
    if CFG.get("MAX_BUDGET_USD"):
        cmd += ["--max-budget-usd", CFG["MAX_BUDGET_USD"]]
    env = dict(os.environ, AGENT_KIT_ROLE=role, AGENT_KIT_BASE=CFG["BASE_BRANCH"],
               AGENT_KIT_HOLDOUT_DIR=CFG.get("HOLDOUT_DIR", ""))
    env.update(extra_env or {})
    try:
        r = run(cmd, cwd=cwd, timeout=timeout_min * 60, env=env)
        raw = r.stdout + "\n" + r.stderr
    except subprocess.TimeoutExpired:
        return {"ok": False, "timeout": True, "limit": False, "result": "timeout", "cost": 0}
    try:
        j = json.loads(r.stdout)
    except Exception:
        j = {}
    text = str(j.get("result", raw))
    limited = bool(LIMIT_RE.search(raw)) and (r.returncode != 0 or j.get("is_error"))
    return {"ok": r.returncode == 0 and not j.get("is_error"), "limit": limited,
            "timeout": False, "result": text, "cost": j.get("total_cost_usd", 0) or 0}


class LimitHit(Exception):
    pass


# ───────────────────────── commands ─────────────────────────
def cmd_status(_args):
    tasks, st = load_tasks(), load_state()
    rows = [("ID", "TYPE", "STATUS", "TRY", "DEPENDS", "ISSUE", "PR")]
    for t in sorted(tasks.values(), key=lambda x: (str(x.get("epic", "")), x["priority"], str(x["id"]))):
        rec = st.get(str(t["id"]), {})
        rows.append((str(t["id"]), t["type"], status_of(t, st), str(rec.get("attempts", 0)),
                     ",".join(t["depends_on"]) or "-", str(t.get("issue") or "-"),
                     rec.get("pr", "-")))
    w = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for r in rows:
        print("  ".join(c.ljust(w[i]) for i, c in enumerate(r)))


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
    print(f"Planner đang đọc {d.relative_to(ROOT)} ...")
    r = claude(prompt, role="planner", cwd=ROOT, agent="planner", timeout_min=30)
    print(r["result"])
    print("\nXem lại tasks/%s/ rồi chạy: python3 runner/kit.py approve %s" % (feature, feature.upper()))


def ensure_labels():
    for name, color in [("agent-kit", "5319e7"), ("epic", "3e4b9e"), ("task", "0e8a16"),
                        ("bug", "d73a4a"), ("needs-human", "fbca04")] + \
                       [(f"status:{s}", "c5def5") for s in STATUSES]:
        gh(["label", "create", name, "--color", color, "--force"], check=False)


def cmd_approve(args):
    tasks, st = load_tasks(), load_state()
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
            st.setdefault(str(t["id"]), {})
            set_status(t, st, "queued")
            if t.get("holdout") is True and CFG.get("HOLDOUT_DIR"):
                write_holdout(t)
        print(f"✓ {t['id']} approved" + (f" (#{t['issue']})" if t.get("issue") else ""))
    print("\nNhớ commit + push thư mục tasks/ để mini PC kéo về.")


def write_holdout(t: dict):
    tid = str(t["id"])
    staging = STATE_DIR / "holdout-staging" / tid
    shutil.rmtree(staging, ignore_errors=True)
    prompt = (f"Viết bài kiểm tra ẩn cho task `{t['_path'].relative_to(ROOT)}` "
              f"(design: `{t.get('design', '')}`). Ghi vào `.agent-kit/holdout-staging/{tid}/`.")
    r = claude(prompt, role="test-writer", cwd=ROOT, agent="test-writer", timeout_min=20)
    if not staging.exists() or not any(staging.rglob("*")):
        print(f"  ! test-writer không tạo file cho {tid}: {r['result'][:200]}")
        return
    dest = Path(CFG["HOLDOUT_DIR"]) / tid
    shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(staging), str(dest))
    print(f"  bài test ẩn → {dest}")


def gh_snapshot() -> dict:
    """issue number → {labels, state} for every agent-kit issue (one API call)."""
    r = gh(["issue", "list", "--label", "agent-kit", "--state", "all", "--limit", "1000",
            "--json", "number,labels,state"], check=False)
    try:
        return {str(i["number"]): i for i in json.loads(r.stdout or "[]")}
    except Exception:
        return {}


def cmd_sync(_args=None, quiet=False):
    tasks, st = load_tasks(), load_state()
    snap = gh_snapshot() if flag("GH_SYNC") else {}
    for t in tasks.values():
        tid = str(t["id"])
        rec = st.get(tid, {})
        # 1) pull status from GitHub labels (the other machine may have moved it)
        issue = snap.get(str(t.get("issue") or ""))
        if issue:
            gh_status = next((l["name"][7:] for l in issue["labels"]
                              if l["name"].startswith("status:")), None)
            if gh_status and gh_status != rec.get("status"):
                st.setdefault(tid, {})["status"] = gh_status
        # 2) review → done when PR merged; closed without merge → failed
        if st.get(tid, {}).get("status") == "review" and st[tid].get("pr") and flag("GH_SYNC"):
            r = gh(["pr", "view", st[tid]["pr"], "--json", "state", "-q", ".state"], check=False)
            state = r.stdout.strip()
            if state == "MERGED":
                set_status(t, st, "done")
            elif state == "CLOSED":
                set_status(t, st, "failed", note="PR bị đóng không merge")
    # 3) epic done when all its tasks are done
    for e in [t for t in tasks.values() if t["type"] == "epic"]:
        kids = [t for t in tasks.values() if t.get("epic") == e.get("epic", e["id"]) and t["type"] != "epic"]
        if kids and all(status_of(k, st) == "done" for k in kids):
            set_status(e, st, "done")
    save_state(st)
    if not quiet:
        cmd_status(None)


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


# ───────────────────────── night run ─────────────────────────
def ready_tasks(tasks, st):
    out = []
    for t in tasks.values():
        if t["type"] == "epic" or status_of(t, st) != "queued":
            continue
        if st.get(str(t["id"]), {}).get("attempts", 0) >= int(CFG["MAX_ATTEMPTS"]):
            continue
        deps = [tasks.get(d) for d in t["depends_on"]]
        if all(d is not None and status_of(d, st) == "done" for d in deps):
            out.append(t)
    return sorted(out, key=lambda t: (t["priority"], str(t["id"])))


def run_holdout(t, wt: Path, log: Path):
    src = Path(CFG["HOLDOUT_DIR"]) / str(t["id"]) if CFG.get("HOLDOUT_DIR") else None
    if not src or not src.exists() or not CFG.get("HOLDOUT_CMD"):
        return None
    copied = []
    for f in src.rglob("*"):
        if f.is_file():
            dst = wt / f.relative_to(src)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)
            copied.append(dst)
    try:
        r = run(CFG["HOLDOUT_CMD"], cwd=wt, timeout=900, shell=True)
        log.write_text(r.stdout + "\n" + r.stderr)
        return r.returncode == 0
    finally:
        for f in copied:
            f.unlink(missing_ok=True)
        git(["checkout", "--", "."], cwd=wt, check=False)  # restore anything overwritten


def run_task(t, st, run_dir: Path) -> dict:
    tid, base = str(t["id"]), CFG["BASE_BRANCH"]
    rec = st.setdefault(tid, {})
    attempt = rec.get("attempts", 0) + 1
    set_status(t, st, "running", attempts=attempt)
    branch = f"agent/{tid}-a{attempt}"
    wt = Path(CFG["WORKTREE_ROOT"]) / tid
    if wt.exists():
        git(["worktree", "remove", "--force", str(wt)], check=False)
    git(["branch", "-D", branch], check=False)
    wt.parent.mkdir(parents=True, exist_ok=True)
    git(["worktree", "add", "-b", branch, str(wt), base])
    out = run_dir / tid
    out.mkdir(parents=True, exist_ok=True)
    (wt / ".agent-kit").mkdir(exist_ok=True)

    prev = rec.get("last_fail")
    prompt = (f"Bạn đang làm task `{tid}` trên nhánh `{branch}`. Đọc `CLAUDE.md` trước.\n\n"
              f"=== TASK ===\n{t['_path'].read_text()}\n=== HẾT TASK ===\n\n"
              + (f"Lần thử trước bị chấm FAIL vì:\n{prev}\nĐừng lặp lại.\n\n" if prev else "")
              + f"Khi xong, làm theo skill `finish-task`. Báo cáo ghi vào `.agent-kit/reports/{tid}.md`.")
    w = claude(prompt, role="worker", cwd=wt, timeout_min=int(CFG["TASK_TIMEOUT_MIN"]))
    (out / "worker.txt").write_text(w["result"])
    if w["limit"]:
        rec["attempts"] = attempt - 1
        set_status(t, st, "queued")
        git(["worktree", "remove", "--force", str(wt)], check=False)
        raise LimitHit(w["result"][-300:])

    if git(["status", "--porcelain"], cwd=wt).stdout.strip():
        git(["add", "-A"], cwd=wt, check=False)
        git(["commit", "-m", f"{tid}: uncommitted changes from agent", "--no-verify"], cwd=wt, check=False)

    has_diff = git(["rev-list", "--count", f"{base}..HEAD"], cwd=wt).stdout.strip() not in ("", "0")
    chk = run(["bash", "eval/checks.sh"], cwd=wt, timeout=900)
    (wt / ".agent-kit" / "checks.log").write_text(chk.stdout + "\n" + chk.stderr)
    checks_ok = chk.returncode == 0
    hold_ok = run_holdout(t, wt, wt / ".agent-kit" / "holdout.log")

    review = {"verdict": "SKIPPED", "reasons": [], "risks": [], "human_should_check": []}
    if flag("REVIEW") and has_diff:
        rp = (f"Chấm task `{tid}`. Spec: `{t['_path'].relative_to(ROOT)}` (nội dung bên dưới). "
              f"So sánh với nhánh gốc bằng `git diff {base}...HEAD`. "
              f"Kết quả checks: `.agent-kit/checks.log` ({'PASS' if checks_ok else 'FAIL'}). "
              f"Bộ test bổ sung: {'không có' if hold_ok is None else ('PASS' if hold_ok else 'FAIL')}"
              + (", log `.agent-kit/holdout.log`" if hold_ok is not None else "")
              + f". Báo cáo của worker: `.agent-kit/reports/{tid}.md` (đừng tin, tự kiểm tra).\n\n"
              f"=== TASK ===\n{t['_path'].read_text()}")
        rv = claude(rp, role="reviewer", cwd=wt, agent="reviewer", timeout_min=20)
        if rv["limit"]:
            raise LimitHit(rv["result"][-300:])
        m = re.search(r"\{.*\}", rv["result"], re.S)
        try:
            review = json.loads(m.group(0)) if m else review
        except Exception:
            review["reasons"] = [rv["result"][:500]]
            review["verdict"] = "FAIL"

    for f in ["checks.log", "holdout.log", f"reports/{tid}.md"]:
        p = wt / ".agent-kit" / f
        if p.exists():
            shutil.copy2(p, out / Path(f).name)
    (out / "review.json").write_text(json.dumps(review, indent=2, ensure_ascii=False))

    passed = has_diff and checks_ok and hold_ok is not False and review.get("verdict") in ("PASS", "SKIPPED")
    reasons = [] if passed else (
        ([] if has_diff else ["không có thay đổi nào"]) +
        ([] if checks_ok else ["eval/checks.sh FAIL"]) +
        ([] if hold_ok is not False else ["bài test ẩn FAIL"]) +
        list(review.get("reasons", [])))
    result = {"id": tid, "passed": passed, "reasons": reasons, "branch": branch,
              "cost": w["cost"], "risks": review.get("risks", []), "pr": ""}

    if passed:
        pr = ""
        if flag("GH_SYNC"):
            git(["push", "-u", "origin", branch, "--force"], cwd=wt, check=False)
            report = (out / f"{tid}.md").read_text() if (out / f"{tid}.md").exists() else ""
            body = (f"{report}\n\n---\n**Chấm tự động**: checks PASS · test ẩn "
                    f"{'PASS' if hold_ok else 'không có'} · reviewer {review.get('verdict')}\n"
                    f"**Rủi ro**: {'; '.join(review.get('risks', [])) or '-'}\n"
                    f"**Nên xem kỹ**: {'; '.join(review.get('human_should_check', [])) or '-'}\n\n"
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
                f"Agent thử {attempt} lần vẫn FAIL. Nhánh `{branch}` (chỉ có trên máy chạy).\n{note}"], check=False)
            gh(["issue", "edit", str(t["issue"]), "--add-label", "needs-human"], check=False)
    git(["worktree", "remove", "--force", str(wt)], check=False)
    return result


def notify(text: str):
    tok, chat = CFG.get("TELEGRAM_BOT_TOKEN"), CFG.get("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        return
    data = urllib.parse.urlencode({"chat_id": chat, "text": text[:4000]}).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage", data, timeout=20)
    except Exception as e:
        print(f"telegram: {e}")


def cmd_night(args):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock = STATE_DIR / "night.lock"
    if lock.exists() and time.time() - lock.stat().st_mtime < 12 * 3600:
        sys.exit("Đang có một lượt chạy khác (night.lock).")
    lock.write_text(str(os.getpid()))
    try:
        if not git(["ls-files", ".claude/settings.json"], check=False).stdout.strip():
            sys.exit("agent-kit chưa được commit lên repo → worktree sẽ không có rào chắn. Commit trước.")
        if flag("GIT_PULL") and not git(["status", "--porcelain", "--untracked-files=no"]).stdout.strip():
            git(["pull", "--ff-only"], check=False)
        cmd_sync(quiet=True)
        tasks, st = load_tasks(), load_state()
        todo = ready_tasks(tasks, st)[: args.max or int(CFG["MAX_TASKS"])]
        run_dir = STATE_DIR / "runs" / dt.datetime.now().strftime("%Y-%m-%d_%H%M")
        run_dir.mkdir(parents=True, exist_ok=True)
        results, stopped = [], ""
        for t in todo:
            print(f"▶ {t['id']}")
            try:
                results.append(run_task(t, st, run_dir))
            except LimitHit as e:
                stopped = f"Dừng sớm: chạm giới hạn gói ({e})"
                break
            except Exception as e:
                set_status(t, st, "queued", last_fail=f"- lỗi runner: {e}")
                results.append({"id": str(t["id"]), "passed": False, "reasons": [f"lỗi runner: {e}"], "pr": "", "cost": 0})
        lines = [f"agent-kit · {ROOT.name} · {dt.date.today()}"]
        for r in results:
            mark = "✅" if r["passed"] else "❌"
            lines.append(f"{mark} {r['id']} {r.get('pr') or ''}".rstrip())
            if not r["passed"]:
                lines += [f"   · {x}" for x in r["reasons"][:3]]
        if not todo:
            lines.append("Không có task nào sẵn sàng.")
        if stopped:
            lines.append(stopped)
        summary = "\n".join(lines)
        (run_dir / "SUMMARY.md").write_text(summary)
        print(summary)
        notify(summary)
    finally:
        lock.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    p = sub.add_parser("plan"); p.add_argument("design_dir"); p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("approve"); p.add_argument("target"); p.set_defaults(fn=cmd_approve)
    p = sub.add_parser("night"); p.add_argument("--max", type=int, default=0); p.set_defaults(fn=cmd_night)
    sub.add_parser("sync").set_defaults(fn=cmd_sync)
    sub.add_parser("import").set_defaults(fn=cmd_import)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
