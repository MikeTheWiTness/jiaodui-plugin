from __future__ import annotations

import pytest

from jiaodui.anchor import AnchorError, resolve_anchor, validate_revision_input


def test_single_match_reports_source_span_and_codepoint_line_column():
    source = "🙂甲词乙\n丙"
    match = resolve_anchor(source, "词")
    assert (match.start, match.end, match.original) == (2, 3, "词")
    assert (match.line, match.column, match.normalized_match) == (1, 3, False)


def test_no_match_and_ambiguous_overlapping_matches_have_diagnostics():
    with pytest.raises(AnchorError) as missing:
        resolve_anchor("甲乙", "丙")
    assert missing.value.code == "anchor.not-found"
    assert missing.value.details["match_count"] == 0

    with pytest.raises(AnchorError) as overlapping:
        resolve_anchor("aaaa", "aa")
    assert overlapping.value.code == "anchor.ambiguous"
    assert overlapping.value.details["match_count"] == 3


def test_context_disambiguates_without_becoming_replacement_span():
    match = resolve_anchor("左甲词乙右 左丙词丁右", "词", context_before="甲", context_after="乙")
    assert (match.start, match.end, match.original) == (2, 3, "词")


def test_occurrence_is_one_based_over_context_plus_old_text():
    source = "甲词乙；甲词乙；甲词乙"
    match = resolve_anchor(source, "词", context_before="甲", context_after="乙", occurrence=2)
    assert (match.start, match.end, match.original) == (5, 6, "词")
    with pytest.raises(AnchorError) as outside:
        resolve_anchor(source, "词", context_before="甲", context_after="乙", occurrence=4)
    assert outside.value.code == "anchor.occurrence-out-of-range"


def test_empty_old_text_and_invalid_occurrence_are_rejected():
    with pytest.raises(AnchorError) as empty:
        resolve_anchor("源", "")
    assert empty.value.code == "anchor.empty"
    with pytest.raises(AnchorError) as invalid:
        resolve_anchor("甲", "甲", occurrence=0)
    assert invalid.value.code == "anchor.occurrence-out-of-range"


def test_crlf_and_zero_width_normalization_maps_back_to_exact_source_codepoints():
    source = "甲\u200b乙\r\n🙂丙\u200c丁\ufeff戊"
    match = resolve_anchor(source, "乙\n🙂丙丁戊")
    assert match.normalized_match is True
    assert match.original == "乙\r\n🙂丙\u200c丁\ufeff戊"
    assert source[match.start:match.end] == match.original
    assert (match.line, match.column) == (1, 3)


def test_normalization_does_not_apply_nfc_or_whitespace_folding():
    with pytest.raises(AnchorError) as error:
        resolve_anchor("e\u0301  甲", "é 甲")
    assert error.value.code == "anchor.not-found"


def test_multiple_normalized_hits_remain_ambiguous():
    with pytest.raises(AnchorError) as error:
        resolve_anchor("甲\u200b乙 / 甲\ufeff乙", "甲乙")
    assert error.value.code == "anchor.ambiguous"
    assert error.value.details["match_count"] == 2


def test_candidate_context_is_bounded_and_invisible_characters_are_escaped():
    source = "前" * 39 + chr(0x200b) + "甲乙" + "后" * 39 + chr(0xfeff) + "甲乙"
    with pytest.raises(AnchorError) as error:
        resolve_anchor(source, "甲乙")
    details = error.value.details
    assert len(details["candidates"]) == 2
    assert details["candidates"][0]["match_index"] == 1
    context = details["candidates"][0]["context_before"] + details["candidates"][0]["context_after"]
    assert "\\u200b" in context
    before = details["candidates"][0]["context_before"].replace("\\u200b", chr(0x200b))
    assert len(before) <= 24
    assert len(details["candidates"][0]["context_after"]) <= 24


def test_candidate_list_is_truncated_after_five():
    with pytest.raises(AnchorError) as error:
        resolve_anchor("甲 甲 甲 甲 甲 甲", "甲")
    assert len(error.value.details["candidates"]) == 5
    assert error.value.details["truncated"] is True


@pytest.mark.parametrize(
    ("source", "old", "required"),
    [("值=$a+b$。", "a+b", "$a+b$"), ("这是**重点内容**。", "重点", "**重点内容**")],
)
def test_partial_formula_or_bold_match_is_rejected_with_required_original(source, old, required):
    with pytest.raises(AnchorError) as error:
        resolve_anchor(source, old)
    assert error.value.code == "anchor.structure-cut"
    assert error.value.details["required_original"] == required


def test_whole_formula_or_bold_span_is_allowed():
    assert resolve_anchor("值=$a+b$。", "$a+b$").original == "$a+b$"
    assert resolve_anchor("这是**重点内容**。", "**重点内容**").original == "**重点内容**"


def test_normalized_empty_old_text_with_matching_context_fails_as_not_found():
    with pytest.raises(AnchorError) as error:
        resolve_anchor("甲乙", "\u200b", context_before="甲", context_after="乙")
    assert error.value.code == "anchor.not-found"


def test_crlf_crossing_context_old_boundary_maps_only_old_lf_codepoint():
    source = "甲\u200b\r\n乙"
    match = resolve_anchor(source, "\n乙", context_before="甲\r")
    assert match.normalized_match is True
    assert (match.start, match.end, match.original) == (3, 5, "\n乙")


@pytest.mark.parametrize(
    ("source", "normalized", "expected"),
    [
        ("\nX", True, "\nX"),
        ("\r\nX", False, "\nX"),
        ("\u200b\r\nX", False, "\nX"),
    ],
)
def test_lf_and_crlf_context_old_boundaries_preserve_old_line_feed(source, normalized, expected):
    match = resolve_anchor(source, "\nX", context_before="\r")
    assert match.normalized_match is normalized
    assert match.original == expected


def test_old_ending_at_cr_before_lf_context_does_not_consume_lf():
    match = resolve_anchor("甲\n乙", "甲\r", context_after="\n乙")
    assert match.normalized_match is True
    assert (match.start, match.end, match.original) == (0, 1, "甲")


def test_old_only_cr_that_normalizes_away_is_not_locatable():
    with pytest.raises(AnchorError) as error:
        resolve_anchor("\n", "\r", context_after="\n")
    assert error.value.code == "anchor.not-found"


def test_normalized_end_boundary_excludes_zero_width_from_following_context():
    source = "甲" + chr(0x200b) + "乙"
    match = resolve_anchor(source, "甲", context_after="乙")
    assert match.normalized_match is True
    assert (match.start, match.end, match.original) == (0, 1, "甲")


def test_candidate_diagnostics_escape_cr_lf_and_tab():
    source = "前\t\r\n甲乙\t\r\n甲乙"
    with pytest.raises(AnchorError) as error:
        resolve_anchor(source, "甲乙")
    candidate = error.value.details["candidates"][0]
    assert "\\t" in candidate["context_before"]
    assert "\\r\\n" in candidate["context_before"]


def test_revision_input_validation_limits_and_semantic_errors():
    validate_revision_input("甲", "", "删除")
    with pytest.raises(AnchorError) as too_long_new:
        validate_revision_input("甲", "新" * 2001, "原因")
    assert too_long_new.value.code == "revise.too-long"
    with pytest.raises(AnchorError) as too_long_reason:
        validate_revision_input("甲", "乙", "因" * 2001)
    assert too_long_reason.value.code == "revise.too-long"
    with pytest.raises(AnchorError) as too_long_evidence:
        validate_revision_input("甲", "乙", "原因", evidence=[{"text": "证" * 4001}])
    assert too_long_evidence.value.code == "revise.too-long"
    with pytest.raises(AnchorError) as empty_reason:
        validate_revision_input("甲", "乙", "  \t\n")
    assert empty_reason.value.code == "revise.reason-empty"
    with pytest.raises(AnchorError) as noop:
        validate_revision_input("甲", "甲", "原因")
    assert noop.value.code == "revise.noop"


def test_context_occurrence_counts_only_matching_composite_strings():
    match = resolve_anchor("词；甲词乙；词；甲词乙", "词", context_before="甲", context_after="乙", occurrence=2)
    assert (match.start, match.end, match.original) == (9, 10, "词")


def test_normalized_occurrence_selects_composite_hit_and_maps_source_offsets():
    match = resolve_anchor("甲\u200b词乙；甲\ufeff词乙", "词", context_before="甲", context_after="乙", occurrence=2)
    assert (match.start, match.end, match.original, match.normalized_match) == (7, 8, "词", True)


def test_strict_match_precedes_additional_normalized_matches():
    match = resolve_anchor("甲\u200b乙；甲乙", "甲乙")
    assert (match.start, match.end, match.original, match.normalized_match) == (4, 6, "甲乙", False)


@pytest.mark.parametrize("zero_width", ["\u200b", "\u200c", "\u200d", "\ufeff"])
def test_only_specified_zero_width_codepoints_are_removed_for_matching(zero_width):
    match = resolve_anchor("🙂甲" + zero_width + "乙", "甲乙")
    assert (match.start, match.end) == (1, 4)
    assert match.original == "甲" + zero_width + "乙"
    assert match.normalized_match is True


@pytest.mark.parametrize("retained", ["\u200e", "\u200f", "\u2060", " ", "\t"])
def test_other_invisible_or_whitespace_codepoints_are_not_normalized(retained):
    with pytest.raises(AnchorError) as error:
        resolve_anchor("甲" + retained + "乙", "甲乙")
    assert error.value.code == "anchor.not-found"


def test_formula_nested_in_bold_requires_transitive_complete_span():
    with pytest.raises(AnchorError) as error:
        resolve_anchor("前**值=$a+b$**后", "a+b")
    assert error.value.code == "anchor.structure-cut"
    assert error.value.details == {"required_original": "**值=$a+b$**", "required_start": 1, "required_end": 12}


def test_input_lengths_at_limits_are_accepted_as_codepoints():
    old = "🙂" * 1000
    before, after = "前" * 200, "后" * 200
    match = resolve_anchor(before + old + after, old, context_before=before, context_after=after)
    assert (match.start, match.end) == (200, 1200)
    validate_revision_input("甲", "🙂" * 2000, "因" * 2000, evidence=[{"text": "证" * 4000}])


def test_old_and_context_length_limits():
    with pytest.raises(AnchorError) as old_too_long:
        resolve_anchor("甲" * 1001, "甲" * 1001)
    assert old_too_long.value.code == "anchor.too-long"
    with pytest.raises(AnchorError) as context_too_long:
        resolve_anchor("甲", "甲", context_before="前" * 201)
    assert context_too_long.value.code == "anchor.too-long"
