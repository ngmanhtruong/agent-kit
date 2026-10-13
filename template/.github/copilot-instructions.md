# Hướng dẫn cho GitHub Copilot

Repo này dùng **agent-kit**. Toàn bộ bối cảnh và quy tắc viết cho mọi AI agent, không riêng Claude. Đọc theo thứ tự:

1. `CLAUDE.md` — sản phẩm làm gì, được/cấm đụng đâu, thế nào là "xong".
2. `docs/architecture.md` — các bộ phận, chỗ nguy hiểm.
3. `docs/orchestration.md` — chọn đúng vai trò cho từng loại việc.

## Vai trò

Mỗi loại việc có một file hướng dẫn trong `.claude/agents/<tên>.md` (planner, bug-triager, context-writer, test-writer, implementer, reviewer). Khi người dùng giao việc:
- Xác định vai trò phù hợp theo `docs/orchestration.md`.
- Đọc file `.claude/agents/<vai trò>.md` và làm **đúng một vai trò** đó, kể cả giới hạn "chỉ được ghi vào đâu".
- Không đọc bài test ẩn (`~/.agent-holdout/`). Chỉ viết test ẩn khi `kit.py work` giao vai test-writer.

## Không có rào cứng ở đây — tự giữ quy tắc

Rào cứng (hooks) của agent-kit chỉ chạy trong Claude Code. Trong Copilot, bạn phải tự tuân thủ:
- Không sửa `eval/`, `.claude/`, `runner/`, `docs/`, `design/`, `CLAUDE.md`, `.env*` trừ khi người dùng yêu cầu rõ.
- Chỉ sửa `tasks/` khi đóng vai planner hoặc bug-triager. Không tự đổi `status: draft` thành `approved` — việc duyệt là của người dùng (`python3 runner/kit.py approve`).
- Không `git push`, không tạo PR/issue (kit.py làm việc đó sau khi chấm).
- Không nới test hay hardcode để test pass. "Xong" = `bash eval/checks.sh` exit 0 và mọi dòng Acceptance đạt.
- Không đoán ý người dùng; thiếu thông tin thì hỏi.

## Làm task: để `kit.py work` dẫn từng bước

Khi người dùng bảo làm task / chạy hàng đợi / "work":
1. Chạy trong terminal: `python3 runner/kit.py work` (hoặc `--task <id>` nếu người dùng chỉ định).
2. Đọc khối **▶ BƯỚC TIẾP THEO** nó in ra và làm đúng bước đó, đóng đúng vai được nêu (test-writer / implementer / reviewer), theo file `.claude/agents/<vai>.md`.
3. Làm xong thì chạy lại `python3 runner/kit.py work`. Lặp lại cho tới khi nó báo task đã chấm xong (✅/❌) và đã về nhánh gốc.
4. Việc chấm do `kit.py` làm: checks, test ẩn, phát hiện sửa vùng bảo vệ. Đừng tìm cách lách; nếu kẹt, báo người dùng hoặc `python3 runner/kit.py work --abort`.
5. Bước test-writer và reviewer nên làm trong một cuộc chat mới; nếu đang ở cùng cuộc chat, hãy nói rõ với người dùng điều đó.

## Lệnh kiểm tra (chạy trong terminal, chỉ đọc)

```bash
python3 runner/kit.py status
python3 runner/kit.py report
python3 runner/kit.py report --task <id>
python3 runner/kit.py doctor
```
