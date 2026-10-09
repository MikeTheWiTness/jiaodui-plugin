"""从 calc operation 元数据导出JSON Schema，避免独立维护第二套参数表。"""
from __future__ import annotations

from typing import Any

from .operations import OPERATIONS


_TYPE_SCHEMAS = {
    "str": {"type": "string"},
    "int": {"type": "integer"},
    "float": {"type": "number"},
    "dict": {"type": "object", "additionalProperties": True},
    "list[str]": {"type": "array", "items": {"type": "string"}},
    "list[float]": {"type": "array", "items": {"type": "number"}},
}


def json_schema_for(operation: str) -> dict[str, Any]:
    """导出单个operation的严格入参schema。"""
    if operation not in OPERATIONS:
        raise ValueError(f"未知计算操作：{operation}")
    properties = {}
    required = []
    for parameter in OPERATIONS[operation]["params"]:
        schema = _TYPE_SCHEMAS.get(parameter["type"])
        if schema is None:
            raise ValueError(f"operation参数类型未映射：{operation}.{parameter['name']} ({parameter['type']})")
        properties[parameter["name"]] = {**schema, "description": parameter["help"]}
        if parameter["default"] is not None and parameter["type"] != "dict":
            properties[parameter["name"]]["default"] = parameter["default"]
        if parameter["required"]:
            required.append(parameter["name"])
    return {"type": "object", "additionalProperties": False,
            "properties": properties, "required": required}


def all_json_schemas() -> dict[str, Any]:
    """返回所有公开operation的schema和描述。"""
    return {name: {"description": meta["summary"], "parameters": json_schema_for(name)}
            for name, meta in OPERATIONS.items()}
