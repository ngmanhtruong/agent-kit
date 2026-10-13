# CLAUDE.md — Bản đồ dự án

> Chỉ ghi những gì AI KHÔNG tự suy ra được từ code. Ngắn > dài.
> Chỉ người được sửa file này. AI chỉ đề xuất thay đổi trong báo cáo, không tự ghi.

## 1. Sản phẩm này để làm gì
<!-- 2-3 câu: ai dùng, giải quyết vấn đề gì, "thành công" trông thế nào -->

## 2. Phạm vi
- Được làm: <!-- ví dụ: sửa logic trong src/, thêm test -->
- KHÔNG được đụng: <!-- ví dụ: config live trading, API key, schema DB production -->

## 3. Kiến trúc tóm tắt
Xem `docs/architecture.md`. Điểm vào chính: <!-- file/module -->

## 4. Quy chuẩn
Xem `docs/conventions.md`. Quyết định đã chốt: `docs/decisions/`.

## 5. Định nghĩa "XONG" (bắt buộc)
Task chỉ xong khi:
1. `bash eval/checks.sh` exit 0 (lint + type + test).
2. Mọi tiêu chí trong mục "Acceptance" của task đạt, kèm bằng chứng (lệnh đã chạy + kết quả).
3. Không sửa `eval/`, `.claude/`, `tasks/`, `design/`, `runner/`, `docs/`, `CLAUDE.md` (hook sẽ chặn).
4. Commit trên nhánh hiện tại, viết báo cáo theo skill `finish-task`. Không push.

Hook sẽ tự chặn nếu bạn dừng khi checks chưa pass. Đừng lách. Bị kẹt → ghi lý do vào báo cáo rồi dừng.

## 6. Khi không chắc
Không đoán ý người dùng. Chọn cách an toàn nhất, ghi giả định vào báo cáo.
