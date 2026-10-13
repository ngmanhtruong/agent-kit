# agent-kit

Bộ khung để AI tự làm việc khi bạn ngủ: **ý tưởng → design → tasks → agent làm → tự chấm → Pull Request → bạn review.**

```
 BẠN (MacBook)                          MINI PC (đêm)                       BẠN (sáng)
 ─────────────                          ─────────────                       ──────────
 Claude Design → design/<feature>/      kit.py night                        GitHub PR
 kit.py plan   → tasks/<feature>/*.md     ├ worker làm task (nhánh riêng)     ├ đọc chấm điểm
 sửa + duyệt   → kit.py approve           ├ checks.sh  (thang điểm)          ├ merge / đóng
   ├ GitHub Issue                         ├ test ẩn    (worker không thấy)   └ kit.py sync
   └ test-writer viết test ẩn             ├ reviewer   (chấm độc lập)
 git push                                 └ PASS → mở PR · FAIL → thử lại
```

## 3 trụ cột trong khung

| Trụ cột | Nằm ở đâu |
|---|---|
| **01 Tự chấm bài** | `eval/checks.sh` (1 lệnh, exit 0 = đạt) · Acceptance trong task · test ẩn ngoài repo · agent `reviewer` · hook Stop chặn dừng khi chưa pass |
| **02 Bối cảnh** | `CLAUDE.md` (bản đồ) · `docs/` · `design/` · Interface + Acceptance trong mỗi task |
| **03 Rào chắn** | Rào cứng: `.claude/hooks/` (chặn lệnh nguy hiểm, chặn sửa bài chấm/spec, giới hạn vùng ghi theo vai trò) · `settings.json` deny · worktree riêng · không cho push · trần số task/lần thử. Rào mềm: `CLAUDE.md` |

"Cấm ghi chú": agent không được sửa `CLAUDE.md`, `docs/`. Muốn đổi gì thì đề xuất trong báo cáo, bạn quyết.

## Bắt đầu

**Trên cả hai máy**: cần `git`, `python3`, `claude` (đã đăng nhập gói Pro, bản mới), `gh` (`gh auth login`).

```bash
python3 agent-kit/install.py ~/code/my-project
cd ~/code/my-project
```

1. Điền `CLAUDE.md` và `docs/architecture.md` (ngắn, chỉ những gì AI không tự đoán được).
2. Điền `eval/checks.sh` bằng lệnh lint/type/test thật. Chưa điền → luôn FAIL (cố ý).
3. Sửa `runner/config.env` (file này riêng từng máy, không commit).
4. `git add -A && git commit -m "add agent-kit" && git push` — runner từ chối chạy nếu khung chưa được commit.

## Dùng hằng ngày

```bash
# 1. Design: export từ Claude Design (PDF/PNG/HTML) + viết spec.md vào design/<feature>/
# 2. Chia việc
python3 runner/kit.py plan design/<feature>
#    → đọc tasks/<feature>/EPIC.md, trả lời "Câu hỏi mở", sửa Acceptance cho đúng ý
#    (cần AGENT_KIT_UNLOCK=1 nếu muốn nhờ Claude sửa tasks/: AGENT_KIT_UNLOCK=1 claude)
# 3. Duyệt (từng task, cả epic, hoặc all)
python3 runner/kit.py approve <FEAT>
git add tasks && git commit -m "approve <FEAT>" && git push
# 4. Đêm: mini PC tự chạy (cron bên dưới). Chạy tay: python3 runner/kit.py night --max 1
# 5. Sáng: review PR trên GitHub, merge → python3 runner/kit.py sync
python3 runner/kit.py status
# Bug: tạo GitHub Issue có nhãn 'agent-ready' + mục '# Acceptance' → kit.py import → approve
```

**Cron trên mini PC** (`crontab -e`, 1h sáng giờ VN):
```
0 1 * * * cd /đường/dẫn/my-project && /usr/bin/python3 runner/kit.py night >> .agent-kit/night.log 2>&1
```
Đặt `CLAUDE_BIN` trong `config.env` bằng đường dẫn tuyệt đối (`which claude`).

## Phân vai 2 máy
- **MacBook**: design, plan, approve, review, sync. Không chạy `night`.
- **Mini PC**: chỉ `night`. Không sửa `tasks/`.
- Trạng thái chạy nằm trên nhãn GitHub Issue (`status:queued/running/review/done/failed`), không nằm trong file → hai máy không đụng nhau.

## Nâng cấp theo nguyên tắc
- Lỗi nào lặp 2 lần → dùng skill `promote-rule`: triệt tiêu bằng thiết kế → check trong `checks.sh` → rule trong hook → cuối cùng mới ghi vào `docs/conventions.md`.
- Chưa tin 1 agent thì đừng tăng `MAX_TASKS`. Bắt đầu `night --max 1`, xem 5-10 PR liên tiếp ổn rồi mới tăng.
- Gói Pro có giới hạn theo cửa sổ thời gian: mỗi task tốn ~2-4 lượt gọi (worker, reviewer, test-writer lúc approve). Runner tự dừng khi chạm giới hạn và để task lại cho đêm sau.

## Biến môi trường khi chạy tay
| Biến | Tác dụng |
|---|---|
| `AGENT_KIT_UNLOCK=1` | cho Claude sửa vùng bảo vệ (khi BẠN làm việc trực tiếp) |
| `AGENT_KIT_SKIP_STOP_CHECK=1` | tắt hook chấm khi dừng (phiên hỏi đáp ban ngày) |
