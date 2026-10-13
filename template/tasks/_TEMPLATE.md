---
id: FEAT-01
type: task            # epic | task | bug
epic: FEAT
status: draft         # draft (nháp) → approved (bạn duyệt). Trạng thái chạy nằm ở GitHub Issue.
depends_on: []
requirements: []      # mã yêu cầu trong PRD mà task này phục vụ, vd [REQ-01, REQ-03] (bỏ trống nếu không dùng PRD)
priority: 2           # 1 = làm trước
holdout: true         # có viết bài kiểm tra ẩn không
design: design/feat
issue:                # runner tự điền số GitHub Issue khi approve
---

# Mục tiêu
<!-- 1-3 câu. Kết quả cuối cùng, không phải cách làm. -->

# Bối cảnh
<!-- File/module liên quan, màn hình nào trong design. Chỉ những gì CLAUDE.md chưa có. -->

# Interface (hợp đồng)
<!-- Tên hàm/endpoint/component + tham số + kiểu trả về. Bài test ẩn bám vào đây. -->

# Acceptance (thang điểm — đo được, có/không)
- [ ] `bash eval/checks.sh` pass
- [ ] <!-- ví dụ: parse_signal("BUY BTC") trả về Signal(side="buy", symbol="BTCUSDT") -->

# Ngoài phạm vi
<!-- Những gì KHÔNG được làm trong task này -->
