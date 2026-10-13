---
name: finish-task
description: Quy trình bắt buộc trước khi báo một task là xong — tự chấm theo eval/checks.sh và tiêu chí Acceptance, rồi viết báo cáo. Dùng ở cuối mọi task code.
---

# Hoàn tất task

1. Chạy `bash eval/checks.sh`. Không pass → sửa code (KHÔNG sửa test, eval/, .claude/).
2. Mở file task, đi qua từng dòng "Acceptance". Với mỗi dòng ghi: đạt / không đạt + bằng chứng (lệnh đã chạy, output rút gọn).
3. `git add -A && git commit -m "<task-id>: <tóm tắt>"`. Không push.
4. Ghi báo cáo vào `.agent-kit/reports/<task-id>.md` theo mẫu:

```
# <task-id>
Kết quả: XONG | KẸT
## Đã làm
## Acceptance (từng dòng + bằng chứng)
## Giả định đã đưa ra
## Đề xuất cho người (sửa CLAUDE.md / thêm rule / thêm test) — nếu có
```

Không tự sửa CLAUDE.md hay docs/ để "ghi nhớ" — chỉ đề xuất ở mục cuối.
