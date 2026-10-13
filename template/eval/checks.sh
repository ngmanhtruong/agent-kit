#!/usr/bin/env bash
# 01 — Thang điểm để AI tự chấm bài. MỘT lệnh duy nhất, exit 0 = đạt.
# Điền lệnh thật của project vào các bước dưới. Bỏ comment phần phù hợp.
# Nguyên tắc: mọi quy tắc trong docs/conventions.md mà tool bắt được → thêm vào đây.
set -uo pipefail
cd "$(dirname "$0")/.."

FAIL=0
step() {
  local name="$1"; shift
  echo "── $name"
  if "$@"; then echo "   ok"; else echo "   FAIL: $name"; FAIL=1; fi
}

# ---- Python ----
# step "lint"  ruff check .
# step "types" mypy src
# step "tests" pytest -q

# ---- Node / React ----
# step "lint"  npx eslint .
# step "types" npx tsc --noEmit
# step "tests" npm test --silent

# ---- Project-specific rules (ví dụ) ----
# step "no hardcoded keys" bash -c '! grep -rEn "(api_key|secret)\s*=\s*[\"\x27][A-Za-z0-9]{16,}" src'

if [ "$FAIL" -eq 0 ] && ! grep -qE '^\s*step ' "$0"; then
  echo "CHƯA CẤU HÌNH: eval/checks.sh chưa có bước nào. Mở file và điền lệnh lint/test."
  exit 1
fi

exit "$FAIL"
