---
name: promote-rule
description: Dùng khi người dùng muốn biến một lỗi lặp lại hoặc một lời nhắc thành quy định tự động (check trong eval/checks.sh hoặc rule trong hook). Chỉ chạy khi người dùng yêu cầu.
---

# Biến lời nhắc thành quy định

Hỏi theo thứ tự, dừng ở câu đầu tiên trả lời "có":

1. **Triệt tiêu được không?** Đổi thiết kế/API để lỗi không thể xảy ra (type, tham số bắt buộc, xoá đường tắt sai).
2. **Tool bắt được không?** Thêm rule linter / test / grep vào `eval/checks.sh`.
3. **Chặn lúc hành động được không?** Thêm pattern vào `.claude/hooks/guard_bash.py` hoặc vùng bảo vệ trong `_common.py`.
4. **Không cách nào trên** → thêm 1 dòng vào `docs/conventions.md`, cột "Đã tự động hoá?" = chưa.

Sau khi thêm: viết 1 ví dụ vi phạm, chạy để chứng minh check bắt được, rồi xoá ví dụ.
Cần `AGENT_KIT_UNLOCK=1` khi khởi động Claude để sửa các file này.
