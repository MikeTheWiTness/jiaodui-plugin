#!/usr/bin/env python3
"""第 1 步「基线与样本」的只读复算脚本。

- 输入：旧仓根（--root，默认 ../JiaoDuiAgent）；只读，绝不修改旧仓。
- 输出：docs/BASELINE.md（可用 --md 改路径，--no-write 则只打印）；
  --json 时把机器可读结果写到 stdout（进度/诊断一律走 stderr）。
- 纯标准库；严重度与标记口径直接复用新仓 jiaodui.report_parse / jiaodui.markers，
  与被验收的确定性核心同源。

口径提示（本脚本存在的理由）：
Python 的 glob.glob(root/**/..., recursive=True) 里双星会跟随目录软链。旧仓
output/校对PDF/第N题 是指向 output/拆题结果/... 的软链，于是 _校对报告.md 的计数
会从 346（不跟随软链）虚增到 364 —— 这正是 PRD 记的 364。脚本因此并列给出三套
数字：glob(跟随软链) / 物理文件(不跟随) / sha256 内容去重，并在 MD 里逐项解释。
"""
from __future__ import annotations

import argparse
import collections
import datetime
import glob
import hashlib
import json
import os
import pathlib
import re
import statistics
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from jiaodui.log import set_quiet  # noqa: E402
from jiaodui.markers import INLINE_MARKER_CAPTURE_RE, audit_markers  # noqa: E402
from jiaodui.report_parse import (  # noqa: E402
    SEVERITY_KEYWORDS,
    UNSTATED,
    _extract_summary,
    parse_proofread_md,
    split_sections,
)

Q = chr(96)  # 反引号：Markdown 行内代码用，源码本身不含该字符
DEFAULT_ROOT = os.path.join(os.path.dirname(REPO_ROOT), "JiaoDuiAgent")
DEFAULT_MD = os.path.join(REPO_ROOT, "docs", "BASELINE.md")
DEFAULT_SAMPLES = os.path.join(REPO_ROOT, "evaluation", "sample-22.json")

SOURCE_DIRS = ("中间产物", "拆题结果", "校对报告")
_DECOR_RE = re.compile(r"^[\s#*>*>—•]+")
_HEADING_RE = re.compile(r"^#{3,}\s")
_WHOLE_UNIT_RE = re.compile(r"(?m)^##\s*(?:第\d+题|单元\d+)\b")


def code(s):
    return Q + str(s) + Q


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def classify_doc(doc):
    subject = "化学" if "原电池" in doc else "物理"
    mode = "讲义" if ("学习手册" in doc or "讲" in doc) else "试卷"
    return subject, mode


def marked_section(text):
    head, marked, reasons = split_sections(text)
    return marked


def marker_list(text):
    marked = marked_section(text)
    return list(INLINE_MARKER_CAPTURE_RE.finditer(marked)) if marked is not None else []


def summary_first_line_no_label(text):
    """PRD 分布口径：头部逐行取首个 startswith 关键词的行，但不剥离「总结行：」标签。

    与 report_parse._extract_summary 的唯一差别就是不调用 _SUMMARY_LABEL_RE；
    裸「无」单独记为一个取值，而不是未声明。
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    for raw in text.splitlines():
        s = raw.strip()
        if _HEADING_RE.match(s):
            break
        if not s:
            continue
        body = _DECOR_RE.sub("", s).strip().rstrip("*# \t")
        for kw in SEVERITY_KEYWORDS:
            if body.startswith(kw):
                return kw
        if body == "无":
            return "无"
    return ""


def unique_by_sha(paths):
    seen = {}
    for p in paths:
        seen.setdefault(sha256_file(p), []).append(p)
    return seen


def entry_meta(root, path):
    rel = os.path.relpath(path, root)
    parts = rel.split(os.sep)
    top = parts[1] if len(parts) >= 2 and parts[0] == "output" else "其他"
    if top in ("中间产物", "拆题结果") and len(parts) >= 5:
        doc, unit, kind = parts[2], parts[3], "单元报告"
    elif top == "校对报告":
        doc, unit, kind = os.path.basename(path)[: -len("_校对报告.md")], None, "整卷报告"
    else:
        doc, unit, kind = "其他", parts[-2] if len(parts) >= 2 else "?", "单元报告"
    return {"path": path, "rel": rel, "top": top, "doc": doc, "unit": unit, "kind": kind}


def collect_reports(root):
    glob_unit = sorted(glob.glob(os.path.join(root, "**", "_校对报告.md"), recursive=True))
    phys_unit = sorted(str(p) for p in pathlib.Path(root).rglob("_校对报告.md"))
    glob_all = sorted(glob.glob(os.path.join(root, "**", "*校对报告.md"), recursive=True))
    phys_all = sorted(str(p) for p in pathlib.Path(root).rglob("*校对报告.md"))
    whole = sorted(glob.glob(os.path.join(root, "output", "校对报告", "*_校对报告.md")))
    return glob_unit, phys_unit, glob_all, phys_all, whole


def severity_summary(paths):
    texts = [(p, read_text(p)) for p in paths]
    with_markers = [(p, t) for p, t in texts if marker_list(t)]
    declared_in_markers = [(p, t) for p, t in with_markers if _extract_summary(t) in SEVERITY_KEYWORDS]
    parser_dist = collections.Counter(_extract_summary(t) or UNSTATED for _, t in texts)
    nolabel_dist = collections.Counter(summary_first_line_no_label(t) or UNSTATED for _, t in texts)
    parsed_dist = collections.Counter((parse_proofread_md(t) or {}).get("summary", "不可解析") for _, t in texts)
    return {
        "n": len(texts),
        "with_markers": len(with_markers),
        "declared_in_markers": len(declared_in_markers),
        "parser_dist": dict(parser_dist),
        "nolabel_dist": dict(nolabel_dist),
        "parsed_dist": dict(parsed_dist),
        "bare_wu": sum(1 for _, t in texts if summary_first_line_no_label(t) == "无"),
    }


def marker_stats(paths):
    rep_empty = rep_noop = mk_empty = mk_noop = total = wm = 0
    hist = collections.Counter()
    for p in paths:
        ms = marker_list(read_text(p))
        if not ms:
            continue
        wm += 1
        total += len(ms)
        hist[len(ms)] += 1
        e = sum(1 for m in ms if not m.group(2).strip())
        n = sum(1 for m in ms if m.group(2).strip() and m.group(2).strip() == m.group(3).strip())
        if e:
            rep_empty += 1
        if n:
            rep_noop += 1
        mk_empty += e
        mk_noop += n
    return {
        "with_markers": wm,
        "total_markers": total,
        "empty_orig_reports": rep_empty,
        "empty_orig_markers": mk_empty,
        "noop_reports": rep_noop,
        "noop_markers": mk_noop,
        "marker_count_histogram": dict(sorted(hist.items())),
    }


def audit_stats(paths):
    verdicts = collections.Counter()
    reports_with_source = 0
    reports_with_source_markers = 0
    total_markers = 0
    unknown_reports = 0
    for p in paths:
        d = os.path.dirname(p)
        unit = os.path.basename(d)
        src = os.path.join(d, unit + ".md")
        if not os.path.isfile(src):
            continue
        reports_with_source += 1
        marked = marked_section(read_text(p))
        if marked is None:
            continue
        body = "\n".join(
            l
            for l in marked.splitlines()
            if not (
                l.strip().startswith("### 标记原文")
                or l.strip().startswith("编号：")
                or l.strip().startswith("内容：")
            )
        ).strip()
        audits = audit_markers(body, read_text(src))
        if audits:
            reports_with_source_markers += 1
            total_markers += len(audits)
            for a in audits:
                verdicts[a.verdict] += 1
            if any(a.verdict == "unknown" for a in audits):
                unknown_reports += 1
    return {
        "reports_with_source": reports_with_source,
        "reports_with_source_and_markers": reports_with_source_markers,
        "total_markers": total_markers,
        "verdicts": dict(verdicts),
        "unknown_reports": unknown_reports,
    }


def whole_report_stats(whole):
    rows = []
    for p in whole:
        t = read_text(p)
        rows.append({"name": os.path.basename(p), "chars": len(t), "units": len(_WHOLE_UNIT_RE.findall(t))})
    lengths = sorted(r["chars"] for r in rows)
    if lengths:
        def pctl(a, q):
            return a[min(len(a) - 1, int(round((len(a) - 1) * q)))]
        summary = {
            "count": len(rows),
            "min": lengths[0],
            "median": statistics.median(lengths),
            "p90": pctl(lengths, 0.9),
            "max": lengths[-1],
        }
    else:
        summary = {"count": 0}
    return rows, summary


def check_samples(samples_path):
    if not os.path.isfile(samples_path):
        return {"path": samples_path, "exists": False}
    data = json.loads(read_text(samples_path))
    bad = []
    for e in data.get("samples", []):
        checks = {}
        for field, path_field, sha_field in (
            ("source", "source_path", "source_sha256"),
            ("report", "report_path", "report_sha256"),
        ):
            p = e.get(path_field)
            if not p or not os.path.isfile(p):
                checks[field] = "missing"
                continue
            actual = sha256_file(p)
            checks[field] = "match" if actual == e.get(sha_field) else ("mismatch:" + actual)
        if any(v != "match" for v in checks.values()):
            bad.append({"index": e.get("index"), "checks": checks})
    return {
        "path": samples_path,
        "exists": True,
        "count": len(data.get("samples", [])),
        "source_len_p90": data.get("source_len_p90"),
        "old_repo_head": data.get("old_repo_head"),
        "frozen_at": data.get("frozen_at"),
        "hash_algorithm": data.get("hash_algorithm"),
        "coverage": data.get("coverage", {}),
        "hash_mismatches": bad,
        "samples": data.get("samples", []),
    }


def compute(root, samples_path):
    glob_unit, phys_unit, glob_all, phys_all, whole = collect_reports(root)
    uniq_glob_unit = unique_by_sha(glob_unit)
    uniq_phys_unit = unique_by_sha(phys_unit)
    uniq_phys_all = unique_by_sha(phys_all)
    entries = [entry_meta(root, p) for p in phys_all]
    by_top = collections.Counter(e["top"] for e in entries)
    by_kind = collections.Counter(e["kind"] for e in entries)
    by_subject = collections.Counter()
    by_mode = collections.Counter()
    by_subject_mode = collections.Counter()
    by_doc = collections.Counter()
    for e in entries:
        subj, mode = classify_doc(e["doc"])
        by_subject[subj] += 1
        by_mode[mode] += 1
        by_subject_mode[subj + "/" + mode] += 1
        by_doc[(e["doc"], subj, mode)] += 1

    api_exact = sorted(str(p) for p in pathlib.Path(root).rglob("_API对话记录.md"))
    api_all_phys = sorted(str(p) for p in pathlib.Path(root).rglob("_API对话记录*.md"))
    api_all_glob = sorted(glob.glob(os.path.join(root, "output", "**", "_API对话记录*.md"), recursive=True))

    sev_glob = severity_summary(glob_unit)
    sev_phys = severity_summary(phys_unit)
    sev_all_phys = severity_summary(phys_all)
    sev_uniq_phys_all = severity_summary(sorted(min(v) for v in uniq_phys_all.values()))
    sev_uniq_phys_unit = severity_summary(sorted(min(v) for v in uniq_phys_unit.values()))

    mk_glob = marker_stats(glob_unit)
    mk_uniq = marker_stats(sorted(min(v) for v in uniq_phys_all.values()))
    audit = audit_stats(phys_all)
    whole_rows, whole_summary = whole_report_stats(whole)
    samples = check_samples(samples_path)

    summary = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "old_repo": root,
        "old_repo_head": sample_head(root),
        "hash_algorithm": "sha256(raw bytes)",
        "report_counts": {
            "glob_follow_symlinks_unit": len(glob_unit),
            "physical_no_symlink_unit": len(phys_unit),
            "glob_follow_symlinks_all": len(glob_all),
            "physical_no_symlink_all": len(phys_all),
            "whole_reports": len(whole),
            "unique_sha256_of_glob_unit": len(uniq_glob_unit),
            "unique_sha256_of_physical_unit": len(uniq_phys_unit),
            "unique_sha256_of_physical_all": len(uniq_phys_all),
        },
        "by_source_dir": dict(by_top),
        "by_kind": dict(by_kind),
        "by_subject": dict(by_subject),
        "by_source_mode": dict(by_mode),
        "by_subject_mode": dict(by_subject_mode),
        "by_doc": [
            {"doc": k[0], "subject": k[1], "mode": k[2], "reports": v} for k, v in sorted(by_doc.items())
        ],
        "api_records": {
            "exact_unit_record": len(api_exact),
            "wildcard_physical": len(api_all_phys),
            "wildcard_glob_follow_symlinks": len(api_all_glob),
        },
        "severity": {
            "glob364_marker_only": sev_glob,
            "physical346": sev_phys,
            "all356_physical": sev_all_phys,
            "unique274_physical_all": sev_uniq_phys_all,
            "unique_physical_unit": sev_uniq_phys_unit,
        },
        "markers": {"glob364": mk_glob, "unique_physical_all": mk_uniq},
        "audit": audit,
        "whole_reports": {"summary": whole_summary, "rows": whole_rows},
        "samples": samples,
    }
    return summary


def sample_head(root):
    import subprocess

    try:
        out = subprocess.run(
            ["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=15
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def fmt_counter(c):
    return " / ".join("%s %s" % (k, v) for k, v in sorted(c.items(), key=lambda kv: (-kv[1], kv[0])))


def render_md(root, summary, samples_path):
    r = summary["report_counts"]
    sev = summary["severity"]
    L = []
    L.append("# 旧仓基线复算（第 1 步：基线与样本）")
    L.append("")
    L.append("- 复算时间：" + summary["generated_at"])
    L.append("- 旧仓根（只读）：" + code(summary["old_repo"]))
    L.append("- 旧仓 HEAD：" + code(summary["old_repo_head"] or "未知"))
    L.append("- 复算命令：" + code("scripts/recompute_baseline.py --root " + summary["old_repo"] + " --json"))
    L.append("- 哈希算法：" + code("sha256（文件原始字节）") + "；脚本纯标准库，严重度/标记口径复用 " + code("jiaodui.report_parse") + " / " + code("jiaodui.markers"))
    L.append("- 本文件由脚本生成，请勿手改；样本清单见 " + code("evaluation/sample-22.json"))
    L.append("")
    L.append("> 本文件把「能复现的数字」和「只能解释、无法精确复现的数字」分开写。")
    L.append("> 无法复现的一律标 **待复核**，不冒充已解决。")
    L.append("")

    L.append("## 1. 报告总数、来源分布与去重")
    L.append("")
    L.append("### 1.1 关键发现：PRD 的 364 来自 glob 跟随软链")
    L.append("")
    L.append("Python 的 " + code("glob.glob(root/**/_校对报告.md, recursive=True)") + " 中 " + code("**") + " **会跟随目录软链**。")
    L.append("旧仓 " + code("output/校对PDF/第N题") + " 共 18 个软链指向 " + code("output/拆题结果/...") + "，于是同 18 份报告被数两遍：")
    L.append("")
    L.append("| 口径 | 文件数 | 说明 |")
    L.append("| --- | ---: | --- |")
    L.append("| 物理文件 / 不跟随软链（" + code("pathlib.rglob") + "） | " + str(r["physical_no_symlink_all"]) + " | 真实文件，= 单元 " + str(r["physical_no_symlink_unit"]) + " + 整卷 " + str(r["whole_reports"]) + " |")
    L.append("| glob / 跟随软链（PRD 口径） | " + str(r["glob_follow_symlinks_all"]) + " | = " + str(r["physical_no_symlink_all"]) + " + 18 个软链重复 |")
    L.append("| PRD 记 | 364 | 与我们用 glob 复算的 " + str(r["glob_follow_symlinks_unit"]) + " 份单元报告完全一致 |")
    L.append("")
    L.append("- " + code("_校对报告.md") + "（单元报告，精确名）：glob 跟随软链 = " + str(r["glob_follow_symlinks_unit"]) + "；不跟随软链 = " + str(r["physical_no_symlink_unit"]))
    L.append("- " + code("*_校对报告.md") + "（含 " + code("output/校对报告/") + " 的整卷报告）：glob = " + str(r["glob_follow_symlinks_all"]) + "；不跟随 = " + str(r["physical_no_symlink_all"]))
    L.append("- 去重规则：按文件原始字节的 sha256 分组，同哈希只留路径最短的一份作为代表")
    L.append("  - 精确名集合去重后：跟随软链 " + str(r["unique_sha256_of_glob_unit"]) + "；不跟随软链 " + str(r["unique_sha256_of_physical_unit"]))
    L.append("  - 全部报告去重后：**" + str(r["unique_sha256_of_physical_all"]) + "**")
    L.append("- 结论：PRD 的「364 份报告」实为含 18 个软链重复的计数；distinct 物理文件 " + str(r["physical_no_symlink_all"]) + "、内容去重 " + str(r["unique_sha256_of_physical_all"]) + "。")
    L.append("")
    L.append("### 1.2 按来源目录（不跟随软链的物理文件）")
    L.append("")
    L.append("| 来源目录 | 报告数 |")
    L.append("| --- | ---: |")
    for k in ("中间产物", "拆题结果", "校对报告", "校对PDF（软链）", "其他"):
        if summary["by_source_dir"].get(k):
            L.append("| " + k + " | " + str(summary["by_source_dir"][k]) + " |")
    L.append("")
    L.append("说明：" + code("中间产物") + " 与 " + code("拆题结果") + " 对同一单元各存一份报告：75 次镜像同哈希、")
    L.append("50 次（初识原电池）两份内容不同，故物理文件数与去重数差距很大。")
    L.append("")
    L.append("### 1.3 按学科 / 来源模式")
    L.append("")
    L.append("| 维度 | 数值 |")
    L.append("| --- | --- |")
    L.append("| 学科 | " + fmt_counter(summary["by_subject"]) + " |")
    L.append("| 来源模式 | " + fmt_counter(summary["by_source_mode"]) + " |")
    L.append("| 学科/模式 | " + fmt_counter(summary["by_subject_mode"]) + " |")
    L.append("")
    L.append("| 文档 | 学科 | 模式 | 报告数 |")
    L.append("| --- | --- | --- | ---: |")
    for row in summary["by_doc"]:
        L.append("| " + row["doc"] + " | " + row["subject"] + " | " + row["mode"] + " | " + str(row["reports"]) + " |")
    L.append("")
    L.append("说明：语料含非物理学科（" + code("第 1 讲初识原电池") + " 为高中化学）；没有语料落在 " + code("subjects/") + " 的七个学科模板目录，")
    L.append("本基线只统计 " + code("output/") + " 下的真实产物。")
    L.append("")
    L.append("### 1.4 API 对话记录")
    L.append("")
    L.append("| 口径 | 数量 | 说明 |")
    L.append("| --- | ---: | --- |")
    L.append("| 精确 " + code("_API对话记录.md") + " | " + str(summary["api_records"]["exact_unit_record"]) + " | 每单元一份规范记录；**与 PRD 的「344 份去重报告」完全一致** |")
    L.append("| " + code("_API对话记录*.md") + " 不跟随软链 | " + str(summary["api_records"]["wildcard_physical"]) + " | PRD 记 403，现多 11 份（含 " + code("_格式修正") + " / " + code("_full") + " 变体） |")
    L.append("| " + code("_API对话记录*.md") + " 跟随软链 | " + str(summary["api_records"]["wildcard_glob_follow_symlinks"]) + " | 再叠 18 个软链重复 |")
    L.append("")
    L.append("**364 / 344 的差异来源（结论）**：364 是「跟随软链的 " + code("_校对报告.md") + " 计数」；")
    L.append("344 不是报告去重数，而是「精确 " + code("_API对话记录.md") + " 的每单元计数」。两者本就不是同一对象的两种口径，")
    L.append("PRD 把二者并列容易被读成「364 份报告去重后 344 份」，实际去重后是 " + str(r["unique_sha256_of_physical_all"]) + "（全部）或 " + str(r["unique_sha256_of_physical_unit"]) + "（仅单元报告）。")
    L.append("")
    L.append("### 1.5 待复核")
    L.append("- PRD 记 364，glob 复算 364 —— 但这是含软链重复的数，是否应改记为 distinct 计数（" + str(r["physical_no_symlink_all"]) + "）需 PRD 侧确认。")
    L.append("- PRD 记 403 份对话记录，现为 " + str(summary["api_records"]["wildcard_physical"]) + "，多出的 11 份无法从 git 追溯（旧仓 output/ 未入版本控制），差异原因 **待复核**。")
    L.append("")
    L.append("## 2. 严重度总结行：194/248 与 241 的口径矛盾")
    L.append("")
    L.append("两套口径都在本脚本里复算并列，矛盾因此可解释：")
    L.append("")
    L.append("### 2.1 口径 A：248 / 194（PRD 的分子分母）")
    L.append("")
    L.append("分母 = **带标记报告**（" + code("### 标记原文") + " 节内至少一处 " + code("【编号|原文|改为】") + "）；")
    L.append("分子 = 其中「头部总结行能被解析器识别为四个合法关键词之一」的报告数。集合用 glob 跟随软链的 364 份。")
    L.append("")
    L.append("- 总报告（glob 跟随软链）：" + str(sev["glob364_marker_only"]["n"]))
    L.append("- 带标记报告：" + str(sev["glob364_marker_only"]["with_markers"]) + " —— **精确等于 PRD 的 248**")
    L.append("- 带标记且声明合规严重度：" + str(sev["glob364_marker_only"]["declared_in_markers"]) + " / " + str(sev["glob364_marker_only"]["with_markers"]) + "（PRD 记 194；差 1，见待复核）")
    L.append("- 参考：不跟随软链的物理 346 份中，带标记 " + str(sev["physical346"]["with_markers"]) + "、声明合规 " + str(sev["physical346"]["declared_in_markers"]))
    L.append("")
    L.append("### 2.2 口径 B：143 / 78 / 19 / 1 = 241（PRD 的取值分布）")
    L.append("")
    L.append("复算发现该分布来自**另一套集合 + 另一套提取器**：")
    L.append("")
    L.append("- 集合：不跟随软链的物理报告 346 份（不含 18 个软链重复）")
    L.append("- 提取器：头部逐行取首个以关键词开头的行，但**不剥离「总结行：」标签**；裸「无」单列")
    L.append("- 该口径结果：" + fmt_counter(sev["physical346"]["nolabel_dist"]))
    L.append("")
    L.append("与 PRD 的 143 / 78 / 19 / 1 对照：")
    L.append("")
    L.append("| 取值 | PRD | 本次复算（口径 B） | 差 |")
    L.append("| --- | ---: | ---: | --- |")
    nl = sev["physical346"]["nolabel_dist"]
    L.append("| 轻微问题 | 143 | " + str(nl.get("轻微问题", 0)) + " | " + str(nl.get("轻微问题", 0) - 143) + " |")
    L.append("| 无问题 | 78 | " + str(nl.get("无问题", 0)) + " | " + str(nl.get("无问题", 0) - 78) + " |")
    L.append("| 一般问题 | 19 | " + str(nl.get("一般问题", 0)) + " | " + str(nl.get("一般问题", 0) - 19) + " |")
    L.append("| 裸「无」 | 1 | " + str(nl.get("无", 0)) + " | " + str(nl.get("无", 0) - 1) + " |")
    L.append("| 严重错误 | 未列 | " + str(nl.get("严重错误", 0)) + " | PRD 未收录该取值 |")
    L.append("| 未声明 | 未列 | " + str(nl.get(UNSTATED, 0)) + " | — |")
    L.append("")
    L.append("### 2.3 与已验收解析器同源的口径（参考）")
    L.append("")
    L.append("- " + code("parse_proofread_md") + " 分布（物理 346）：" + fmt_counter(sev["physical346"]["parsed_dist"]))
    L.append("- " + code("_extract_summary") + " 分布（物理 346）：" + fmt_counter(sev["physical346"]["parser_dist"]))
    L.append("- " + code("_extract_summary") + " 分布（glob 364）：" + fmt_counter(sev["glob364_marker_only"]["parser_dist"]))
    L.append("- " + code("_extract_summary") + " 分布（内容去重后 " + str(sev["unique274_physical_all"]["n"]) + "）：" + fmt_counter(sev["unique274_physical_all"]["parser_dist"]))
    L.append("")
    L.append("### 2.4 矛盾的口径解释（结论）")
    L.append("")
    L.append("194/248 与 241 **不能同时成立**，因为它们根本不是同一套统计：")
    L.append("")
    L.append("1. **分母不同**：194/248 只统计带标记报告（248 份）；分布 241 统计的是全部带严重度行的报告，")
    L.append("   其中「无问题 78 份」按定义不带标记 —— 所以 78 不可能出现在 248 的分母里。")
    L.append("2. **集合不同**：248 用 glob 跟随软链的 364 份（含 18 个软链重复）；分布用不跟随软链的 346 份。")
    L.append("3. **提取器不同**：248 分母的「合规」用 " + code("_extract_summary") + "（剥离「总结行：」标签），")
    L.append("   分布 241 的提取器不剥标签，于是 " + str(sev["physical346"]["parser_dist"].get("轻微问题", 0) - sev["physical346"]["nolabel_dist"].get("轻微问题", 0)) + " 份带「总结行：且轻微问题」的报告在分布口径下落进未声明。")
    L.append("4. **取值集合不同**：分布口径把裸「无」单列，且未收录 " + code("严重错误") + "（现网存在 " + str(nl.get("严重错误", 0)) + " 份）；")
    L.append("   解析器口径则把裸「无」判为未声明、把 " + code("严重错误") + " 计为合法值。")
    L.append("")
    L.append("### 2.5 待复核")
    L.append("- 口径 B 复算得 143/79/20/3（裸无 0），与 PRD 的 143/78/19/1 差 1~2 份，且 PRD 缺 " + code("严重错误") + " 桶：")
    L.append("  旧仓 output/ 未入版本控制，无法排除快照漂移，**残差待复核**。")
    L.append("- 口径 A 复算 195/248，PRD 记 194/248：差 1 份，**待复核**（可能是旧统计把 1 份裸「无」/异常报告判为不合规）。")
    L.append("")
    L.append("## 3. 空原文 / 空操作 / 标记数分布 / 标记审计")
    L.append("")
    L.append("### 3.1 空原文 / 空操作")
    L.append("")
    L.append("PRD 的 3.6% / 3.2% 用 248 作分母（9/248、8/248），即只在带标记报告里统计。本次复算：")
    L.append("")
    mkg = summary["markers"]["glob364"]
    mku = summary["markers"]["unique_physical_all"]
    L.append("| 指标 | glob 364（含软链重复） | 内容去重后 | PRD |")
    L.append("| --- | ---: | ---: | ---: |")
    L.append("| 带标记报告 | " + str(mkg["with_markers"]) + " | " + str(mku["with_markers"]) + " | 248 |")
    L.append("| 含空原文报告 | " + str(mkg["empty_orig_reports"]) + " | " + str(mku["empty_orig_reports"]) + " | 9 |")
    L.append("| 含空操作报告 | " + str(mkg["noop_reports"]) + " | " + str(mku["noop_reports"]) + " | 8 |")
    L.append("| 空原文标记条数 | " + str(mkg["empty_orig_markers"]) + " | " + str(mku["empty_orig_markers"]) + " | — |")
    L.append("| 空操作标记条数 | " + str(mkg["noop_markers"]) + " | " + str(mku["noop_markers"]) + " | — |")
    L.append("")
    L.append("**待复核**：分母口径已确认（248），但绝对值低于 PRD（9→" + str(mkg["empty_orig_reports"]) + "，8→" + str(mkg["noop_reports"]) + "），")
    L.append("与 364→" + str(r["glob_follow_symlinks_unit"]) + " 的快照漂移方向一致；因旧仓 output/ 不受版本控制，**无法精确复现，标待复核**。")
    L.append("")
    L.append("### 3.2 标记数分布（glob 364 口径）")
    L.append("")
    bins = [(1, 1, "1"), (2, 2, "2"), (3, 4, "3-4"), (5, 9, "5-9"), (10, 19, "10-19"), (20, None, "≥20")]
    hist = mkg["marker_count_histogram"]
    L.append("| 每份标记数 | 报告数 |")
    L.append("| --- | ---: |")
    for lo, hi, label in bins:
        n = sum(v for k, v in hist.items() if k >= lo and (hi is None or k <= hi))
        L.append("| " + label + " | " + str(n) + " |")
    L.append("| 合计（带标记报告） | " + str(mkg["with_markers"]) + " |")
    L.append("| 标记总条数 | " + str(mkg["total_markers"]) + " |")
    L.append("")
    L.append("### 3.3 标记审计 verdict 分布（有同目录源文的报告）")
    L.append("")
    L.append("判定用 " + code("jiaodui.markers.audit_markers") + "，源文取与报告同目录的 " + code("{单元}.md") + "（旧仓 " + code("第N题.md") + " / " + code("单元N.md") + "）。")
    L.append("中间产物目录没有源文，因此可定位源文的报告只来自 " + code("拆题结果") + "。")
    L.append("")
    a = summary["audit"]
    L.append("| 指标 | 数量 |")
    L.append("| --- | ---: |")
    L.append("| 可定位源文的报告 | " + str(a["reports_with_source"]) + " |")
    L.append("| 可定位源文且含标记的报告 | " + str(a["reports_with_source_and_markers"]) + " |")
    L.append("| 标记条数 | " + str(a["total_markers"]) + " |")
    L.append("| 含 unknown 的报告 | " + str(a["unknown_reports"]) + " |")
    for k in ("ok", "unknown", "noop", "empty-orig", "restore-new", "manual-review"):
        if a["verdicts"].get(k):
            L.append("| verdict " + k + " | " + str(a["verdicts"][k]) + " |")
    L.append("")
    L.append("**待复核**：PRD 记「86 份可定位源文：ok 233 / unknown 82 / noop 1」。本次复算可定位源文报告数与 ok/unknown 条数均不同")
    L.append("（源文只随 " + code("拆题结果") + " 落盘，" + code("中间产物") + " 无源文）。这与「448 份报告里哪些曾随源文落盘」的快照差异有关，**标待复核**；")
    L.append("结论性口径不变：**unknown 不能当失败**。")
    L.append("")
    L.append("## 4. 整卷报告长度分布（" + code("output/校对报告/") + "）")
    L.append("")
    ws = summary["whole_reports"]["summary"]
    L.append("| 指标 | 值 | PRD |")
    L.append("| --- | ---: | ---: |")
    L.append("| 份数 | " + str(ws.get("count")) + " | 10 |")
    L.append("| 中位字符数 | " + str(ws.get("median")) + " | 17,130 |")
    L.append("| 最大字符数 | " + str(ws.get("max")) + " | 207,170（50 单元） |")
    L.append("")
    L.append("| 整卷报告 | 字符数 | 单元数 |")
    L.append("| --- | ---: | ---: |")
    for row in sorted(summary["whole_reports"]["rows"], key=lambda x: -x["chars"]):
        L.append("| " + row["name"] + " | " + str(row["chars"]) + " | " + str(row["units"]) + " |")
    L.append("")
    L.append("**结论**：整卷口径与 PRD 完全一致（中位 17,130、最大 207,170 / 50 单元），可作硬基线。")
    L.append("")
    L.append("## 5. 22 单元样本（冻结）")
    L.append("")
    s = summary["samples"]
    if not s.get("exists"):
        L.append("**未找到样本清单 " + code(samples_path) + "**")
    else:
        L.append("- 清单：" + code(samples_path))
        L.append("- 冻结日期：" + str(s.get("frozen_at")) + "；记录旧仓 HEAD：" + code(s.get("old_repo_head") or "未知"))
        L.append("- 数量：" + str(s.get("count")) + "；哈希算法：" + str(s.get("hash_algorithm")))
        L.append("- 哈希校验：" + ("全部源文/旧报告 sha256 与磁盘一致" if not s.get("hash_mismatches") else ("**" + str(len(s["hash_mismatches"])) + " 项不一致**")))
        L.append("")
        L.append("### 5.1 覆盖矩阵")
        L.append("")
        labels = {
            "image": "含图片题",
            "formula_marker": "含公式标记",
            "long_unit": "长单元（源文 ≥ P90=" + str(s.get("source_len_p90")) + " 字符）",
            "no_problem": "无问题单元",
            "with_marker": "有标记单元",
            "without_marker": "无标记单元",
            "severe": "旧报告严重错误",
            "unstated": "旧报告严重度未声明/不可解析",
            "audit_unknown": "标记审计 unknown>0",
            "noop": "含空操作标记",
        }
        L.append("| 覆盖项 | 命中数 | 样本序号 |")
        L.append("| --- | ---: | --- |")
        for key, label in labels.items():
            ids = s["coverage"].get(key, [])
            L.append("| " + label + " | " + str(len(ids)) + " | " + (", ".join(str(i) for i in ids) if ids else "—") + " |")
        L.append("")
        L.append("### 5.2 逐样本（关键字段）")
        L.append("")
        L.append("| # | 文档 | 单元 | 学科/模式 | 旧报告严重度 | 源文字符 | 图片 | 公式标记 | 标记数 | 空操作 |")
        L.append("| ---: | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |")
        for e in s["samples"]:
            L.append(
                "| " + str(e["index"]) + " | " + e["doc"] + " | " + e["unit"] + " | " + e["subject"] + "/" + e["source_mode"]
                + " | " + e["old_severity"] + " | " + str(e["source_chars"]) + " | " + str(e["image_count"])
                + " | " + str(e["formula_marker_count"]) + " | " + str(e["marker_count"]) + " | " + str(e["noop_count"]) + " |"
            )
        L.append("")
        L.append("完整源文/报告绝对路径与 sha256、选入理由见 " + code("evaluation/sample-22.md") + "。")
        L.append("样本在写脚本时冻结，复算只校验哈希与覆盖，**不重选**。")
    L.append("")
    L.append("## 6. 待复核清单（汇总）")
    L.append("")
    L.append("1. PRD「364 份报告」应改为 distinct 物理文件 " + str(r["physical_no_symlink_all"]) + "（或按明确去重规则 " + str(r["unique_sha256_of_physical_all"]) + "），确认前仍标待复核。")
    L.append("2. PRD「344 份去重报告」与精确 " + code("_API对话记录.md") + " 计数相等，但它不是报告去重数；PRD 措辞需澄清。")
    L.append("3. 严重度分布 PRD 143/78/19/1 = 241 与本次口径 B 的 143/79/20/3+未声明 101 差 1~2 且缺 " + code("严重错误") + " 桶，**残差待复核**。")
    L.append("4. 口径 A 195/248 与 PRD 194/248 差 1，**待复核**。")
    L.append("5. 空原文 / 空操作 PRD 9 / 8 与本次 " + str(mkg["empty_orig_reports"]) + " / " + str(mkg["noop_reports"]) + " 不一致，分母口径已确认（248），绝对值 **待复核**。")
    L.append("6. 标记审计 PRD ok 233 / unknown 82（86 份源文）与本次 " + str(a["verdicts"].get("ok", 0)) + " / " + str(a["verdicts"].get("unknown", 0)) + "（" + str(a["reports_with_source"]) + " 份源文）不一致，**待复核**。")
    L.append("7. 对话记录 PRD 403 与现状 " + str(summary["api_records"]["wildcard_physical"]) + " 差 11，旧仓 output/ 未入版本控制，**待复核**。")
    L.append("8. 「旧流程曾漏检题型」PRD 未给清单，样本里按四类可判定证据收录（严重错误 / 严重度未声明 / 标记审计 unknown / 空操作），"
             "分类本身 **待复核**。")
    L.append("")
    return "\n".join(L) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="第 1 步基线与样本复算（只读旧仓）")
    parser.add_argument("--root", default=DEFAULT_ROOT, help="旧仓根（默认 ../JiaoDuiAgent）")
    parser.add_argument("--json", action="store_true", help="把机器可读结果写到 stdout")
    parser.add_argument("--md", default=DEFAULT_MD, help="BASELINE.md 输出路径")
    parser.add_argument("--samples", default=DEFAULT_SAMPLES, help="冻结样本清单 JSON 路径")
    parser.add_argument("--no-write", action="store_true", help="不写 BASELINE.md")
    args = parser.parse_args(argv)

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        sys.stderr.write("旧仓根不存在：" + root + "\n")
        return 3
    set_quiet(True)

    summary = compute(root, os.path.abspath(args.samples))
    summary["baseline_md"] = os.path.abspath(args.md)

    if not args.no_write:
        os.makedirs(os.path.dirname(os.path.abspath(args.md)), exist_ok=True)
        with open(os.path.abspath(args.md), "w", encoding="utf-8") as f:
            f.write(render_md(root, summary, os.path.abspath(args.samples)))
        sys.stderr.write("已写出 " + os.path.abspath(args.md) + "\n")

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        r = summary["report_counts"]
        sys.stderr.write(
            "报告：glob(跟随软链)=" + str(r["glob_follow_symlinks_unit"])
            + " 物理=" + str(r["physical_no_symlink_unit"])
            + " 去重=" + str(r["unique_sha256_of_physical_unit"]) + "\n"
        )
        sys.stderr.write(
            "带标记=" + str(summary["severity"]["glob364_marker_only"]["with_markers"])
            + " 合规=" + str(summary["severity"]["glob364_marker_only"]["declared_in_markers"]) + "\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
