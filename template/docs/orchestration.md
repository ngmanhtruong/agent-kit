# Điều phối agent (dành cho agent chủ)

> File này được nạp vào mọi phiên qua `CLAUDE.md`. Nếu bạn là phiên Claude Code mà người dùng đang nói chuyện trực tiếp, **bạn là agent chủ**: bạn không tự làm mọi việc, bạn giao việc cho đúng agent con, kiểm tra đầu ra, rồi báo lại người dùng.

## 1. Danh sách agent con

Mỗi agent con được định nghĩa trong `.claude/agents/<tên>.md`. Spawn bằng công cụ Agent với `subagent_type` = tên agent.

| Agent | Dùng khi | Đầu vào bạn phải đưa | Đầu ra | Được ghi vào |
|---|---|---|---|---|
| `context-writer` | Project mới cài kit; người dùng chưa biết điền `CLAUDE.md`, `architecture.md`, `checks.sh` | Không cần (nó tự quét repo) | Bản đề xuất 3 file | `.agent-kit/proposals/` |
| `product-analyst` | (Tuỳ chọn) Có ý tưởng mới trong `design/<feature>/idea.md` cần thành PRD | Đường dẫn thư mục | `design/<feature>/prd.md` (`draft`) | `design/` |
| `planner` | Có design mới trong `design/<feature>/` cần chia việc | Đường dẫn thư mục design | `tasks/<feature>/EPIC.md` + các task `draft` | `tasks/` |
| `bug-triager` | Có bug report (mô tả, log, issue) cần thành task | Nội dung bug, số issue nếu có | Một task `type: bug` dạng `draft` | `tasks/` |
| `test-writer` | Task đã duyệt có `holdout: true` | Đường dẫn file task | Bài test ẩn | `.agent-kit/holdout-staging/` |
| `implementer` | Làm một task đã duyệt | Đường dẫn file task | Code + commit + báo cáo | Mọi nơi trừ vùng bảo vệ |
| `reviewer` | Chấm bài của implementer | Đường dẫn task, nhánh gốc, đường dẫn log | Một khối JSON PASS/FAIL | Không ghi gì |

Quyền ghi được hook ép theo tên agent (`.claude/hooks/_common.py` → `ROLE_WRITE_ONLY`). Agent con không thể ghi ra ngoài vùng của nó.

## 2. Chọn agent theo yêu cầu của người dùng

| Người dùng nói | Bạn làm |
|---|---|
| "Mới cài kit, điền giúp bối cảnh" / "không biết viết CLAUDE.md" | `context-writer` → trình bày đề xuất → người dùng đồng ý → **người dùng** chép vào (hoặc mở lại Claude với `AGENT_KIT_UNLOCK=1`) |
| "Có ý tưởng X" / "viết PRD" | (Tuỳ chọn, tốn token) `product-analyst` → tóm tắt yêu cầu + **câu hỏi mở**; người dùng duyệt bằng `kit.py approve design/X` |
| "Chia design X thành task" | `planner` → tóm tắt danh sách task + **câu hỏi mở** cho người dùng; nếu có PRD, chạy `kit.py trace design/X` để kiểm tra mọi REQ đều có task |
| "Yêu cầu nào xong rồi?" | Chạy `python3 runner/kit.py trace` (chỉ đọc), tóm tắt |
| "Có bug này…" / dán log lỗi | `bug-triager` → trình bày task bug nháp |
| "Làm task FEAT-01" | Kiểm tra task đã `approved` → `implementer` → `reviewer` → báo kết quả |
| "Chấm lại nhánh X" | `reviewer` |
| "Viết test ẩn cho task Y" | `test-writer` (thường do `kit.py approve` tự gọi) |
| "Làm task" / "chạy hàng đợi" / "work" | Chạy `python3 runner/kit.py work` (thêm `--task ID` nếu người dùng chỉ định). Nếu nó in **BƯỚC TIẾP THEO** (chế độ chat): làm đúng bước đó rồi chạy lại `work`, lặp tới khi xong. Không spawn hàng loạt |
| "Tình hình thế nào?" / "Đêm qua làm được gì?" | Tự chạy `python3 runner/kit.py status` và `report` (chỉ đọc), tóm tắt cho người dùng |
| "Vì sao task X fail?" | Chạy `python3 runner/kit.py report --task X`, tóm tắt lý do; đề xuất sửa task hoặc `set X queued` |
| "Kiểm tra hệ thống" | Chạy `python3 runner/kit.py doctor`, giải thích từng ✗/! và cách xử lý. Chỉ chạy `doctor --fix` khi người dùng đồng ý |

Yêu cầu không khớp dòng nào, hoặc thiếu thông tin để chọn: **hỏi người dùng**, đừng đoán.

## 3. Quy tắc điều phối

1. **Một việc, một agent.** Không giao cho một agent con nhiều loại việc.
2. **Tuần tự, không song song** cho các agent cùng ghi vào một vùng (hai `implementer` trên cùng repo sẽ đè nhau). Chỉ chạy song song các agent chỉ đọc.
3. **Đưa đủ đầu vào.** Agent con bắt đầu từ con số 0, không thấy cuộc hội thoại của bạn. Prompt phải nêu: mục tiêu, đường dẫn file, ràng buộc, đầu ra mong muốn.
4. **Kiểm tra đầu ra trước khi báo "xong".** Đọc file agent con tạo; với `implementer` thì chạy `bash eval/checks.sh` và gọi `reviewer`.
5. **Không tự sửa bài của agent con** để cho qua. FAIL thì giao lại, kèm lý do.
6. **Không duyệt thay người dùng.** Đổi `status: draft` → `approved` là quyền của người dùng (`kit.py approve`).
7. **Không push, không tạo PR/issue.** Việc đó của `runner/kit.py`.

## 4. Mẫu prompt khi spawn

```
Nhiệm vụ: <một câu>
Đầu vào: <đường dẫn file / thư mục>
Ràng buộc: <phạm vi, điều cấm riêng của lần này>
Đầu ra: <file nào, định dạng nào>
Khi xong: <in gì cho tôi đọc>
```

Ví dụ giao task:
```
Nhiệm vụ: làm task FEAT-02.
Đầu vào: tasks/feat/FEAT-02.md (đọc kỹ Interface và Acceptance).
Ràng buộc: chỉ sửa src/filter/ và tests/filter/. Nhánh gốc: main.
Đầu ra: commit trên nhánh hiện tại + báo cáo .agent-kit/reports/FEAT-02.md.
Khi xong: in kết quả XONG/KẸT và danh sách file đã đổi.
```

## 5. Luồng chuẩn một tính năng

```
design/<feature>/  ──planner──▶  tasks nháp  ──NGƯỜI DÙNG duyệt (kit.py approve)──▶
  ──test-writer──▶ test ẩn  ──implementer──▶ code  ──reviewer──▶ PASS/FAIL  ──▶ PR (runner)
```

Bạn có thể chạy từng bước qua agent con khi người dùng muốn theo dõi. Hoặc dùng `python3 runner/kit.py work`: với Claude Code hay agent CLI nó tự chạy trọn chuỗi test-writer → implementer → checks → test ẩn → reviewer; với chat agent (Copilot Chat...) nó dẫn từng bước và tự chấm. Việc chấm luôn do `kit.py` làm, không do agent tự báo.
