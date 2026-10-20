"""Jev (TypeSafe System One) — phán đoán có/không bằng HTTP API. TUỲ CHỌN, mặc định tắt.

Dùng ở hai chỗ, đều chỉ để CỐ VẤN, không thay khâu bắt buộc nào:
  - hook guard_bash: chặn thêm lệnh shell nguy hiểm / lạc đề (sau các luật regex, regex vẫn là rào chính)
  - kit.py approve:   cảnh báo dòng Acceptance khó kiểm chứng bằng có/không

Bật: JEV_ENABLED=1 trong runner/config.env (hoặc `install.py <repo> --with-jev`) và đặt khoá TYPESAFE_API_KEY
(biến môi trường, hoặc dòng trong runner/config.env). Tài liệu API: https://docs.typesafe.ai/api.md

Lưu ý riêng tư: bật nghĩa là lệnh shell và nội dung task/Acceptance được gửi tới dịch vụ TypeSafe.
Chỉ dùng thư viện chuẩn Python 3.8+. Mọi lỗi mạng/API trả None (người gọi quyết định cho qua hay chặn).
"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTS = {
    "JEV_ENABLED": "0",        # 1 = bật
    "JEV_GUARD": "1",          # (khi bật) 1 = hook guard_bash hỏi Jev về mỗi lệnh shell
    "JEV_MODEL": "jev-latest",
    "JEV_BASE_URL": "https://api.typesafe.ai",
    "JEV_TIMEOUT_S": "5",
    "JEV_BLOCK_AT": "0.85",    # xác suất "nguy hiểm"/"lạc đề" từ ngưỡng này trở lên thì chặn lệnh
    "JEV_ACCEPT_MIN": "0.5",   # xác suất "kiểm chứng được" thấp hơn ngưỡng này thì cảnh báo Acceptance
    "JEV_ON_ERROR": "allow",   # Jev lỗi/chậm: allow = cho qua (chỉ còn regex), block = chặn
}
last_error = ""


def _config_file() -> dict:
    out = {}
    f = ROOT / "runner" / "config.env"
    try:
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def setting(name: str) -> str:
    """Biến môi trường > runner/config.env > mặc định. (kit.py đưa cấu hình vào môi trường của agent,
    nên hook chạy trong worktree — không có config.env — vẫn thấy.)"""
    if os.environ.get(name):
        return os.environ[name]
    return _config_file().get(name) or DEFAULTS.get(name, "")


def api_key() -> str:
    return os.environ.get("TYPESAFE_API_KEY") or _config_file().get("TYPESAFE_API_KEY") \
        or os.environ.get("JEV_API_KEY") or ""


def key_source() -> str:
    if os.environ.get("TYPESAFE_API_KEY"):
        return "biến môi trường TYPESAFE_API_KEY"
    if _config_file().get("TYPESAFE_API_KEY"):
        return "runner/config.env"
    if os.environ.get("JEV_API_KEY"):
        return "biến môi trường JEV_API_KEY"
    return ""


def set_config(path: Path, key: str, value: str) -> None:
    """Đặt key=value trong config.env (sửa dòng có sẵn, không thì thêm cuối). Không đụng dòng khác."""
    lines = path.read_text().splitlines() if path.exists() else []
    out, done = [], False
    for l in lines:
        if l.strip().startswith(key + "="):
            out.append(f"{key}={value}")
            done = True
        else:
            out.append(l)
    if not done:
        out += ["", f"{key}={value}"]
    path.write_text("\n".join(out) + "\n")


def wired(root: Path) -> bool:
    """Hook guard_bash của project có nối Jev không (project cài từ bản cũ thì không)."""
    try:
        return "import jev" in (root / ".claude" / "hooks" / "guard_bash.py").read_text()
    except OSError:
        return False


def enabled() -> bool:
    return setting("JEV_ENABLED") == "1" and bool(api_key())


def env_for_agent() -> dict:
    """Biến môi trường cần đưa cho tiến trình agent để hook của nó dùng được Jev. Rỗng nếu tắt."""
    if not enabled():
        return {}
    env = {"JEV_ENABLED": "1", "TYPESAFE_API_KEY": api_key()}
    for k in DEFAULTS:
        if k != "JEV_ENABLED":
            env[k] = setting(k)
    return env


def ask(state, questions: dict):
    """questions: {tên: câu hỏi có/không}. Trả {tên: xác suất "có" 0..1} hoặc None nếu lỗi (xem last_error)."""
    global last_error
    last_error = ""
    body = {
        "model": setting("JEV_MODEL"),
        "state": state,
        "questions": {k: {"type": "noul", "instructions": q} for k, q in questions.items()},
    }
    req = urllib.request.Request(
        setting("JEV_BASE_URL").rstrip("/") + "/v1/systemone",
        data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key()}"})
    try:
        with urllib.request.urlopen(req, timeout=float(setting("JEV_TIMEOUT_S"))) as r:
            answers = json.loads(r.read().decode())["answers"]
        return {k: float(answers[k]["noul"]) for k in questions}
    except urllib.error.HTTPError as e:
        last_error = f"HTTP {e.code}"
    except Exception as e:  # mạng, timeout, JSON sai dạng...
        last_error = f"{type(e).__name__}: {e}"[:200]
    return None


def check_key():
    """(ok, thông báo) — dùng cho doctor. GET /v1/models, không tốn token."""
    req = urllib.request.Request(setting("JEV_BASE_URL").rstrip("/") + "/v1/models",
                                 headers={"Authorization": f"Bearer {api_key()}"})
    try:
        with urllib.request.urlopen(req, timeout=float(setting("JEV_TIMEOUT_S"))) as r:
            r.read()
        return True, "kết nối được"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}" + (" (khoá sai/hết hạn?)" if e.code in (401, 403) else "")
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"[:120]
