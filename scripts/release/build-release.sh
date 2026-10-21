#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
# 构建解释器：显式 PYTHON 优先；否则按 python3.12 → 仓库 .venv → python3
# 选择第一个满足「>=3.12 且已安装 build」的解释器。必须解析成绝对路径：
# 脚本后面会 cd 到临时目录，相对路径会失效。
resolve_python() {
  local candidate="$1"
  if [[ "$candidate" != */* ]]; then
    candidate="$(command -v "$candidate" 2>/dev/null || true)"
  fi
  [[ -n "$candidate" ]] || return 0
  if [[ "$candidate" != /* ]]; then
    candidate="$(cd -- "$(dirname -- "$candidate")" && pwd -P)/$(basename -- "$candidate")"
  fi
  [[ -x "$candidate" ]] && printf '%s\n' "$candidate"
  return 0
}

python_can_build() {
  local candidate="$1"
  [[ -n "$candidate" && -x "$candidate" ]] || return 1
  "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' >/dev/null 2>&1 || return 1
  "$candidate" -m build --version >/dev/null 2>&1
}

EXPLICIT_PYTHON="$(printenv PYTHON || true)"
if [[ -n "$EXPLICIT_PYTHON" ]]; then
  PYTHON_BIN="$(resolve_python "$EXPLICIT_PYTHON")"
  if ! python_can_build "$PYTHON_BIN"; then
    printf '指定的 PYTHON=%s 不可用于构建：需要 Python >=3.12 且已安装 build。\n' "$EXPLICIT_PYTHON" >&2
    printf '请先执行：<该解释器> -m pip install build，或用 PYTHON=/path/to/python 重新运行。\n' >&2
    exit 3
  fi
else
  PYTHON_BIN=""
  for candidate in python3.12 "$REPOSITORY_ROOT/.venv/bin/python" python3; do
    resolved="$(resolve_python "$candidate")"
    if python_can_build "$resolved"; then
      PYTHON_BIN="$resolved"
      break
    fi
  done
  if [[ -z "$PYTHON_BIN" ]]; then
    printf '%s\n' '未找到可用于构建的 Python：已检查 python3.12、仓库 .venv/bin/python、python3。' >&2
    printf '%s\n' '需要 Python >=3.12 且已安装 build；请执行 python3.12 -m pip install build，' >&2
    printf '%s\n' '或设置 PYTHON 指向带 build 的解释器后重试。' >&2
    exit 3
  fi
fi
PYTHON="$PYTHON_BIN"

# 已落地的学科插件包：一次发布同时带全部包，目标机只装需要的那一个。
BUNDLE_PACKAGES=(dsh-jiaodui dsh-jiaodui-chemistry)
CORE_VERSION="$("$PYTHON" -c 'import pathlib,sys,tomllib; print(tomllib.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))["project"]["version"])' "$REPOSITORY_ROOT/pyproject.toml")"
for package in "${BUNDLE_PACKAGES[@]}"; do
  PACKAGE_ROOT="$REPOSITORY_ROOT/packages/$package"
  if [[ ! -f "$PACKAGE_ROOT/package.json" ]]; then
    printf '学科插件包缺失：%s\n' "$PACKAGE_ROOT" >&2
    exit 6
  fi
  BUNDLE_VERSION="$("$PYTHON" -c 'import json,pathlib,sys; print(json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))["version"])' "$PACKAGE_ROOT/package.json")"
  if [[ "$CORE_VERSION" != "$BUNDLE_VERSION" ]]; then
    printf 'Python CLI 与 DSH bundle 版本不一致：%s / %s %s\n' "$CORE_VERSION" "$package" "$BUNDLE_VERSION" >&2
    exit 6
  fi
done

VERSION="$CORE_VERSION"
RELEASE_BASE="${JIAODUI_RELEASE_DIR:-$REPOSITORY_ROOT/dist/plugin-release}"
ARCHIVE="$RELEASE_BASE/dsh-jiaodui-$VERSION.tar.gz"
CHECKSUM="$ARCHIVE.sha256"

hash_files() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$@"
  else
    shasum -a 256 "$@"
  fi
}

"$PYTHON" -m pip --version >/dev/null
command -v pandoc >/dev/null || {
  printf '%s\n' '未找到 pandoc。请先按 https://pandoc.org/installing.html 安装 Pandoc 后重试。' >&2
  exit 3
}
pandoc --version >/dev/null
command -v tar >/dev/null || {
  printf '%s\n' '未找到 tar 命令，无法生成最终压缩包。' >&2
  exit 3
}

if [[ -e "$ARCHIVE" || -e "$CHECKSUM" ]]; then
  printf '发布文件已存在，拒绝覆盖：%s\n' "$ARCHIVE" >&2
  exit 2
fi
mkdir -p "$RELEASE_BASE"
STAGING="$(mktemp -d "${TMPDIR:-/tmp}/jiaodui-release.XXXXXX")"
STAGING="$(cd -- "$STAGING" && pwd -P)"
case "$(basename -- "$STAGING")" in
  jiaodui-release.*) ;;
  *) printf '临时发布目录不符合预期，拒绝清理：%s\n' "$STAGING" >&2; exit 6 ;;
esac
trap 'rm -rf -- "$STAGING"' EXIT

"$PYTHON" -m build --wheel --outdir "$STAGING/wheelhouse" "$REPOSITORY_ROOT"
if [[ ! -s "$STAGING/wheelhouse/jiaodui-$VERSION-py3-none-any.whl" ]]; then
  printf '构建 wheel 缺失或版本错误：jiaodui-%s-py3-none-any.whl\n' "$VERSION" >&2
  exit 6
fi

RELEASE_NAME="JiaoDuiAgentSkill-$VERSION"
for package in "${BUNDLE_PACKAGES[@]}"; do
  BUNDLE_STAGE="$STAGING/$RELEASE_NAME/$package"
  mkdir -p "$BUNDLE_STAGE"
  while IFS= read -r -d '' tracked_path; do
    relative_path="${tracked_path#packages/$package/}"
    source_path="$REPOSITORY_ROOT/$tracked_path"
    destination="$BUNDLE_STAGE/$relative_path"
    if [[ ! -f "$source_path" ]]; then
      printf 'bundle 文件缺失：%s\n' "$source_path" >&2
      exit 6
    fi
    mkdir -p "$(dirname -- "$destination")"
    cp "$source_path" "$destination"
  done < <(git -C "$REPOSITORY_ROOT" ls-files -z -- "packages/$package")
done
cp "$STAGING/wheelhouse/jiaodui-$VERSION-py3-none-any.whl" "$STAGING/$RELEASE_NAME/"
cp "$SCRIPT_DIR/runtime-constraints.txt" "$STAGING/$RELEASE_NAME/"
cp "$SCRIPT_DIR/install-macos.sh" "$STAGING/$RELEASE_NAME/"
cp "$SCRIPT_DIR/install-windows.ps1" "$STAGING/$RELEASE_NAME/"
cp "$SCRIPT_DIR/README.md" "$STAGING/$RELEASE_NAME/"

(
  cd "$STAGING/$RELEASE_NAME"
  "$PYTHON" - <<'PY'
from hashlib import sha256
from pathlib import Path

manifest = Path("SHA256SUMS")
files = sorted(path for path in Path(".").rglob("*") if path.is_file() and path != manifest)
with manifest.open("w", encoding="utf-8", newline="\n") as output:
    for path in files:
        digest = sha256(path.read_bytes()).hexdigest()
        output.write(f"{digest}  {path.as_posix()}\n")
PY
)
(
  cd "$STAGING"
  tar -czf "$ARCHIVE" "$RELEASE_NAME"
)
(
  cd "$RELEASE_BASE"
  hash_files "$(basename -- "$ARCHIVE")" > "$(basename -- "$CHECKSUM")"
)
printf '发布包：%s\n校验文件：%s\n' "$ARCHIVE" "$CHECKSUM"
