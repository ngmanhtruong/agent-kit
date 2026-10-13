# agent-kit

Bộ khung để các AI agent (Claude Code) **tự làm việc khi bạn ngủ** mà vẫn đáng tin:

```
Ý tưởng → Design (Claude Design) → Tasks (markdown + GitHub Issue)
       → Agent làm từng task → Tự chấm bài → Pull Request → Bạn review & merge
```

Tài liệu này viết cho **hai loại người đọc**:
- **Người dùng**: đọc từ mục 1 đến mục 9.
- **AI agent** (Claude Code làm việc trong repo): đọc mục 10 trước khi làm bất cứ việc gì.

---

## Mục lục
1. [Triết lý: 3 việc bắt buộc](#1-triết-lý-3-việc-bắt-buộc)
2. [Toàn cảnh hệ thống](#2-toàn-cảnh-hệ-thống)
3. [Bản đồ file](#3-bản-đồ-file)
4. [Cài đặt](#4-cài-đặt)
5. [Điền 4 file bắt buộc](#5-điền-4-file-bắt-buộc)
6. [Quy trình hằng ngày](#6-quy-trình-hằng-ngày)
7. [Lệnh `kit.py`](#7-lệnh-kitpy)
8. [Cấu hình `runner/config.env`](#8-cấu-hình-runnerconfigenv)
9. [Xử lý sự cố & câu hỏi thường gặp](#9-xử-lý-sự-cố--câu-hỏi-thường-gặp)
10. [Dành cho AI agent](#10-dành-cho-ai-agent)

---

## 1. Triết lý: 3 việc bắt buộc

> "Chưa xong 3 việc này mà mở hàng chục AI thì chỉ tổ đốt tiền."
> AI giống một nhân viên lành nghề nhưng vừa vào làm được 5 giây.

| # | Việc | Câu hỏi nó trả lời | Hiện thực trong kit |
|---|---|---|---|
| 01 | **Đặt thang điểm để AI tự chấm bài** | "Làm sao biết bài đúng mà không cần tôi xem từng dòng?" | `eval/checks.sh`, mục Acceptance trong task, **bài test ẩn**, agent `reviewer`, hook chặn dừng khi chưa pass |
| 02 | **Viết sẵn bối cảnh** | "AI cần biết gì mà nó không tự đoán được?" | `CLAUDE.md`, `docs/`, `design/`, mục Interface trong task |
| 03 | **Dựng hàng rào** | "Làm sao chặn AI vượt giới hạn mà không cần ai nhớ đi kiểm?" | Rào cứng: hooks + permissions + worktree riêng + không cho push. Rào mềm: `CLAUDE.md` |

Các nguyên tắc đi kèm:
- **Chưa tin 1 agent thì đừng mở thêm.** Bắt đầu 1 task/đêm, tăng dần.
- **Rào cứng > rào mềm.** Lỗi nào lặp lại 2 lần → biến thành check tự động (skill `promote-rule`).
- **Cấm AI tự ghi chú.** AI không được sửa `CLAUDE.md`, `docs/`. Muốn đổi thì đề xuất trong báo cáo, người quyết. Tránh "một lời góp ý thành lệnh cấm vĩnh viễn".
- **Giấu bài kiểm tra.** Test ẩn nằm ngoài repo, đặt tên như test bình thường; agent làm bài không bao giờ thấy.
- **Cách làm đúng phải là cách dễ nhất.** Một lệnh chấm duy nhất, một lệnh chạy duy nhất.

---

## 2. Toàn cảnh hệ thống

### 2.1 Luồng công việc

```
 BẠN · MacBook (ngày)                MINI PC (đêm, cron)                    BẠN (sáng)
 ────────────────────                ───────────────────                    ──────────
 1. Claude Design                    5. kit.py night                        7. GitHub: đọc PR
    → export vào design/<feature>/      với mỗi task sẵn sàng:                 (đã kèm điểm chấm)
 2. kit.py plan                          a. tạo nhánh + worktree riêng       8. Merge hoặc đóng PR
    → planner sinh tasks nháp            b. WORKER làm bài                   9. kit.py sync
 3. Bạn sửa, trả lời câu hỏi mở          c. eval/checks.sh  (thang điểm)        → task "done",
 4. kit.py approve                       d. test ẩn         (worker không thấy)    mở khoá task phụ thuộc
    → GitHub Issue                       e. REVIEWER chấm độc lập
    → TEST-WRITER viết test ẩn           f. PASS → push + mở PR
    → git push                              FAIL → thử lại, kèm lý do lần trước
                                     6. Báo cáo → file + Telegram
```

### 2.2 Bốn vai trò agent

| Vai trò | Khi nào chạy | Được ghi vào đâu | File định nghĩa |
|---|---|---|---|
| **planner** | `kit.py plan` | chỉ `tasks/` | `.claude/agents/planner.md` |
| **test-writer** | `kit.py approve` (task có `holdout: true`) | chỉ `.agent-kit/holdout-staging/` | `.claude/agents/test-writer.md` |
| **worker** | `kit.py night` | mọi nơi **trừ** vùng bảo vệ | (mặc định, theo `CLAUDE.md`) |
| **reviewer** | `kit.py night`, sau worker | không ghi gì | `.claude/agents/reviewer.md` |

Vai trò được truyền qua biến môi trường `AGENT_KIT_ROLE`, hook đọc biến này để giới hạn quyền ghi.

### 2.3 Vòng đời một task

```
draft ──approve──▶ queued ──night──▶ running ──┬─ PASS ─▶ review ──merge PR──▶ done
                     ▲                         │                 └─đóng PR───▶ failed
                     └──── FAIL (còn lượt) ────┤
                                               └─ FAIL (hết lượt) ─▶ failed + nhãn needs-human
```

- `draft`, `approved`: ghi trong file `tasks/*.md` (do **người** quyết).
- `queued`, `running`, `review`, `done`, `failed`: trạng thái chạy, ghi ở `.agent-kit/state.json` và nhãn GitHub Issue `status:*`.
- Task chỉ chạy khi mọi task trong `depends_on` đã `done` (tức PR đã merge).

### 2.4 Vì sao trạng thái chạy không nằm trong file task?

MacBook (bạn sửa `tasks/`) và mini PC (runner) cùng làm việc trên một repo. Nếu runner sửa file task, hai máy sẽ xung đột git. Vì vậy:
- **File task = spec**, chỉ người sửa, commit + push từ MacBook.
- **Trạng thái chạy = GitHub Issue labels**, cả hai máy đọc qua `kit.py sync`.

---

## 3. Bản đồ file

Sau khi cài vào project, repo của bạn có thêm:

```
your-project/
├── CLAUDE.md                     ★ Bản đồ dự án cho AI (bạn điền)
├── docs/
│   ├── architecture.md           ★ Sơ đồ các bộ phận (bạn điền)
│   ├── conventions.md              Quy chuẩn chưa tự động hoá được (thêm dần)
│   └── decisions/0000-template.md  Mẫu ghi quyết định kiến trúc (ADR)
├── design/
│   ├── README.md                   Hướng dẫn đặt file design
│   └── <feature>/                  spec.md + file export từ Claude Design
├── tasks/
│   ├── _TEMPLATE.md                Mẫu một task
│   └── <feature>/                  EPIC.md + các task (planner sinh, bạn duyệt)
├── eval/
│   └── checks.sh                 ★ Thang điểm: 1 lệnh, exit 0 = đạt (bạn điền)
├── runner/
│   ├── kit.py                      Bộ điều phối (plan / approve / night / sync / ...)
│   ├── config.env.example          Mẫu cấu hình
│   └── config.env                ★ Cấu hình riêng từng máy (bạn điền, KHÔNG commit)
├── .claude/
│   ├── settings.json               Permissions + đăng ký hooks
│   ├── hooks/
│   │   ├── _common.py              Vùng bảo vệ, vai trò, tiện ích chung
│   │   ├── guard_bash.py           Chặn lệnh shell nguy hiểm
│   │   ├── guard_files.py          Chặn ghi file vào vùng bảo vệ / ngoài vai trò
│   │   └── stop_checks.py          Không cho worker dừng khi checks.sh chưa pass
│   ├── agents/
│   │   ├── planner.md              Design → epic + tasks
│   │   ├── test-writer.md          Task → bài test ẩn
│   │   └── reviewer.md             Chấm độc lập → JSON PASS/FAIL
│   └── skills/
│       ├── finish-task/SKILL.md    Quy trình bắt buộc khi hoàn tất task
│       └── promote-rule/SKILL.md   Biến lỗi lặp lại thành quy định tự động
└── .agent-kit/                     (gitignore) state, logs, báo cáo từng đêm
```

★ = 4 file bắt buộc phải điền (xem mục 5).

### 3.1 Tác dụng chi tiết từng file

| File | Ai sửa | Tác dụng |
|---|---|---|
| `CLAUDE.md` | Người | Claude Code tự đọc file này đầu mỗi phiên. Nói AI biết sản phẩm làm gì, được/cấm đụng đâu, thế nào là "xong". |
| `docs/architecture.md` | Người | Module nào làm gì, dữ liệu chạy qua đâu, chỗ nào nguy hiểm. Giúp AI sửa đúng chỗ. |
| `docs/conventions.md` | Người | Quy tắc code mà **chưa** biến được thành check tự động. Mỗi dòng ghi rõ đã tự động hoá chưa. |
| `docs/decisions/` | Người | Lý do các quyết định đã chốt, để AI không "sáng tạo" ngược lại. |
| `design/<feature>/spec.md` | Người | Mục tiêu, người dùng, luồng chính, ràng buộc, điều KHÔNG làm. |
| `design/<feature>/*.pdf/png/html` | Người | Export từ Claude Design. Planner đọc được ảnh và PDF. |
| `tasks/_TEMPLATE.md` | Người | Định dạng chuẩn của một task. Planner bám theo. |
| `tasks/<feature>/*.md` | Planner sinh, người duyệt | Spec của từng task: mục tiêu, interface, acceptance. |
| `eval/checks.sh` | Người | Bài chấm chung. Worker phải pass mới được dừng; runner chạy lại để xác nhận. |
| `runner/kit.py` | Không ai (trừ khi nâng cấp kit) | Điều phối toàn bộ luồng. |
| `runner/config.env` | Người, từng máy | Số task/đêm, đường dẫn `claude`, test ẩn, GitHub, Telegram. |
| `.claude/settings.json` | Người | Danh sách lệnh được phép/cấm và đăng ký hooks. |
| `.claude/hooks/*.py` | Người | Rào cứng. Chạy tự động trước mỗi lệnh/ghi file và khi agent dừng. |
| `.claude/agents/*.md` | Người | Định nghĩa tính cách, công cụ, nhiệm vụ của planner/test-writer/reviewer. |
| `.claude/skills/*` | Người | Quy trình chuẩn agent gọi theo tên. |

---

## 4. Cài đặt

### 4.1 Yêu cầu (trên cả MacBook và mini PC)

| Công cụ | Kiểm tra | Ghi chú |
|---|---|---|
| `git` | `git --version` | |
| `python3` ≥ 3.8 | `python3 --version` | Chỉ dùng thư viện chuẩn, không cần `pip install` |
| `claude` (Claude Code) | `claude --version` | Đã đăng nhập gói Pro. Cần bản **≥ 2.1.295** (hook `onFailure`, cờ `--permission-prompts`) |
| `gh` (GitHub CLI) | `gh auth status` | Chỉ cần nếu bật `GH_SYNC=1`. Đăng nhập bằng `gh auth login` |

### 4.2 Cài vào project có sẵn

```bash
git clone git@github.com:ngmanhtruong/agent-kit.git
python3 agent-kit/install.py ~/code/my-project
```

Installer **không ghi đè** file của bạn:
- File chưa có → chép vào.
- `CLAUDE.md` đã có → tạo `CLAUDE.agent-kit.md`, bạn tự gộp mục 5–6 vào `CLAUDE.md`.
- `.claude/settings.json` đã có → tự gộp permissions và hooks, giữ nguyên phần của bạn.
- Thêm `.agent-kit/` và `runner/config.env` vào `.gitignore`.
- Tạo `runner/config.env` từ file mẫu.

### 4.3 Commit khung

```bash
cd ~/code/my-project
# điền 4 file ở mục 5 trước
git add -A && git commit -m "add agent-kit" && git push
```

Bắt buộc phải commit: runner tạo worktree từ nhánh gốc, nếu `.claude/` chưa commit thì worker sẽ chạy **không có rào chắn**. `kit.py night` tự kiểm tra và từ chối chạy trong trường hợp này.

### 4.4 Trên mini PC

```bash
git clone <repo project> && cd <project>
cp runner/config.env.example runner/config.env   # rồi chỉnh (mục 8)
gh auth login
python3 runner/kit.py night --max 1               # chạy thử 1 task
```

Đặt lịch (Linux, `crontab -e`), ví dụ 1h sáng:
```
0 1 * * * cd /home/<user>/code/<project> && /usr/bin/python3 runner/kit.py night >> .agent-kit/night.log 2>&1
```
Trong cron PATH rất ngắn, nên đặt `CLAUDE_BIN` trong `config.env` bằng đường dẫn tuyệt đối (lấy từ `which claude`).

---

## 5. Điền 4 file bắt buộc

### 5.1 `CLAUDE.md` — bản đồ cho AI

**Tác dụng:** Claude Code đọc file này đầu tiên mỗi phiên. Không có nó, AI phải tự đoán dự án làm gì.

**Điền mục 1–4** (mục 5–6 đã viết sẵn, giữ nguyên):

```markdown
## 1. Sản phẩm này để làm gì
Bot nhận tín hiệu TradingView qua webhook, lọc theo bộ lọc xu hướng,
rồi gửi lệnh sang MT5. Thành công = không bỏ lỡ tín hiệu hợp lệ, không gửi lệnh trùng.

## 2. Phạm vi
- Được làm: src/, tests/
- KHÔNG được đụng: config/live.yaml, mọi code gửi lệnh thật khi chưa có test

## 3. Kiến trúc tóm tắt
Xem docs/architecture.md. Điểm vào chính: src/main.py
```

**Nguyên tắc:** chỉ ghi điều AI **không tự suy ra được** từ code. Ngắn hơn luôn tốt hơn.

### 5.2 `docs/architecture.md` — sơ đồ bộ phận

**Tác dụng:** cho AI biết module nào làm gì và chỗ nào nguy hiểm, để sửa đúng chỗ.

```markdown
| Module / thư mục | Vai trò           | Ai gọi nó   |
|------------------|-------------------|-------------|
| src/webhook/     | nhận tín hiệu     | TradingView |
| src/filter/      | lọc xu hướng      | webhook     |
| src/executor/    | gửi lệnh MT5      | filter      |

## Luồng dữ liệu chính
webhook → filter → executor → MT5

## Ranh giới nguy hiểm
src/executor/ chạm tiền thật. Mọi thay đổi phải có test với broker giả.
```

### 5.3 `eval/checks.sh` — thang điểm

**Tác dụng:** đây là bài chấm. Worker chỉ được dừng khi lệnh này exit 0; runner chạy lại một lần nữa để xác nhận. **Chưa điền thì luôn FAIL** (cố ý, để hệ thống không chạy khi chưa có cách chấm).

Bỏ dấu `#` ở các dòng hợp với project. Ví dụ Python:

```bash
step "lint"  ruff check .
step "types" mypy src
step "tests" pytest -q
```

Ví dụ Node/React:

```bash
step "lint"  npx eslint .
step "types" npx tsc --noEmit
step "tests" npm test --silent
```

Thêm quy tắc riêng bằng `step` với một lệnh bất kỳ trả về 0/khác 0. Kiểm tra: `bash eval/checks.sh` phải in `ok` cho từng bước và exit 0.

### 5.4 `runner/config.env` — cấu hình từng máy

**Tác dụng:** cho runner biết chạy bao nhiêu, `claude` ở đâu, có dùng GitHub/Telegram không. Mỗi máy một bản, không commit.

Tối thiểu cần chỉnh: `BASE_BRANCH`, `CLAUDE_BIN`, `HOLDOUT_DIR`, `HOLDOUT_CMD`, `GH_SYNC`. Chi tiết từng biến ở mục 8.

---

## 6. Quy trình hằng ngày

### Bước 1 — Design (MacBook)

1. Làm design trên Claude Design.
2. Export ra PDF/PNG/HTML, bỏ vào `design/<feature>/`.
3. Viết `design/<feature>/spec.md`: mục tiêu, người dùng, luồng chính, ràng buộc, **điều KHÔNG làm**.

### Bước 2 — Chia việc

```bash
python3 runner/kit.py plan design/<feature>
```

Planner tạo `tasks/<feature>/EPIC.md` và các file task `<FEAT>-01.md`, `<FEAT>-02.md`, ... với `status: draft`.

### Bước 3 — Bạn duyệt nháp (bước quan trọng nhất)

Mở `tasks/<feature>/`:
- Đọc **"Câu hỏi mở"** trong `EPIC.md`. Planner được dặn không đoán; câu hỏi nào chưa trả lời thì task liên quan sẽ thiếu.
- Sửa **Acceptance** cho đúng ý bạn. Đây chính là thang điểm; nếu sai thì agent làm "đúng" một thứ sai.
- Kiểm tra **Interface**: test ẩn sẽ bám vào đây.
- Kiểm tra `depends_on` và `priority`.

Muốn nhờ Claude sửa giúp file task (vốn bị khoá), khởi động bằng:
```bash
AGENT_KIT_UNLOCK=1 claude
```

### Bước 4 — Duyệt

```bash
python3 runner/kit.py approve <FEAT>     # cả epic
python3 runner/kit.py approve FEAT-03    # một task
python3 runner/kit.py approve all        # mọi task nháp
git add tasks && git commit -m "approve <FEAT>" && git push
```

`approve` làm gì:
- Từ chối task có Acceptance trống hoặc còn placeholder.
- Đổi `status: draft` → `approved` trong file.
- Nếu `GH_SYNC=1`: tạo GitHub Issue (nhãn `agent-kit`, loại, `status:queued`), ghi số issue vào file.
- Nếu task có `holdout: true` và đã đặt `HOLDOUT_DIR`: gọi test-writer viết test ẩn, chuyển ra `HOLDOUT_DIR/<task-id>/`.

### Bước 5 — Đêm (mini PC, tự động)

`kit.py night`:
1. `git pull --ff-only` để nhận task mới duyệt.
2. `sync` trạng thái từ GitHub.
3. Chọn tối đa `MAX_TASKS` task sẵn sàng, theo `priority`.
4. Với từng task: worker → checks → test ẩn → reviewer → PR hoặc thử lại.
5. Dừng sớm nếu chạm giới hạn gói Pro; task dở được trả về hàng đợi cho đêm sau.
6. Ghi `.agent-kit/runs/<ngày>/SUMMARY.md` và gửi Telegram.

### Bước 6 — Sáng: review

Mỗi PR có sẵn: báo cáo của worker, kết quả chấm (checks / test ẩn / reviewer), **rủi ro** và **chỗ nên xem kỹ** do reviewer chỉ ra.

- Đạt → merge. PR có `Closes #<issue>` nên issue tự đóng.
- Không đạt → đóng PR (task thành `failed`), hoặc comment rồi sửa task và approve lại.

```bash
python3 runner/kit.py sync      # cập nhật trạng thái, mở khoá task phụ thuộc
python3 runner/kit.py status
```

### Bug

Tạo GitHub Issue gắn nhãn `agent-ready` (thêm `bug` nếu là bug), trong body có mục `# Acceptance` dạng checklist. Rồi:

```bash
python3 runner/kit.py import    # kéo về tasks/imported/GH-<số>.md (draft)
# sửa Acceptance nếu cần
python3 runner/kit.py approve GH-<số>
```

### Phân vai 2 máy

| Máy | Làm | Không làm |
|---|---|---|
| **MacBook** | design, plan, sửa task, approve, review PR, sync | `night` |
| **Mini PC** | `night` (cron) | sửa `tasks/` |

---

## 7. Lệnh `kit.py`

Chạy từ thư mục gốc project: `python3 runner/kit.py <lệnh>`

| Lệnh | Tác dụng | Gọi Claude? |
|---|---|---|
| `status` | Bảng: ID, loại, trạng thái, số lần thử, phụ thuộc, issue, PR | Không |
| `plan design/<feature>` | Planner đọc design → sinh epic + tasks nháp vào `tasks/<feature>/` | 1 lần |
| `approve <id\|epic\|all>` | Duyệt nháp → issue + test ẩn | 1 lần/task có holdout |
| `night [--max N]` | Chạy tối đa N task sẵn sàng (mặc định `MAX_TASKS`) | 2 lần/task (worker + reviewer) |
| `sync` | Kéo trạng thái từ nhãn GitHub; PR merged → `done`, đóng → `failed`; epic xong khi mọi task xong | Không |
| `import` | Issue nhãn `agent-ready` → task nháp trong `tasks/imported/` | Không |

### 7.1 Định dạng file task

```markdown
---
id: FEAT-01           # duy nhất trong repo
type: task            # epic | task | bug
epic: FEAT
status: draft         # draft | approved — chỉ người đổi (qua approve)
depends_on: []        # ví dụ [FEAT-01, FEAT-02]
priority: 2           # 1 = làm trước
holdout: true         # có viết test ẩn không
design: design/feat
issue:                # approve tự điền
---

# Mục tiêu
# Bối cảnh
# Interface (hợp đồng)
# Acceptance (thang điểm — đo được, có/không)
- [ ] `bash eval/checks.sh` pass
- [ ] ...
# Ngoài phạm vi
```

Quy tắc viết Acceptance tốt: mỗi dòng phải trả lời được **có/không** bằng một lệnh hoặc một test. Cấm "code sạch", "chạy ổn".

### 7.2 Nơi lưu kết quả

| Đường dẫn | Nội dung |
|---|---|
| `.agent-kit/state.json` | Trạng thái chạy, số lần thử, lý do fail lần trước, nhánh, PR |
| `.agent-kit/runs/<ngày_giờ>/SUMMARY.md` | Tóm tắt một đêm |
| `.agent-kit/runs/<ngày_giờ>/<task>/` | `worker.txt`, `checks.log`, `holdout.log`, `review.json`, báo cáo |
| `.agent-kit/logs/guard.log` | Mọi lần hook chặn agent (dùng để tìm rule cần thêm) |
| Nhánh `agent/<task>-a<n>` | Code của lần thử thứ n. Nhánh FAIL chỉ nằm trên máy chạy |
| `$HOLDOUT_DIR/<task>/` | Test ẩn (ngoài repo) |

---

## 8. Cấu hình `runner/config.env`

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `BASE_BRANCH` | `main` | Nhánh gốc: tạo nhánh task từ đây, PR mở về đây |
| `MAX_TASKS` | `3` | Số task tối đa mỗi lần `night` |
| `TASK_TIMEOUT_MIN` | `60` | Worker chạy quá thời gian này thì bị dừng |
| `MAX_ATTEMPTS` | `2` | Số lần thử tối đa một task trước khi `failed` |
| `MAX_BUDGET_USD` | trống | Phanh an toàn theo chi phí **ước tính** mỗi lần gọi (với gói Pro không phải hoá đơn). Trống = tắt |
| `CLAUDE_BIN` | `claude` | Đường dẫn tới Claude Code. Dùng đường dẫn tuyệt đối khi chạy cron |
| `HOLDOUT_DIR` | trống | Thư mục test ẩn, **ngoài repo**. Trống = tắt test ẩn |
| `HOLDOUT_CMD` | trống | Lệnh chạy test ẩn trong worktree, ví dụ `pytest -q tests` |
| `REVIEW` | `1` | Bật reviewer độc lập |
| `GH_SYNC` | `0` trong code, `1` trong file mẫu | Dùng GitHub Issue + PR qua `gh` |
| `GIT_PULL` | `1` | `git pull --ff-only` trước mỗi lần `night` (chỉ khi working tree sạch) |
| `WORKTREE_ROOT` | `../.agent-worktrees-<project>` | Nơi tạo worktree tạm, ngoài repo |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | trống | Gửi tóm tắt đêm qua Telegram |

### 8.1 Biến môi trường khi bạn dùng Claude trực tiếp

| Biến | Tác dụng |
|---|---|
| `AGENT_KIT_UNLOCK=1` | Cho Claude sửa vùng bảo vệ (khi **bạn** muốn nhờ nó sửa `CLAUDE.md`, `tasks/`, hooks, ...) |
| `AGENT_KIT_SKIP_STOP_CHECK=1` | Tắt hook chấm khi dừng (phiên hỏi đáp, thử nghiệm) |
| `AGENT_KIT_MAX_FIX_ATTEMPTS` | Số lần hook Stop bắt worker sửa lại (mặc định 3) |

### 8.2 Giới hạn gói Pro

Mỗi task tốn khoảng 2–3 lượt gọi Claude (worker, reviewer, cộng test-writer lúc approve). Gói Pro giới hạn theo cửa sổ thời gian nên runner chạy **tuần tự**, ít task, và **tự dừng** khi chạm giới hạn (task dở được trả về hàng đợi, không tính là một lần thử).

---

## 9. Xử lý sự cố & câu hỏi thường gặp

| Hiện tượng | Nguyên nhân / cách xử lý |
|---|---|
| `checks.sh` báo "CHƯA CẤU HÌNH" | Chưa bỏ `#` ở dòng `step` nào. Xem mục 5.3 |
| `night` báo "agent-kit chưa được commit" | `git add .claude eval runner && git commit && git push` |
| `night` báo "Đang có một lượt chạy khác" | Lượt trước còn chạy, hoặc bị kill giữa chừng. Lock tự hết hạn sau 12h, hoặc xoá `.agent-kit/night.lock` |
| `approve` báo "Acceptance trống" | Mục `# Acceptance` cần ít nhất một dòng `- [ ]` thật (ngoài dòng checks.sh, không còn `<!-- -->`) |
| Task mãi không chạy | `depends_on` chưa `done`, hoặc đã hết `MAX_ATTEMPTS`. Xem `kit.py status` |
| Hook báo lỗi "onFailure" / cờ lạ | Claude Code quá cũ. Cập nhật lên ≥ 2.1.295 |
| Cron không tìm thấy `claude` | Đặt `CLAUDE_BIN` là đường dẫn tuyệt đối |
| Muốn biết agent bị chặn những gì | Xem `.agent-kit/logs/guard.log` |
| Không tạo được issue/PR | `gh auth status`; kiểm tra quyền repo |

**Hỏi: Có thể chạy song song nhiều task không?**
Có thể về kỹ thuật (mỗi task một worktree), nhưng kit cố ý chạy tuần tự vì giới hạn gói Pro và vì "chưa tin 1 agent thì đừng mở thêm".

**Hỏi: Vì sao không cho agent push?**
Push là hành động ra ngoài, khó thu hồi. Chỉ runner (một script, không phải AI) mới push, và chỉ khi bài đã được chấm PASS.

**Hỏi: Test ẩn có thực sự ẩn không?**
Có ba lớp: nằm ngoài repo; permission `Read(~/.agent-holdout/**)` bị cấm; hook chặn mọi lệnh shell chứa đường dẫn đó. Test chỉ được chép vào worktree **sau khi** worker đã dừng, rồi xoá ngay.

**Hỏi: Thêm quy định mới thế nào?**
Dùng skill `promote-rule` (khởi động Claude với `AGENT_KIT_UNLOCK=1`). Thứ tự ưu tiên: triệt tiêu bằng thiết kế → check trong `checks.sh` → rule trong hook → cuối cùng mới ghi vào `docs/conventions.md`.

**Hỏi: Áp dụng cho project mới?**
Chạy lại `install.py` vào repo mới, điền 4 file ở mục 5. Mọi thứ khác dùng lại nguyên.

---

## 10. Dành cho AI agent

> Phần này viết cho Claude Code hoặc bất kỳ AI agent nào làm việc trong repo có cài agent-kit. Đọc hết trước khi hành động.

### 10.1 Xác định vai trò của bạn

Đọc biến môi trường `AGENT_KIT_ROLE`:

| Giá trị | Bạn là | Việc của bạn |
|---|---|---|
| `worker` hoặc không đặt | Người làm task | Làm đúng task được giao, tự chấm, commit, báo cáo |
| `planner` | Người chia việc | Đọc `design/<feature>/`, ghi epic + tasks vào `tasks/<feature>/` |
| `test-writer` | Người ra đề | Viết test ẩn vào `.agent-kit/holdout-staging/<task-id>/` |
| `reviewer` | Người chấm | Đọc diff + log, trả về một khối JSON PASS/FAIL, không sửa gì |

Định nghĩa chi tiết của planner, test-writer, reviewer nằm trong `.claude/agents/`.

### 10.2 Thứ tự đọc khi bắt đầu

1. `CLAUDE.md`: mục đích, phạm vi, định nghĩa "xong".
2. `docs/architecture.md`: các bộ phận, chỗ nguy hiểm.
3. File task được giao (runner dán nguyên văn vào prompt).
4. `docs/conventions.md`, `docs/decisions/` nếu task chạm vào phần liên quan.

### 10.3 Quy tắc bắt buộc với worker

1. **Chỉ làm trong phạm vi task.** Không sửa thứ không được yêu cầu, không thêm tính năng.
2. **Không sửa vùng bảo vệ:** `eval/`, `.claude/`, `tasks/`, `runner/`, `design/`, `docs/`, `CLAUDE.md`, `.env*`, `.git/`. Hook sẽ chặn; đừng tìm cách lách (ví dụ ghi bằng shell, đổi tên, tắt hook).
3. **Không làm cho test pass bằng cách nới test**, hardcode giá trị, hay bỏ qua check. Reviewer được dặn tìm đúng những hành vi này.
4. **"Xong" nghĩa là:** `bash eval/checks.sh` exit 0 **và** mọi dòng Acceptance đạt kèm bằng chứng. Hook Stop sẽ không cho bạn dừng nếu checks chưa pass (tối đa 3 lần), sau đó task bị tính FAIL.
5. **Kết thúc bằng skill `finish-task`:** commit trên nhánh hiện tại (không push), viết báo cáo vào `.agent-kit/reports/<task-id>.md`.
6. **Không đoán ý người dùng.** Thiếu thông tin → chọn cách an toàn nhất, ghi giả định vào báo cáo.
7. **Không tự ghi chú vào bối cảnh.** Muốn đề xuất sửa `CLAUDE.md`, thêm rule, thêm test → ghi ở mục "Đề xuất cho người" trong báo cáo.

### 10.4 Lệnh bị chặn (rào cứng)

Hook `guard_bash.py` từ chối: `rm -rf` trên thư mục gốc/home/cha, `sudo`, `git push`, `git reset --hard`, `git clean -f`, chuyển sang nhánh gốc, `--no-verify`, `curl|sh`, `chmod 777`, đọc `.env`, in toàn bộ biến môi trường, đổi biến `AGENT_KIT_*`, tắt hook, `--dangerously-skip-permissions`, đọc thư mục test ẩn, lệnh `gh pr/issue/release/repo`, và mọi lệnh shell ghi vào vùng bảo vệ.

Khi bị chặn: **đừng thử cách khác để đạt cùng mục đích.** Nếu việc đó thật sự cần cho task, dừng lại và ghi lý do vào báo cáo với kết quả `KẸT`.

### 10.5 Mẫu báo cáo (worker)

```markdown
# <task-id>
Kết quả: XONG | KẸT
## Đã làm
## Acceptance (từng dòng: đạt/không + bằng chứng: lệnh đã chạy, output rút gọn)
## Giả định đã đưa ra
## Đề xuất cho người (sửa CLAUDE.md / thêm rule / thêm test) — nếu có
```

### 10.6 Nếu bạn được người dùng nhờ sửa chính agent-kit

Chỉ làm khi phiên được khởi động với `AGENT_KIT_UNLOCK=1`. Giữ các bất biến sau:
- Trạng thái chạy không ghi vào file `tasks/*.md` (tránh xung đột giữa hai máy).
- Test ẩn không bao giờ nằm trong repo hoặc trong tầm đọc của worker.
- Chỉ runner (script) được push và tạo PR; agent thì không.
- Hook dùng `onFailure: "block"`: hook lỗi thì chặn, không cho qua.
- `runner/kit.py` và hooks chỉ dùng thư viện chuẩn Python.
