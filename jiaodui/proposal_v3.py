"""无状态原文修订提案到既有 schema v2 的确定性编译。"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .anchor import resolve_anchor, validate_revision_input
from .evidence_layers import merge_layers, prune_inherited_evidence, split_v2
from .errors import BusinessError
from .report_suggestions import _SEVERITY_RANK, bind_current_proposal, proposal_json_schema as v2_schema
from .source_index import _location_id, resolve_location, source_digest

_REQUIRED = {"id", "old_text", "new_text", "reason", "category", "severity", "evidence_ids"}
_OPTIONAL = {"context_before", "context_after", "occurrence", "evidence"}


def proposal_json_schema() -> dict[str, Any]:
    """导出模型填写的 v3 schema；身份、定位、总结由 core 绑定。"""
    v2 = v2_schema()["properties"]
    properties = deepcopy(v2["corrections"]["items"]["properties"])
    properties.pop("location_id")
    properties.pop("expected_original")
    properties.pop("replacement")
    properties["evidence_ids"]["minItems"] = 0
    properties.update({
        "old_text": {"type": "string", "minLength": 1, "maxLength": 1000},
        "new_text": {"type": "string", "maxLength": 2000},
        "context_before": {"type": "string", "maxLength": 200},
        "context_after": {"type": "string", "maxLength": 200},
        "occurrence": {"type": "integer", "minimum": 1},
    })
    properties["reason"]["maxLength"] = 2000
    evidence = deepcopy(v2["evidence"])
    image = evidence["properties"]["images"]["oneOf"][0]["items"]
    image["required"] = [key for key in image["required"]
                         if key not in {"original_path", "actual_read_path", "position"}]
    local = []
    for kind, shape in (("assumption", evidence["properties"]["assumptions"]["items"]),
                        ("calculation", evidence["properties"]["calculations"]["oneOf"][0]["items"]),
                        ("image", image)):
        item = deepcopy(shape)
        item["required"] = [*item["required"], "kind"]
        item["properties"]["kind"] = {"type": "string", "const": kind}
        local.append(item)
    properties["evidence"] = {"type": "array", "items": {"oneOf": local}}
    return {
        "type": "object", "additionalProperties": False,
        "required": ["schema_version", "corrections", "self_check"],
        "anyOf": [{"required": ["unit_evidence"]}, {"required": ["base_proposal_revision"]}],
        "properties": {
            "schema_version": {"type": "integer", "const": 3},
            "corrections": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": sorted(_REQUIRED), "properties": properties}},
            "unit_evidence": evidence,
            "self_check": deepcopy(v2["self_check"]),
            "base_proposal_revision": {"type": "integer", "minimum": 1},
            "withdrawn": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["id", "reason"],
                "properties": {"id": {"type": "string", "minLength": 1},
                               "reason": {"type": "string", "minLength": 1}}}},
        },
    }


def _invalid(message: str, *, code: str = "proposal.schema", **details: Any) -> BusinessError:
    return BusinessError(message, code=code, details=details)


def _validate_correction(item: Any) -> None:
    if not isinstance(item, dict) or _REQUIRED - set(item) or set(item) - _REQUIRED - _OPTIONAL:
        raise _invalid("修订必须包含 id、old_text、new_text、reason、category、severity、evidence_ids；仅允许附加定位上下文和局部 evidence")
    for key in ("id", "old_text", "reason", "category", "severity"):
        if not isinstance(item[key], str) or not item[key].strip():
            raise _invalid(f"修订 {key} 必须为非空字符串")
    if not isinstance(item["new_text"], str):
        raise _invalid("new_text 必须为字符串（空字符串表示删除）")
    if item["severity"] not in _SEVERITY_RANK:
        raise _invalid("severity 必须为轻微问题、一般问题或严重错误", code="proposal.severity")
    for key in ("context_before", "context_after"):
        if key in item and not isinstance(item[key], str):
            raise _invalid(f"{key} 必须为字符串")
    if "occurrence" in item and (type(item["occurrence"]) is not int or item["occurrence"] < 1):
        raise _invalid("occurrence 必须是从 1 开始的整数", code="anchor.occurrence-out-of-range")
    if not isinstance(item["evidence_ids"], list) or any(not isinstance(ref, str) or not ref for ref in item["evidence_ids"]):
        raise _invalid("evidence_ids 必须为非空字符串组成的数组", code="proposal.evidence-reference")
    validate_revision_input(item["old_text"], item["new_text"], item["reason"], evidence=item.get("evidence"))


def _from_v2(source: str, base: dict) -> tuple[dict, list[dict]]:
    evidence, corrections = split_v2(base)
    for item in corrections:
        span = resolve_location(source, source_digest(source), item.pop("location_id"), item["expected_original"])
        item["old_text"] = item.pop("expected_original")
        item["new_text"] = item.pop("replacement")
        # 保留源文中该区间的序号，避免继承重复原文时重新选位。
        from .anchor import _overlapping_matches
        item["occurrence"] = _overlapping_matches(source, item["old_text"]).index(span["start"]) + 1
    return evidence, corrections


def compile_proposal(source: str, payload: dict, snapshot: dict, *, image_manifest: dict,
                     base_proposal: dict | None = None, base_layers: dict | None = None) -> tuple[dict, dict]:
    """返回可交给既有事务的 v2 和当前有效分层提案；本函数不读写磁盘。"""
    allowed = {"schema_version", "corrections", "unit_evidence", "self_check", "base_proposal_revision", "withdrawn"}
    required = {"schema_version", "corrections", "self_check"}
    if (not isinstance(payload, dict) or required - set(payload) or set(payload) - allowed
            or type(payload.get("schema_version")) is not int or payload["schema_version"] != 3):
        raise _invalid("v3 顶层只接受 schema_version、corrections、unit_evidence、self_check、base_proposal_revision、withdrawn")
    additions = deepcopy(payload["corrections"])
    if not isinstance(additions, list):
        raise _invalid("corrections 必须为数组")
    for item in additions:
        _validate_correction(item)
    old: list[dict] = []
    if "base_proposal_revision" in payload:
        revision = payload["base_proposal_revision"]
        if (type(revision) is not int or revision < 1 or base_proposal is None
                or revision != base_proposal.get("proposal_revision")):
            raise _invalid("基础版本已过期或不存在，请重读当前 snapshot --with-proposal", code="proposal-revision-stale")
        if base_layers is None:
            inherited_evidence, old = _from_v2(source, base_proposal)
        else:
            inherited_evidence = deepcopy(base_layers["unit_evidence"])
            old = deepcopy(base_layers["corrections"])
        evidence = deepcopy(payload.get("unit_evidence", inherited_evidence))
    else:
        if "withdrawn" in payload:
            raise _invalid("withdrawn 必须同时指定 base_proposal_revision")
        if "unit_evidence" not in payload:
            raise _invalid("完整提案必须提供 unit_evidence")
        evidence = deepcopy(payload["unit_evidence"])
    withdrawals = payload.get("withdrawn", [])
    if not isinstance(withdrawals, list):
        raise _invalid("withdrawn 必须为数组")
    old_ids = {item["id"] for item in old}
    withdrawn_ids: set[str] = set()
    for item in withdrawals:
        if (not isinstance(item, dict) or set(item) != {"id", "reason"}
                or not isinstance(item["id"], str) or not isinstance(item["reason"], str)
                or not item["reason"].strip() or item["id"] not in old_ids or item["id"] in withdrawn_ids):
            raise _invalid("withdrawn 须逐项引用不同的当前修订 ID 并提供非空 reason", code="revise.withdrawn")
        withdrawn_ids.add(item["id"])
    new_ids = [item["id"] for item in additions]
    if len(set(new_ids)) != len(new_ids) or set(new_ids) & old_ids:
        raise _invalid("新增修订 ID 必须唯一，修改旧项须撤回旧 ID 并使用新 ID", code="revise.correction-id-duplicate")
    history = [{**item, "status": "retracted"} if item["id"] in withdrawn_ids else item for item in old] + additions
    compiled_evidence, active = merge_layers(evidence, history, image_manifest=image_manifest)
    output = []
    spans = []
    for item in active:
        _validate_correction(item)
        match = resolve_anchor(source, item["old_text"], context_before=item.get("context_before", ""),
                               context_after=item.get("context_after", ""), occurrence=item.get("occurrence"))
        if match.original == item["new_text"]:
            raise _invalid("归一化定位后原文与 new_text 相同，无有效修改", code="revise.noop")
        from .convert import _PANDOC_IMAGE_RE
        if _PANDOC_IMAGE_RE.fullmatch(match.original.strip()):
            raise _invalid("当前入口不支持纯图片替换，请保留图片并报告需人工处理的原因", code="revise.image-only")
        spans.append((match.start, match.end, item["id"]))
        output.append({key: deepcopy(item[key]) for key in ("id", "reason", "category", "severity", "evidence_ids")})
        output[-1].update(location_id=_location_id(source_digest(source), match.start, match.end),
                          expected_original=match.original, replacement=item["new_text"])
    previous_end = -1
    for start, end, identity in sorted(spans):
        if start < previous_end:
            raise _invalid("有效修订区间重叠，请撤回冲突项或合并成一条建议", code="proposal.overlap", correction_id=identity)
        previous_end = end
    summary = max((item["severity"] for item in output), key=_SEVERITY_RANK.__getitem__, default="无问题")
    compiled = bind_current_proposal({"schema_version": 2, "corrections": output,
        "evidence": compiled_evidence, "summary": summary, "self_check": deepcopy(payload["self_check"])}, snapshot)
    # 只保留当前有效层；与 merge_layers 共用同一修剪谓词，但这里保留 inherited_ref
    # 供后续增量继承。条件比 merge_layers 更窄（withdrawn ⊆ inactive、
    # active_refs ⊇ active_references），重编译时会把多留的项再剪掉，不会造成 restored != base。
    active_refs = {ref for item in history if item.get("status") != "retracted" for ref in item["evidence_ids"]}
    prune_inherited_evidence(evidence, withdrawn_ids, active_refs)
    for key in ("assumptions", "calculations"):
        if isinstance(evidence.get(key), list):
            for entry in evidence[key]:
                if "inherited_ref" in entry:
                    owners = [item["id"] for item in history if item.get("status") != "retracted"
                              and entry["id"] in item["evidence_ids"]]
                    if len(owners) == 1:
                        entry["inherited_ref"] = owners[0]
                    elif len(owners) > 1:
                        entry.pop("inherited_ref")
    layers = {"schema_version": 3, "unit_evidence": evidence,
              "corrections": [deepcopy(item) for item in history if item.get("status") != "retracted"],
              "self_check": deepcopy(payload["self_check"])}
    return compiled, layers
