# design/

Mỗi tính năng một thư mục: `design/<feature>/`

| File | Ai viết | Bắt buộc? |
|---|---|---|
| `idea.md` | Bạn (mẫu: `_IDEA_TEMPLATE.md`) | Tuỳ chọn |
| `prd.md` | `kit.py idea design/<feature>` (product-analyst), bạn sửa và duyệt | Tuỳ chọn (bắt buộc nếu `REQUIRE_PRD=1`) |
| `spec.md` | Bạn — dùng thay PRD nếu muốn tiết kiệm token | Cần `prd.md` **hoặc** `spec.md` |
| File export từ Claude Design (PDF / PNG / HTML) | Bạn | Tuỳ chọn |

Luồng đầy đủ:
```bash
python3 runner/kit.py idea design/<feature>      # (tuỳ chọn) idea.md → prd.md
python3 runner/kit.py approve design/<feature>   # duyệt PRD
python3 runner/kit.py plan design/<feature>      # chia epic + tasks
python3 runner/kit.py trace design/<feature>     # mọi REQ đều có task chưa?
```
Luồng tối giản: viết `spec.md` rồi `plan`.
