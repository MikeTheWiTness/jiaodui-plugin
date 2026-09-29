"""一次性：把 22 单元评估样本冻结为高中物理（M1/M2 只用物理流程跑）。

用法：
    .venv/bin/python scripts/freeze_sample22.py            # 预览，不写盘
    .venv/bin/python scripts/freeze_sample22.py --apply    # 写入 evaluation/sample-22.json / .md

规则（PRD §8 / D29）：
- 先从「有同目录源文 {unit}.md」的真实旧产物中取物理单元（排除化学《初识原电池》）；
- 保留已有样本中的物理成员，再按类别贪心补足到 22，覆盖：含图片、含公式、长单元（≥P90）、
  无问题、有/无标记、旧报告严重错误、严重度未声明、标记审计 unknown、空操作；
- 冻结后不再重选；复算脚本只校验哈希与覆盖。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OLD_ROOT = Path("/Users/chouchou/开发/JiaoDuiAgent")
sys.path.insert(0, str(REPO_ROOT))

from jiaodui.markers import INLINE_MARKER_CAPTURE_RE, audit_markers  # noqa: E402
from jiaodui.report_parse import (marker_numbers, parse_proofread_md,  # noqa: E402
                                  split_sections, strip_reference_preamble)

SPLIT_ROOT = OLD_ROOT / "output" / "拆题结果"
MID_ROOT = OLD_ROOT / "output" / "中间产物"
SAMPLES_JSON = REPO_ROOT / "evaluation" / "sample-22.json"
SAMPLES_MD = REPO_ROOT / "evaluation" / "sample-22.md"
HASH = "sha256"
TARGET = 22
IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _mode(doc: str) -> str:
    return "讲义" if ("讲" in doc or "手册" in doc) else "试卷"


def _is_physics(doc: str) -> bool:
    return "原电池" not in doc


def compute_unit(doc: str, unit_dir: Path, index: int) -> dict | None:
    unit = unit_dir.name
    src = unit_dir / f"{unit}.md"
    rep = unit_dir / "_校对报告.md"
    if not src.is_file() or not rep.is_file():
        return None
    source_text = src.read_text(encoding="utf-8")
    report_text = rep.read_text(encoding="utf-8")
    _head, marked, _reasons = split_sections(report_text)
    marked = strip_reference_preamble(marked) if marked is not None else ""
    nums = marker_numbers(marked or "")
    formula_marker_count = 0
    for m in INLINE_MARKER_CAPTURE_RE.finditer(marked or ""):
        if "$" in m.group(2) or "$" in m.group(3):
            formula_marker_count += 1
    audits = audit_markers(marked or "", source_text) if marked else []
    verdicts = Counter(a.verdict for a in audits)
    parsed = parse_proofread_md(report_text)
    if parsed is None:
        old_severity = "<unparseable>"
    else:
        old_severity = parsed["summary"]
    raw_sev = parse_proofread_md(report_text)
    images = IMG_RE.findall(source_text)
    mirrors = []
    for root in (MID_ROOT, SPLIT_ROOT):
        cand = root / doc / unit / "_校对报告.md"
        if cand.is_file():
            mirrors.append(str(cand))
    return {
        "index": index,
        "doc": doc,
        "unit": unit,
        "subject": "物理",
        "source_mode": _mode(doc),
        "source_path": str(src),
        "source_sha256": sha256_file(src),
        "source_chars": len(source_text),
        "unit_dir": str(unit_dir),
        "report_path": str(rep),
        "report_sha256": sha256_file(rep),
        "report_len_chars": len(report_text),
        "report_mirrors": mirrors,
        "has_image": bool(images),
        "image_count": len(images),
        "has_formula": ("$" in source_text) or bool(formula_marker_count),
        "formula_marker_count": formula_marker_count,
        "marker_count": len(nums),
        "empty_orig_count": verdicts.get("empty-orig", 0),
        "noop_count": verdicts.get("noop", 0),
        "old_severity": old_severity,
        "old_raw_severity": (raw_sev or {}).get("summary", ""),
        "old_audit_verdicts": dict(verdicts),
        "_classes": set(),
    }


def classify(e: dict, p90: int) -> set[str]:
    c = set()
    if e["has_image"]:
        c.add("image")
    if e["formula_marker_count"] > 0:
        c.add("formula_marker")
    if e["source_chars"] >= p90:
        c.add("long_unit")
    if e["old_severity"] == "无问题":
        c.add("no_problem")
    if e["marker_count"] > 0:
        c.add("with_marker")
    else:
        c.add("without_marker")
    if e["old_severity"] == "严重错误":
        c.add("severe")
    if e["old_severity"] in ("未声明", "<unparseable>"):
        c.add("unstated")
    if e["old_audit_verdicts"].get("unknown", 0) > 0:
        c.add("audit_unknown")
    if e["noop_count"] > 0:
        c.add("noop")
    return c


def enumerate_candidates() -> list[dict]:
    out = []
    for doc_dir in sorted(SPLIT_ROOT.iterdir()):
        if not doc_dir.is_dir() or not _is_physics(doc_dir.name):
            continue
        for unit_dir in sorted(doc_dir.iterdir()):
            if not unit_dir.is_dir() or not (unit_dir.name.startswith("第") or unit_dir.name.startswith("单元")):
                continue
            e = compute_unit(doc_dir.name, unit_dir, 0)
            if e:
                out.append(e)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    old = json.loads(SAMPLES_JSON.read_text(encoding="utf-8")) if SAMPLES_JSON.is_file() else {"samples": []}
    kept = [e for e in old.get("samples", []) if e.get("subject") == "物理"]
    kept_paths = {e["source_path"] for e in kept}

    allc = enumerate_candidates()
    lens = sorted(e["source_chars"] for e in allc)
    p90 = lens[int(len(lens) * 0.9)] if lens else 0
    for e in allc:
        e["_classes"] = classify(e, p90)
    for e in kept:
        e["_classes"] = classify(e, p90)

    need = TARGET - len(kept)
    pool = [e for e in allc if e["source_path"] not in kept_paths]
    covered = set().union(*[classify(k, p90) for k in kept]) if kept else set()
    chosen = list(kept)
    for _ in range(max(0, need)):
        pool.sort(key=lambda e: (-len(e["_classes"] - covered), -e["source_chars"], e["doc"], e["unit"]))
        pick = pool.pop(0)
        chosen.append(pick)
        covered |= pick["_classes"]

    chosen.sort(key=lambda e: (e["doc"], e["unit"]))
    for i, e in enumerate(chosen, 1):
        e["index"] = i
        e["selection_reasons"] = _reasons_for(e, p90)

    coverage: dict[str, list[int]] = {k: [] for k in
        ["image", "formula_marker", "long_unit", "no_problem", "with_marker",
         "without_marker", "severe", "unstated", "audit_unknown", "noop"]}
    for e in chosen:
        for k in e["_classes"]:
            coverage[k].append(e["index"])
    for e in chosen:
        e.pop("_classes", None)

    data = {
        "version": 1,
        "frozen_at": "2026-09-29",
        "old_repo": str(OLD_ROOT),
        "old_repo_head": _head(),
        "new_repo": str(REPO_ROOT),
        "hash_algorithm": HASH,
        "source_len_p90": p90,
        "count": len(chosen),
        "selection_rule": "仅高中物理；从有同目录源文 {unit}.md 的真实旧产物中按类别贪心选取，覆盖图片/公式/长单元/无问题/严重错误/未声明/audit unknown/空操作。序在写脚本时冻结。",
        "note": "M1/M2 只用高中物理流程；样本冻结后不重选，复算只校验哈希与覆盖。",
        "coverage": coverage,
        "samples": chosen,
    }
    print("physics-only samples:", len(chosen), "p90:", p90, "coverage:", {k: len(v) for k, v in coverage.items()})
    if not args.apply:
        print("(预览，未写盘；加 --apply 写入)")
        return 0
    SAMPLES_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    SAMPLES_MD.write_text(_render_md(data), encoding="utf-8")
    print("written:", SAMPLES_JSON, SAMPLES_MD)
    return 0


def _reasons_for(e: dict, p90: int) -> list[str]:
    r = []
    if e["has_image"]:
        r.append(f"含图片题（{e['image_count']} 张）")
    if e["formula_marker_count"]:
        r.append(f"含公式标记（{e['formula_marker_count']}）")
    if e["source_chars"] >= p90:
        r.append(f"长单元（源文 {e['source_chars']} ≥ P90）")
    if e["old_severity"] == "无问题":
        r.append("无问题单元")
    if e["old_severity"] in ("未声明", "<unparseable>"):
        r.append(f"旧报告严重度{e['old_severity']}")
    if e["old_severity"] == "严重错误":
        r.append("旧报告严重错误")
    if e["old_audit_verdicts"].get("unknown", 0):
        r.append("标记审计 unknown")
    if e["noop_count"]:
        r.append("含空操作标记")
    if e["marker_count"] == 0:
        r.append("无标记")
    return r


def _head() -> str:
    import subprocess
    try:
        return subprocess.run(["git", "-C", str(OLD_ROOT), "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
    except OSError:
        return ""


def _render_md(d: dict) -> str:
    L = ["# 22 单元评估样本（冻结）", "",
         f"- 冻结日期：{d['frozen_at']}",
         f"- 旧仓：`{d['old_repo']}` @ `{d['old_repo_head'][:12]}`",
         f"- 清单：`evaluation/sample-22.json`（本文件是人读版）",
         f"- 源文长度 P90：{d['source_len_p90']} 字符", f"- 哈希算法：{d['hash_algorithm']}",
         f"- **学科：仅高中物理（22 份）**", "",
         "> **冻结声明**：样本在编写 `scripts/freeze_sample22.py` 时确定并冻结；索引与成员不再变动。",
         "> 新版结果只能与本清单对照，不得因新版表现更换样本（PRD §8 / D29）。", "",
         "## 选入规则", "", d["selection_rule"], "", "## 覆盖矩阵", "",
         "| 覆盖项 | 命中数 | 样本序号 |", "| --- | ---: | --- |"]
    labels = {"image": "含图片题", "formula_marker": "含公式标记",
              "long_unit": f"长单元（源文 ≥ P90={d['source_len_p90']}）", "no_problem": "无问题单元",
              "with_marker": "有标记单元", "without_marker": "无标记单元", "severe": "旧报告严重错误",
              "unstated": "旧报告严重度未声明/不可解析", "audit_unknown": "标记审计 unknown>0",
              "noop": "含空操作标记"}
    for k, lab in labels.items():
        ids = d["coverage"].get(k, [])
        L.append(f"| {lab} | {len(ids)} | " + (", ".join(map(str, ids)) if ids else "—") + " |")
    L += ["", "学科：物理 22 / 其他 0；来源模式：" +
          " / ".join(f"{m} {sum(1 for e in d['samples'] if e['source_mode']==m)}" for m in ("试卷", "讲义")),
          "", "## 逐样本清单", "",
          "| # | 文档 | 单元 | 学科/模式 | 旧报告严重度 | 源文字符 | 图片 | 公式标记 | 标记数 | 空原文 | 空操作 |",
          "| ---: | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for e in d["samples"]:
        L.append(f"| {e['index']} | {e['doc']} | {e['unit']} | {e['subject']}/{e['source_mode']} "
                 f"| {e['old_severity']} | {e['source_chars']} | {e['image_count']} "
                 f"| {e['formula_marker_count']} | {e['marker_count']} | {e['empty_orig_count']} | {e['noop_count']} |")
    L += ["", "完整源文/报告绝对路径与 sha256、选入理由见 `evaluation/sample-22.json`。", ""]
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
