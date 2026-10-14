# Changelog

Phiên bản nằm ở `template/runner/VERSION` (một nguồn duy nhất; `install.py` ghi vào `.agent-kit-manifest.json` của project đích,
`kit.py --version` và `kit.py doctor` đọc lại). Theo [SemVer](https://semver.org): sửa lỗi → patch, thêm tính năng tương thích → minor,
đổi cách dùng/định dạng file → major. **Sửa `template/` thì phải tăng VERSION và thêm một dòng ở đây**, nếu không `--upgrade` không có gì để báo.

## 0.2.0 — 2026-10-14
- `kit.py report --by-task [--last N]`: mỗi task một dòng (lượt, PASS/FAIL, chi phí, thời gian, kết quả lượt cuối), tổng cộng và lý do FAIL hay gặp. Chỉ đọc. Có trong menu mục 3.
- `result.json` của mỗi lượt ghi thêm `costs` (theo vai: worker / reviewer / test-writer; trước đây chỉ tính worker) và `seconds`. Chi phí chỉ đo được với `AGENT=claude`.

## 0.1.0 — 2026-10-14
Bản đầu tiên có số phiên bản.
- Quy trình: ý tưởng → PRD → epic/task → `work` (chấm bởi `kit.py`) → PR → kiểm thử cấp epic; chạy với `claude` / `cli` / `chat`.
- Trạng thái dùng chung nhiều máy trên nhánh `agent-kit/log`; `status` / `report` / `doctor` chỉ đọc.
- `kit.py` không tham số: menu chọn việc; `kit.py menu --json` cho AI agent.
- `updated` ghi theo mili-giây.
- Quy tắc của kit tách khỏi `CLAUDE.md` của project: `.claude/rules/agent-kit.md`, `.github/instructions/agent-kit.instructions.md`.
- `install.py --upgrade [--force] [--dry-run]`, `.agent-kit-manifest.json`; `doctor` cảnh báo file của kit bị sửa.
- `tests/smoke.py`: kiểm tra nhanh cài / nâng cấp / hook / menu (không nằm trong bản cài).
