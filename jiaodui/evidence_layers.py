"""v3 分层证据与 schema v2 报告证据之间的纯函数转换。"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


class EvidenceError(Exception):
    """证据转换失败，供交互层返回稳定错误码与诊断详情。"""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


_EVIDENCE_KEYS = ("assumptions", "symbols", "images", "calculations")
_LOCAL_KINDS = {"assumption": "assumptions", "calculation": "calculations", "image": "images"}


def _error(code: str, message: str, **details: Any) -> EvidenceError:
    return EvidenceError(code, message, details)


def _active(correction: dict[str, Any]) -> bool:
    return correction.get("status", "effective") not in {"retracted", "superseded"}


def _evidence_shape(evidence: Any) -> dict[str, Any]:
    if not isinstance(evidence, dict) or set(evidence) != set(_EVIDENCE_KEYS):
        raise _error("proposal.evidence", "unit_evidence 必须包含 assumptions、symbols、images、calculations 四键")
    result = deepcopy(evidence)
    for key in _EVIDENCE_KEYS:
        value = result[key]
        if key in {"images", "calculations"} and isinstance(value, dict):
            if (set(value) != {"status", "reason"} or value.get("status") != "not_applicable"
                    or not isinstance(value.get("reason"), str) or not value["reason"].strip()):
                raise _error(f"proposal.evidence-{key}", f"{key} 的 not_applicable 形态无效")
        elif not isinstance(value, list):
            raise _error(f"proposal.evidence-{key}", f"{key} 必须为数组或有效 not_applicable 对象")
    for key in ("assumptions", "images", "calculations"):
        if not isinstance(result[key], list):
            continue
        for entry in result[key]:
            if (not isinstance(entry, dict) or not isinstance(entry.get("id"), str)
                    or not entry["id"]):
                raise _error(f"proposal.evidence-{key}", f"{key} 每项须含非空字符串 id")
            if "inherited_ref" in entry and (not isinstance(entry["inherited_ref"], str) or not entry["inherited_ref"]):
                raise _error("proposal.evidence", "inherited_ref 必须为非空修订 ID")
    if not result["assumptions"]:
        raise _error("proposal.evidence-assumptions", "必须记录至少一条单元级假设/核验依据")
    if not isinstance(result["symbols"], list):
        raise _error("proposal.evidence-symbols", "symbols 必须为数组")
    return result


def _manifest_map(manifest: dict[str, Any] | None) -> dict[int, dict[str, Any]] | None:
    if manifest is None:
        return None
    if not isinstance(manifest, dict) or not isinstance(manifest.get("references", []), list):
        raise _error("proposal.evidence-images", "图片清单必须包含 references 数组")
    by_index: dict[int, dict[str, Any]] = {}
    for reference in manifest.get("references", []):
        if not isinstance(reference, dict):
            raise _error("proposal.evidence-images", "图片清单项必须为对象")
        index = reference.get("reference_index")
        if type(index) is not int or index < 1 or index in by_index:
            raise _error("proposal.evidence-images", "图片清单 reference_index 必须唯一且为正整数")
        by_index[index] = reference
    return by_index


def _fill_images(images: Any, manifest: dict[str, Any] | None, *, require_coverage: bool = True) -> Any:
    if not isinstance(images, list):
        if manifest is not None and manifest:
            raise _error("proposal.evidence-images", "源文含图片引用时，单元级 images 必须逐项覆盖")
        return images
    seen: set[int] = set()
    filled = []
    for item in images:
        if not isinstance(item, dict):
            raise _error("proposal.evidence-images", "图片证据项必须为对象")
        entry = deepcopy(item)
        if (not isinstance(entry.get("id"), str) or not entry["id"]
                or entry.get("readable") is not True
                or not isinstance(entry.get("semantic"), str)
                or not isinstance(entry.get("verdict"), str)):
            raise _error("proposal.evidence-images", "图片证据须含 id、semantic、verdict 且 readable 必须为 true")
        index = entry.get("reference_index")
        if type(index) is not int or index < 1 or index in seen:
            raise _error("proposal.evidence-images", "图片证据 reference_index 必须唯一且为正整数")
        seen.add(index)
        if manifest is not None:
            reference = manifest.get(index)
            if reference is None:
                raise _error("proposal.evidence-images", f"图片证据引用了清单外索引 {index}")
            for field in ("original_path", "actual_read_path", "position"):
                if field not in reference:
                    raise _error("proposal.evidence-images", f"图片清单缺少 {field}")
                entry[field] = deepcopy(reference[field])
        filled.append(entry)
    if require_coverage and manifest is not None and seen != set(manifest):
        raise _error("proposal.evidence-images", "图片证据必须覆盖图片清单中的全部引用",
                     missing=sorted(set(manifest) - seen), extra=sorted(seen - set(manifest)))
    return filled


def _iter_ids(evidence: dict[str, Any]):
    for key in ("assumptions", "images", "calculations"):
        for entry in evidence[key] if isinstance(evidence[key], list) else []:
            if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                yield entry["id"]


def _check_unique_ids(evidence: dict[str, Any], corrections: list[dict[str, Any]]) -> set[str]:
    seen: set[str] = set()
    for correction in corrections:
        identity = correction.get("id")
        if not isinstance(identity, str) or not identity:
            raise _error("revise.correction-id", "修订必须含非空 id")
        if identity in seen:
            raise _error("revise.correction-id-duplicate", f"修订 ID 重复：{identity}", id=identity)
        seen.add(identity)
    evidence_ids: set[str] = set()
    for identity in _iter_ids(evidence):
        if identity in seen or identity in evidence_ids:
            raise _error("revise.evidence-id-duplicate", f"证据 ID 重复：{identity}", id=identity)
        evidence_ids.add(identity)
    return evidence_ids


def prune_inherited_evidence(evidence: dict[str, Any], inactive_ids: set[str],
                             active_references: set[str]) -> None:
    """修剪「所属修订已失效且无有效引用」的继承假设/计算。

    原地修改并保留 inherited_ref，供提交路径与 merge_layers 共用。
    """
    for key in ("assumptions", "calculations"):
        entries = evidence.get(key)
        if isinstance(entries, list):
            evidence[key] = [entry for entry in entries if not (
                isinstance(entry, dict)
                and entry.get("inherited_ref") in inactive_ids
                and entry.get("id") not in active_references)]


def merge_layers(unit_evidence: dict[str, Any], effective_corrections: list[dict[str, Any]], *,
                 image_manifest: dict[str, Any] | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """修剪继承项、合并有效修订局部证据并编译 v2 evidence。

    调用方可传入带 status 的修订历史；撤回/替代项仅参与继承修剪。
    图片清单由调用方提供；传入时先单独校验单元图片覆盖，再回填三项定位字段。
    同图局部观察按原序带 ID 折叠入规范图片的 semantic/verdict，引用映射到规范 ID。
    本函数不修改输入；完整提案的身份、定位及 calc 调用绑定仍由提交闸门复核。
    """
    evidence = _evidence_shape(unit_evidence)
    if not isinstance(effective_corrections, list) or any(not isinstance(c, dict) for c in effective_corrections):
        raise _error("revise.corrections", "corrections 必须为对象数组")
    for correction in effective_corrections:
        if not isinstance(correction.get("id"), str) or not correction["id"]:
            raise _error("revise.correction-id", "修订必须含非空 id")
        if correction.get("status", "effective") not in ("effective", "retracted", "superseded"):
            raise _error("revise.corrections", "修订状态无效")
        local = correction.get("evidence", [])
        if not isinstance(local, list):
            raise _error("proposal.evidence", "修订局部 evidence 必须为数组")
        for item in local:
            if not isinstance(item, dict) or not isinstance(item.get("kind"), str) or item["kind"] not in _LOCAL_KINDS:
                raise _error("proposal.evidence", "修订局部证据 kind 无效")
    manifest = _manifest_map(image_manifest)
    evidence["images"] = _fill_images(evidence["images"], manifest)
    corrections = deepcopy(effective_corrections)
    active = [c for c in corrections if _active(c)]
    for correction in corrections:
        refs = correction.get("evidence_ids", [])
        if not isinstance(refs, list) or any(not isinstance(identity, str) for identity in refs):
            raise _error("proposal.evidence-reference", "evidence_ids 必须为字符串数组")
    active_references = {identity for c in active for identity in c.get("evidence_ids", [])}
    inactive_ids = {c["id"] for c in corrections if not _active(c)}
    prune_inherited_evidence(evidence, inactive_ids, active_references)
    if not evidence["assumptions"]:
        raise _error("revise.evidence-required", "修剪后缺少单元级假设/核验依据，请补充单元依据")

    ids = _check_unique_ids(evidence, corrections)
    used_ids = set(ids) | {correction["id"] for correction in corrections}
    compiled = {key: deepcopy(evidence[key]) for key in _EVIDENCE_KEYS}
    for key in ("assumptions", "calculations"):
        if isinstance(compiled[key], list):
            for entry in compiled[key]:
                if isinstance(entry, dict):
                    entry.pop("inherited_ref", None)
    local_images: dict[int, list[dict[str, Any]]] = {}
    local_kinds = {item.get("kind") for correction in active
                   for item in correction.get("evidence", []) if isinstance(item, dict)}
    if "image" in local_kinds and isinstance(compiled["images"], dict):
        compiled["images"] = []
    if "calculation" in local_kinds and isinstance(compiled["calculations"], dict):
        compiled["calculations"] = []
    by_kind = {"assumption": compiled["assumptions"], "calculation": compiled["calculations"]}
    image_by_index = {item["reference_index"]: item for item in compiled["images"]
                      if isinstance(compiled["images"], list)}
    local_id_to_canonical: dict[str, str] = {}
    output_corrections = []
    for correction in active:
        refs = correction.get("evidence_ids", [])
        if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
            raise _error("proposal.evidence-reference", "evidence_ids 必须为字符串数组")
        unresolved_unit = sorted(set(refs) - set(_iter_ids(evidence)))
        if unresolved_unit:
            raise _error("proposal.evidence-reference", "evidence_ids 只能指向单元级证据", unresolved=unresolved_unit)
        all_refs = list(refs)
        local = correction.get("evidence", [])
        if not isinstance(local, list):
            raise _error("proposal.evidence", "修订局部 evidence 必须为数组")
        for item in local:
            if not isinstance(item, dict) or item.get("kind") not in _LOCAL_KINDS:
                raise _error("proposal.evidence", "修订局部证据 kind 必须为 assumption、calculation 或 image")
            entry = {k: deepcopy(v) for k, v in item.items() if k != "kind"}
            if not isinstance(entry.get("id"), str) or not entry["id"]:
                raise _error("revise.evidence-id", "修订局部证据必须含非空 id")
            if entry["id"] in used_ids:
                raise _error("revise.evidence-id-duplicate", f"证据 ID 重复：{entry['id']}", id=entry["id"])
            used_ids.add(entry["id"])
            ids.add(entry["id"])
            if item["kind"] == "image":
                allowed = {"id", "reference_index", "readable", "semantic", "verdict",
                           "original_path", "actual_read_path", "position"}
                if set(entry) - allowed or entry.get("readable") is not True:
                    raise _error("proposal.evidence-images", "局部图片只接受有效语义字段且 readable 必须为 true")
                if manifest is None:
                    raise _error("proposal.evidence-images", "局部图片需要当前图片清单以回填路径和位置")
                entry = _fill_images([entry], manifest, require_coverage=False)[0]
                index = entry["reference_index"]
                canonical = image_by_index.get(index)
                if canonical is None:
                    raise _error("proposal.evidence-images", f"局部图片引用索引 {index} 没有单元级规范图片证据")
                local_images.setdefault(index, []).append(entry)
                local_id_to_canonical[entry["id"]] = canonical["id"]
                all_refs.append(canonical["id"])
            else:
                by_kind[item["kind"]].append(entry)
                all_refs.append(entry["id"])
        if not all_refs:
            raise _error("proposal.evidence-reference", f"修订 {correction.get('id')} 至少需要一个证据引用")
        all_refs = [local_id_to_canonical.get(ref, ref) for ref in all_refs]
        unresolved = sorted(set(all_refs) - ids)
        if unresolved:
            raise _error("proposal.evidence-reference", "修订引用了不存在的证据 ID", unresolved=unresolved)
        output = {k: deepcopy(v) for k, v in correction.items()
                  if k not in {"evidence", "status", "inherited_ref"}}
        output["evidence_ids"] = list(dict.fromkeys(all_refs))
        output_corrections.append(output)
    for index, observations in local_images.items():
        canonical = image_by_index[index]
        for field in ("semantic", "verdict"):
            original = canonical[field]
            additions = [f"局部证据[{item['id']}]：{item[field]}" for item in observations]
            canonical[field] = "\n".join([f"单元观察：{original}", *additions])
    from .report_suggestions import SuggestionError, _validate_first_pass_evidence, _validate_image_evidence

    try:
        _validate_first_pass_evidence(compiled)
        if image_manifest is not None:
            _validate_image_evidence(compiled["images"], image_manifest)
    except SuggestionError as error:
        raise EvidenceError(error.code, str(error), {"stage": "v2-validation"}) from error
    return compiled, output_corrections


def split_v2(proposal_v2: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """将 v2 evidence 整体放入单元层，并标记单修订引用的可修剪证据。"""
    if not isinstance(proposal_v2, dict):
        raise _error("proposal.evidence", "v2 提案必须为对象")
    evidence = _evidence_shape(proposal_v2.get("evidence"))
    corrections = deepcopy(proposal_v2.get("corrections"))
    if not isinstance(corrections, list) or any(not isinstance(c, dict) for c in corrections):
        raise _error("proposal.corrections", "v2 corrections 必须为对象数组")
    ids = _check_unique_ids(evidence, corrections)
    usage: dict[str, set[str]] = {identity: set() for identity in ids}
    for correction in corrections:
        refs = correction.get("evidence_ids")
        if not isinstance(refs, list) or not refs or any(not isinstance(identity, str) for identity in refs):
            raise _error("proposal.evidence-reference", "v2 evidence_ids 必须为非空字符串数组")
        for identity in refs:
            if identity not in ids:
                raise _error("proposal.evidence-reference", f"未知证据 ID：{identity}", id=identity)
            usage[identity].add(correction["id"])
    for key in ("assumptions", "calculations"):
        if isinstance(evidence[key], list):
            for entry in evidence[key]:
                if isinstance(entry, dict) and len(usage.get(entry.get("id"), [])) == 1:
                    entry["inherited_ref"] = next(iter(usage[entry["id"]]))
    return evidence, corrections
