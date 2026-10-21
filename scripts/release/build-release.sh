#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
PYTHON="${PYTHON:-python3.12}"
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

"$PYTHON" -c 'import sys; assert sys.version_info >= (3, 12), "需要独立 Python 3.12+"'
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
