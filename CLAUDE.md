# CLAUDE.md — repo agent-kit

Repo này là **bộ khung** (không phải một sản phẩm). Người dùng cài nó vào project khác bằng `install.py`. Mọi thứ trong `template/` sẽ được chép vào project đích.

Đọc `README.md` mục 2 (toàn cảnh), mục 3 (bản đồ file) và mục 10 (dành cho AI agent) trước khi sửa gì.

Lưu ý: `template/CLAUDE.md`, `template/docs/` là **mẫu** cho project đích, không phải quy tắc của repo này. Đừng làm theo chúng khi sửa agent-kit; hãy sửa chúng như sửa văn bản.

## Cấu trúc
- `install.py` — chép `template/` vào repo đích, gộp `settings.json`, không ghi đè file người dùng.
- `template/` — nội dung được cài. Hooks, agents, skills, runner nằm ở đây.
- `README.md` — hướng dẫn đầy đủ cho người dùng và agent. Sửa hành vi thì **phải** sửa README tương ứng.

## Bất biến — không được phá
1. Trạng thái chạy không ghi vào `tasks/*.md` (tránh xung đột giữa các máy). Trạng thái dùng chung nằm trên nhánh orphan `agent-kit/log`; **mỗi máy chỉ ghi file của chính nó** (`state/<máy>.json`, `runs/<máy>/...`), đọc thì gộp theo `updated` (UTC) mới nhất. `lock.json` trên nhánh đó chống hai máy chạy `work` cùng lúc. Không có khái niệm máy "ngày"/"đêm": mọi máy ngang hàng, phiên `work` chạy lúc nào cũng được.
1b. `status`, `report`, `doctor` (không `--fix`) **chỉ đọc**: chỉ `git fetch` ref nhánh log, không sửa file, không đổi nhánh, không push, không ghi `.agent-kit/state.json`.
1c. `work` không chạy spec cũ: `git pull --ff-only` thất bại thì dừng.
1d. `kit.py` chạy với mọi agent qua `call_agent()` (chế độ `claude` / `cli` qua `AGENT_CMD` / `chat`). Không gọi thẳng một CLI cụ thể ở chỗ khác. Chỉ `work` và `plan` cần AI; `approve`, `status`, `report`, `doctor`, `sync`, `set`, `import` không bao giờ gọi AI. Chế độ `chat`: `work` là máy trạng thái, mỗi lần chạy làm một bước, lưu ở `.agent-kit/session.json`, in **BƯỚC TIẾP THEO**. Bài test ẩn được viết trong `work`, trước khi implementer bắt đầu.
1e. Việc chấm (`grade()`) phải do kit.py làm và giống nhau cho mọi agent: có diff, không sửa vùng bảo vệ (`PROTECTED` trong kit.py, giữ khớp với hooks), checks pass, test ẩn pass. Không bao giờ tin agent tự báo kết quả.
2. Test ẩn không bao giờ nằm trong repo đích hay trong tầm đọc của worker/implementer.
3. Chỉ runner (script) được push, tạo PR/issue. Agent thì không.
4. Hook dùng `onFailure: "block"`: hook lỗi thì chặn.
5. `runner/kit.py`, hooks, `install.py` chỉ dùng thư viện chuẩn Python 3.8+. Script phải chạy trên cả macOS và Linux.
6. Quyền ghi của agent con được ép trong `template/.claude/hooks/_common.py` (`ROLE_WRITE_ONLY`). Thêm agent mới thì thêm vùng ghi tương ứng.
7. `install.py` không bao giờ ghi đè file đã có của người dùng.

## Thêm một agent con mới
1. Tạo `template/.claude/agents/<tên>.md` (frontmatter: name, description, tools).
2. Nếu agent chỉ được ghi một vùng: thêm vào `ROLE_WRITE_ONLY`.
3. Thêm một dòng vào bảng ở `template/docs/orchestration.md` (mục 1 và 2).
4. Cập nhật README mục 2.2 và mục 3.

## Kiểm tra trước khi commit
```bash
python3 -m py_compile install.py template/runner/kit.py template/.claude/hooks/*.py
```
Rồi chạy thử end-to-end: cài vào một repo git tạm, dùng một file `claude` giả (script in JSON) qua `CLAUDE_BIN` trong `runner/config.env`, chạy `kit.py approve` và `kit.py work` ở cả ba chế độ (`AGENT=claude` với claude giả, `AGENT=cli` với script giả đọc stdin, `AGENT=chat` bằng cách tự làm từng bước), kiểm tra cả nhánh PASS lẫn FAIL.

Hook test nhanh:
```bash
export CLAUDE_PROJECT_DIR=$PWD/template
echo '{"tool_input":{"command":"git push"}}' | python3 template/.claude/hooks/guard_bash.py      # phải in deny
echo '{"agent_type":"planner","tool_input":{"file_path":"src/a.py"}}' | python3 template/.claude/hooks/guard_files.py  # phải in deny
```
