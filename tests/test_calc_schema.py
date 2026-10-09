from __future__ import annotations

from jiaodui.calc import OPERATIONS
from jiaodui.calc.schema import all_json_schemas, json_schema_for


def test_json_schema_is_derived_from_core_operation_parameter_metadata():
    schemas = all_json_schemas()
    assert set(schemas) == set(OPERATIONS)
    for name, meta in OPERATIONS.items():
        schema = schemas[name]["parameters"]
        assert schema["additionalProperties"] is False
        assert schema["required"] == [p["name"] for p in meta["params"] if p["required"]]
        assert set(schema["properties"]) == {p["name"] for p in meta["params"]}


def test_operation_specific_schema_rejects_unknown_operation():
    try:
        json_schema_for("not-a-calc-op")
    except ValueError as error:
        assert "未知计算操作" in str(error)
    else:
        raise AssertionError("unknown operation should be rejected")


def test_evaluate_schema_requires_expression_and_rejects_expression_typo():
    schema = json_schema_for("evaluate")
    assert schema["required"] == ["expression"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["expression"]["type"] == "string"
