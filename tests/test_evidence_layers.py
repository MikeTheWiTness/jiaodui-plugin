from __future__ import annotations

import copy

import pytest

from jiaodui.evidence_layers import EvidenceError, merge_layers, split_v2


def unit_evidence():
    return {
        "assumptions": [
            {"id": "a1", "text": "依据一", "source_locations": []},
            {"id": "a2", "text": "依据二", "source_locations": []},
        ],
        "symbols": [],
        "images": {"status": "not_applicable", "reason": "默认无图"},
        "calculations": [],
    }


def correction(identity="c1", evidence_ids=None, **extra):
    item = {
        "id": identity, "location_id": "loc1", "expected_original": "原文",
        "replacement": "改文", "reason": "理由", "category": "term",
        "severity": "一般问题", "evidence_ids": evidence_ids or ["a1"],
    }
    item.update(extra)
    return item


def test_split_merge_round_trip_backfills_image_manifest():
    original_evidence = unit_evidence()
    original_evidence["images"] = [{"id": "i1", "reference_index": 1,
                                  "readable": True, "semantic": "图示向右", "verdict": "一致"}]
    manifest = {"references": [{
        "reference_index": 1, "original_path": "source/pic.png",
        "actual_read_path": "units/u/images/pic.png",
        "position": {"line": 4, "column": 2},
    }]}
    compiled_evidence, compiled_corrections = merge_layers(
        original_evidence, [correction()], image_manifest=manifest)
    assert compiled_evidence["images"] == [{
        "id": "i1", "reference_index": 1, "original_path": "source/pic.png",
        "actual_read_path": "units/u/images/pic.png",
        "position": {"line": 4, "column": 2}, "readable": True,
        "semantic": "图示向右", "verdict": "一致",
    }]
    proposal = {"evidence": compiled_evidence, "corrections": compiled_corrections}
    layers, corrections = split_v2(proposal)
    assert layers["images"][0]["id"] == "i1"
    assert "inherited_ref" not in layers["images"][0]
    again, corrections_again = merge_layers(layers, corrections, image_manifest=manifest)
    assert again == compiled_evidence
    assert corrections_again == compiled_corrections


def test_split_counts_distinct_corrections_not_repeated_references():
    evidence = unit_evidence()
    evidence["assumptions"] = [{"id": "a1", "text": "依据", "source_locations": []}]
    layers, _ = split_v2({"evidence": evidence,
                         "corrections": [correction(evidence_ids=["a1", "a1"])]})
    assert layers["assumptions"][0]["inherited_ref"] == "c1"


def test_split_marks_all_single_correction_assumptions_and_calculations():
    evidence = unit_evidence()
    evidence["assumptions"] = [
        {"id": "a1", "text": "依据", "source_locations": []}]
    evidence["images"] = {"status": "not_applicable", "reason": "无图"}
    evidence["calculations"] = [{"id": "k1", "call_id": "call1",
                                   "expression": "1/2", "result": 0.5}]
    layers, corrections = split_v2({"evidence": evidence, "corrections": [correction(evidence_ids=["a1", "k1"]) ]})
    assert layers["assumptions"][0]["inherited_ref"] == "c1"
    assert layers["calculations"][0]["inherited_ref"] == "c1"
    assert corrections[0]["evidence_ids"] == ["a1", "k1"]


def test_merge_prunes_retracted_or_superseded_inheritance_except_when_still_referenced():
    layers = unit_evidence()
    layers["assumptions"][0]["inherited_ref"] = "old"
    layers["assumptions"][1]["inherited_ref"] = "old"
    retained = merge_layers(layers, [
        correction("old", status="superseded", evidence_ids=["a1", "a2"]),
        correction("new", evidence_ids=["a2"]),
    ])[0]
    assert [item["id"] for item in retained["assumptions"]] == ["a2"]
    assert all("inherited_ref" not in item for item in retained["assumptions"])
    with pytest.raises(EvidenceError) as caught:
        merge_layers(layers, [correction("old", status="retracted", evidence_ids=["a1", "a2"])])
    assert caught.value.code == "revise.evidence-required"
    assert isinstance(caught.value.details, dict)


def test_coverage_is_checked_only_against_unit_evidence():
    layers = unit_evidence()
    layers["assumptions"] = []
    with pytest.raises(EvidenceError) as caught:
        merge_layers(layers, [correction(evidence_ids=["local-a"], evidence=[{
            "kind": "assumption", "id": "local-a", "text": "局部依据",
            "source_locations": [],
        }])])
    assert caught.value.code == "proposal.evidence-assumptions"


def test_active_local_evidence_is_compiled_and_ids_are_unique():
    layers = unit_evidence()
    layers["assumptions"] = [{"id": "a1", "text": "单元依据", "source_locations": []}]
    local = {"kind": "assumption", "id": "local1", "text": "修订依据", "source_locations": []}
    evidence, corrections = merge_layers(layers, [correction(evidence_ids=["a1"], evidence=[local])])
    assert [e["id"] for e in evidence["assumptions"]] == ["a1", "local1"]
    assert corrections[0]["evidence_ids"] == ["a1", "local1"]
    duplicate = copy.deepcopy(local)
    with pytest.raises(EvidenceError) as caught:
        merge_layers(layers, [correction(evidence_ids=["a1"], evidence=[duplicate]),
                              correction("c2", evidence_ids=["a1"], evidence=[duplicate])])
    assert caught.value.code == "revise.evidence-id-duplicate"


def test_local_images_fold_losslessly_and_pass_v2_manifest_validation():
    from jiaodui.report_suggestions import _validate_image_evidence

    layers = unit_evidence()
    layers["images"] = [
        {"id": "i1", "reference_index": 1, "readable": True, "semantic": "单元观察一", "verdict": "单元一致"},
        {"id": "i2", "reference_index": 2, "readable": True, "semantic": "单元观察二", "verdict": "单元一致"},
    ]
    manifest = {"references": [
        {"reference_index": 1, "original_path": "a.png", "actual_read_path": "b.png", "position": {"line": 1, "column": 1}},
        {"reference_index": 2, "original_path": "c.png", "actual_read_path": "d.png", "position": {"line": 2, "column": 1}},
    ]}
    local = {"kind": "image", "id": "local-image", "reference_index": 1,
             "readable": True, "semantic": "局部语义原文", "verdict": "局部判定原文"}
    local2 = {**local, "id": "local-image-2", "semantic": "第二条局部观察"}
    corrections = [correction(evidence_ids=["a1"], evidence=[local, local2]),
                   correction("c2", evidence_ids=["a2"], status="retracted", evidence=[
                       {**local, "id": "withdrawn-image", "semantic": "撤回观察"}])]
    evidence, compiled_corrections = merge_layers(layers, corrections, image_manifest=manifest)
    _validate_image_evidence(evidence["images"], manifest)
    image = evidence["images"][0]
    assert image["id"] == "i1"
    assert "单元观察一" in image["semantic"] and "局部语义原文" in image["semantic"]
    assert "局部判定原文" in image["verdict"] and "第二条局部观察" in image["semantic"]
    assert "撤回观察" not in image["semantic"]
    assert compiled_corrections[0]["evidence_ids"] == ["a1", "i1"]


def test_local_calculation_can_expand_not_applicable_layer():
    layers = unit_evidence()
    layers["calculations"] = {"status": "not_applicable", "reason": "单元覆盖未用计算"}
    local = {"kind": "calculation", "id": "local-calc", "call_id": "call-1",
             "expression": "2+2", "result": 4}
    evidence, _ = merge_layers(layers, [correction(evidence=[local])])
    assert evidence["calculations"] == [{k: v for k, v in local.items() if k != "kind"}]


def test_local_evidence_id_cannot_collide_with_correction_id():
    with pytest.raises(EvidenceError) as caught:
        merge_layers(unit_evidence(), [correction(evidence=[{
            "kind": "assumption", "id": "c1", "text": "理由", "source_locations": [],
        }])])
    assert caught.value.code == "revise.evidence-id-duplicate"


def test_malformed_active_evidence_references_raise_evidence_error():
    with pytest.raises(EvidenceError) as caught:
        merge_layers(unit_evidence(), [correction(evidence_ids=[{"bad": True}])])
    assert caught.value.code == "proposal.evidence-reference"


def test_image_references_must_cover_manifest_and_unknown_references_fail():
    layers = unit_evidence()
    layers["images"] = [{"id": "i1", "reference_index": 1, "readable": True,
                        "semantic": "图一", "verdict": "一致"}]
    manifest = {"references": [{
        "reference_index": 1, "original_path": "a.png", "actual_read_path": "b.png",
        "position": {"line": 1, "column": 3},
    }, {
        "reference_index": 2, "original_path": "c.png", "actual_read_path": "d.png",
        "position": {"line": 2, "column": 1},
    }]}
    with pytest.raises(EvidenceError) as caught:
        merge_layers(layers, [correction()], image_manifest=manifest)
    assert caught.value.code == "proposal.evidence-images"
    layers["images"].append({"id": "i2", "reference_index": 2, "readable": True,
                                "semantic": "图二", "verdict": "一致"})
    evidence, _ = merge_layers(layers, [correction()], image_manifest=manifest)
    assert evidence["images"][1]["original_path"] == "c.png"


@pytest.mark.parametrize("extra", [
    {"evidence": None}, {"evidence": {}},
    {"evidence": [{"kind": [], "id": "bad"}]},
    {"evidence": [{"kind": "assumption", "id": "bad", "text": "缺字段"}]},
])
def test_malformed_local_evidence_raises_evidence_error(extra):
    with pytest.raises(EvidenceError):
        merge_layers(unit_evidence(), [correction(**extra)])


def test_inactive_correction_without_id_raises_evidence_error():
    with pytest.raises(EvidenceError):
        merge_layers(unit_evidence(), [{"status": "retracted", "evidence_ids": []}])


def test_references_cannot_reach_another_corrections_local_evidence():
    local = {"kind": "assumption", "id": "only-c1", "text": "局部依据", "source_locations": []}
    with pytest.raises(EvidenceError) as caught:
        merge_layers(unit_evidence(), [correction(evidence=[local]),
                                      correction("c2", evidence_ids=["only-c1"])])
    assert caught.value.code == "proposal.evidence-reference"


def test_local_only_correction_is_accepted_without_evidence_ids():
    item = correction(evidence=[{"kind": "assumption", "id": "local", "text": "局部依据", "source_locations": []}])
    item.pop("evidence_ids")
    _, corrections = merge_layers(unit_evidence(), [item])
    assert corrections[0]["evidence_ids"] == ["local"]
