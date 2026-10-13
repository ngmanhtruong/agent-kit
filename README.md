# agent-kit

Bộ khung để các AI agent **tự làm việc** mà vẫn đáng tin — với **bất kỳ agent nào**: Claude Code, một agent CLI khác, hay Copilot Chat trong VS Code:

```
Ý tưởng → Design (Claude Design) → Tasks (markdown + GitHub Issue)
       → Agent làm từng task → Tự chấm bài → Pull Request → Bạn review & merge
```

Tài liệu này viết cho **hai loại người đọc**:
- **Người dùng**: đọc từ mục 1 đến mục 9.
- **AI agent** (bất kỳ agent nào làm việc trong repo): đọc mục 10 trước khi làm bất cứ việc gì.

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
- **Chưa tin 1 agent thì đừng mở thêm.** Bắt đầu 1 task mỗi phiên, tăng dần.
- **Rào cứng > rào mềm.** Lỗi nào lặp lại 2 lần → biến thành check tự động (skill `promote-rule`).
- **Cấm AI tự ghi chú.** AI không được sửa `CLAUDE.md`, `docs/`. Muốn đổi thì đề xuất trong báo cáo, người quyết. Tránh "một lời góp ý thành lệnh cấm vĩnh viễn".
- **Giấu bài kiểm tra.** Test ẩn nằm ngoài repo, đặt tên như test bình thường; agent làm bài không bao giờ thấy.
- **Cách làm đúng phải là cách dễ nhất.** Một lệnh chấm duy nhất, một lệnh chạy duy nhất.

---

## 2. Toàn cảnh hệ thống

### 2.1 Luồng công việc

Không có máy "ngày" hay máy "đêm". Mọi máy ngang hàng; một **phiên làm việc** (`kit.py work`) chạy lúc nào cũng được, trên máy nào cũng được, với agent nào cũng được (xem mục 2.5). Các bước chuẩn bị và review làm ở máy nào cũng được.

```
 CHUẨN BỊ (bất kỳ máy nào)             PHIÊN `kit.py work` (bất kỳ máy,          REVIEW (bất kỳ máy nào)
                                       bất kỳ agent, lúc nào cũng được)
 ───────────────────────────           ──────────────────────────────────────   ──────────────────────
 0. (tuỳ chọn) ý tưởng → PRD           5. epic nào đã merge đủ task:             7. status / report / trace
    idea.md → kit.py idea                 kiểm thử END-TO-END cấp epic          8. GitHub: đọc PR
    → prd.md (REQ-01..) → approve          (FAIL → mở bug, sửa xong tự kiểm lại)     (đã kèm điểm chấm)
 1. (tuỳ chọn) Claude Design           6. với mỗi task sẵn sàng:                 9. Merge hoặc đóng PR
    → export vào design/<feature>/        a. TEST-WRITER viết test ẩn (nếu cần)  10. kit.py sync
 2. kit.py plan                           b. tạo nhánh riêng                         → task "done",
    → planner sinh epic + tasks nháp      c. IMPLEMENTER làm bài                       mở khoá task phụ thuộc,
      (mỗi task ghi REQ nó phục vụ)       d. eval/checks.sh  (thang điểm)              epic sang kiểm thử
 3. Bạn sửa, trả lời câu hỏi mở           e. test ẩn         (worker không thấy)
    kit.py trace: REQ nào chưa có task    f. REVIEWER chấm độc lập
 4. kit.py approve (không gọi AI)         g. PASS → push + mở PR
    → GitHub Issue → git push                FAIL → thử lại, kèm lý do lần trước
```

### 2.1.1 Khâu bắt buộc và khâu tuỳ chọn

Mỗi khâu tốn token nên chỉ ba nhóm là bắt buộc; còn lại bạn dùng khi cần.

| Khâu | Bắt buộc? | Tốn AI? | Ghi chú |
|---|---|---|---|
| Lập kế hoạch: task có Acceptance đo được, `approve` | **Bắt buộc** | `plan` tốn 1 lượt (hoặc bạn tự viết task) | Không có task duyệt thì không có gì để làm |
| Tự chấm điểm: `checks.sh`, reviewer độc lập, phát hiện sửa vùng bảo vệ | **Bắt buộc** | reviewer: 1 lượt/task | Luôn chạy, không tắt được |
| Kiểm thử: test ẩn từng task, kiểm thử cấp epic | **Bắt buộc** | test-writer: 1 lượt/task có `holdout: true`, 1 lượt/epic | Planner quyết task/epic nào có test ẩn (`holdout`); task thuần giao diện có thể `false` |
| Ý tưởng → PRD (`idea`, product-analyst) | Tuỳ chọn | 1 lượt | Bật bắt buộc bằng `REQUIRE_PRD=1` |
| Truy vết yêu cầu (`trace`, mục PRD trong `doctor`) | Tuỳ chọn | Không | Chỉ có tác dụng khi dùng PRD |
| Claude Design | Tuỳ chọn | — | Có thể chỉ viết `spec.md` |
| context-writer, bug-triager | Tuỳ chọn | 1 lượt mỗi lần gọi | Chỉ chạy khi bạn yêu cầu |
| GitHub Issue/PR, chia sẻ nhiều máy, Telegram | Tuỳ chọn | Không | `GH_SYNC`, `PUBLISH`, `TELEGRAM_*` |
| Deploy, staging, production | **Không có sẵn** | — | Tự bổ sung khi cần, xem mục 2.6 |

### 2.2 Agent chủ và bảy agent con

Mỗi công việc có một file hướng dẫn riêng trong `.claude/agents/<tên>.md`. **Agent chủ** (phiên agent bạn đang nói chuyện: Claude Code, Copilot Chat...) đọc `docs/orchestration.md` (được nạp sẵn qua `CLAUDE.md`) để biết khi nào spawn agent con nào, đưa đầu vào gì, kiểm tra đầu ra thế nào.

| Agent con | Công việc | Ai gọi | Được ghi vào đâu |
|---|---|---|---|
| **context-writer** | Quét codebase → đề xuất `CLAUDE.md`, `architecture.md`, `checks.sh` | Agent chủ | chỉ `.agent-kit/proposals/` |
| **product-analyst** | (Tuỳ chọn) Ý tưởng → PRD có mã yêu cầu REQ-xx | Agent chủ hoặc `kit.py idea` | chỉ `design/` |
| **planner** | PRD/spec + design → epic + tasks nháp, mỗi task ghi REQ nó phục vụ | Agent chủ hoặc `kit.py plan` | chỉ `tasks/` |
| **bug-triager** | Bug report → task bug nháp có bước tái hiện | Agent chủ | chỉ `tasks/bugs/` |
| **test-writer** | Task → bài test ẩn; epic → kiểm thử end-to-end | `kit.py work` (trước khi làm task) | chỉ `.agent-kit/holdout-staging/` |
| **implementer** | Làm một task đã duyệt | `kit.py work` hoặc agent chủ | mọi nơi **trừ** vùng bảo vệ |
| **reviewer** | Chấm độc lập → JSON PASS/FAIL | `kit.py work` hoặc agent chủ | không ghi gì |

Quyền ghi được hook ép theo vai trò. Vai trò lấy từ tên agent con (`agent_type` trong dữ liệu hook) khi agent chủ spawn, hoặc từ biến môi trường `AGENT_KIT_ROLE` khi runner gọi. Hook chấm bài khi dừng chạy cho cả phiên chính (`Stop`) lẫn agent con (`SubagentStop`), nhưng chỉ khi có **code** thay đổi (sửa `tasks/`, `docs/`... không kích hoạt chấm).

### 2.3 Vòng đời một task

```
draft ──approve──▶ queued ──run────▶ running ──┬─ PASS ─▶ review ──merge PR──▶ done
                     ▲                         │                 └─đóng PR───▶ failed
                     └──── FAIL (còn lượt) ────┤
                                               └─ FAIL (hết lượt) ─▶ failed + nhãn needs-human
```

- `draft`, `approved`: ghi trong file `tasks/*.md` (do **người** quyết).
- `queued`, `running`, `review`, `done`, `failed`: trạng thái chạy, xem mục 2.4.
- Task chỉ chạy khi đã `approved` **và** mọi task trong `depends_on` đã `done` (tức PR đã merge).

Vòng đời một **epic**:
```
approved ──mọi task done──▶ verify ──work: kiểm thử end-to-end trên nhánh gốc──┬─ PASS ─▶ done
                               ▲                                                └─ FAIL ─▶ failed
                               └──── task sửa (epic: <mã epic>) merge xong ◀──── mở bug (GH_SYNC), import, bug-triager
```

### 2.4 Nhiều máy cùng làm việc mà không sai lệch

Bạn có thể chạy một phiên `work` trên máy A, rồi lúc nào đó mở máy B, `git pull` và kiểm tra mọi thứ đã xảy ra — hoặc tiếp tục làm việc ngay trên máy B. Thiết kế đảm bảo điều đó như sau:

| Loại dữ liệu | Nằm ở đâu | Ai ghi |
|---|---|---|
| **Spec** (`tasks/*.md`, `design/`, `CLAUDE.md`...) | Nhánh code (`main`) | Chỉ người (máy nào cũng được), commit + push |
| **Trạng thái chạy** của từng task | Nhánh riêng `agent-kit/log`, file `state/<tên-máy>.json` | Mỗi máy chỉ ghi file của chính nó |
| **Log từng lượt chạy** (tóm tắt, checks, test ẩn, reviewer, báo cáo) | Nhánh `agent-kit/log`, thư mục `runs/<tên-máy>/<thời-điểm>/` | Máy đã chạy lượt đó |
| **Code của từng lần thử** | Nhánh `agent/<task>-a<n>` trên origin (cả PASS lẫn FAIL) | Runner |
| **Khoá "đang chạy"** | Nhánh `agent-kit/log`, file `lock.json` | Máy đang chạy phiên `work` |
| Nhãn GitHub Issue `status:*` | GitHub (nếu `GH_SYNC=1`) | Runner, `sync`, hoặc bạn sửa tay |

Vì sao không sai lệch:
1. **Không ai ghi đè ai.** Mỗi máy chỉ ghi file mang tên mình trên nhánh `agent-kit/log`, nên push từ hai máy không bao giờ xung đột (bị từ chối thì runner tự thử lại trên bản mới nhất).
2. **Gộp theo bản mới nhất.** Khi đọc, `kit.py` gộp trạng thái của mọi máy; với mỗi task, bản ghi có thời điểm (UTC) mới nhất thắng. Nhãn GitHub được sửa tay sau đó cũng thắng.
3. **Không chạy trùng.** `work` lấy khoá `lock.json` trước khi chạy; máy khác thấy khoá còn hạn thì từ chối chạy. Khoá của lượt chạy bị chết tự hết hạn sau `LOCK_HOURS`.
4. **Không chạy spec cũ.** `work` bắt buộc `git pull --ff-only` thành công; máy đó có thay đổi chưa commit/push thì dừng và báo.
5. **Biết khi spec bị sửa sau khi chạy.** Mỗi lần chạy ghi lại mã băm của spec và commit gốc; `doctor` cảnh báo nếu spec đã đổi sau đó.
6. **Lệnh kiểm tra chỉ đọc.** `status`, `report`, `doctor` (không `--fix`) chỉ `git fetch` nhánh log; không sửa file, không đổi nhánh, không push.

Nhánh `agent-kit/log` không chứa code của bạn (tạo dạng orphan), không bao giờ merge vào `main`.

### 2.5 Chạy với bất kỳ agent nào

`kit.py` tự làm mọi phần cơ học (pull, khoá, tạo nhánh, chạy checks, chạy test ẩn, chấm, push, mở PR, ghi trạng thái). Phần cần AI (viết test ẩn, làm task, review) được giao cho agent theo một trong ba chế độ, đặt bằng `AGENT` trong `runner/config.env`:

| `AGENT` | Dùng khi | Cách chạy | Rào chắn |
|---|---|---|---|
| `claude` | Máy có Claude Code CLI | `kit.py work` chạy tự động trọn các task, mỗi task trong một worktree riêng | Rào cứng (hooks) + kit.py chấm |
| `cli` | Máy có agent CLI khác (Copilot CLI, Codex, Gemini...) | Như trên. Lệnh gọi agent đặt ở `AGENT_CMD`; kit.py đưa kèm hướng dẫn vai trò từ `.claude/agents/<vai>.md` | kit.py chấm |
| `chat` | Không có CLI, chỉ có chat (Copilot Chat trong VS Code...) | Bảo agent trong chat chạy `python3 runner/kit.py work`. Mỗi lần chạy, kit.py làm một bước rồi in **BƯỚC TIẾP THEO** cho agent; agent làm xong thì chạy lại `work`, cho tới khi task được chấm xong | kit.py chấm |
| `auto` (mặc định) | — | `claude` nếu có Claude Code → `cli` nếu đặt `AGENT_CMD` → `chat` | |

**Chấm bài như nhau với mọi agent**, vì do `kit.py` làm chứ không do agent tự báo: có thay đổi không, có sửa vùng bảo vệ không (`eval/`, `.claude/`, `tasks/`, `runner/`, `design/`, `docs/`, `CLAUDE.md`, `.env`...), `eval/checks.sh` có pass không, test ẩn có pass không (test được chép mới từ ngoài repo mỗi lần chấm, nên agent không sửa được).

**Khác biệt cần biết:**
- Chỉ Claude Code có rào cứng **trong lúc làm** (hooks chặn lệnh nguy hiểm, chặn ghi vùng bảo vệ). Với `cli` và `chat`, agent chỉ được dặn bằng văn bản; vi phạm vẫn bị phát hiện **khi chấm** và task bị FAIL.
- Với `chat`, các vai trò test-writer và reviewer nên làm trong **một cuộc chat mới**, để không phải chính agent vừa làm bài tự chấm. Bài test ẩn nằm trên cùng máy, nên "ẩn" ở đây dựa vào quy ước; kit.py không cho agent xem nội dung test khi chấm FAIL.
- Với `chat`, task được làm ngay trong thư mục repo đang mở (kit.py tạo và chuyển sang nhánh `agent/<task>-a<n>`, xong thì chuyển về nhánh gốc).

### 2.6 Mở rộng: deploy, staging, production (không có sẵn)

agent-kit dừng ở mức **code đã merge và đã kiểm thử cấp epic**. Deploy phụ thuộc hạ tầng từng project nên không đóng gói sẵn. Nếu cần, gợi ý cách thêm mà không phá các nguyên tắc của kit:

1. **Script riêng của project:** `deploy/staging.sh`, `deploy/production.sh`, `deploy/rollback.sh`, `deploy/smoke.sh`. Thêm `deploy/` vào vùng bảo vệ (`PROTECTED` trong `runner/kit.py` và `_common.py`) để agent không sửa.
2. **Staging tự động:** sau khi epic `done`, chạy `deploy/staging.sh` rồi `deploy/smoke.sh`; smoke FAIL thì mở bug như kiểm thử epic.
3. **Production luôn cần người duyệt:** một lệnh riêng (ví dụ `kit.py release <epic>`) chỉ chạy khi bạn gọi, in release notes từ các task/REQ đã xong, hỏi xác nhận, rồi mới deploy. Không cho agent tự gọi lệnh này (thêm vào `guard_bash.py`).
4. **Theo dõi sau deploy:** lỗi production đưa vào GitHub Issue nhãn `bug,agent-ready` → `kit.py import` → bug-triager, cùng luồng bug hiện có.
5. **Trạng thái:** có thể thêm `staged`, `released` sau `done`, ghi trên nhánh `agent-kit/log` giống các trạng thái khác (mỗi máy chỉ ghi file của mình).

---

## 3. Bản đồ file

Sau khi cài vào project, repo của bạn có thêm:

```
your-project/
├── CLAUDE.md                     ★ Bản đồ dự án cho AI (bạn điền)
├── docs/
│   ├── architecture.md           ★ Sơ đồ các bộ phận (bạn điền)
│   ├── orchestration.md            Hướng dẫn agent chủ: khi nào spawn agent con nào
│   ├── conventions.md              Quy chuẩn chưa tự động hoá được (thêm dần)
│   └── decisions/0000-template.md  Mẫu ghi quyết định kiến trúc (ADR)
├── design/
│   ├── README.md                   Hướng dẫn đặt file design
│   ├── _IDEA_TEMPLATE.md           (tuỳ chọn) Mẫu ghi ý tưởng
│   ├── _PRD_TEMPLATE.md            (tuỳ chọn) Mẫu PRD có mã REQ-xx
│   └── <feature>/                  idea.md, prd.md (tuỳ chọn) hoặc spec.md + file export từ Claude Design
├── tasks/
│   ├── _TEMPLATE.md                Mẫu một task
│   └── <feature>/                  EPIC.md + các task (planner sinh, bạn duyệt)
├── eval/
│   └── checks.sh                 ★ Thang điểm: 1 lệnh, exit 0 = đạt (bạn điền)
├── runner/
│   ├── kit.py                      Bộ điều phối (plan / approve / run / status / ...)
│   ├── config.env.example          Mẫu cấu hình
│   └── config.env                ★ Cấu hình riêng từng máy (bạn điền, KHÔNG commit)
├── .github/
│   └── copilot-instructions.md     Dặn Copilot đọc CLAUDE.md + orchestration và tự giữ quy tắc
├── .claude/
│   ├── settings.json               Permissions + đăng ký hooks
│   ├── hooks/
│   │   ├── _common.py              Vùng bảo vệ, vai trò, tiện ích chung
│   │   ├── guard_bash.py           Chặn lệnh shell nguy hiểm
│   │   ├── guard_files.py          Chặn ghi file vào vùng bảo vệ / ngoài vai trò
│   │   └── stop_checks.py          Không cho worker dừng khi checks.sh chưa pass
│   ├── agents/                     Mỗi công việc một file, agent chủ spawn theo tên
│   │   ├── context-writer.md       Codebase → đề xuất bối cảnh (CLAUDE.md, architecture, checks)
│   │   ├── product-analyst.md      (tuỳ chọn) Ý tưởng → PRD có mã yêu cầu
│   │   ├── planner.md              Design → epic + tasks
│   │   ├── bug-triager.md          Bug report → task bug nháp
│   │   ├── test-writer.md          Task → bài test ẩn
│   │   ├── implementer.md          Làm một task đã duyệt
│   │   └── reviewer.md             Chấm độc lập → JSON PASS/FAIL
│   └── skills/
│       ├── finish-task/SKILL.md    Quy trình bắt buộc khi hoàn tất task
│       └── promote-rule/SKILL.md   Biến lỗi lặp lại thành quy định tự động
└── .agent-kit/                     (gitignore) state, logs, báo cáo từng phiên
```

★ = 4 file bắt buộc phải điền (xem mục 5).

### 3.1 Tác dụng chi tiết từng file

| File | Ai sửa | Tác dụng |
|---|---|---|
| `CLAUDE.md` | Người | Claude Code tự đọc file này đầu mỗi phiên. Nói AI biết sản phẩm làm gì, được/cấm đụng đâu, thế nào là "xong". |
| `docs/architecture.md` | Người | Module nào làm gì, dữ liệu chạy qua đâu, chỗ nào nguy hiểm. Giúp AI sửa đúng chỗ. |
| `docs/conventions.md` | Người | Quy tắc code mà **chưa** biến được thành check tự động. Mỗi dòng ghi rõ đã tự động hoá chưa. |
| `docs/decisions/` | Người | Lý do các quyết định đã chốt, để AI không "sáng tạo" ngược lại. |
| `design/<feature>/idea.md` | Người (tuỳ chọn) | Ý tưởng thô, đầu vào cho product-analyst. |
| `design/<feature>/prd.md` | product-analyst viết, người sửa và duyệt (tuỳ chọn) | Yêu cầu có mã `REQ-01`... kèm cách kiểm chứng. Task trỏ về các mã này để truy vết. |
| `design/<feature>/spec.md` | Người | Dùng thay PRD khi muốn tiết kiệm token: mục tiêu, người dùng, luồng chính, ràng buộc, điều KHÔNG làm. |
| `design/<feature>/*.pdf/png/html` | Người | Export từ Claude Design. Planner đọc được ảnh và PDF. |
| `tasks/_TEMPLATE.md` | Người | Định dạng chuẩn của một task. Planner bám theo. |
| `tasks/<feature>/*.md` | Planner sinh, người duyệt | Spec của từng task: mục tiêu, interface, acceptance. |
| `eval/checks.sh` | Người | Bài chấm chung. Worker phải pass mới được dừng; runner chạy lại để xác nhận. |
| `runner/kit.py` | Không ai (trừ khi nâng cấp kit) | Điều phối toàn bộ luồng. |
| `runner/config.env` | Người, từng máy | Số task mỗi phiên, đường dẫn `claude`, test ẩn, GitHub, Telegram. |
| `.claude/settings.json` | Người | Danh sách lệnh được phép/cấm và đăng ký hooks. |
| `.claude/hooks/*.py` | Người | Rào cứng. Chạy tự động trước mỗi lệnh/ghi file và khi agent dừng. |
| `docs/orchestration.md` | Người | Sổ tay của agent chủ: bảng agent con, chọn agent theo yêu cầu, quy tắc điều phối, mẫu prompt khi spawn. Được nạp sẵn qua `CLAUDE.md`. |
| `.claude/agents/*.md` | Người | Mỗi file là hướng dẫn cho một công việc (context-writer, planner, bug-triager, test-writer, implementer, reviewer): nhiệm vụ, công cụ, đầu vào, đầu ra. |
| `.claude/skills/*` | Người | Quy trình chuẩn agent gọi theo tên. |

---

## 4. Cài đặt

### 4.1 Yêu cầu

| Công cụ | Kiểm tra | Cần trên máy nào |
|---|---|---|
| `git` | `git --version` | Mọi máy |
| `python3` ≥ 3.8 | `python3 --version` | Mọi máy. Chỉ dùng thư viện chuẩn, không cần `pip install` |
| `gh` (GitHub CLI) | `gh auth status` | Mọi máy, nếu bật `GH_SYNC=1`. Đăng nhập bằng `gh auth login` |
| Một agent | — | Claude Code (bản ≥ 2.1.295), **hoặc** agent CLI khác, **hoặc** chỉ cần chat (Copilot Chat...). Xem mục 2.5 |

### 4.1.1 Máy chỉ có Copilot Chat (hoặc chat agent khác)

Đặt `AGENT=chat` (hoặc để `auto` trên máy không có Claude Code / `AGENT_CMD`). Mọi lệnh đều dùng được:

| Việc | Cách làm |
|---|---|
| `approve`, `status`, `report`, `doctor`, `sync`, `set`, `import` | Chạy bình thường, không gọi AI |
| Chia design thành task | `kit.py plan design/<feature>` in ra prompt; dán vào Copilot Chat (chế độ Agent) |
| Làm task | Nói với Copilot: *"chạy `python3 runner/kit.py work` và làm theo hướng dẫn nó in ra, lặp lại cho tới khi xong"*. `.github/copilot-instructions.md` (được cài sẵn) đã dặn Copilot quy trình này |
| Viết test ẩn, review | `work` sẽ yêu cầu ở bước tương ứng; nên mở một cuộc chat mới cho hai vai này |
| Huỷ task đang làm dở | `kit.py work --abort` (không tính lượt thử) |

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

Bắt buộc phải commit: runner tạo worktree từ nhánh gốc, nếu `.claude/` chưa commit thì worker sẽ chạy **không có rào chắn**. `kit.py work` tự kiểm tra và từ chối chạy trong trường hợp này.

### 4.4 Thêm một máy khác

Máy nào cũng cài giống nhau:

```bash
git clone <repo project> && cd <project>
cp runner/config.env.example runner/config.env   # chỉnh (mục 8); đặt MACHINE_NAME riêng cho máy này
gh auth login                                    # nếu GH_SYNC=1
python3 runner/kit.py doctor                     # kiểm tra máy này
python3 runner/kit.py work --max 1               # chạy thử 1 task
```

Chạy `work` lúc nào bạn muốn. Với `claude`/`cli`, **tuỳ chọn** đặt lịch tự động, ví dụ mỗi 4 tiếng (Linux/macOS, `crontab -e`):
```
0 */4 * * * cd /đường/dẫn/project && /usr/bin/python3 runner/kit.py work >> .agent-kit/work.log 2>&1
```
Khi chạy theo lịch, PATH rất ngắn nên đặt `CLAUDE_BIN` trong `config.env` bằng đường dẫn tuyệt đối (lấy từ `which claude`). Hai máy cùng đặt lịch cũng không sao: khoá đảm bảo một lúc chỉ một máy chạy, máy kia tự bỏ qua.

---

## 5. Điền 4 file bắt buộc

**Cách nhanh:** mở agent (Claude Code, Copilot Chat...) trong project và nói *"dùng context-writer để đề xuất bối cảnh cho project này"*. Agent con `context-writer` quét code, chạy thử lệnh test, rồi ghi bản đề xuất `CLAUDE.md`, `architecture.md`, `checks.sh` vào `.agent-kit/proposals/`, kèm các câu hỏi cần bạn xác nhận. Bạn đọc, sửa, rồi chép vào chỗ thật (hoặc khởi động `AGENT_KIT_UNLOCK=1 claude` và nhờ agent chép). Dưới đây là cách tự điền.

Mục 7 của `CLAUDE.md` (`@docs/architecture.md`, `@docs/orchestration.md`) làm Claude Code nạp luôn hai file đó vào mọi phiên. Giữ nguyên.

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

### Bước 0 — (Tuỳ chọn) Ý tưởng → PRD

```bash
mkdir -p design/<feature> && cp design/_IDEA_TEMPLATE.md design/<feature>/idea.md   # viết ý tưởng
python3 runner/kit.py idea design/<feature>      # product-analyst viết design/<feature>/prd.md (draft)
# đọc prd.md: trả lời Câu hỏi mở, sửa yêu cầu REQ-xx và mục Kiểm chứng cho đúng ý
python3 runner/kit.py approve design/<feature>   # duyệt PRD (không gọi AI)
```
Bỏ qua bước này nếu muốn tiết kiệm token: viết thẳng `spec.md` ở Bước 1.

### Bước 1 — Design

1. (Tuỳ chọn) Làm design trên Claude Design, export PDF/PNG/HTML vào `design/<feature>/`.
2. Nếu không dùng PRD: viết `design/<feature>/spec.md`: mục tiêu, người dùng, luồng chính, ràng buộc, **điều KHÔNG làm**.

### Bước 2 — Chia việc

```bash
python3 runner/kit.py plan design/<feature>
```

Planner tạo `tasks/<feature>/EPIC.md` và các file task `<FEAT>-01.md`, `<FEAT>-02.md`, ... với `status: draft`. Có PRD đã duyệt thì mỗi task ghi `requirements: [REQ-..]`; PRD chưa duyệt thì `plan` từ chối.

```bash
python3 runner/kit.py trace design/<feature>     # REQ nào chưa có task, REQ nào đã xong (chỉ đọc)
```

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
- **Không gọi AI**, chạy được trên mọi máy.

Bài test ẩn cho task `holdout: true` được viết trong **phiên `work`**, ngay trước khi làm task đó: test-writer đọc spec và code gốc hiện tại, ghi ra `HOLDOUT_DIR/<task-id>/` trên chính máy chạy task. Đã có thì dùng lại. Test-writer không viết được thì task được bỏ qua phiên đó mà không tính lượt thử.

### Bước 5 — Phiên làm việc (`kit.py work`, máy nào, agent nào, lúc nào cũng được)

Với `AGENT=claude`/`cli`: `kit.py work` tự chạy hết. Với `AGENT=chat`: agent trong chat chạy `kit.py work` nhiều lần, mỗi lần một bước (mục 2.5). Các bước giống nhau:
1. `git pull --ff-only` để nhận task mới duyệt (thất bại → dừng và báo).
2. Lấy khoá `lock.json` trên nhánh `agent-kit/log` (máy khác đang chạy → dừng).
3. `sync` trạng thái từ mọi máy và GitHub.
4. **Kiểm thử cấp epic** cho mọi epic đã merge đủ task (trạng thái `verify`): test-writer viết kiểm thử end-to-end nếu epic có `holdout: true` (một lần), rồi chạy `checks.sh` + kiểm thử đó trên nhánh gốc. PASS → epic `done`. FAIL → epic `failed`, và nếu `GH_SYNC=1` thì mở GitHub Issue nhãn `bug,agent-ready` kèm log; `kit.py import` → bug-triager viết task sửa với `epic: <mã epic>`; khi task sửa merge, epic tự quay lại `verify`.
5. Chọn tối đa `MAX_TASKS` task sẵn sàng, theo `priority`.
6. Với từng task: test-writer (nếu cần) → implementer → checks → test ẩn → reviewer → push nhánh → PR (PASS) hoặc thử lại (FAIL). Sau mỗi task, trạng thái và log được đẩy lên nhánh `agent-kit/log`, nên máy khác thấy tiến độ ngay cả khi phiên chưa xong.
7. Dừng sớm nếu chạm giới hạn gói Pro; task dở được trả về hàng đợi cho phiên sau.
8. Ghi tóm tắt, nhả khoá, gửi Telegram.

### Bước 6 — Kiểm tra (bất kỳ máy nào, bất kỳ lúc nào)

```bash
git pull
python3 runner/kit.py status              # bảng mọi task, gộp từ mọi máy
python3 runner/kit.py report              # tóm tắt các lượt chạy gần nhất
python3 runner/kit.py report --task FEAT-02   # vì sao FAIL: lý do, checks, test ẩn, reviewer, báo cáo
python3 runner/kit.py doctor              # kiểm tra toàn bộ: cài đặt, đồng bộ, tasks, task kẹt
```

Ba lệnh này **chỉ đọc**, chạy bao nhiêu lần, trên máy nào cũng được, kể cả khi máy khác đang chạy phiên `work`.

Muốn xem code của một lần thử FAIL: `git fetch origin && git checkout agent/FEAT-02-a2`.

### Bước 7 — Review PR

Mỗi PR có sẵn: báo cáo của worker, kết quả chấm (checks / test ẩn / reviewer), **rủi ro**, **chỗ nên xem kỹ**, và máy/commit gốc/mã spec đã dùng.

- Đạt → merge. PR có `Closes #<issue>` nên issue tự đóng.
- Không đạt → đóng PR (task thành `failed`), hoặc comment rồi sửa task và cho chạy lại.

```bash
python3 runner/kit.py sync                    # PR merged → done, mở khoá task phụ thuộc, chia sẻ cho máy khác
python3 runner/kit.py set FEAT-02 queued      # cho chạy lại task failed (đặt lại số lần thử)
```

### Bug

Tạo GitHub Issue gắn nhãn `agent-ready` (thêm `bug` nếu là bug), trong body có mục `# Acceptance` dạng checklist. Rồi:

```bash
python3 runner/kit.py import    # kéo về tasks/imported/GH-<số>.md (draft)
# sửa Acceptance nếu cần
python3 runner/kit.py approve GH-<số>
```

### Làm việc trực tiếp với agent chủ

Mở `claude` trong project và nói việc cần làm. Agent chủ tự chọn agent con theo `docs/orchestration.md`:

| Bạn nói | Agent chủ spawn |
|---|---|
| "Đề xuất bối cảnh cho project" | `context-writer` |
| "Chia design/feat thành task" | `planner` |
| "Có bug: <mô tả / log>" | `bug-triager` |
| "Làm task FEAT-02" | `implementer` → `reviewer` |
| "Chấm lại nhánh X" | `reviewer` |

Agent chủ không duyệt task thay bạn, không push, không tạo PR. Những việc đó vẫn qua `kit.py`.

### Nhiều máy

Mọi máy ngang hàng, làm được mọi lệnh, với agent nào cũng được. Chỉ cần nhớ:
- Đặt `MACHINE_NAME` khác nhau trên mỗi máy (ví dụ `macbook`, `minipc`) để báo cáo ghi rõ máy nào đã làm gì.
- Sửa `tasks/` xong thì commit + push, để máy khác thấy.
- Trước khi `work`, máy đó phải ở nhánh gốc, sạch và đã push (nếu không `work` sẽ dừng và nhắc).
- Một lúc chỉ một máy chạy `work`; khoá tự đảm bảo.

---

## 7. Lệnh `kit.py`

Chạy từ thư mục gốc project: `python3 runner/kit.py <lệnh>`

**Lệnh kiểm tra — chỉ đọc, an toàn mọi lúc, mọi máy:**

| Lệnh | Tác dụng |
|---|---|
| `status [--offline]` | Bảng mọi task: trạng thái, số lần thử, phụ thuộc, máy chạy, giờ cập nhật, PR/nhánh. Cuối bảng: lượt chạy cuối của từng máy, máy nào đang chạy. `running?` = task kẹt. `--offline` không fetch |
| `report [--last N]` | Tóm tắt N lượt chạy gần nhất của mọi máy (mặc định 3) |
| `report --task <id> [--last N]` | Chi tiết một task qua các lượt: PASS/FAIL, lý do, nhánh, commit gốc, mã spec, reviewer, báo cáo worker, đuôi log checks/test ẩn/worker |
| `doctor` | Kiểm tra toàn bộ. Trả mã thoát 1 nếu có lỗi (✗), dùng được trong script |
| `trace [design/<feature>] [--offline]` | Yêu cầu → task → trạng thái: REQ nào chưa có task, bao nhiêu REQ đã xong, epic đang ở đâu |

`doctor` kiểm tra:
- **Cài đặt:** `config.env`, phiên bản `claude`, `gh` đăng nhập, khung đã commit, `checks.sh` đã cấu hình, có remote.
- **Đồng bộ:** đọc được nhánh log; máy này chậm/nhanh hơn `origin/<BASE_BRANCH>`; `tasks/` có thay đổi chưa commit; phiên cuối của từng máy (cảnh báo nếu đặt `STALE_RUN_HOURS` và đã quá — lịch tự động có còn chạy?); khoá đang giữ hay đã chết.
- **Yêu cầu (nếu dùng PRD):** PRD chưa duyệt, REQ chưa có task, task trỏ tới REQ không tồn tại.
- **Tasks:** frontmatter hỏng, id trùng, `depends_on` trỏ tới task không tồn tại, vòng phụ thuộc, task đã duyệt mà Acceptance trống hoặc chưa có issue, thiếu test ẩn.
- **Trạng thái chạy:** task kẹt `running`, spec bị sửa sau khi agent chạy, task `failed`, nhánh lần thử không có trên origin, PR đã merge/đóng mà chưa `sync`.

**Lệnh làm việc:**

| Lệnh | Tác dụng | Gọi Claude? |
|---|---|---|
| `idea design/<feature>` | (Tuỳ chọn) product-analyst: `idea.md` → `prd.md` có mã REQ-xx. Chế độ chat → in prompt | 1 lần |
| `approve design/<feature>` | Duyệt PRD (cần ít nhất một REQ) | Không |
| `plan design/<feature>` | Planner đọc PRD/spec + design → sinh epic + tasks nháp vào `tasks/<feature>/`, mỗi task ghi REQ. PRD có mà chưa duyệt → từ chối. Chế độ chat → in prompt | 1 lần |
| `approve <id\|epic\|all>` (task) | Xem bảng dưới | |
| `approve <id\|epic\|all>` | Duyệt nháp → GitHub Issue | Không |
| `work [--max N] [--task ID]` | Phiên làm việc: làm các task sẵn sàng (tối đa N, mặc định `MAX_TASKS`). Chế độ chat: mỗi lần chạy làm một bước, in bước tiếp theo | 2 lần/task (implementer + reviewer), +1 nếu cần viết test ẩn |
| `work --abort` | (chế độ chat) Huỷ task đang làm dở, về nhánh gốc, không tính lượt thử | Không |
| `sync` | Gộp trạng thái mọi máy; nhãn GitHub sửa tay; PR merged → `done`, đóng → `failed`; epic có đủ task `done` → `verify`; chia sẻ kết quả | Không |
| `set <id> <status>` | Đổi trạng thái tay, ví dụ `failed` → `queued` để chạy lại (đặt lại số lần thử) | Không |
| `doctor --fix` | Đưa task kẹt `running` về `queued`, rồi `sync` | Không |
| `import` | Issue nhãn `agent-ready` → task nháp trong `tasks/imported/` | Không |

### 7.1 Định dạng file task

```markdown
---
id: FEAT-01           # duy nhất trong repo
type: task            # epic | task | bug
epic: FEAT
status: draft         # draft | approved — chỉ người đổi (qua approve)
depends_on: []        # ví dụ [FEAT-01, FEAT-02]
requirements: []      # (tuỳ chọn) mã REQ trong PRD mà task phục vụ
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

| Đường dẫn | Nội dung | Máy khác thấy? |
|---|---|---|
| Nhánh `agent-kit/log`: `state/<máy>.json` | Trạng thái chạy mà máy đó biết, kèm giờ lượt chạy cuối | Có |
| Nhánh `agent-kit/log`: `runs/<máy>/<thời-điểm>/SUMMARY.md`, `meta.json` | Tóm tắt một lượt chạy | Có |
| Nhánh `agent-kit/log`: `runs/<máy>/<thời-điểm>/<task>/` | `result.json`, `review.json`, `checks.log`, `holdout.log`, `worker.txt`, báo cáo | Có |
| Nhánh `agent-kit/log`: `lock.json` | Máy đang chạy phiên `work` (chỉ có khi đang chạy) | Có |
| Nhánh `agent/<task>-a<n>` trên origin | Code của lần thử thứ n, cả PASS lẫn FAIL | Có |
| `.agent-kit/state.json` | Bản sao trạng thái trên máy này | Không (bản chia sẻ nằm ở nhánh log) |
| `.agent-kit/runs/` | Bản gốc log của máy này | Không |
| `.agent-kit/logs/guard.log` | Mọi lần hook chặn agent trên máy này | Không |
| `$HOLDOUT_DIR/<task>/` | Test ẩn (ngoài repo, cố ý không chia sẻ) | Không |

Không có remote `origin` (hoặc `PUBLISH=0`): mọi thứ chỉ nằm trên máy chạy, các lệnh kiểm tra vẫn đọc được log local.

Lưu ý bảo mật: log của worker được đẩy lên nhánh `agent-kit/log` trong cùng repo. Agent không đọc được `.env`, nhưng nếu repo public thì đừng bật `PUBLISH`.

---

## 8. Cấu hình `runner/config.env`

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `BASE_BRANCH` | `main` | Nhánh gốc: tạo nhánh task từ đây, PR mở về đây |
| `MAX_TASKS` | `3` | Số task tối đa mỗi phiên `work` |
| `TASK_TIMEOUT_MIN` | `60` | Worker chạy quá thời gian này thì bị dừng |
| `MAX_ATTEMPTS` | `2` | Số lần thử tối đa một task trước khi `failed` |
| `MAX_BUDGET_USD` | trống | Phanh an toàn theo chi phí **ước tính** mỗi lần gọi (với gói Pro không phải hoá đơn). Trống = tắt |
| `AGENT` | `auto` | `claude` / `cli` / `chat` / `auto` (mục 2.5) |
| `AGENT_CMD` | trống | (AGENT=cli) Lệnh gọi agent CLI. `{prompt}` được thay bằng prompt; không có `{prompt}` thì prompt đi qua stdin |
| `CLAUDE_BIN` | `claude` | (AGENT=claude) Đường dẫn tới Claude Code. Dùng đường dẫn tuyệt đối khi chạy theo lịch |
| `HOLDOUT_DIR` | `~/.agent-holdout/<project>` | Thư mục test ẩn, **ngoài repo** |
| `HOLDOUT_CMD` | trống | Lệnh chạy test ẩn trong worktree, ví dụ `pytest -q tests` |
| `EPIC_TEST_CMD` | trống | Lệnh chạy kiểm thử end-to-end cấp epic. Trống = dùng `HOLDOUT_CMD` |
| `REQUIRE_PRD` | `0` | `1` = `plan` bắt buộc có PRD đã duyệt |
| `GH_SYNC` | `0` trong code, `1` trong file mẫu | Dùng GitHub Issue + PR qua `gh` |
| `GIT_PULL` | `1` | `git pull --ff-only` đầu mỗi phiên `work`. Thất bại hoặc có thay đổi chưa commit → dừng, không chạy spec cũ |
| `PUBLISH` | `1` | Đẩy trạng thái, log và nhánh mọi lần thử lên origin để máy khác kiểm tra |
| `LOG_BRANCH` | `agent-kit/log` | Tên nhánh chứa trạng thái + log dùng chung |
| `MACHINE_NAME` | hostname | Tên máy trong báo cáo. Mỗi máy phải khác nhau |
| `LOCK_HOURS` | `12` | Khoá "đang chạy" của một lượt bị chết tự hết hạn sau số giờ này |
| `STALE_RUN_HOURS` | trống (tắt) | Chỉ khi bạn đặt lịch tự động: `doctor` cảnh báo nếu một máy quá số giờ này chưa chạy phiên nào |
| `WORKTREE_ROOT` | `../.agent-worktrees-<project>` | Nơi tạo worktree tạm, ngoài repo |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | trống | Gửi tóm tắt mỗi phiên qua Telegram |

### 8.1 Biến môi trường khi bạn dùng Claude trực tiếp

| Biến | Tác dụng |
|---|---|
| `AGENT_KIT_UNLOCK=1` | Cho Claude sửa vùng bảo vệ (khi **bạn** muốn nhờ nó sửa `CLAUDE.md`, `tasks/`, hooks, ...) |
| `AGENT_KIT_SKIP_STOP_CHECK=1` | Tắt hook chấm khi dừng (phiên hỏi đáp, thử nghiệm) |
| `AGENT_KIT_MAX_FIX_ATTEMPTS` | Số lần hook Stop bắt worker sửa lại (mặc định 3) |

### 8.2 Giới hạn gói Pro

Mỗi task tốn khoảng 2–3 lượt gọi Claude (worker, reviewer, cộng test-writer ở lần chạy đầu nếu task có test ẩn). Gói Pro giới hạn theo cửa sổ thời gian nên runner chạy **tuần tự**, ít task, và **tự dừng** khi chạm giới hạn (task dở được trả về hàng đợi, không tính là một lần thử).

---

## 9. Xử lý sự cố & câu hỏi thường gặp

| Hiện tượng | Nguyên nhân / cách xử lý |
|---|---|
| `checks.sh` báo "CHƯA CẤU HÌNH" | Chưa bỏ `#` ở dòng `step` nào. Xem mục 5.3 |
| `work` báo "agent-kit chưa được commit" | `git add .claude eval runner && git commit && git push` |
| `work` báo "Đang có một phiên work khác trên máy này" | Phiên trước còn chạy, hoặc bị kill giữa chừng. Khoá tự hết hạn sau `LOCK_HOURS`, hoặc xoá `.agent-kit/work.lock` |
| `work` (chế độ chat) cứ in lại cùng một bước | Agent chưa làm xong bước đó (ví dụ chưa ghi file test ẩn / file review). Làm xong rồi chạy lại, hoặc `work --abort` |
| `work` báo "đang ở nhánh ..." | Chuyển về nhánh gốc (`git checkout main`) rồi chạy lại. Nếu đang có phiên chat dở, `work` tự tiếp tục nó |
| `work` báo "Máy khác đang làm việc" | Máy đó đang giữ khoá. Chờ, hoặc nếu chắc lượt đó đã chết thì chờ khoá hết hạn (`LOCK_HOURS`) |
| `work` dừng vì `git pull` thất bại / có thay đổi chưa commit | Máy này có thay đổi chưa commit hoặc commit chưa push. Commit + push (hoặc `git stash`), rồi chạy lại |
| `status` hiện `running?` | Lượt chạy chết giữa chừng (mất điện, kill). `kit.py doctor --fix` đưa về `queued` |
| `status` báo "Không đọc được nhánh log" | Chưa có phiên `work` nào đẩy lên, hoặc mất mạng/không có `origin`. Bảng chỉ hiện dữ liệu máy này |
| `doctor` báo "spec đã sửa SAU khi agent chạy" | Bạn sửa task sau khi agent làm. Kết quả có thể không khớp spec mới → `kit.py set <id> queued` để chạy lại |
| `doctor` báo "máy X: phiên cuối ... lịch chạy tự động có còn hoạt động?" | Chỉ xuất hiện khi đặt `STALE_RUN_HOURS`. Kiểm tra `crontab -l`, `.agent-kit/work.log` trên máy X |
| `approve` báo "Acceptance trống" | Mục `# Acceptance` cần ít nhất một dòng `- [ ]` thật (ngoài dòng checks.sh, không còn `<!-- -->`) |
| Task mãi không chạy | `depends_on` chưa `done`, hoặc đã hết `MAX_ATTEMPTS`. Xem `kit.py status` |
| Hook báo lỗi "onFailure" / cờ lạ | Claude Code quá cũ. Cập nhật lên ≥ 2.1.295 |
| Chạy theo lịch không tìm thấy `claude` | Đặt `CLAUDE_BIN` là đường dẫn tuyệt đối |
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

- **Bạn đang nói chuyện trực tiếp với người dùng** (không phải agent con, không chạy từ runner) → bạn là **agent chủ**. Làm theo `docs/orchestration.md`: chọn đúng agent con, đưa đủ đầu vào, kiểm tra đầu ra, báo lại người dùng.
- **Bạn được spawn theo một file trong `.claude/agents/`** → làm đúng file đó, không làm việc của agent khác.
- **Bạn được runner gọi** → vai trò nằm trong biến `AGENT_KIT_ROLE` (hoặc được nêu đầu prompt).
- **Bạn là chat agent và người dùng bảo làm task / chạy work** → chạy `python3 runner/kit.py work` trong terminal, đọc khối **BƯỚC TIẾP THEO** nó in ra, làm đúng bước đó (đóng đúng vai được nêu), rồi chạy lại `work`. Lặp tới khi nó báo task đã chấm xong. Không tự sửa file trong `.agent-kit/` ngoài file mà bước đó yêu cầu.

| Agent / vai trò | Việc của bạn | File hướng dẫn |
|---|---|---|
| agent chủ | Điều phối, không tự làm việc của agent con | `docs/orchestration.md` |
| `context-writer` | Đề xuất bối cảnh vào `.agent-kit/proposals/` | `.claude/agents/context-writer.md` |
| `product-analyst` | Ý tưởng → `design/<feature>/prd.md` (draft) | `.claude/agents/product-analyst.md` |
| `planner` | PRD/spec + design → epic + tasks nháp trong `tasks/<feature>/`, ghi `requirements:` | `.claude/agents/planner.md` |
| `bug-triager` | Bug report → task nháp trong `tasks/bugs/` | `.claude/agents/bug-triager.md` |
| `test-writer` | Test ẩn vào `.agent-kit/holdout-staging/<task-id>/` | `.claude/agents/test-writer.md` |
| `implementer` (= `worker`) | Làm một task, tự chấm, commit, báo cáo | `.claude/agents/implementer.md` |
| `reviewer` | Đọc diff + log, trả JSON PASS/FAIL, không sửa gì | `.claude/agents/reviewer.md` |

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
