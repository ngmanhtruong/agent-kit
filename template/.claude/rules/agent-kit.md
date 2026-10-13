# agent-kit — quy tắc cho mọi phiên làm việc trong repo này

> File này do agent-kit cài và Claude Code tự nạp (`.claude/rules/`). Nó **không thay** `CLAUDE.md` của project:
> sản phẩm làm gì, phạm vi được/cấm đụng, kiến trúc, quy chuẩn viết ở `CLAUDE.md` của bạn. Đọc `CLAUDE.md` trước nếu có.
> Chỉ người được sửa file này. AI chỉ đề xuất thay đổi trong báo cáo, không tự ghi.

## 1. Định nghĩa "XONG" (bắt buộc)
Task chỉ xong khi:
1. `bash eval/checks.sh` exit 0 (lint + type + test).
2. Mọi tiêu chí trong mục "Acceptance" của task đạt, kèm bằng chứng (lệnh đã chạy + kết quả).
3. Không sửa `eval/`, `.claude/`, `tasks/`, `design/`, `runner/`, `docs/`, `CLAUDE.md` (hook sẽ chặn).
4. Commit trên nhánh hiện tại, viết báo cáo theo skill `finish-task`. Không push.

Hook sẽ tự chặn nếu bạn dừng khi checks chưa pass. Đừng lách. Bị kẹt → ghi lý do vào báo cáo rồi dừng.

## 2. Phạm vi
Phạm vi được/cấm đụng nằm ở `CLAUDE.md` của project (mục "Phạm vi"). Chưa có mục đó thì chỉ sửa những file mà task nêu, không làm thêm.

## 3. Khi không chắc
Không đoán ý người dùng. Chọn cách an toàn nhất, ghi giả định vào báo cáo.

## 4. Nạp sẵn (không xoá)
@../../docs/architecture.md
@../../docs/orchestration.md
