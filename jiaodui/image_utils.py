"""共享图片工具 —— 统一的 Markdown 图片复制逻辑。

消除 7 个 subject.py + 3 处 core/defaults.py 中的重复图片处理代码。
"""
import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from .workdir import ensure_inside, ensure_tree


def inline_image_matches(content: str):
    """返回代码跨度之外的行内图片匹配，位置对应原始正文。"""
    from .convert import _IMG_RE
    from .inspect_images import _mask_code

    masked = _mask_code(content)
    matches = []
    for scanned in _IMG_RE.finditer(masked):
        match = _IMG_RE.match(content, scanned.start())
        if match is not None:
            matches.append(match)
    return matches


def rewrite_inline_images(content: str, replace):
    """仅遍历代码跨度之外的行内图片，复用转换入口的目标路径解析。"""
    matches = inline_image_matches(content)
    if not matches:
        return content
    chunks = []
    cursor = 0
    for match in matches:
        chunks.append(content[cursor:match.start()])
        chunks.append(replace(match))
        cursor = match.end()
    chunks.append(content[cursor:])
    return "".join(chunks)


@dataclass
class ImageCopyResult:
    """图片复制结果。"""
    content: str      # 重写路径后的 Markdown 内容
    copied: int = 0   # 成功复制的图片数
    missing: int = 0  # 未找到的图片数
    conflicts: int = 0  # 同名但内容不一致，拒绝静默覆盖
    warnings: list[str] | None = None


def copy_md_images(
    md_content: str,
    src_dirs: list[Path],
    target_img_dir: Path,
    *,
    relative_img_path: str = "./images",
) -> ImageCopyResult:
    """将 Markdown 内容中引用的本地图片复制到目标目录，重写路径。

    遍历 `md_content` 中的所有 `![...](...)` 图片引用：
    - HTTP/HTTPS 图片 → 跳过，保留原引用
    - 本地图片 → 在 `src_dirs` 中依次查找，找到后复制到 `target_img_dir`，
      并将路径重写为 `{relative_img_path}/{filename}`

    Args:
        md_content: 包含图片引用的 Markdown 文本
        src_dirs: 图片源目录列表（按优先级搜索）
        target_img_dir: 目标图片目录（自动创建）
        relative_img_path: 重写后的相对路径前缀，默认 "./images"

    Returns:
        ImageCopyResult: 包含重写后的内容、复制数、丢失数
    """
    target_img_dir = ensure_tree(target_img_dir)
    if not md_content:
        return ImageCopyResult(content=md_content)

    target_img_dir.mkdir(parents=True, exist_ok=True)

    from .convert import image_destination

    copied = 0
    missing = 0
    conflicts = 0
    destination_sources: dict[Path, Path] = {}

    def _replace(m):
        nonlocal copied, missing, conflicts
        alt = m.group(1)
        src = image_destination(m.group(2)) or ""

        # 跳过 HTTP/HTTPS 图片
        if src.lower().startswith(('http://', 'https://')):
            return m.group(0)

        img_name = Path(src).name
        if not img_name:
            missing += 1
            return m.group(0)

        # 先按正文中的相对路径精确查找，再退回 basename；候选冲突时拒绝猜测。
        exact_candidates = []
        fallback_candidates = []
        for sd in src_dirs:
            try:
                root = sd.resolve()
                if src and not src.startswith(('/', '\\')):
                    candidate = (sd / src).resolve()
                    if candidate.is_relative_to(root) and candidate.is_file():
                        exact_candidates.append(candidate)
                candidate = (sd / img_name).resolve()
                if candidate.is_relative_to(root) and candidate.is_file():
                    fallback_candidates.append(candidate)
            except (OSError, PermissionError, ValueError):
                continue

        candidates = exact_candidates or fallback_candidates
        if not candidates:
            missing += 1
            return m.group(0)
        digests = {hashlib.sha256(path.read_bytes()).hexdigest() for path in candidates}
        if len(digests) > 1:
            missing += 1
            conflicts += 1
            return m.group(0)
        src_path = candidates[0]

        # 同一批次已有不同源身份占用目标名时冲突；重跑允许当前源图更新旧目标。
        dest = ensure_inside(target_img_dir / img_name)
        try:
            previous_source = destination_sources.get(dest.resolve())
            if previous_source is not None and previous_source.resolve() != src_path.resolve():
                if hashlib.sha256(previous_source.read_bytes()).hexdigest() != next(iter(digests)):
                    missing += 1
                    conflicts += 1
                    return m.group(0)
            if dest.resolve() != src_path.resolve():
                shutil.copy2(src_path, dest)
            destination_sources[dest.resolve()] = src_path
        except (OSError, PermissionError, shutil.Error):
            missing += 1
            return m.group(0)

        copied += 1
        return f"![{alt}]({relative_img_path}/{img_name})"

    new_content = rewrite_inline_images(md_content, _replace)
    return ImageCopyResult(content=new_content, copied=copied, missing=missing, conflicts=conflicts)
