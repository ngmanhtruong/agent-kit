# CLAUDE.md — repo agent-kit

Repo này là **bộ khung** (không phải một sản phẩm). Người dùng cài nó vào project khác bằng `install.py`. Mọi thứ trong `template/` sẽ được chép vào project đích.

Đọc `README.md` mục 2 (toàn cảnh), mục 3 (bản đồ file) và mục 10 (dành cho AI agent) trước khi sửa gì.

Lưu ý: `template/.claude/rules/agent-kit.md`, `starter/CLAUDE.md`, `template/docs/` là **mẫu** cho project đích, không phải quy tắc của repo này. Đừng làm theo chúng khi sửa agent-kit; hãy sửa chúng như sửa văn bản.

## Cấu trúc
- `starter/CLAUDE.md` — `CLAUDE.md` khởi đầu, chỉ chép vào project đích khi nó CHƯA có `CLAUDE.md`. Không bao giờ chạm `CLAUDE.md` của người dùng; quy tắc của kit nằm ở `template/.claude/rules/agent-kit.md`.
- `install.py` — chép `template/` vào repo đích, gộp `settings.json`, không ghi đè file người dùng.
- `template/` — nội dung được cài. Hooks, agents, skills, runner nằm ở đây.
- `tests/smoke.py` — kiểm tra nhanh, không thuộc bản cài. `LICENSE` (MIT), `CHANGELOG.md`.
- `README.md` — hướng dẫn đầy đủ cho người dùng và agent. Sửa hành vi thì **phải** sửa README tương ứng.

## Bất biến — không được phá
1. Trạng thái chạy không ghi vào `tasks/*.md` (tránh xung đột giữa các máy). Trạng thái dùng chung nằm trên nhánh orphan `agent-kit/log`; **mỗi máy chỉ ghi file của chính nó** (`state/<máy>.json`, `runs/<máy>/...`), đọc thì gộp theo `updated` (UTC) mới nhất. `lock.json` trên nhánh đó chống hai máy chạy `work` cùng lúc. Không có khái niệm máy "ngày"/"đêm": mọi máy ngang hàng, phiên `work` chạy lúc nào cũng được.
1b. `status`, `report`, `doctor` (không `--fix`) **chỉ đọc**: chỉ `git fetch` ref nhánh log, không sửa file, không đổi nhánh, không push, không ghi `.agent-kit/state.json`.
1c. `work` không chạy spec cũ: `git pull --ff-only` thất bại thì dừng.
1d. `kit.py` chạy với mọi agent qua `call_agent()` (chế độ `claude` / `cli` qua `AGENT_CMD` / `chat`). Không gọi thẳng một CLI cụ thể ở chỗ khác. Chỉ `work` và `plan` cần AI; `approve`, `status`, `report`, `doctor`, `sync`, `set`, `import` không bao giờ gọi AI. Chế độ `chat`: `work` là máy trạng thái, mỗi lần chạy làm một bước, lưu ở `.agent-kit/session.json`, in **BƯỚC TIẾP THEO**. Bài test ẩn được viết trong `work`, trước khi implementer bắt đầu.
1d2. `kit.py` không tham số (hoặc `menu`) là menu chọn việc: chỉ gọi lại các `cmd_*` có sẵn, không có logic riêng; không có TTY thì in menu rồi thoát (không `input()`); `menu --json` cho AI agent dùng chung `menu_state()` với menu tương tác (một nguồn lựa chọn); phần tóm tắt chỉ đọc. Thêm lệnh mới thì thêm vào `MENU` nếu người dùng cần tìm thấy nó, và mục gọi AI phải hỏi xác nhận.
1e. Việc chấm (`grade()`) phải do kit.py làm và giống nhau cho mọi agent: có diff, không sửa vùng bảo vệ (`PROTECTED` trong kit.py, giữ khớp với hooks), checks pass, test ẩn pass. Không bao giờ tin agent tự báo kết quả.
1f. Khâu **bắt buộc** (không thêm công tắc tắt): lập kế hoạch (task có Acceptance, `approve`), tự chấm (`grade()` + reviewer luôn chạy), kiểm thử (test ẩn theo `holdout` của task, kiểm thử cấp epic khi epic sang `verify`). Mọi khâu khác **tuỳ chọn**, chỉ chạy khi người dùng gọi hoặc bật trong config (idea/PRD, trace, context-writer, bug-triager, GitHub, publish, Telegram). Không thêm bước tốn token chạy mặc định.
1g. PRD (`design/<feature>/prd.md`) là tuỳ chọn: `plan` vẫn chạy khi không có PRD (trừ `REQUIRE_PRD=1`), nhưng nếu có PRD thì phải `approved`. Mã yêu cầu đọc bằng `REQ_DEF_RE`; task trỏ về bằng `requirements:`.
1h. Epic: mọi task `done` → `verify` (trong `sync`) → `work` kiểm thử trên nhánh gốc → `done`/`failed`. FAIL chỉ mở GitHub Issue (`bug,agent-ready`), không ghi `tasks/`. Task sửa có `epic: <mã>` merge xong → epic tự về `verify`.
1i. Deploy/staging/production **không** thuộc kit; chỉ tài liệu hoá (README mục 2.6).
2. Test ẩn không bao giờ nằm trong repo đích hay trong tầm đọc của worker/implementer.
3. Chỉ runner (script) được push, tạo PR/issue. Agent thì không.
4. Hook dùng `onFailure: "block"`: hook lỗi thì chặn.
5. `runner/kit.py`, hooks, `install.py` chỉ dùng thư viện chuẩn Python 3.8+. Script phải chạy trên cả macOS và Linux.
6. Quyền ghi của agent con được ép trong `template/.claude/hooks/_common.py` (`ROLE_WRITE_ONLY`). Thêm agent mới thì thêm vùng ghi tương ứng.
7. `install.py` không bao giờ ghi đè file của người dùng (`CLAUDE.md`, `eval/checks.sh`, `docs/architecture.md`, `config.env`...). Chỉ `--upgrade` mới đụng file của kit (danh sách `OWNED` trong `install.py`), và chỉ khi file chưa bị sửa so với `.agent-kit-manifest.json`; file đã sửa thì đặt bản mới ở `.agent-kit/upgrade/`, `--force` mới ghi đè và phải sao lưu. Thêm file vào `template/` thì quyết định nó thuộc kit (thêm vào `OWNED`) hay thuộc người dùng.

## Thêm một agent con mới
1. Tạo `template/.claude/agents/<tên>.md` (frontmatter: name, description, tools).
2. Nếu agent chỉ được ghi một vùng: thêm vào `ROLE_WRITE_ONLY`.
3. Thêm một dòng vào bảng ở `template/docs/orchestration.md` (mục 1 và 2).
4. Cập nhật README mục 2.2 và mục 3.

## Kiểm tra trước khi commit
```bash
python3 -m py_compile install.py template/runner/kit.py template/.claude/hooks/*.py
python3 tests/smoke.py        # cài / nâng cấp / hook / menu / doctor, không gọi AI
```
Sửa `template/` hoặc `install.py` thì tăng `template/runner/VERSION` và thêm mục vào `CHANGELOG.md` (smoke test kiểm tra hai thứ này khớp nhau).
`tests/smoke.py` không có kiểm tra `work` với agent giả. Bản đầy đủ từng có ở commit `6057217` (`git show 6057217:selftest.py`). Rồi chạy thử end-to-end: cài vào một repo git tạm, dùng một file `claude` giả (script in JSON) qua `CLAUDE_BIN` trong `runner/config.env`, chạy `kit.py approve` và `kit.py work` ở cả ba chế độ (`AGENT=claude` với claude giả, `AGENT=cli` với script giả đọc stdin, `AGENT=chat` bằng cách tự làm từng bước), kiểm tra cả nhánh PASS lẫn FAIL.

Hook test nhanh:
```bash
export CLAUDE_PROJECT_DIR=$PWD/template
echo '{"tool_input":{"command":"git push"}}' | python3 template/.claude/hooks/guard_bash.py      # phải in deny
echo '{"agent_type":"planner","tool_input":{"file_path":"src/a.py"}}' | python3 template/.claude/hooks/guard_files.py  # phải in deny
```
