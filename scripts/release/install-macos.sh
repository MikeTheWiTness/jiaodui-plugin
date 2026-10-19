#!/usr/bin/env bash
set -euo pipefail

RELEASE_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${JIAODUI_PYTHON:-$(command -v python3.12 || true)}"
if [[ -z "$PYTHON_BIN" ]]; then
  printf '%s\n' '未找到独立 Python 3.12。请先安装 python.org、Homebrew 或 pyenv 的 Python 3.12。' >&2
  exit 3
fi
case "$PYTHON_BIN" in
  *"/.dsh/dsh-runtimes/"*)
    printf '%s\n' '拒绝使用 DSH 签名 Python；请通过 JIAODUI_PYTHON 指定独立 CPython 3.12。' >&2
    exit 3
    ;;
esac
"$PYTHON_BIN" -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)' || {
  printf '要求独立 CPython 3.12，当前解释器为：%s\n' "$PYTHON_BIN" >&2
  exit 3
}

WHEELS=("$RELEASE_ROOT"/jiaodui-*-py3-none-any.whl)
if [[ ${#WHEELS[@]} -ne 1 || ! -f "${WHEELS[0]}" ]]; then
  printf '%s\n' '发布目录必须且只能包含一个 jiaodui-*-py3-none-any.whl。' >&2
  exit 6
fi
WHEEL_NAME="$(basename -- "${WHEELS[0]}")"
VERSION="${WHEEL_NAME#jiaodui-}"
VERSION="${VERSION%-py3-none-any.whl}"
BUNDLE_VERSION="$("$PYTHON_BIN" -c 'import json,pathlib,sys; print(json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))["version"])' "$RELEASE_ROOT/dsh-jiaodui/package.json")"
if [[ "$VERSION" != "$BUNDLE_VERSION" ]]; then
  printf 'CLI wheel 与 DSH bundle 版本不一致：%s / %s\n' "$VERSION" "$BUNDLE_VERSION" >&2
  exit 6
fi

if ! command -v pandoc >/dev/null 2>&1 || ! pandoc --version >/dev/null 2>&1; then
  printf '%s\n' '未找到可执行的 Pandoc。请按 https://pandoc.org/installing.html 安装后重试。' >&2
  exit 3
fi
CONSTRAINTS="$RELEASE_ROOT/runtime-constraints.txt"
if [[ ! -f "$CONSTRAINTS" ]]; then
  printf '缺少运行依赖约束：%s\n' "$CONSTRAINTS" >&2
  exit 6
fi
(
  cd "$RELEASE_ROOT"
  shasum -a 256 -c SHA256SUMS
)
VENV="$HOME/Library/Application Support/JiaoDuiAgentSkill/versions/$VERSION/venv"
if [[ ! -x "$VENV/bin/python" ]]; then
  mkdir -p "$(dirname -- "$VENV")"
  "$PYTHON_BIN" -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --force-reinstall --constraint "$CONSTRAINTS" "${WHEELS[0]}[render]"
"$VENV/bin/python" -m pip check
CLI="$VENV/bin/jiaodui"
if [[ ! -x "$CLI" ]]; then
  printf '安装后未找到 CLI：%s\n' "$CLI" >&2
  exit 3
fi
if ! CHECK_ENV="$("$CLI" check-env --json)"; then
  printf '%s\n' "$CHECK_ENV" >&2
  exit 3
fi
printf '%s\n' "$CHECK_ENV"
"$VENV/bin/python" -c 'import json,sys; sys.exit(0 if json.load(sys.stdin).get("ok") else 1)' <<< "$CHECK_ENV" || {
  printf '%s\n' 'check-env 未通过；请修复必需依赖后重试。' >&2
  exit 3
}
printf '\nCLI 已安装并通过 check-env：%s\n' "$CLI"
printf '请通过 DSH 官方 install_bundle 安装：%s\n' "$RELEASE_ROOT/dsh-jiaodui"
printf '插件会按 bundle 版本自动发现该 CLI；如需覆盖，可在插件配置中设置 command。\n'
