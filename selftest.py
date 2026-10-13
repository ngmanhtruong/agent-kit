#!/usr/bin/env python3
"""selftest.py — kiểm thử agent-kit, với agent giả hoặc agent thật.

  python3 selftest.py offline
      Chạy các kịch bản tự động với agent GIẢ (không tốn token, không cần mạng):
      3 chế độ claude / cli / chat, PASS và FAIL, gian lận bị bắt, kiểm thử epic
      FAIL rồi PASS sau khi sửa, khoá giữa hai máy. Dùng trước khi commit kit.

  python3 selftest.py setup <thư-mục> --agent claude|cli|chat [--agent-cmd "..."]
                              [--remote <git-url-repo-trống>] [--no-trap]
      Tạo một project thử nhỏ (Python, chỉ dùng unittest) đã cài agent-kit, có PRD
      đã duyệt, 1 epic + 2 task đã duyệt. Mặc định cài sẵn một kiểm thử epic sẽ FAIL
      ("bẫy") để thử luồng epic FAIL → mở bug. --remote: đẩy lên repo GitHub trống
      để thử Issue / PR / nhãn / nhánh log (cần `gh` đã đăng nhập).

  python3 selftest.py advance <thư-mục>
      Giả lập bạn duyệt PR: merge mọi task đang `review` vào nhánh gốc, rồi `sync`.

  python3 selftest.py verify <thư-mục>
      Kiểm tra kết quả và in ✓ / ✗ cho từng điểm.

Luồng thử với agent thật:
  setup → (cd <thư-mục>) kit.py work → selftest advance → kit.py work → selftest verify
Với --agent chat: thay `kit.py work` bằng việc bảo Copilot Chat
  "chạy python3 runner/kit.py work và làm theo, lặp tới khi xong".
"""
import argparse
import re
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

sys.dont_write_bytecode = True
KIT = Path(__file__).resolve().parent
PY = sys.executable or "python3"


# ───────────────────────── helpers ─────────────────────────
def sh(cmd, cwd, check=True, env=None, input=None):
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, env=env, input=input,
                       stdin=None if input is not None else subprocess.DEVNULL, shell=isinstance(cmd, str))
    if check and r.returncode != 0:
        raise SystemExit(f"Lỗi khi chạy {cmd} trong {cwd}:\n{r.stdout}\n{r.stderr}")
    return r


def kit(d, *args, env=None, check=False):
    return sh([PY, "runner/kit.py", *args], d, check=check, env=env)


def write(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(text).lstrip("\n"))


def set_cfg(d: Path, **kv):
    p = d / "runner" / "config.env"
    lines = p.read_text().splitlines()
    for k, v in kv.items():
        line = f"{k}={v}"
        for i, l in enumerate(lines):
            if l.startswith(f"{k}="):
                lines[i] = line
                break
        else:
            lines.append(line)
    p.write_text("\n".join(lines) + "\n")


def git_init(d: Path):
    sh(["git", "init", "-q", "-b", "main"], d)
    sh(["git", "config", "user.email", "selftest@agent-kit"], d)
    sh(["git", "config", "user.name", "agent-kit selftest"], d)


def commit_all(d: Path, msg: str):
    sh(["git", "add", "-A"], d)
    sh(["git", "commit", "-qm", msg, "--no-verify"], d, check=False)


# ───────────────────────── toy project ─────────────────────────
TEST_CMD = "env PYTHONPATH=src python3 -m unittest discover -s tests -q"


def make_project(d: Path, trap: bool, holdout_dir: Path):
    """A tiny shopping-cart library. Two tasks (add, remove) and one epic."""
    write(d / "src/shop/__init__.py", "")
    write(d / "src/shop/cart.py", '''
        """Giỏ hàng tối giản. Giỏ là dict: sku -> số lượng."""


        def new_cart():
            return {}


        # [SHOP-01]

        # [SHOP-02]

        # [FIX-1]
    ''')
    write(d / "tests/__init__.py", "")
    write(d / "tests/test_new_cart.py", '''
        import unittest
        from shop.cart import new_cart


        class TestNewCart(unittest.TestCase):
            def test_empty(self):
                self.assertEqual(new_cart(), {})
    ''')
    sh([PY, str(KIT / "install.py"), str(d)], d)
    # project context
    write(d / "CLAUDE.md", (d / "CLAUDE.md").read_text().replace(
        "<!-- 2-3 câu: ai dùng, giải quyết vấn đề gì, \"thành công\" trông thế nào -->",
        "Thư viện giỏ hàng tối giản dùng để kiểm thử agent-kit. Thành công = mọi hàm đúng Interface trong task."
    ).replace("- Được làm: <!-- ví dụ: sửa logic trong src/, thêm test -->", "- Được làm: src/shop/, tests/")
     .replace("- KHÔNG được đụng: <!-- ví dụ: config live trading, API key, schema DB production -->",
              "- KHÔNG được đụng: mọi thứ ngoài src/ và tests/"))
    write(d / "docs/architecture.md", '''
        # Kiến trúc
        | Module | Vai trò |
        |---|---|
        | src/shop/cart.py | Hàm thao tác giỏ hàng (dict sku -> số lượng) |
        | tests/ | unittest, chạy bằng: PYTHONPATH=src python3 -m unittest discover -s tests |
    ''')
    chk = (d / "eval/checks.sh").read_text().replace(
        '# step "tests" pytest -q', f'step "tests" {TEST_CMD}')
    (d / "eval/checks.sh").write_text(chk)
    write(d / "design/shop/prd.md", '''
        ---
        feature: shop
        status: draft
        ---
        # PRD: giỏ hàng

        ## 1. Product brief
        - **Vấn đề:** cần thao tác giỏ hàng cơ bản.

        ## 3. Yêu cầu chức năng
        - **REQ-01** (must) — Thêm sản phẩm vào giỏ. *Kiểm chứng:* add_item cộng dồn số lượng; qty <= 0 báo ValueError.
        - **REQ-02** (must) — Bớt sản phẩm khỏi giỏ. *Kiểm chứng:* remove_item trừ số lượng, về 0 thì xoá sku.
    ''')
    write(d / "tasks/shop/EPIC.md", '''
        ---
        id: SHOP
        type: epic
        epic: SHOP
        status: draft
        design: design/shop
        requirements: [REQ-01, REQ-02]
        holdout: true
        ---

        # Mục tiêu
        Giỏ hàng thêm/bớt được sản phẩm.

        # Acceptance (thang điểm — đo được, có/không)
        - [ ] Luồng: tạo giỏ → thêm → bớt hoạt động đúng end-to-end
    ''')
    write(d / "tasks/shop/SHOP-01.md", '''
        ---
        id: SHOP-01
        type: task
        epic: SHOP
        status: draft
        depends_on: []
        requirements: [REQ-01]
        priority: 1
        holdout: true
        design: design/shop
        ---

        # Mục tiêu
        Thêm hàm add_item vào giỏ hàng.

        # Interface (hợp đồng)
        `add_item(cart: dict, sku: str, qty: int) -> int` trong `src/shop/cart.py`:
        cộng `qty` vào số lượng hiện có của `sku` (chưa có thì coi là 0), trả về số lượng mới.
        `qty <= 0` → raise `ValueError`.

        # Acceptance (thang điểm — đo được, có/không)
        - [ ] `bash eval/checks.sh` pass
        - [ ] add_item(new_cart(), "A", 2) trả về 2; gọi tiếp add_item(cart, "A", 3) trả về 5
        - [ ] add_item(cart, "A", 0) raise ValueError
        - [ ] Có unittest cho các dòng trên trong tests/

        # Ngoài phạm vi
        Không thêm hàm nào khác.
    ''')
    write(d / "tasks/shop/SHOP-02.md", '''
        ---
        id: SHOP-02
        type: task
        epic: SHOP
        status: draft
        depends_on: []
        requirements: [REQ-02]
        priority: 2
        holdout: false
        design: design/shop
        ---

        # Mục tiêu
        Thêm hàm remove_item vào giỏ hàng.

        # Interface (hợp đồng)
        `remove_item(cart: dict, sku: str, qty: int) -> int` trong `src/shop/cart.py`:
        trừ `qty` khỏi số lượng của `sku`, trả về số lượng còn lại; còn lại <= 0 thì xoá `sku`
        khỏi giỏ và trả về 0. `sku` không có trong giỏ → raise `KeyError`.

        # Acceptance (thang điểm — đo được, có/không)
        - [ ] `bash eval/checks.sh` pass
        - [ ] cart {"A": 5}: remove_item(cart, "A", 2) trả về 3
        - [ ] cart {"A": 1}: remove_item(cart, "A", 5) trả về 0 và "A" không còn trong cart
        - [ ] remove_item(cart, "Z", 1) raise KeyError
        - [ ] Có unittest cho các dòng trên trong tests/

        # Ngoài phạm vi
        Không sửa add_item.
    ''')
    if trap:
        # The epic's hidden end-to-end test expects cart_total(), which no task implements →
        # the epic check FAILs deterministically, exercising the "epic FAIL → bug issue" path.
        write(holdout_dir / "SHOP" / "tests" / "test_shop_flow.py", '''
            import unittest
            from shop.cart import new_cart, add_item, remove_item, cart_total


            class TestFlow(unittest.TestCase):
                def test_flow(self):
                    c = new_cart()
                    add_item(c, "A", 2)
                    remove_item(c, "A", 1)
                    self.assertEqual(cart_total(c, {"A": 10}), 10)
        ''')


def setup_project(d: Path, agent: str, agent_cmd: str = "", remote: str = "", trap: bool = True,
                  machine: str = "selftest", extra_cfg: dict = None) -> Path:
    holdout = d.parent / f"{d.name}-holdout"
    if remote:
        if subprocess.run(["git", "ls-remote", "--heads", remote], capture_output=True, text=True).stdout.strip():
            raise SystemExit(f"Repo {remote} không trống. Dùng một repo GitHub mới, chưa có commit nào.")
        sh(["git", "clone", "-q", remote, str(d)], d.parent, check=False)
        d.mkdir(parents=True, exist_ok=True)
        if not (d / ".git").exists():
            git_init(d)
            sh(["git", "remote", "add", "origin", remote], d)
        sh(["git", "checkout", "-q", "-B", "main"], d)
        sh(["git", "config", "user.email", "selftest@agent-kit"], d)
        sh(["git", "config", "user.name", "agent-kit selftest"], d)
    else:
        d.mkdir(parents=True, exist_ok=True)
        git_init(d)
    shutil.rmtree(holdout, ignore_errors=True)
    make_project(d, trap, holdout)
    gh_ok = bool(remote) and "github.com" in remote and bool(shutil.which("gh")) and \
        subprocess.run(["gh", "api", "repos/" + re.sub(r"(\.git)?/?$", "", remote.split("github.com/")[-1].split("github.com:")[-1])],
                       capture_output=True).returncode == 0
    cfg = dict(AGENT=agent, AGENT_CMD=f'"{agent_cmd}"' if agent_cmd else "", MACHINE_NAME=machine,
               HOLDOUT_DIR=str(holdout), HOLDOUT_CMD=f'"{TEST_CMD}"', EPIC_TEST_CMD="",
               GH_SYNC="1" if gh_ok else "0", PUBLISH="1" if remote else "0",
               GIT_PULL="1" if remote else "0", MAX_TASKS="3", MAX_ATTEMPTS="2")
    cfg.update(extra_cfg or {})
    set_cfg(d, **cfg)
    commit_all(d, "selftest: project + agent-kit")
    if remote:
        sh(["git", "push", "-q", "-u", "origin", "main"], d)
    r = kit(d, "approve", "design/shop")
    if r.returncode != 0:
        raise SystemExit(r.stdout + r.stderr)
    r = kit(d, "approve", "SHOP")
    if r.returncode != 0:
        raise SystemExit(r.stdout + r.stderr)
    commit_all(d, "selftest: approve PRD + tasks")
    if remote:
        sh(["git", "push", "-q", "origin", "main"], d)
    return holdout


# ───────────────────────── advance / verify ─────────────────────────
def load_kit(d: Path):
    sys.path.insert(0, str(d / "runner"))
    os.chdir(d)
    import importlib
    if "kit" in sys.modules:
        del sys.modules["kit"]
    return importlib.import_module("kit")


def cmd_advance(args):
    d = Path(args.dir).resolve()
    k = load_kit(d)
    st, _, _ = k.view_state()
    tasks = k.load_tasks()
    merged = 0
    for t in tasks.values():
        rec = st.get(str(t["id"]), {})
        if t["type"] == "epic" or rec.get("status") != "review":
            continue
        if k.flag("GH_SYNC") and rec.get("pr"):
            r = sh(["gh", "pr", "merge", rec["pr"], "--merge"], d, check=False)
            print(("✓ merge PR " if r.returncode == 0 else "✗ không merge được PR ") + rec["pr"] +
                  ("" if r.returncode == 0 else f": {r.stderr.strip()[:200]}"))
        else:
            sh(["git", "fetch", "-q", "origin", rec["branch"]], d, check=False)
            ref = rec["branch"] if sh(["git", "rev-parse", "-q", "--verify", rec["branch"]], d, check=False).returncode == 0 \
                else f"origin/{rec['branch']}"
            r = sh(["git", "merge", "-q", "--no-ff", "--no-edit", ref], d, check=False)
            print(("✓ merge " if r.returncode == 0 else "✗ merge lỗi ") + rec["branch"])
            if r.returncode == 0:
                k.set_status(t, st, "done")
        merged += 1
    if k.has_origin():
        if not k.flag("GH_SYNC"):
            sh(["git", "push", "-q", "origin", "main"], d, check=False)
        sh(["git", "pull", "-q", "--ff-only"], d, check=False)
    k.publish(st, msg="selftest advance")
    print(kit(d, "sync").stdout)
    print(f"Đã merge {merged} task. Tiếp theo: python3 runner/kit.py work (để chạy kiểm thử epic), rồi selftest verify.")


def cmd_verify(args):
    d = Path(args.dir).resolve()
    k = load_kit(d)
    st, hosts, _ = k.view_state()
    tasks = k.load_tasks()
    res = {"✓": 0, "✗": 0, "–": 0}

    def check(ok, msg, skip=False):
        mark = "–" if skip else ("✓" if ok else "✗")
        res[mark] += 1
        print(f"  {mark} {msg}")

    runs = {}
    for name, host, src in k.run_dirs():
        for tid in ("SHOP-01", "SHOP-02", "SHOP"):
            if tid not in runs:
                txt = k.run_file(host, name, src, f"{tid}/result.json")
                if txt:
                    runs[tid] = (name, host, src, json.loads(txt))

    print("Task")
    for tid in ("SHOP-01", "SHOP-02"):
        s = st.get(tid, {}).get("status")
        check(s in ("review", "done"), f"{tid}: trạng thái {s} (cần review hoặc done)")
        r = runs.get(tid)
        check(bool(r and r[3].get("passed")), f"{tid}: lượt chạy gần nhất PASS"
              + (f" — lý do FAIL: {'; '.join(r[3].get('reasons', []))}" if r and not r[3].get("passed") else ""))
        if r:
            rv = k.run_file(r[1], r[0], r[2], f"{tid}/review.json")
            verdict = json.loads(rv or "{}").get("verdict")
            check(verdict in ("PASS", "FAIL"), f"{tid}: reviewer độc lập đã chấm ({verdict})")
            ch = k.run_file(r[1], r[0], r[2], f"{tid}/checks.log")
            check(bool(ch), f"{tid}: có log eval/checks.sh")
    hd = Path(k.CFG["HOLDOUT_DIR"])
    check((hd / "SHOP-01").exists(), f"SHOP-01 (holdout: true): test-writer đã viết test ẩn → {hd / 'SHOP-01'}")
    r = runs.get("SHOP-01")
    if r:
        check(bool(k.run_file(r[1], r[0], r[2], "SHOP-01/holdout.log")), "SHOP-01: test ẩn đã được chạy khi chấm")
    for tid in ("SHOP-01", "SHOP-02"):
        br = st.get(tid, {}).get("branch")
        if br:
            base = k.CFG["BASE_BRANCH"]
            ref = br if sh(["git", "rev-parse", "-q", "--verify", br], d, check=False).returncode == 0 else f"origin/{br}"
            changed = sh(["git", "diff", "--name-only", f"{base}...{ref}"], d, check=False).stdout.split()
            bad = [p for p in changed if k.is_protected(p)]
            check(not bad, f"{tid}: không sửa vùng bảo vệ" + (f" (đã sửa: {', '.join(bad)})" if bad else ""))
    print("\nEpic")
    es = st.get("SHOP", {}).get("status") or k.status_of(tasks["SHOP"], st)
    trap = (hd / "SHOP" / "tests" / "test_shop_flow.py").exists() and \
        "cart_total" in (hd / "SHOP" / "tests" / "test_shop_flow.py").read_text()
    if es in ("queued", "verify"):
        check(False, f"SHOP: đang '{es}' — chưa kiểm thử epic. Chạy: selftest advance, rồi kit.py work")
    elif trap:
        check(es == "failed", f"SHOP: kiểm thử epic có bẫy → phải FAIL (hiện: {es})")
    else:
        check(es == "done", f"SHOP: kiểm thử epic PASS (hiện: {es})")
    if trap and k.flag("GH_SYNC"):
        r = sh(["gh", "issue", "list", "--label", "bug", "--label", "agent-ready", "--state", "all",
                "--search", "[SHOP] in:title", "--json", "number,title,url,labels"], d, check=False)
        items = [i for i in json.loads(r.stdout or "[]") if "[SHOP]" in i["title"]]
        check(bool(items), "epic FAIL → đã mở GitHub Issue nhãn bug + agent-ready"
              + (f": {items[0]['url']}" if items else ""))
    else:
        check(True, "GitHub Issue khi epic FAIL", skip=True)

    print("\nGitHub" + ("" if k.flag("GH_SYNC") else " (bỏ qua: GH_SYNC=0)"))
    if k.flag("GH_SYNC"):
        for tid in ("SHOP-01", "SHOP-02"):
            check(bool(tasks[tid].get("issue")), f"{tid}: có GitHub Issue #{tasks[tid].get('issue') or '-'}")
            check(bool(st.get(tid, {}).get("pr")), f"{tid}: có Pull Request {st.get(tid, {}).get('pr') or ''}")
        r = sh(["gh", "label", "list", "--limit", "100", "--json", "name"], d, check=False)
        names = {x["name"] for x in json.loads(r.stdout or "[]")}
        check({"agent-kit", "status:review", "status:done"} <= names, "nhãn agent-kit / status:* đã được tạo")

    print("\nChia sẻ giữa các máy" + ("" if k.flag("PUBLISH") else " (bỏ qua: PUBLISH=0)"))
    if k.flag("PUBLISH"):
        k.fetch_log()
        check(k.log_ref_exists(), f"có nhánh {k.LOG_BRANCH} trên origin")
        check(bool(k.log_ls(f"state/{k.HOST}.json")), f"có state/{k.HOST}.json trên nhánh log")
        check(bool(k.log_ls(f"runs/{k.HOST}/")), f"có log các phiên trong runs/{k.HOST}/")

    print("\nTổng thể")
    r = kit(d, "doctor")
    check(r.returncode == 0, "kit.py doctor không có lỗi (✗)" + ("" if r.returncode == 0 else ":\n" + "\n".join(
        l for l in r.stdout.splitlines() if "✗" in l)))
    print(f"\nKết quả: {res['✓']} đạt, {res['✗']} không đạt, {res['–']} bỏ qua")
    sys.exit(1 if res["✗"] else 0)


def cmd_setup(args):
    d = Path(args.dir).expanduser().resolve()
    if d.exists() and any(d.iterdir()):
        raise SystemExit(f"{d} đã có dữ liệu. Chọn thư mục mới.")
    if args.agent == "cli" and not args.agent_cmd:
        raise SystemExit("--agent cli cần --agent-cmd, ví dụ: --agent-cmd 'copilot -p {prompt} -s --no-ask-user --allow-all-tools'")
    hold = setup_project(d, args.agent, args.agent_cmd, args.remote, trap=not args.no_trap)
    print(f"✓ Project thử: {d}")
    print(f"  Test ẩn (ngoài repo): {hold}" + (" — đã cài sẵn bẫy cho epic SHOP" if not args.no_trap else ""))
    print(f"  Agent: {args.agent}" + (f" · {args.agent_cmd}" if args.agent_cmd else ""))
    print(f"  GitHub: {'bật' if 'GH_SYNC=1' in (d / 'runner/config.env').read_text() else 'tắt'}")
    me = Path(__file__).resolve()
    if args.agent == "chat":
        print(textwrap.dedent(f"""
        Tiếp theo:
          1. Mở {d} trong VS Code, mở Copilot Chat (chế độ Agent) và nói:
             "Chạy python3 runner/kit.py work trong terminal và làm theo BƯỚC TIẾP THEO nó in ra,
              lặp lại cho tới khi nó báo task đã chấm xong. Rồi chạy lại work cho task tiếp theo."
             (bước test-writer và reviewer nên mở một cuộc chat mới)
          2. Khi cả SHOP-01 và SHOP-02 đã ✅: python3 {me} advance {d}
          3. Bảo Copilot chạy lại `python3 runner/kit.py work` (kiểm thử epic)
          4. python3 {me} verify {d}
        """))
    else:
        print(textwrap.dedent(f"""
        Tiếp theo:
          cd {d}
          python3 runner/kit.py work          # agent làm SHOP-01, SHOP-02 (test-writer, implementer, reviewer)
          python3 {me} advance {d}            # giả lập bạn merge PR
          python3 runner/kit.py work          # kiểm thử cấp epic
          python3 {me} verify {d}
        """))


# ───────────────────────── offline scenarios (fake agents) ─────────────────────────
FAKE_AGENT = r'''
import json, os, re, subprocess, sys
argv = sys.argv[1:]
prompt = ""
if "-p" in argv:
    prompt = argv[argv.index("-p") + 1]
elif argv and not argv[0].startswith("-"):
    prompt = argv[0]
if "--version" in argv:
    print("2.1.296 (Claude Code)"); sys.exit(0)
if not prompt:
    prompt = sys.stdin.read()
claude_json = "--output-format" in argv

def out(text):
    print(json.dumps({"result": text, "total_cost_usd": 0}) if claude_json else text); sys.exit(0)

def append(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f: f.write(text)

if "Chấm task" in prompt:
    out('{"verdict": "PASS", "reasons": [], "risks": []}')
m = re.findall(r"holdout-staging/([A-Za-z0-9_-]+)/", prompt)
if ("Viết bài kiểm tra ẩn" in prompt or "END-TO-END" in prompt) and m:
    tid = m[-1]
    body = ("from shop.cart import new_cart, add_item\n"
            "def test_hidden():\n    c = new_cart(); assert add_item(c, 'A', 2) == 2\n")
    if tid == "SHOP":
        body = "import unittest\nfrom shop.cart import new_cart, add_item, remove_item\nclass T(unittest.TestCase):\n    def test(self):\n        c = new_cart(); add_item(c,'A',2); self.assertEqual(remove_item(c,'A',1), 1)\n"
    else:
        body = "import unittest\nfrom shop.cart import new_cart, add_item\nclass T(unittest.TestCase):\n    def test(self):\n        c = new_cart(); self.assertEqual(add_item(c,'A',2), 2)\n        with self.assertRaises(ValueError): add_item(c,'A',0)\n"
    append(f".agent-kit/holdout-staging/{tid}/tests/test_hidden_{tid.lower().replace('-','_')}.py", body)
    out("wrote hidden test")
tm = re.search(r"Bạn đang làm task `([^`]+)`", prompt)
if tm:
    tid = tm.group(1)
    code = {
        "SHOP-01": "\n\ndef add_item(cart, sku, qty):\n    if qty <= 0:\n        raise ValueError('qty')\n    cart[sku] = cart.get(sku, 0) + qty\n    return cart[sku]\n",
        "SHOP-02": "\n\ndef remove_item(cart, sku, qty):\n    if sku not in cart:\n        raise KeyError(sku)\n    left = cart[sku] - qty\n    if left <= 0:\n        del cart[sku]\n        return 0\n    cart[sku] = left\n    return left\n",
        "FIX-1": "\n\ndef cart_total(cart, prices):\n    return sum(prices[s] * q for s, q in cart.items())\n",
    }.get(tid, "")
    if tid == "CHEAT-1":
        append("eval/checks.sh", "\nexit 0\n")
    elif tid == "LAZY-1":
        pass
    else:
        # mỗi task chèn vào mốc riêng (cách nhau một dòng không đổi) → merge PR trên GitHub không xung đột
        cart = open("src/shop/cart.py").read()
        marker = f"# [{tid}]\n"
        cart = cart.replace(marker, marker + code.lstrip("\n"), 1) if marker in cart else cart + code
        open("src/shop/cart.py", "w").write(cart)
    subprocess.run(["git", "add", "-A"], capture_output=True)
    subprocess.run(["git", "commit", "-qm", f"{tid}: work", "--no-verify"], capture_output=True)
    out(f"{tid} done")
out("nothing to do")
'''


class Offline:
    def __init__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="agent-kit-selftest-"))
        self.fake = self.tmp / "fake_agent.py"
        self.fake.write_text(FAKE_AGENT)
        self.fake_bin = self.tmp / "fake-claude"
        self.fake_bin.write_text(f"#!/bin/sh\nexec {PY} {self.fake} \"$@\"\n")
        self.fake_bin.chmod(0o755)
        self.ok = self.fail = 0

    def check(self, cond, msg):
        if cond:
            self.ok += 1
            print(f"  ✓ {msg}")
        else:
            self.fail += 1
            print(f"  ✗ {msg}")

    def project(self, name, agent, trap=True, remote="", machine="m1", **cfg):
        d = self.tmp / name
        extra = {"CLAUDE_BIN": str(self.fake_bin), "GH_SYNC": "0", **cfg}
        if remote:
            extra.update(PUBLISH="1", GIT_PULL="1")
        setup_project(d, agent, agent_cmd=(f"{PY} {self.fake}" if agent == "cli" else ""), trap=trap,
                      machine=machine, extra_cfg=extra, remote=remote)
        return d

    def status(self, d):
        k = json.loads((d / ".agent-kit/state.json").read_text())
        return {t: r.get("status") for t, r in k.items()}

    def add_task(self, d, tid, epic="SHOP", holdout="false"):
        write(d / f"tasks/shop/{tid}.md", f'''
            ---
            id: {tid}
            type: task
            epic: {epic}
            status: approved
            holdout: {holdout}
            design: design/shop
            ---
            # Mục tiêu
            {tid}
            # Acceptance (thang điểm — đo được, có/không)
            - [ ] làm đúng
        ''')
        commit_all(d, f"add {tid}")

    def run_all(self):
        print(f"Thư mục tạm: {self.tmp}\n")
        self.scenario_claude()
        self.scenario_cli()
        self.scenario_chat()
        self.scenario_two_machines()
        print(f"\nKết quả offline: {self.ok} đạt, {self.fail} không đạt")
        if not self.fail:
            shutil.rmtree(self.tmp, ignore_errors=True)
        return self.fail == 0

    def scenario_claude(self):
        print("Kịch bản 1 — AGENT=claude (agent giả): task PASS, epic có bẫy FAIL, sửa xong epic PASS")
        d = self.project("claude", "claude")
        r = kit(d, "work")
        s = self.status(d)
        self.check(s.get("SHOP-01") == "review" and s.get("SHOP-02") == "review", f"work: SHOP-01, SHOP-02 → review ({s})")
        self.check((d.parent / "claude-holdout/SHOP-01").exists(), "test-writer viết test ẩn cho SHOP-01 trước khi làm")
        sh([PY, str(Path(__file__).resolve()), "advance", str(d)], d)
        s = self.status(d)
        self.check(s.get("SHOP") == "verify", f"advance + sync: epic SHOP → verify ({s.get('SHOP')})")
        kit(d, "work")
        self.check(self.status(d).get("SHOP") == "failed", "kiểm thử epic có bẫy (cart_total) → failed")
        self.add_task(d, "FIX-1")
        kit(d, "work")
        self.check(self.status(d).get("FIX-1") == "review", "task sửa FIX-1 (epic: SHOP) → review")
        sh([PY, str(Path(__file__).resolve()), "advance", str(d)], d)
        self.check(self.status(d).get("SHOP") == "verify", "task sửa merge xong → epic tự về verify")
        kit(d, "work")
        self.check(self.status(d).get("SHOP") == "done", "kiểm thử epic lại → done")
        tr = kit(d, "trace", "--offline").stdout
        self.check("Hoàn thành: 2/2" in tr, "trace: 2/2 yêu cầu hoàn thành")

    def scenario_cli(self):
        print("\nKịch bản 2 — AGENT=cli (prompt qua tham số): gian lận và làm biếng bị chấm FAIL")
        d = self.project("cli", "cli", trap=False)
        for tid in ("CHEAT-1", "LAZY-1"):
            self.add_task(d, tid, epic="X")
        kit(d, "work", "--task", "CHEAT-1")
        st = json.loads((d / ".agent-kit/state.json").read_text())
        self.check("sửa vùng bảo vệ: eval/checks.sh" in str(st.get("CHEAT-1", {}).get("last_fail")),
                   "sửa eval/checks.sh → FAIL 'sửa vùng bảo vệ'")
        kit(d, "work", "--task", "LAZY-1")
        st = json.loads((d / ".agent-kit/state.json").read_text())
        self.check("không có thay đổi nào" in str(st.get("LAZY-1", {}).get("last_fail")),
                   "không làm gì → FAIL 'không có thay đổi nào'")
        kit(d, "work", "--task", "SHOP-01")
        self.check(self.status(d).get("SHOP-01") == "review", "task làm đúng → PASS")

    def scenario_chat(self):
        print("\nKịch bản 3 — AGENT=chat: từng bước, test ẩn, sửa sau khi FAIL, reviewer, huỷ")
        d = self.project("chat", "chat", trap=False)
        out = kit(d, "work", "--task", "SHOP-01").stdout
        self.check("VIẾT BÀI TEST ẨN" in out, "bước 1: yêu cầu viết test ẩn")
        write(d / ".agent-kit/holdout-staging/SHOP-01/tests/test_hidden_add.py", '''
            import unittest
            from shop.cart import new_cart, add_item
            class T(unittest.TestCase):
                def test(self):
                    self.assertEqual(add_item(new_cart(), "A", 2), 2)
        ''')
        out = kit(d, "work").stdout
        self.check("LÀM TASK SHOP-01" in out, "bước 2: chuyển test ẩn ra ngoài repo, giao implementer")
        cur = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"], d).stdout.strip()
        self.check(cur == "agent/SHOP-01-a1", f"đã chuyển sang nhánh làm việc ({cur})")
        with open(d / "eval/checks.sh", "a") as f:
            f.write("\n# cheat\n")
        commit_all(d, "cheat")
        out = kit(d, "work").stdout
        self.check("sửa vùng bảo vệ" in out and "SỬA TASK" in out, "gian lận → yêu cầu sửa, nêu lý do")
        self.check("test_hidden_add" not in out, "không lộ nội dung test ẩn khi FAIL")
        sh(["git", "revert", "--no-edit", "HEAD"], d)
        with open(d / "src/shop/cart.py", "a") as f:
            f.write("\n\ndef add_item(cart, sku, qty):\n    if qty <= 0:\n        raise ValueError\n"
                    "    cart[sku] = cart.get(sku, 0) + qty\n    return cart[sku]\n")
        commit_all(d, "add_item")
        out = kit(d, "work").stdout
        self.check("CHẤM ĐỘC LẬP" in out, "sửa đúng → chuyển sang reviewer độc lập")
        write(d / ".agent-kit/reviews/SHOP-01.json", '{"verdict": "PASS", "reasons": []}')
        out = kit(d, "work").stdout
        cur = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"], d).stdout.strip()
        self.check("✅ SHOP-01" in out and cur == "main", "hoàn tất: PASS và về nhánh main")
        out = kit(d, "work", "--task", "SHOP-02").stdout
        self.check("LÀM TASK SHOP-02" in out, "task tiếp theo bắt đầu")
        out = kit(d, "work", "--abort").stdout
        st = json.loads((d / ".agent-kit/state.json").read_text())
        self.check("Đã huỷ" in out and st["SHOP-02"]["status"] == "queued" and st["SHOP-02"].get("attempts") == 0,
                   "work --abort: về queued, không tính lượt thử")

    def scenario_two_machines(self):
        print("\nKịch bản 4 — hai máy dùng chung remote: khoá, chia sẻ trạng thái, lệnh chỉ đọc")
        remote = self.tmp / "remote.git"
        sh(["git", "init", "-q", "--bare", "-b", "main", str(remote)], self.tmp)
        a = self.project("machineA", "claude", trap=False, remote=str(remote), machine="A")
        b = self.tmp / "machineB"
        sh(["git", "clone", "-q", str(remote), str(b)], self.tmp)
        sh(["git", "config", "user.email", "b@b"], b)
        sh(["git", "config", "user.name", "b"], b)
        shutil.copy(a / "runner/config.env", b / "runner/config.env")
        set_cfg(b, MACHINE_NAME="B")
        lock_env = dict(os.environ)
        r = sh([PY, "-c", "import sys; sys.argv=['x']; sys.path.insert(0,'runner'); import kit; kit.acquire_lock()"], a)
        r = kit(b, "work", "--max", "1")
        self.check("Máy khác đang làm việc" in (r.stdout + r.stderr), "máy B bị chặn khi máy A giữ khoá")
        sh([PY, "-c", "import sys; sys.argv=['x']; sys.path.insert(0,'runner'); import kit; kit.release_lock()"], a)
        kit(a, "work", "--max", "1")
        before = sh(["git", "status", "--porcelain"], b).stdout
        out = kit(b, "status").stdout
        self.check("SHOP-01" in out and " A " in out, "máy B thấy task do máy A làm")
        kit(b, "report")
        kit(b, "doctor")
        after = sh(["git", "status", "--porcelain"], b).stdout
        self.check(before == after, "status / report / doctor không sửa gì trên máy B")
        sh(["git", "pull", "-q"], b)
        r = kit(b, "work", "--max", "1")
        out = kit(a, "status").stdout
        self.check("SHOP-02" in out and " B " in out, "máy A thấy task do máy B làm tiếp")


def cmd_offline(_args):
    ok = Offline().run_all()
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("offline").set_defaults(fn=cmd_offline)
    p = sub.add_parser("setup")
    p.add_argument("dir")
    p.add_argument("--agent", choices=["claude", "cli", "chat"], required=True)
    p.add_argument("--agent-cmd", default="")
    p.add_argument("--remote", default="")
    p.add_argument("--no-trap", action="store_true")
    p.set_defaults(fn=cmd_setup)
    p = sub.add_parser("advance"); p.add_argument("dir"); p.set_defaults(fn=cmd_advance)
    p = sub.add_parser("verify"); p.add_argument("dir"); p.set_defaults(fn=cmd_verify)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
