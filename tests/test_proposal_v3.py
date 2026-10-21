"""v3 生产入口的必要正反向契约。"""
from copy import deepcopy
import json

import pytest

from jiaodui.errors import BusinessError
from jiaodui.markers import split_marked_body
from jiaodui.paths import data_path, report_path
from jiaodui.report_parse import split_sections
from jiaodui.unit_delivery import commit_unit_submission, preview_unit_submission, read_unit_snapshot
from jiaodui.verify import verify_unit
from test_unit_delivery import _prepared


def _v3(v2):
    return {
        "schema_version": 3,
        "corrections": [{"id": "c1", "old_text": "木板", "new_text": "木块",
                         "reason": "上下文对象应为木块。", "category": "term", "severity": "一般问题",
                         "evidence_ids": ["e1"], "occurrence": 3}],
        "unit_evidence": deepcopy(v2["evidence"]), "self_check": deepcopy(v2["self_check"]),
    }


def test_v3_preview_commit_and_compact_snapshot(tmp_path, monkeypatch):
    _, _, unit, data, uid, text, v2, snap = _prepared(tmp_path, monkeypatch)
    proposal = _v3(v2)
    preview = preview_unit_submission(data["task_id"], uid, proposal, snap["snapshot_sha256"])
    assert preview["marker_count"] == 1
    assert not report_path(unit).exists()
    result = commit_unit_submission(data["task_id"], uid, proposal, snap["snapshot_sha256"])
    assert result["verified"] and verify_unit(unit).ok
    saved = json.loads(data_path(unit).read_text())
    assert saved["schema_version"] == saved["proposal"]["schema_version"] == 2
    assert saved["proposal"]["summary"] == "一般问题"
    assert saved["proposal"]["corrections"][0]["expected_original"] == "木板"
    assert split_marked_body(split_sections(report_path(unit).read_text())[1], escaped=True) == text
    current = read_unit_snapshot(data["task_id"], uid, with_proposal=True)
    assert current["proposal"]["proposal_revision"] == 1
    assert current["proposal"]["corrections"] == [{"id": "c1", "old_text": "木板", "new_text": "木块",
        "reason": "上下文对象应为木块。", "category": "term", "severity": "一般问题"}]
    assert current["snapshot_sha256"] == read_unit_snapshot(data["task_id"], uid)["snapshot_sha256"]


@pytest.mark.parametrize("corrections, code", [
    ([{"old_text": "木板", "occurrence": None}], "anchor.ambiguous"),
    ([{"old_text": "不存在"}], "anchor.not-found"),
    ([{}, {"id": "c2"}], "proposal.overlap"),
])
def test_v3_anchor_errors_do_not_write(tmp_path, monkeypatch, corrections, code):
    _, root, unit, data, uid, _, v2, snap = _prepared(tmp_path, monkeypatch)
    proposal = _v3(v2)
    base = proposal["corrections"][0]
    proposal["corrections"] = [{**base, **change} for change in corrections]
    for item in proposal["corrections"]:
        if item.get("occurrence") is None:
            item.pop("occurrence", None)
    before = (root / "_校对记录.json").read_bytes()
    with pytest.raises(BusinessError) as caught:
        commit_unit_submission(data["task_id"], uid, proposal, snap["snapshot_sha256"])
    assert caught.value.code == code
    if code == "anchor.ambiguous":
        assert caught.value.details["match_count"] == 3
    assert not report_path(unit).exists() and not data_path(unit).exists()
    assert (root / "_校对记录.json").read_bytes() == before


def test_v3_incremental_withdraw_and_replace_prunes_local_evidence(tmp_path, monkeypatch):
    _, _, unit, data, uid, _, v2, snap = _prepared(tmp_path, monkeypatch)
    first = _v3(v2)
    first["unit_evidence"]["assumptions"].append({"id": "shared", "text": "全单元核验依据。", "source_locations": []})
    first["corrections"][0]["evidence"] = [{"kind": "assumption", "id": "local1",
        "text": "只支撑旧修订的依据。", "source_locations": []}]
    commit_unit_submission(data["task_id"], uid, first, snap["snapshot_sha256"])
    current = read_unit_snapshot(data["task_id"], uid)
    replacement = {**first["corrections"][0], "id": "c2", "new_text": "木质块"}
    replacement.pop("evidence")
    delta = {"schema_version": 3, "base_proposal_revision": 1,
             "withdrawn": [{"id": "c1", "reason": "重新确定术语。"}], "corrections": [replacement],
             "self_check": first["self_check"]}
    commit_unit_submission(data["task_id"], uid, delta, current["snapshot_sha256"])
    saved = json.loads(data_path(unit).read_text())["proposal"]
    assert [c["id"] for c in saved["corrections"]] == ["c2"]
    assert {e["id"] for e in saved["evidence"]["assumptions"]} == {"e1", "shared"}
    assert "只支撑旧修订" not in report_path(unit).read_text()
    now = read_unit_snapshot(data["task_id"], uid)
    before = data_path(unit).read_bytes()
    with pytest.raises(BusinessError, match="基础版本"):
        commit_unit_submission(data["task_id"], uid, delta, now["snapshot_sha256"])
    with pytest.raises(BusinessError) as caught:
        commit_unit_submission(data["task_id"], uid, delta, current["snapshot_sha256"])
    assert caught.value.code == "snapshot-stale"
    assert data_path(unit).read_bytes() == before


def test_v3_image_local_withdrawal_preserves_other_observation_and_coverage(tmp_path, monkeypatch):
    from PIL import Image
    from jiaodui import material
    from jiaodui.paths import find_source_md
    _, root, unit, data, uid, _, v2, _ = _prepared(tmp_path, monkeypatch)
    source = find_source_md(unit)
    source.write_text(source.read_text() + "\n![示意](./images/图.png)\n")
    (unit / "images").mkdir(exist_ok=True)
    Image.new("RGB", (8, 8), "white").save(unit / "images" / "图.png")
    data["unit_inputs"][unit.name] = material.unit_inputs(root, unit)
    (root / material.MANIFEST).write_text(json.dumps(data, ensure_ascii=False))
    first = _v3(v2)
    first["unit_evidence"]["images"] = [{"id": "img1", "reference_index": 1, "readable": True,
        "semantic": "单元图示对象核对。", "verdict": "单元图片可读且归属一致。"}]
    first["corrections"][0]["evidence"] = [{"kind": "image", "id": "local-image1",
        "reference_index": 1, "readable": True, "semantic": "仅属于c1的观察", "verdict": "仅属于c1的判断"}]
    second = {**deepcopy(first["corrections"][0]), "id": "c2", "occurrence": 1}
    second["evidence"][0].update(id="local-image2", semantic="仅属于c2的观察", verdict="仅属于c2的判断")
    first["corrections"].append(second)
    snap = read_unit_snapshot(data["task_id"], uid)
    commit_unit_submission(data["task_id"], uid, first, snap["snapshot_sha256"])
    delta = {"schema_version": 3, "base_proposal_revision": 1, "corrections": [],
             "withdrawn": [{"id": "c1", "reason": "撤回首项判断。"}], "self_check": first["self_check"]}
    current = read_unit_snapshot(data["task_id"], uid)
    commit_unit_submission(data["task_id"], uid, delta, current["snapshot_sha256"])
    image = json.loads(data_path(unit).read_text())["proposal"]["evidence"]["images"][0]
    assert "仅属于c1" not in image["semantic"] + image["verdict"]
    assert "仅属于c2的观察" in image["semantic"]
    assert image["semantic"].count("仅属于c2的观察") == 1
    delta.update(base_proposal_revision=2, withdrawn=[{"id": "c2", "reason": "撤回余项。"}],
                 self_check={"status": "passed", "checks": ["no_issue_review"], "unresolved": []})
    current = read_unit_snapshot(data["task_id"], uid)
    commit_unit_submission(data["task_id"], uid, delta, current["snapshot_sha256"])
    saved = json.loads(data_path(unit).read_text())["proposal"]
    assert saved["corrections"] == []
    assert saved["evidence"]["images"][0]["semantic"] == "单元图示对象核对。"
    assert verify_unit(unit).ok


def test_v3_structure_calc_and_image_only_remain_gated(tmp_path, monkeypatch):
    from jiaodui.proposal_v3 import compile_proposal
    _, _, unit, data, uid, _, v2, snap = _prepared(tmp_path, monkeypatch)
    proposal = _v3(v2)
    proposal["corrections"][0].pop("occurrence")
    proposal["corrections"][0]["old_text"] = "x"
    with pytest.raises(Exception) as caught:
        compile_proposal("公式$x$。", proposal, snap, image_manifest={"references": []})
    assert caught.value.code == "anchor.structure-cut"
    proposal["corrections"][0]["old_text"] = "![图](./images/图.png)"
    with pytest.raises(Exception) as caught:
        compile_proposal("![图](./images/图.png)", proposal, snap, image_manifest={"references": []})
    assert caught.value.code == "revise.image-only"
    proposal = _v3(v2)
    proposal["unit_evidence"]["calculations"] = [{"id": "fakecalc", "call_id": "not-recorded",
        "expression": "1+1", "result": 2}]
    with pytest.raises(BusinessError) as caught:
        commit_unit_submission(data["task_id"], uid, proposal, snap["snapshot_sha256"])
    assert caught.value.code.startswith("proposal.calc-")
    assert not report_path(unit).exists()


def test_v2_base_inherited_owner_moves_and_v2_resubmit_clears_layers(tmp_path, monkeypatch):
    _, root, unit, data, uid, _, v2, snap = _prepared(tmp_path, monkeypatch)
    v2["evidence"]["assumptions"].append({"id": "unit", "text": "全单元核验依据。", "source_locations": []})
    commit_unit_submission(data["task_id"], uid, v2, snap["snapshot_sha256"])
    addition = _v3(v2)["corrections"][0]
    addition["id"] = "c2"
    delta = {"schema_version": 3, "base_proposal_revision": 1, "corrections": [addition],
        "withdrawn": [{"id": "c1", "reason": "用新意见替换。"}], "self_check": v2["self_check"]}
    snap = read_unit_snapshot(data["task_id"], uid)
    commit_unit_submission(data["task_id"], uid, delta, snap["snapshot_sha256"])
    delta.update(base_proposal_revision=2, corrections=[], withdrawn=[{"id": "c2", "reason": "复核撤回。"}],
                 self_check={"status": "passed", "checks": ["no_issue_review"], "unresolved": []})
    snap = read_unit_snapshot(data["task_id"], uid)
    commit_unit_submission(data["task_id"], uid, delta, snap["snapshot_sha256"])
    saved = json.loads(data_path(unit).read_text())["proposal"]
    assert [item["id"] for item in saved["evidence"]["assumptions"]] == ["unit"]
    snap = read_unit_snapshot(data["task_id"], uid)
    saved.pop("proposal_revision")
    commit_unit_submission(data["task_id"], uid, saved, snap["snapshot_sha256"], bind_current=True)
    assert "submission_v3" not in json.loads(data_path(unit).read_text())


def test_v3_no_issue_requires_fresh_self_check(tmp_path, monkeypatch):
    _, _, unit, data, uid, _, v2, snap = _prepared(tmp_path, monkeypatch)
    proposal = _v3(v2)
    proposal["corrections"] = []
    proposal["self_check"]["checks"] = ["no_issue_review"]
    commit_unit_submission(data["task_id"], uid, proposal, snap["snapshot_sha256"])
    assert json.loads(data_path(unit).read_text())["proposal"]["summary"] == "无问题"
    current = read_unit_snapshot(data["task_id"], uid)
    delta = {"schema_version": 3, "base_proposal_revision": 1, "corrections": []}
    with pytest.raises(BusinessError):
        commit_unit_submission(data["task_id"], uid, delta, current["snapshot_sha256"])
