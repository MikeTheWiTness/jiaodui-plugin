"""装饰图片清除工具（所有学科通用）。

清除 pandoc 从 Word 转换时产生的无意义装饰图标：
- 附着在板块标题行（必备知识/模型大招/图像问题等）的小图标，实测显示尺寸恒为 0.194×0.194in
- alt 为空或 "test"（Word docPr descr 残留）

阈值依据（2026-08-11 实测两个物理讲义共 313 张图）：
- 装饰图标显示尺寸全部为 0.194×0.194in
- 真实题目图最小 0.479×0.667in
- 取 0.4in 为分界：图标侧 2 倍余量、真实图侧 1.2 倍余量
- 注：同一图标被 Word 拉伸显示（如表格内 1.222×1.472in）时无法仅凭显示尺寸识别，接受漏删

移植自旧仓 shared/decor_utils.py，行为契约逐字保留。
"""
from __future__ import annotations

import re

# 装饰图片尺寸阈值（英寸）：宽高均低于此值的视为装饰图标
DECOR_MAX_W = 0.4
DECOR_MAX_H = 0.4

# 匹配空 alt 或 [test] alt 的图片，捕获其宽高尺寸
_DECOR_IMG_RE = re.compile(
    r'!\[(?:test)?\]\([^)]*\)\{width="([\d.]+)in" height="([\d.]+)in"\}'
)


def _is_decor(match: re.Match) -> str:
    """判断匹配到的图片是否为装饰图标。是则返回空串（删除），否则返回原文。"""
    try:
        w = float(match.group(1))
        h = float(match.group(2))
        if w < DECOR_MAX_W and h < DECOR_MAX_H:
            return ""
    except (ValueError, IndexError):
        pass
    return match.group(0)


def strip_decor_images(text: str) -> str:
    """清除文本中的装饰图标，返回清理后的文本。"""
    return _DECOR_IMG_RE.sub(_is_decor, text)


def strip_decor_images_from_file(md_file: str) -> bool:
    """读入文件 → 清除装饰图标 → 写回。返回是否做了修改。"""
    with open(md_file, encoding="utf-8") as f:
        content = f.read()
    new_content = _DECOR_IMG_RE.sub(_is_decor, content)
    if new_content != content:
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(new_content)
        return True
    return False
