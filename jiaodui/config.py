"""学科配置的读取、Schema 校验与正则编译（单一源）。

移植自旧仓 core/config_schema.py + core/config_loader.py（HEAD 1c45243），按新契约
改写：

- 不再读 `.env`，不再要求 `agent_prompt.json`（那是旧 LLM 链路）；新仓的人读
  学科规范改放 `references/subjects/<学科>.md`，由 agent 侧阅读，Python 侧不碰。
- 机器读配置统一放 `config/subjects/<学科>.json`，只承载确定性拆分需要的参数：
  工具集白名单、支持扩展名、拆分参数。
- 兼容旧仓的嵌套写法（`lecture_split` / `exam_split`），便于从旧配置平滑迁移；
  顶层扁平键优先。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .errors import ContractError
from .log import log

# 默认 section_pattern（ADR-0017 决策1）：匹配 ##/### 标题 + 例题标记 + 通用知识标题
DEFAULT_SECTION_PATTERN = (
    r"^#{2,3}\s"                       # ## / ### 标题
    r"|^\*\*(例|练|变式|真题)\d+\*\*"    # **例1**、**练1**、**变式1**、**真题1**
    r"|^\*\*教师版\*\*"                 # **教师版**
    r"|必备知识"                         # 通用知识标题
    r"|模型大招"                         # 方法/模型总结标题
    r"|重难点突破"                        # 重难点专题标题
)

# 旧哨兵：历史上 `lecture_section_pattern == r"^##\s"` 表示「未显式配置」。
# 新配置里空串表示同一含义；此处保留哨兵以兼容历史配置。
SECTION_PATTERN_SENTINEL = r"^##\s"

DEFAULT_EXAM_QUESTION_PATTERN = r"^(\d+)．"

# 导航/封面板块的默认标题匹配模式（移植自 shared/split_post_utils.py）
DEFAULT_NAV_PATTERNS = [r"直击课堂", r"本讲导航"]

# 新仓机器读配置目录（相对仓库根）
DEFAULT_SUBJECTS_DIR = Path("config") / "subjects"

_MISSING = object()


def subject_config_path(subject: str, config_root: str | Path | None = None) -> Path:
    """把学科名解析为 `config/subjects/<学科>.json` 路径。

    若 `config_root` 省略，则相对当前工作目录的 `config/subjects`；调用方也可
    传入仓库根或任意配置目录。
    """
    root = Path(config_root) if config_root is not None else DEFAULT_SUBJECTS_DIR
    name = subject if subject.endswith(".json") else f"{subject}.json"
    return root / name


def _field_error(source: str | None, field: str | None, detail: str) -> ContractError:
    """构造含文件路径与字段名的契约错误。"""
    where = f"（{source}）" if source else ""
    label = f"字段 '{field}'" if field else "配置"
    return ContractError(
        f"学科配置校验失败{where}：{label} {detail}",
        location=source,
        details={"field": field} if field else {},
    )


def _path_get(raw: dict, path: tuple[str, ...]):
    cur: object = raw
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return _MISSING
        cur = cur[key]
    return cur


def _pick(raw: dict, keys: tuple[str, ...], nested: tuple[str, ...] | None = None):
    """按「顶层键优先、再嵌套键」的顺序取第一个非 None 值。"""
    for key in keys:
        value = raw.get(key)
        if value is not None:
            return value
    if nested:
        value = _path_get(raw, nested)
        if value is not _MISSING and value is not None:
            return value
    return _MISSING


def _str_list(raw: dict, field: str, keys: tuple[str, ...],
              nested: tuple[str, ...] | None, source: str | None) -> list[str]:
    value = _pick(raw, keys, nested)
    if value is _MISSING:
        return []
    if not isinstance(value, list):
        raise _field_error(source, field, "必须是字符串数组")
    for i, item in enumerate(value):
        if not isinstance(item, str):
            raise _field_error(source, field, f"第 {i + 1} 个元素必须是字符串")
    return list(value)


def _str(raw: dict, field: str, keys: tuple[str, ...],
         nested: tuple[str, ...] | None, source: str | None, default: str) -> str:
    value = _pick(raw, keys, nested)
    if value is _MISSING:
        return default
    if not isinstance(value, str):
        raise _field_error(source, field, "必须是字符串")
    return value


def _normalize(raw: dict, source: str | None = None) -> dict:
    """内部实现：校验并标准化，`source` 为配置文件路径（用于错误定位）。"""
    if not isinstance(raw, dict):
        raise _field_error(source, None, "必须是 JSON 对象")

    tools = _str_list(raw, "tools", ("tools", "tool_whitelist"), None, source)
    extensions = _str_list(raw, "extensions",
                           ("extensions", "supported_extensions", "file_extensions"),
                           None, source)
    split_mode = _str(raw, "split_mode", ("split_mode",),
                      ("lecture_split", "split_mode"), source, "section")
    section_pattern = _str(raw, "section_pattern", ("section_pattern",),
                           ("lecture_split", "section_pattern"), source, "")
    section_extensions = _str_list(
        raw, "section_extensions",
        ("section_extensions", "section_pattern_extensions"),
        ("lecture_split", "section_pattern_extensions"), source)
    wrapped_patterns = _str_list(raw, "wrapped_patterns", ("wrapped_patterns",),
                                 ("lecture_split", "wrapped_patterns"), source)
    unwrapped_patterns = _str_list(raw, "unwrapped_patterns", ("unwrapped_patterns",),
                                   ("lecture_split", "unwrapped_patterns"), source)
    exam_question_pattern = _str(
        raw, "exam_question_pattern", ("exam_question_pattern",),
        ("exam_split", "question_pattern"), source, DEFAULT_EXAM_QUESTION_PATTERN)
    nav_patterns = _str_list(raw, "nav_patterns", ("nav_patterns",),
                             ("lecture_split", "nav_patterns"), source)
    if not nav_patterns:
        nav_patterns = list(DEFAULT_NAV_PATTERNS)
    subject = _str(raw, "subject", ("subject", "name"), None, source, "")

    return {
        "tools": tools,
        "extensions": extensions,
        "split_mode": split_mode,
        "section_pattern": section_pattern,
        "section_extensions": section_extensions,
        "wrapped_patterns": wrapped_patterns,
        "unwrapped_patterns": unwrapped_patterns,
        "exam_question_pattern": exam_question_pattern,
        "nav_patterns": nav_patterns,
        "subject": subject,
    }


def normalize_subject_config(raw: dict) -> dict:
    """校验并标准化学科配置，填充默认值。

    Returns:
        dict，键固定为：tools、extensions、split_mode、section_pattern、
        section_extensions、wrapped_patterns、unwrapped_patterns、
        exam_question_pattern、nav_patterns、subject。

    Raises:
        ContractError: 字段类型非法，消息含字段名。
    """
    return _normalize(raw, None)


def load_subject_config(path: str | Path) -> dict:
    """读取并校验 `config/subjects/<学科>.json`。

    Args:
        path: 配置文件路径；传目录时读取其下 `config.json`（历史兼容）。

    Returns:
        标准化后的配置 dict。

    Raises:
        ContractError: 文件不存在、JSON 解析失败或字段非法；
            消息必含文件路径与出错字段。
    """
    p = Path(path)
    if p.is_dir():
        p = p / "config.json"
    if not p.is_file():
        raise ContractError(
            f"学科配置不存在（{p}）：请检查 config/subjects/<学科>.json",
            location=str(p),
            details={"field": "path"},
        )
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContractError(
            f"学科配置读取失败（{p}）：{exc}", location=str(p),
            details={"field": "path"},
        ) from exc
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ContractError(
            f"学科配置解析失败（{p}）：{exc}", location=str(p),
            details={"field": "json"},
        ) from exc
    return _normalize(raw, str(p))


def get_lecture_split_mode(config: dict | None) -> str:
    """讲义拆分模式：section（默认）/ title（旧学科兼容）。"""
    return (config or {}).get("split_mode") or "section"


def get_section_pattern(config: dict | None) -> re.Pattern:
    """构建 section_pattern：基础 pattern + 学科扩展。

    显式配置了非空 section_pattern 时直接编译；否则用 DEFAULT_SECTION_PATTERN
    追加 section_extensions（扩展字符串按字面转义）。非法正则回退默认 pattern，
    与旧仓行为一致（不因单科配置写错而中断整卷拆分）。
    """
    raw = (config or {}).get("section_pattern") or ""
    if isinstance(raw, str) and raw and raw != SECTION_PATTERN_SENTINEL:
        try:
            return re.compile(raw)
        except re.error:
            log(f"   ⚠️ 无效的 section_pattern，回退默认：{raw!r}")
            return re.compile(DEFAULT_SECTION_PATTERN)

    pattern = DEFAULT_SECTION_PATTERN
    for ext in (config or {}).get("section_extensions") or []:
        pattern += "|" + re.escape(ext)
    try:
        return re.compile(pattern)
    except re.error:
        return re.compile(DEFAULT_SECTION_PATTERN)


def get_exam_question_pattern(config: dict | None) -> re.Pattern:
    r"""试卷题目起始行正则（默认 `^(\d+)．`）。"""
    raw = (config or {}).get("exam_question_pattern") or DEFAULT_EXAM_QUESTION_PATTERN
    try:
        return re.compile(raw)
    except re.error:
        log(f"   ⚠️ 无效的 exam_question_pattern，回退默认：{raw!r}")
        return re.compile(DEFAULT_EXAM_QUESTION_PATTERN)


def get_lecture_patterns(config: dict | None) -> tuple[list[re.Pattern], list[re.Pattern]]:
    """编译 (wrapped, unwrapped) 标题模式；非法正则跳过并告警。"""
    wrapped: list[re.Pattern] = []
    for pat in (config or {}).get("wrapped_patterns") or []:
        try:
            wrapped.append(re.compile(r'^\*\*' + pat + r'\*\*.*$'))
        except re.error:
            log(f"   ⚠️ 无效正则 (wrapped): {pat!r}")
    unwrapped: list[re.Pattern] = []
    for pat in (config or {}).get("unwrapped_patterns") or []:
        try:
            unwrapped.append(re.compile(pat))
        except re.error:
            log(f"   ⚠️ 无效正则 (unwrapped): {pat!r}")
    return wrapped, unwrapped


def get_compiled_title_patterns(config: dict | None) -> list[re.Pattern]:
    """wrapped + unwrapped 标题模式合集（title 模式拆分用）。"""
    wrapped, unwrapped = get_lecture_patterns(config)
    return wrapped + unwrapped


def get_nav_patterns(config: dict | None) -> list[str]:
    """导航/封面板块的标题匹配模式列表（默认直击课堂/本讲导航）。"""
    patterns = (config or {}).get("nav_patterns")
    if not patterns:
        return list(DEFAULT_NAV_PATTERNS)
    return list(patterns)
